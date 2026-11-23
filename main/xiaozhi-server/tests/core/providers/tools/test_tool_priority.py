"""统一工具管理器：同名冲突按 ToolType 优先级保留，并记录冲突来源与调用指标。"""
from __future__ import annotations

from types import SimpleNamespace

import asyncio

from core.providers.tools.base import ToolDefinition, ToolType
from core.providers.tools.unified_tool_manager import ToolManager
from plugins_func.register import Action, ActionResponse


class _Exec:
    def __init__(self, tools, result=None, raises=None):
        self._tools = tools
        self._result = result
        self._raises = raises
        self.calls = 0

    def get_tools(self):
        return self._tools

    async def execute(self, conn, tool_name, arguments, speaker=None):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._result


def _defn(name, tool_type):
    return ToolDefinition(
        name=name,
        description={"type": "function", "function": {"name": name}},
        tool_type=tool_type,
    )


def _manager():
    return ToolManager(SimpleNamespace(config={}))


def test_higher_priority_tool_wins_regardless_of_registration_order():
    # 先注册低优先级，再注册高优先级
    manager = _manager()
    manager.register_executor(
        ToolType.DEVICE_MCP, _Exec({"get_weather": _defn("get_weather", ToolType.DEVICE_MCP)})
    )
    manager.register_executor(
        ToolType.SERVER_PLUGIN,
        _Exec({"get_weather": _defn("get_weather", ToolType.SERVER_PLUGIN)}),
    )

    assert manager.get_tool_type("get_weather") is ToolType.SERVER_PLUGIN
    assert manager.get_tool_conflicts() == [
        {"name": "get_weather", "kept": "server_plugin", "ignored": "device_mcp"}
    ]


def test_priority_also_applies_when_low_priority_registered_last():
    manager = _manager()
    manager.register_executor(
        ToolType.SERVER_PLUGIN,
        _Exec({"get_weather": _defn("get_weather", ToolType.SERVER_PLUGIN)}),
    )
    manager.register_executor(
        ToolType.DEVICE_MCP, _Exec({"get_weather": _defn("get_weather", ToolType.DEVICE_MCP)})
    )

    assert manager.get_tool_type("get_weather") is ToolType.SERVER_PLUGIN
    assert manager.get_tool_conflicts()[0]["ignored"] == "device_mcp"


def test_non_conflicting_tools_are_all_kept():
    manager = _manager()
    manager.register_executor(
        ToolType.SERVER_PLUGIN, _Exec({"get_weather": _defn("get_weather", ToolType.SERVER_PLUGIN)})
    )
    manager.register_executor(
        ToolType.DEVICE_MCP, _Exec({"self_light_set": _defn("self_light_set", ToolType.DEVICE_MCP)})
    )

    assert set(manager.get_supported_tool_names()) == {"get_weather", "self_light_set"}
    assert manager.get_tool_conflicts() == []


def test_function_descriptions_are_copied_not_shared():
    manager = _manager()
    manager.register_executor(
        ToolType.SERVER_PLUGIN, _Exec({"a": _defn("a", ToolType.SERVER_PLUGIN)})
    )

    first = manager.get_function_descriptions()
    first.clear()
    assert len(manager.get_function_descriptions()) == 1


def test_unknown_tool_returns_notfound():
    manager = _manager()
    result = asyncio.run(manager.execute_tool("nope", {}))
    assert result.action is Action.NOTFOUND


def test_executor_exception_is_not_leaked_to_tts():
    manager = _manager()
    manager.register_executor(
        ToolType.SERVER_PLUGIN,
        _Exec({"boom": _defn("boom", ToolType.SERVER_PLUGIN)}, raises=RuntimeError("internal db password")),
    )

    result = asyncio.run(manager.execute_tool("boom", {}))
    assert result.action is Action.ERROR
    assert "internal db password" not in result.response
    metrics = manager.get_runtime_metrics()["boom"]
    assert metrics["calls"] == 1
    assert metrics["failures"] == 1


def test_success_metrics_recorded():
    manager = _manager()
    manager.register_executor(
        ToolType.SERVER_PLUGIN,
        _Exec(
            {"ok": _defn("ok", ToolType.SERVER_PLUGIN)},
            result=ActionResponse(Action.RESPONSE, None, "done"),
        ),
    )

    result = asyncio.run(manager.execute_tool("ok", {}))
    assert result.response == "done"
    metrics = manager.get_runtime_metrics()["ok"]
    assert metrics["calls"] == 1
    assert metrics["failures"] == 0
    assert metrics["total_ms"] >= 0

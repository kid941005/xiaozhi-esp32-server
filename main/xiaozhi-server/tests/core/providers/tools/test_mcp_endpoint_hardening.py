"""MCP 接入点加固回归测试（客户端清理 / 执行器 action 白名单 / 处理器重连与发送失败）。"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from core.providers.tools.mcp_endpoint import mcp_endpoint_client as client_mod
from core.providers.tools.mcp_endpoint import mcp_endpoint_executor as exec_mod
from core.providers.tools.mcp_endpoint import mcp_endpoint_handler as handler_mod
from plugins_func.register import Action


class FakeWS:
    def __init__(self, messages=None, send_exc=None):
        self.messages = list(messages or [])
        self.send_exc = send_exc
        self.sent = []
        self.closed = False

    async def send(self, message):
        if self.send_exc is not None:
            raise self.send_exc
        self.sent.append(message)

    def __aiter__(self):
        self._it = iter(self.messages)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    async def close(self):
        self.closed = True


def test_fail_all_call_results_wakes_pending_only():
    async def run():
        client = client_mod.MCPEndpointClient()
        loop = asyncio.get_running_loop()
        pending1 = loop.create_future()
        pending2 = loop.create_future()
        done = loop.create_future()
        done.set_result("already")
        await client.register_call_result_future(3, pending1)
        await client.register_call_result_future(4, pending2)
        await client.register_call_result_future(5, done)

        await client.fail_all_call_results("连接挂了")

        assert client.call_results == {}
        assert pending1.done() and pending2.done()
        for fut in (pending1, pending2):
            with pytest.raises(RuntimeError, match="连接挂了"):
                fut.result()
        assert done.result() == "already"

    asyncio.run(run())


def test_close_marks_closed():
    async def run():
        client = client_mod.MCPEndpointClient()
        assert client.closed is False
        await client.close()
        assert client.closed is True

    asyncio.run(run())


def _run_execute(monkeypatch, payload, arguments=None):
    async def fake_call(mcp_client, tool_name, args_str, timeout=30, meta=None):
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(exec_mod, "call_mcp_endpoint_tool", fake_call)

    class Client:
        async def is_ready(self):
            return True

    conn = SimpleNamespace(mcp_endpoint_client=Client(), config=None)
    executor = exec_mod.MCPEndpointExecutor(conn)
    return asyncio.run(
        executor.execute(conn, "demo_tool", dict(arguments or {}), speaker=None)
    )


def test_executor_action_whitelist_exists():
    assert "RESPONSE" in exec_mod._ACTION_NAMES
    assert "turn_off" not in exec_mod._ACTION_NAMES


def test_executor_valid_action_passthrough(monkeypatch):
    out = _run_execute(
        monkeypatch, json.dumps({"action": "RESPONSE", "response": "好的"})
    )
    assert out.action is Action.RESPONSE
    assert out.response == "好的"


def test_executor_non_string_response_coerced(monkeypatch):
    out = _run_execute(monkeypatch, json.dumps({"action": "RECORD", "response": 123}))
    assert out.action is Action.RECORD
    assert out.response == "123"


def test_executor_unknown_action_falls_back_to_reqllm(monkeypatch):
    out = _run_execute(
        monkeypatch, json.dumps({"action": "turn_off", "response": "关灯"})
    )
    assert out.action is Action.REQLLM
    assert out.response is None
    assert "turn_off" in out.result


def test_executor_missing_action_falls_back_to_reqllm(monkeypatch):
    out = _run_execute(monkeypatch, json.dumps({"value": 1}))
    assert out.action is Action.REQLLM
    assert "value" in out.result


def test_executor_non_dict_payload_falls_back(monkeypatch):
    out = _run_execute(monkeypatch, json.dumps("plain text"))
    assert out.action is Action.REQLLM
    assert out.result == "plain text"


def test_executor_value_error_sanitized(monkeypatch):
    out = _run_execute(monkeypatch, ValueError("工具 demo_tool 不存在"))
    assert out.action is Action.NOTFOUND
    assert out.response == "未找到对应的 MCP 工具。"


def test_executor_unexpected_error_sanitized(monkeypatch):
    out = _run_execute(monkeypatch, RuntimeError("socket closed"))
    assert out.action is Action.ERROR
    assert out.response == "调用 MCP 工具失败，请稍后再试。"


def test_connect_passes_hardening_options(monkeypatch):
    captured = {}

    async def fake_connect(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeWS()

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(handler_mod.websockets, "connect", fake_connect)
    monkeypatch.setattr(handler_mod, "send_mcp_endpoint_initialize", noop)
    monkeypatch.setattr(handler_mod, "send_mcp_endpoint_notification", noop)
    monkeypatch.setattr(handler_mod, "send_mcp_endpoint_tools_list", noop)
    monkeypatch.setattr(handler_mod, "_message_listener", noop)
    monkeypatch.setattr(handler_mod.asyncio, "create_task", lambda coro: coro.close())

    client = asyncio.run(handler_mod.connect_mcp_endpoint("ws://gw/mcp/?token=t"))

    assert client is not None
    assert captured["url"] == "ws://gw/mcp/?token=t"
    assert captured["kwargs"]["max_size"] == 16 * 1024 * 1024
    assert captured["kwargs"]["ping_interval"] == 20
    assert captured["kwargs"]["ping_timeout"] == 20
    assert captured["kwargs"]["open_timeout"] == 15
    assert client.mcp_endpoint_url == "ws://gw/mcp/?token=t"


def test_connect_failure_cleans_up(monkeypatch):
    async def fake_connect(url, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr(handler_mod.websockets, "connect", fake_connect)
    assert asyncio.run(handler_mod.connect_mcp_endpoint("ws://gw/mcp/")) is None


def test_listener_triggers_fail_and_reconnect(monkeypatch):
    reconnects = []

    async def fake_reconnect(client):
        reconnects.append(client)

    monkeypatch.setattr(handler_mod, "_reconnect_mcp_endpoint", fake_reconnect)
    created = []
    monkeypatch.setattr(
        handler_mod.asyncio, "create_task", lambda coro: created.append(coro)
    )

    async def run():
        client = client_mod.MCPEndpointClient()
        client.mcp_endpoint_url = "ws://gw/mcp/"
        client.set_websocket(FakeWS(messages=[]))
        future = asyncio.get_running_loop().create_future()
        await client.register_call_result_future(3, future)
        await client.set_ready(True)

        await handler_mod._message_listener(client)

        assert client.ready is False
        with pytest.raises(RuntimeError):
            future.result()
        # 监听器必须调度一次重连
        assert len(created) == 1
        await created[0]
        assert reconnects == [client]

    asyncio.run(run())


def test_listener_skips_reconnect_after_close(monkeypatch):
    reconnects = []

    async def fake_reconnect(client):
        reconnects.append(client)

    monkeypatch.setattr(handler_mod, "_reconnect_mcp_endpoint", fake_reconnect)
    created = []
    monkeypatch.setattr(
        handler_mod.asyncio, "create_task", lambda coro: created.append(coro)
    )

    async def run():
        client = client_mod.MCPEndpointClient()
        client.mcp_endpoint_url = "ws://gw/mcp/"
        client.set_websocket(FakeWS(messages=[]))
        await client.set_ready(True)
        client.closed = True

        await handler_mod._message_listener(client)
        # 主动关闭后不得重连
        assert created == []

    asyncio.run(run())


def test_reconnect_replaces_client_and_refreshes(monkeypatch):
    calls = []

    class Handler:
        def upload_functions_desc(self):
            calls.append("upload")

        def current_support_functions(self):
            calls.append("support")

    new_client = SimpleNamespace(marker="new")

    async def fake_connect(url, conn=None):
        calls.append(("connect", url))
        return new_client

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr(handler_mod, "connect_mcp_endpoint", fake_connect)
    monkeypatch.setattr(handler_mod.asyncio, "sleep", fast_sleep)

    async def run():
        conn = SimpleNamespace(func_handler=Handler())
        old = client_mod.MCPEndpointClient(conn)
        old.mcp_endpoint_url = "ws://gw/mcp/"
        conn.mcp_endpoint_client = old

        await handler_mod._reconnect_mcp_endpoint(old)

        assert old.closed is True
        assert old.websocket is None
        assert conn.mcp_endpoint_client is new_client
        assert calls == [("connect", "ws://gw/mcp/"), "upload", "support"]
        assert old.reconnecting is False

    asyncio.run(run())


def test_call_tool_send_failure_cleans_pending(monkeypatch):
    async def run():
        client = client_mod.MCPEndpointClient()
        await client.add_tool({"name": "demo", "description": "", "inputSchema": {}})
        client.set_websocket(FakeWS(send_exc=RuntimeError("boom")))
        await client.set_ready(True)

        with pytest.raises(RuntimeError, match="发送 MCP 工具调用失败"):
            await handler_mod.call_mcp_endpoint_tool(client, "demo", "{}")

        assert client.call_results == {}

    asyncio.run(run())

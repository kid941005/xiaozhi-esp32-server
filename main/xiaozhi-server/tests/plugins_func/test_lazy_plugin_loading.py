"""插件按需加载（源码索引 + lazy import）测试。

覆盖：
1. 源码索引覆盖多行 @register_function 写法；
2. 建立索引不 import / 不执行插件模块；
3. 只为启用的插件 import 对应模块；
4. 单个插件模块语法错误不影响其它模块；
5. ServerPluginExecutor.get_tools 只暴露「必要函数 + 启用插件」；
6. 配置为空时必要函数仍可用，未知名字不抛异常。
"""

import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

SERVER_DIR = Path(__file__).resolve().parents[2]


class _FakeLogger:
    def bind(self, **kwargs):
        return self

    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def _run(code: str) -> str:
    """在服务端目录下用独立进程执行，保证 sys.modules 干净。"""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(SERVER_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_scan_plugin_index_covers_multiline_decorators():
    from plugins_func.loadplugins import scan_plugin_index

    func_to_module, module_to_funcs = scan_plugin_index(force=True)

    # 单行写法
    assert func_to_module["play_music"] == "play_music"
    assert func_to_module["get_weather"] == "get_weather"
    # 同一模块注册多个函数
    assert func_to_module["get_lunar"] == "get_time"
    # 多行写法必须也能扫描到
    assert func_to_module["get_news_from_newsnow"] == "get_news_from_newsnow"
    assert func_to_module["hass_play_music"] == "hass_play_music"
    assert func_to_module["search_from_ragflow"] == "search_from_ragflow"
    assert "get_time" in module_to_funcs
    assert "get_lunar" in module_to_funcs["get_time"]


def test_scan_index_does_not_import_modules():
    out = _run(
        """
        import sys
        from plugins_func.loadplugins import scan_plugin_index

        func_to_module, _ = scan_plugin_index(force=True)
        assert "play_music" in func_to_module
        leaked = [m for m in sys.modules if m.startswith("plugins_func.functions.")]
        print(",".join(sorted(leaked)))
        """
    )
    assert out.strip() == "", f"扫描索引不应 import 任何插件模块，实际: {out.strip()}"


def test_ensure_plugins_loaded_only_imports_needed_modules():
    out = _run(
        """
        import sys
        from plugins_func.loadplugins import ensure_plugins_loaded

        ensure_plugins_loaded(["get_weather"])
        assert "plugins_func.functions.get_weather" in sys.modules
        assert "plugins_func.functions.play_music" not in sys.modules
        assert "plugins_func.functions.hass_state" not in sys.modules
        print("OK")
        """
    )
    assert out.strip() == "OK"


def test_unknown_name_does_not_raise_and_falls_back():
    out = _run(
        """
        from plugins_func.loadplugins import ensure_plugins_loaded

        # 未命中索引的名字（例如 MCP 工具名）应走全量兜底，且不抛异常
        ensure_plugins_loaded(["__not_a_plugin_name__"])
        print("OK")
        """
    )
    assert out.strip() == "OK"


def test_soft_import_isolates_broken_module(tmp_path, monkeypatch):
    from plugins_func import loadplugins

    package_dir = tmp_path / "tplug_lazy"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "good_module.py").write_text(
        "from plugins_func.register import register_function\n"
        "@register_function('lazy_good_fn', {}, None)\n"
        "def lazy_good_fn():\n"
        "    return None\n",
        encoding="utf-8",
    )
    # 语法错误的模块：导入时必须被单独捕获
    (package_dir / "broken_module.py").write_text(
        "def broken(:\n    pass\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    loadplugins._LOADED_MODULES.discard("good_module")
    loaded, failed = loadplugins.auto_import_modules_soft(
        "tplug_lazy", log=_FakeLogger()
    )

    assert "good_module" in loaded
    assert "broken_module" in failed


def _make_executor(functions):
    conn = SimpleNamespace(
        logger=_FakeLogger(),
        config={
            "selected_module": {"Intent": "Intent_function_call"},
            "Intent": {"Intent_function_call": {"type": "function_call", "functions": functions}},
            "plugins": {},
        },
    )
    from core.providers.tools.server_plugins.plugin_executor import ServerPluginExecutor

    return ServerPluginExecutor(conn)


def test_get_tools_exposes_only_necessary_and_enabled_plugins():
    tools = _make_executor(["change_role"]).get_tools()

    assert "handle_exit_intent" in tools
    assert "get_lunar" in tools
    assert "change_role" in tools
    # 未启用（且此前未 import）的插件不应出现在工具表里
    assert "play_music" not in tools
    assert "hass_state" not in tools
    assert all(t.tool_type.value == "server_plugin" for t in tools.values())


def test_get_tools_expands_module_level_plugin_name():
    tools = _make_executor(["play_music"]).get_tools()

    # 配置写模块名（智控台下发的 provider_code 就是模块名），应展开成函数名
    assert "play_music" in tools


def test_get_tools_with_empty_functions_keeps_necessary_only():
    tools = _make_executor([]).get_tools()
    assert set(tools) == {"handle_exit_intent", "get_lunar"}


def test_get_tools_with_unknown_name_does_not_raise():
    tools = _make_executor(["__not_a_plugin_name__"]).get_tools()
    assert "handle_exit_intent" in tools
    assert "get_lunar" in tools
    assert "__not_a_plugin_name__" not in tools

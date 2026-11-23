"""提示词那条天气路径：失败/空结果不写 8 小时缓存（#3478）。"""
import asyncio
import threading

from core.utils.cache.manager import cache_manager, CacheType
from core.utils.prompt_manager import PromptManager
from plugins_func.functions import get_weather as weather_module
from plugins_func.register import Action, ActionResponse


class _Logger:
    def bind(self, **kwargs):
        return self

    def error(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


class _Conn:
    def __init__(self, loop):
        self.loop = loop


def _make_manager():
    manager = PromptManager.__new__(PromptManager)
    manager.cache_manager = cache_manager
    manager.CacheType = CacheType
    manager.logger = _Logger()
    return manager


def _call_in_loop(loop, func):
    holder = {}

    def target():
        try:
            holder["value"] = func()
        except BaseException as exc:  # noqa: BLE001 - 测试里把异常带回主线程
            holder["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(15)
    assert "error" not in holder, holder.get("error")
    return holder["value"]


def _with_loop(test):
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        return test(loop)
    finally:
        loop.call_soon_threadsafe(loop.stop)


def test_failure_result_is_not_cached(monkeypatch):
    async def fake_get_weather(conn, location=None, lang="zh_CN"):
        return ActionResponse(Action.REQLLM, "暂时查不到 杭州 的天气", None)

    monkeypatch.setattr(weather_module, "get_weather", fake_get_weather)
    cache_manager.clear(CacheType.WEATHER)
    manager = _make_manager()

    def run(loop):
        return _call_in_loop(loop, lambda: manager._get_weather_info(_Conn(loop), "杭州"))

    text = _with_loop(run)

    assert text == "暂时查不到 杭州 的天气"
    assert cache_manager.get(CacheType.WEATHER, "杭州") is None


def test_success_report_is_cached(monkeypatch):
    report = weather_module.build_weather_report(
        {"name": "杭州"}, {"now": {"text": "晴"}}, {"daily": []}
    )

    async def fake_get_weather(conn, location=None, lang="zh_CN"):
        return ActionResponse(Action.REQLLM, report, None)

    monkeypatch.setattr(weather_module, "get_weather", fake_get_weather)
    cache_manager.clear(CacheType.WEATHER)
    manager = _make_manager()

    def run(loop):
        return _call_in_loop(loop, lambda: manager._get_weather_info(_Conn(loop), "杭州"))

    text = _with_loop(run)

    assert text == report
    assert cache_manager.get(CacheType.WEATHER, "杭州") == report


def test_missing_credentials_hint_reaches_prompt(monkeypatch):
    async def fake_get_weather(conn, location=None, lang="zh_CN"):
        return ActionResponse(Action.RESPONSE, None, "天气功能还没有配置好，请联系管理员")

    monkeypatch.setattr(weather_module, "get_weather", fake_get_weather)
    cache_manager.clear(CacheType.WEATHER)
    manager = _make_manager()

    def run(loop):
        return _call_in_loop(loop, lambda: manager._get_weather_info(_Conn(loop), "杭州"))

    text = _with_loop(run)

    assert "还没有配置好" in text
    assert cache_manager.get(CacheType.WEATHER, "杭州") is None


def test_stale_empty_cache_entry_is_bypassed(monkeypatch):
    calls = []

    async def fake_get_weather(conn, location=None, lang="zh_CN"):
        calls.append(location)
        return ActionResponse(Action.REQLLM, None, "暂时查不到")

    monkeypatch.setattr(weather_module, "get_weather", fake_get_weather)
    cache_manager.clear(CacheType.WEATHER)
    cache_manager.set(CacheType.WEATHER, "杭州", None)
    manager = _make_manager()

    def run(loop):
        return _call_in_loop(loop, lambda: manager._get_weather_info(_Conn(loop), "杭州"))

    text = _with_loop(run)

    assert calls == ["杭州"]
    assert text == "暂时查不到"

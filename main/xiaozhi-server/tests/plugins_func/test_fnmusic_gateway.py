import asyncio

import httpx
import pytest

from plugins_func.functions import fnmusic_gateway as fm
from plugins_func.register import all_function_registry


class FakeLogger:
    def bind(self, **kwargs):
        return self

    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass


class FakeConn:
    def __init__(self, base_url="http://gw.local:8766", **extra):
        self.logger = FakeLogger()
        plugins = {}
        if base_url is not None:
            cfg = {"base_url": base_url}
            cfg.update(extra)
            plugins["fnmusic_gateway"] = cfg
        self.config = {"plugins": plugins}
        self.mcp_client = object()


@pytest.fixture
def conn():
    return FakeConn()


def _patch_play(monkeypatch, info=None, raise_exc=None):
    seen = {}

    async def fake_fetch(_conn, params):
        seen["params"] = dict(params)
        if raise_exc is not None:
            raise raise_exc
        return dict(info or {"url": "/playlist/a.mp3", "title": "稻香"})

    monkeypatch.setattr(fm, "_fetch_play", fake_fetch)
    return seen


def _patch_device(monkeypatch, raise_exc=None):
    calls = []

    async def fake_call(_conn, tool_name, args):
        calls.append((tool_name, dict(args)))
        if raise_exc is not None:
            raise raise_exc
        return "{}"

    monkeypatch.setattr(fm, "_call_device", fake_call)
    return calls


INFO = {
    "url": "/playlist/tok1.mp3",
    "title": "稻香",
    "artist": "周杰伦",
    "lyric_url": "/lrc/tok1.lrc",
    "duration": "269.4",
    "count": 3,
}


def test_registers_four_tools():
    for name in ("fnmusic_play", "fnmusic_next", "fnmusic_previous", "fnmusic_stop"):
        assert name in all_function_registry


def test_not_configured_returns_hint(monkeypatch):
    conn = FakeConn(base_url=None)
    seen = _patch_play(monkeypatch, INFO)

    result = asyncio.run(fm.fnmusic_play(conn, query="稻香"))

    assert result.action == fm.Action.RESPONSE
    assert result.response == fm.MSG_NOT_CONFIGURED
    assert "params" not in seen


def test_play_sends_params_and_device_args(conn, monkeypatch):
    seen = _patch_play(monkeypatch, INFO)
    calls = _patch_device(monkeypatch)

    result = asyncio.run(fm.fnmusic_play(conn, query="稻香"))

    assert seen["params"]["query"] == "稻香"
    assert seen["params"]["repeat"] == "off"
    assert calls[0][0] == "self.music.play_url"
    args = calls[0][1]
    assert args["url"] == "http://gw.local:8766/playlist/tok1.mp3"
    assert args["lyric_url"] == "http://gw.local:8766/lrc/tok1.lrc"
    assert args["title"] == "稻香"
    assert args["duration"] == 269
    assert result.action == fm.Action.RECORD
    assert result.response == "正在为您播放稻香"


def test_library_shuffle_with_chinese_repeat(conn, monkeypatch):
    seen = _patch_play(monkeypatch, INFO)
    _patch_device(monkeypatch)

    asyncio.run(fm.fnmusic_play(conn, scope="音乐库", shuffle=True, repeat="单曲循环"))

    params = seen["params"]
    assert params["scope"] == "library"
    assert params["shuffle"] == "1"
    assert params["repeat"] == "one"
    assert "query" not in params


def test_default_library_random_when_no_condition(conn, monkeypatch):
    seen = _patch_play(monkeypatch, INFO)
    _patch_device(monkeypatch)

    asyncio.run(fm.fnmusic_play(conn))

    assert seen["params"]["scope"] == "library"
    assert seen["params"]["shuffle"] == "1"


def test_gateway_error_returns_friendly_message(conn, monkeypatch):
    _patch_play(monkeypatch, raise_exc=httpx.ConnectError("boom"))
    calls = _patch_device(monkeypatch)

    result = asyncio.run(fm.fnmusic_play(conn, query="稻香"))

    assert result.action == fm.Action.RESPONSE
    assert result.response == fm.MSG_GATEWAY_FAILED
    assert calls == []


def test_device_unavailable_returns_hint(conn, monkeypatch):
    _patch_play(monkeypatch, INFO)
    _patch_device(monkeypatch, raise_exc=RuntimeError("MCP客户端尚未准备就绪"))

    result = asyncio.run(fm.fnmusic_play(conn, playlist="晚安"))

    assert result.action == fm.Action.RESPONSE
    assert result.response == fm.MSG_DEVICE_UNAVAILABLE


def test_empty_url_from_gateway(conn, monkeypatch):
    _patch_play(monkeypatch, {"message": "音乐库里没有这首歌"})
    calls = _patch_device(monkeypatch)

    result = asyncio.run(fm.fnmusic_play(conn, query="不存在"))

    assert result.action == fm.Action.RESPONSE
    assert result.response == "音乐库里没有这首歌"
    assert calls == []


def test_too_long_url_rejected(conn, monkeypatch):
    long_info = dict(INFO, url="/playlist/" + "x" * (fm.MAX_URL_LENGTH + 10))
    _patch_play(monkeypatch, long_info)
    calls = _patch_device(monkeypatch)

    result = asyncio.run(fm.fnmusic_play(conn, playlist="晚安"))

    assert result.action == fm.Action.RESPONSE
    assert calls == []


def test_next_uses_next_index(conn, monkeypatch):
    _patch_play(monkeypatch, INFO)
    _patch_device(monkeypatch)
    asyncio.run(fm.fnmusic_play(conn, playlist="晚安", index=1))

    seen = _patch_play(monkeypatch, dict(INFO, title="晴天", url="/playlist/tok2.mp3"))
    result = asyncio.run(fm.fnmusic_next(conn))

    assert seen["params"]["playlist"] == "晚安"
    assert seen["params"]["index"] == 2
    assert "下一首" in result.response
    assert conn.fnmusic_state["index"] == 2


def test_next_without_state_returns_hint(conn):
    result = asyncio.run(fm.fnmusic_next(conn))
    assert result.action == fm.Action.RESPONSE
    assert result.response == fm.MSG_NOTHING_PLAYING


def test_previous_at_first_track_returns_hint(conn, monkeypatch):
    _patch_play(monkeypatch, INFO)
    _patch_device(monkeypatch)
    asyncio.run(fm.fnmusic_play(conn, playlist="晚安", index=1))

    result = asyncio.run(fm.fnmusic_previous(conn))

    assert result.action == fm.Action.RESPONSE
    assert "第一首" in result.response


def test_next_at_last_track_wraps_when_repeat_all(conn, monkeypatch):
    _patch_play(monkeypatch, INFO)
    _patch_device(monkeypatch)
    asyncio.run(fm.fnmusic_play(conn, playlist="晚安", index=3, repeat="all"))
    conn.fnmusic_state["index"] = 3

    seen = _patch_play(monkeypatch, dict(INFO, title="回到第一首", url="/playlist/tok0.mp3"))
    asyncio.run(fm.fnmusic_next(conn))

    assert seen["params"]["index"] == 1
    assert seen["params"]["repeat"] == "all"


def test_stop_calls_device_and_clears_state(conn, monkeypatch):
    calls = _patch_device(monkeypatch)
    conn.fnmusic_state = {"playlist": "晚安", "index": 2}

    result = asyncio.run(fm.fnmusic_stop(conn))

    assert calls[0][0] == "self.music.stop"
    assert conn.fnmusic_state == {}
    assert result.action == fm.Action.RECORD

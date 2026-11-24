"""startToChat 必须在 function_call 提前返回前归一化音乐同音词。"""

import json
from types import SimpleNamespace

import pytest

from core.handle import receiveAudioHandle as ra


class _Logger:
    def bind(self, **kwargs):
        return self

    def info(self, *args, **kwargs):
        pass


def _make_conn(**overrides):
    conn = SimpleNamespace(
        logger=_Logger(),
        introduced_speakers=set(),
        current_speaker=None,
        need_bind=False,
        max_output_size=0,
        client_is_speaking=False,
        client_listen_mode="auto",
        client_abort=False,
        chat=lambda *args, **kwargs: None,
        executor=SimpleNamespace(submit=lambda *args, **kwargs: None),
    )
    for key, value in overrides.items():
        setattr(conn, key, value)
    return conn


@pytest.mark.asyncio
async def test_start_to_chat_normalizes_cut_ge_before_function_call(monkeypatch):
    captured = {}

    async def fake_intent(conn, text, speaker=None):
        captured["text"] = text
        return True

    monkeypatch.setattr(ra, "handle_user_intent", fake_intent)
    conn = _make_conn()

    await ra.startToChat(conn, "切割")

    assert captured["text"] == "切歌"


@pytest.mark.asyncio
async def test_start_to_chat_normalizes_json_content(monkeypatch):
    captured = {}

    async def fake_intent(conn, text, speaker=None):
        captured["text"] = text
        return True

    monkeypatch.setattr(ra, "handle_user_intent", fake_intent)
    conn = _make_conn()

    await ra.startToChat(conn, json.dumps({"content": "帮我切割"}, ensure_ascii=False))

    assert captured["text"] == "帮我切歌"


@pytest.mark.asyncio
async def test_start_to_chat_passes_normalized_text_to_chat(monkeypatch):
    captured = {}

    async def fake_intent(conn, text, speaker=None):
        captured["intent_text"] = text
        return False

    async def fake_send_stt(conn, text):
        captured["stt_text"] = text

    def fake_submit(fn, *args, **kwargs):
        captured["chat_arg"] = args[0]

    monkeypatch.setattr(ra, "handle_user_intent", fake_intent)
    monkeypatch.setattr(ra, "send_stt_message", fake_send_stt)
    conn = _make_conn(executor=SimpleNamespace(submit=fake_submit))

    await ra.startToChat(conn, "下一曲")

    assert captured["intent_text"] == "下一首"
    assert captured["stt_text"] == "下一首"
    assert captured["chat_arg"] == "下一首"


@pytest.mark.asyncio
async def test_start_to_chat_keeps_unrelated_text(monkeypatch):
    captured = {}

    async def fake_intent(conn, text, speaker=None):
        captured["text"] = text
        return True

    monkeypatch.setattr(ra, "handle_user_intent", fake_intent)
    conn = _make_conn()

    await ra.startToChat(conn, "播放晴天")

    assert captured["text"] == "播放晴天"

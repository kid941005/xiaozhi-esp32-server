import asyncio
import os
from types import SimpleNamespace

import pytest

from plugins_func.functions import play_music as pm


class FakeQueue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


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


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(payload)


class FakeConn:
    def __init__(self, music_dir):
        self.logger = FakeLogger()
        self.config = {
            "plugins": {
                "play_music": {
                    "music_dir": str(music_dir),
                    "music_ext": [".mp3"],
                    "refresh_time": 300,
                }
            }
        }
        self.sentence_id = "s-1"
        self.intent_type = "function_call"
        self.client_abort = False
        self.tts = SimpleNamespace(
            tts_text_queue=FakeQueue(), store_tts_text=lambda sid, text: None
        )
        self.websocket = FakeWebSocket()
        self.cleared = 0
        self.speak_cleared = 0

    def clear_queues(self):
        self.cleared += 1

    def clearSpeakStatus(self):
        self.speak_cleared += 1


def _queued_files(conn):
    return [
        m.content_file
        for m in conn.tts.tts_text_queue.items
        if getattr(m, "content_type", None) == pm.ContentType.FILE
    ]


@pytest.fixture
def music_conn(tmp_path, monkeypatch):
    for name in ("a.mp3", "b.mp3", "c.mp3"):
        (tmp_path / name).write_bytes(b"ID3")
    pm.MUSIC_CACHE.clear()
    conn = FakeConn(tmp_path)
    yield conn
    pm.MUSIC_CACHE.clear()


def test_next_switches_to_another_track(music_conn):
    asyncio.run(pm.play_music(music_conn, "random", "play"))
    first = _queued_files(music_conn)
    assert len(first) == 1
    current = music_conn.music_state["current"]
    assert current is not None

    music_conn.tts.tts_text_queue.items.clear()
    result = asyncio.run(pm.play_music(music_conn, action="next"))

    played = _queued_files(music_conn)
    assert len(played) == 1
    assert played[0] != first[0], "下一首必须换成另一首歌"
    assert music_conn.music_state["current"] == os.path.basename(played[0])
    # 切歌前必须先停掉当前音频
    assert music_conn.cleared == 1
    assert any('"state": "stop"' in msg for msg in music_conn.websocket.sent)
    assert music_conn.client_abort is False
    assert result.action == pm.Action.RECORD


def test_previous_after_next_returns_to_same_track(music_conn):
    asyncio.run(pm.play_music(music_conn, "random", "play"))
    asyncio.run(pm.play_music(music_conn, action="next"))
    after_next = music_conn.music_state["current"]
    music_conn.tts.tts_text_queue.items.clear()
    asyncio.run(pm.play_music(music_conn, action="previous"))
    assert music_conn.music_state["current"] != after_next
    assert len(_queued_files(music_conn)) == 1


def test_next_without_music_files_reports_error(tmp_path):
    pm.MUSIC_CACHE.clear()
    conn = FakeConn(tmp_path)  # 空目录
    result = asyncio.run(pm.play_music(conn, action="next"))
    assert result.action == pm.Action.RESPONSE
    assert _queued_files(conn) == []
    pm.MUSIC_CACHE.clear()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("切割", "切歌"),
        ("帮我切个歌", "帮我切歌"),
        ("下一曲", "下一首"),
        ("放首歌", "放首歌"),
        ("", ""),
    ],
)
def test_normalize_music_text(raw, expected):
    assert pm.normalize_music_text(raw) == expected

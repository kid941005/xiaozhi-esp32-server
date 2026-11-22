"""上下文源拉取：并发、总超时、失败隔离、连接复用。"""
from __future__ import annotations

import threading
import time

from core.utils.context_provider import ContextDataProvider


class _Logger:
    """最小 logger 桩：记录日志，不依赖 config/logger。"""

    def __init__(self):
        self.messages: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def bind(self, **_kwargs):
        return self

    def _add(self, level, msg):
        with self._lock:
            self.messages.append((level, str(msg)))

    def debug(self, msg):
        self._add("debug", msg)

    def info(self, msg):
        self._add("info", msg)

    def warning(self, msg):
        self._add("warning", msg)

    def error(self, msg):
        self._add("error", msg)


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """按 url 返回预置响应的假 httpx.Client。"""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[dict] = []
        self.closed = False

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        return self._handler(url, headers, timeout)

    def close(self):
        self.closed = True


def _provider(config, client):
    provider = ContextDataProvider(config, _Logger())
    provider._get_client = lambda: client  # 绕开真实网络
    return provider


def test_multiple_providers_are_fetched_concurrently():
    def handler(url, headers, timeout):
        time.sleep(0.2)
        return _Resp(200, {"code": 0, "data": {"src": url}})

    client = _FakeClient(handler)
    provider = _provider(
        {
            "context_providers": [
                {"url": "http://a/context"},
                {"url": "http://b/context"},
                {"url": "http://c/context"},
            ]
        },
        client,
    )

    started = time.monotonic()
    text = provider.fetch_all("dev-1")
    elapsed = time.monotonic() - started

    # 串行需要 0.6s，并发应明显更快
    assert elapsed < 0.5, f"上下文源未并发拉取，耗时 {elapsed:.3f}s"
    assert len(client.calls) == 3
    assert "http://a/context" in text and "http://c/context" in text


def test_output_order_follows_config_order_not_completion_order():
    delays = {"http://slow/context": 0.15, "http://fast/context": 0.0}

    def handler(url, headers, timeout):
        time.sleep(delays[url])
        return _Resp(200, {"code": 0, "data": [url]})

    provider = _provider(
        {
            "context_providers": [
                {"url": "http://slow/context"},
                {"url": "http://fast/context"},
            ]
        },
        _FakeClient(handler),
    )

    lines = provider.fetch_all("dev-1").splitlines()
    assert lines == ["- http://slow/context", "- http://fast/context"]


def test_dict_data_is_formatted_and_device_id_injected():
    seen = {}

    def handler(url, headers, timeout):
        seen.update(headers or {})
        return _Resp(200, {"code": 0, "data": {"steps": 8123, "sleep": "7h"}})

    provider = _provider(
        {
            "context_providers": [
                {"url": "http://a/context", "headers": {"Authorization": "t"}}
            ]
        },
        _FakeClient(handler),
    )

    text = provider.fetch_all("dev-42")
    assert seen["device-id"] == "dev-42"
    assert seen["Authorization"] == "t"
    assert "- **steps：** 8123" in text
    assert "- **sleep：** 7h" in text


def test_failed_provider_does_not_break_others():
    def handler(url, headers, timeout):
        if "bad" in url:
            raise RuntimeError("connect refused")
        if "status" in url:
            return _Resp(500, None)
        return _Resp(200, {"code": 1, "msg": "no auth"})

    provider = _provider(
        {
            "context_providers": [
                {"url": "http://bad/context"},
                {"url": "http://status/context"},
                {"url": "http://code/context"},
            ]
        },
        _FakeClient(handler),
    )

    # 全部失败也不抛异常，只是没有上下文
    assert provider.fetch_all("dev-1") == ""
    levels = [level for level, _ in provider.logger.messages]
    assert levels.count("error") == 1
    assert levels.count("warning") == 2


def test_total_timeout_skips_slow_provider_without_blocking():
    def handler(url, headers, timeout):
        if "slow" in url:
            time.sleep(0.6)
            return _Resp(200, {"code": 0, "data": ["slow"]})
        return _Resp(200, {"code": 0, "data": ["fast"]})

    provider = _provider(
        {
            "context_providers": [
                {"url": "http://slow/context"},
                {"url": "http://fast/context"},
            ],
            "context_providers_total_timeout": 0.15,
        },
        _FakeClient(handler),
    )

    started = time.monotonic()
    text = provider.fetch_all("dev-1")
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, f"总超时未生效，耗时 {elapsed:.3f}s"
    assert text == "- fast"
    assert provider.last_timeout_count == 1


def test_client_is_reused_across_calls():
    created = []

    class _CountingClient(_FakeClient):
        pass

    client = _CountingClient(lambda url, headers, timeout: _Resp(200, {"code": 0, "data": ["x"]}))
    provider = ContextDataProvider({"context_providers": [{"url": "http://a/context"}]}, _Logger())
    real_get_client = provider._get_client

    def _get_client():
        if provider._client is None:
            created.append(1)
        return real_get_client()

    provider._get_client = _get_client
    provider._client = client

    provider.fetch_all("dev-1")
    provider.fetch_all("dev-1")
    assert len(created) == 0
    assert provider._client is client
    assert len(client.calls) == 2


def test_empty_or_blank_provider_list_returns_empty():
    provider = _provider({"context_providers": [{"url": ""}]}, _FakeClient(lambda *a: None))
    assert provider.fetch_all("dev-1") == ""

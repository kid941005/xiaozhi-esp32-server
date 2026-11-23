"""#3456 独立缺陷2：CORS 头不再同时下发 * 与凭证"""
from aiohttp import web
import pytest

from core.api import base_handler as base_handler_module
from core.api.base_handler import BaseHandler


class _FakeLogger:
    def __init__(self):
        self.records = []

    def warning(self, msg):
        self.records.append(("warning", msg))

    def debug(self, msg):
        self.records.append(("debug", msg))


class _FakeRequest:
    def __init__(self, origin=None):
        self.headers = {}
        if origin is not None:
            self.headers["Origin"] = origin


@pytest.fixture
def make_handler(monkeypatch):
    def _make(allowed_origins):
        monkeypatch.setattr(
            base_handler_module, "setup_logging", lambda *a, **k: _FakeLogger()
        )
        return BaseHandler({"server": {"cors": {"allowed_origins": allowed_origins}}})

    return _make


def test_wildcard_reflects_origin_without_credentials(make_handler):
    handler = make_handler(["*"])
    response = web.Response(text="ok")
    handler._add_cors_headers(response, _FakeRequest("https://a.example"))
    assert response.headers["Access-Control-Allow-Origin"] == "https://a.example"
    assert "Access-Control-Allow-Credentials" not in response.headers
    assert response.headers["Vary"] == "Origin"


def test_allowed_origin_gets_credentials(make_handler):
    handler = make_handler(["https://console.example"])
    response = web.Response(text="ok")
    handler._add_cors_headers(response, _FakeRequest("https://console.example"))
    assert response.headers["Access-Control-Allow-Origin"] == "https://console.example"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_unlisted_origin_not_echoed(make_handler):
    handler = make_handler(["https://console.example"])
    response = web.Response(text="ok")
    handler._add_cors_headers(response, _FakeRequest("https://evil.example"))
    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_no_origin_no_cors_origin_header(make_handler):
    handler = make_handler(["*"])
    response = web.Response(text="ok")
    handler._add_cors_headers(response, _FakeRequest(None))
    assert "Access-Control-Allow-Origin" not in response.headers


def test_empty_whitelist_denies_cross_origin(make_handler):
    handler = make_handler([])
    response = web.Response(text="ok")
    handler._add_cors_headers(response, _FakeRequest("https://a.example"))
    assert "Access-Control-Allow-Origin" not in response.headers

"""#3448/#3456：白名单不再免 token、OTA 签发收紧、固件下载鉴权"""
import asyncio

from aiohttp import web

from core.auth import AuthManager, AuthenticationError
from core.api.ota_handler import OTAHandler
from core.websocket_server import WebSocketServer

MAC = "00:11:22:33:44:55"


class _FakeLogger:
    def bind(self, **kwargs):
        return self

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def debug(self, msg):
        pass

    def error(self, msg):
        pass


class _FakeRequest:
    def __init__(self, headers=None, match_info=None):
        self.headers = dict(headers or {})
        self.match_info = dict(match_info or {})


def _make_ota(auth_enable=True, allowed_devices=(), strict_ota=False,
              protect_download=False, expire_seconds=30):
    handler = OTAHandler.__new__(OTAHandler)
    handler.logger = _FakeLogger()
    handler.auth_enable = auth_enable
    handler.allowed_devices = set(allowed_devices)
    handler.allowed_devices_expire_seconds = 3600
    handler.strict_ota = strict_ota
    handler.protect_firmware_download = protect_download
    handler._bootstrapped_devices = set()
    handler.auth = AuthManager("unit-test-secret", expire_seconds=expire_seconds)
    handler.bin_dir = "does-not-exist"
    handler._cors_origins = []
    handler._cors_wildcard = False
    return handler


# ---------- 设备标识/型号校验 ----------
def test_device_id_validation():
    assert OTAHandler._is_valid_device_id(MAC) is True
    assert OTAHandler._is_valid_device_id("00-11-22-33-44-55") is True
    assert OTAHandler._is_valid_device_id("") is False
    assert OTAHandler._is_valid_device_id("not-a-mac") is False
    assert OTAHandler._is_valid_device_id("00:11:22:33:44:55\n") is False


def test_device_model_validation():
    assert OTAHandler._is_valid_device_model("test-board") is True
    assert OTAHandler._is_valid_device_model("a/b") is False
    assert OTAHandler._is_valid_device_model("x" * 65) is False


# ---------- OTA 签发策略 ----------
def test_legacy_mode_still_issues_token():
    handler = _make_ota(strict_ota=False)
    allowed, reason = handler._resolve_token_issuance(_FakeRequest(), MAC, "cid")
    assert (allowed, reason) == (True, "insecure_legacy")


def test_allowlisted_device_always_allowed():
    handler = _make_ota(strict_ota=True, allowed_devices=[MAC])
    allowed, reason = handler._resolve_token_issuance(_FakeRequest(), MAC, "cid")
    assert (allowed, reason) == (True, "allowlisted")


def test_strict_mode_bootstraps_once_then_rejects():
    handler = _make_ota(strict_ota=True)
    assert handler._resolve_token_issuance(_FakeRequest(), MAC, "cid")[0] is True
    allowed, reason = handler._resolve_token_issuance(_FakeRequest(), MAC, "cid")
    assert (allowed, reason) == (False, "unauthenticated")


def test_strict_mode_accepts_valid_credential():
    handler = _make_ota(strict_ota=True)
    token = handler.auth.generate_token("cid", MAC)
    request = _FakeRequest({"authorization": "Bearer " + token})
    allowed, reason = handler._resolve_token_issuance(request, MAC, "cid")
    assert (allowed, reason) == (True, "renew")


def test_strict_mode_rejects_expired_credential():
    handler = _make_ota(strict_ota=True, expire_seconds=1)
    import time

    old_ts = int(time.time()) - 100
    token = f"{handler.auth._sign(f'cid|{MAC}|{old_ts}')}.{old_ts}"
    handler._bootstrapped_devices.add(MAC)  # 已自举过，不能再放行
    request = _FakeRequest({"authorization": "Bearer " + token})
    allowed, reason = handler._resolve_token_issuance(request, MAC, "cid")
    assert (allowed, reason) == (False, "unauthenticated")


# ---------- 固件下载鉴权 ----------
def test_download_requires_credential_when_enabled():
    handler = _make_ota(auth_enable=True, protect_download=True)
    request = _FakeRequest({"device-id": MAC, "client-id": "cid"},
                           {"filename": "fw.bin"})
    resp = asyncio.run(handler.handle_download(request))
    assert resp.status == 401


def test_download_open_when_not_protected():
    handler = _make_ota(auth_enable=True, protect_download=False)
    request = _FakeRequest({"device-id": MAC, "client-id": "cid"},
                           {"filename": "fw.bin"})
    resp = asyncio.run(handler.handle_download(request))
    # 文件不存在 -> 404，说明没有被鉴权层拦住
    assert resp.status == 404


# ---------- WebSocket 白名单不再免 token ----------
def _make_ws(auth_enable=True, allowed_devices=(), expire_seconds=30):
    server = WebSocketServer.__new__(WebSocketServer)
    server.auth_enable = auth_enable
    server.allowed_devices = set(allowed_devices)
    server.allowed_devices_expire_seconds = 3600
    server.auth = AuthManager("unit-test-secret", expire_seconds=expire_seconds)
    server.logger = _FakeLogger()
    return server


class _FakeWebsocket:
    def __init__(self, headers):
        self.request = type("Req", (), {"headers": headers})()


def _run_auth(server, headers):
    return asyncio.run(server._handle_auth(_FakeWebsocket(headers)))


def test_ws_allowlisted_without_token_is_rejected():
    server = _make_ws(allowed_devices=[MAC])
    try:
        _run_auth(server, {"device-id": MAC, "client-id": "cid"})
    except AuthenticationError:
        return
    raise AssertionError("白名单设备无 token 却通过了认证")


def test_ws_allowlisted_with_valid_token_passes():
    server = _make_ws(allowed_devices=[MAC])
    token = server.auth.generate_token("cid", MAC)
    _run_auth(server, {"device-id": MAC, "client-id": "cid",
                       "authorization": "Bearer " + token})


def test_ws_non_allowlisted_with_valid_token_passes():
    server = _make_ws()
    token = server.auth.generate_token("cid", MAC)
    _run_auth(server, {"device-id": MAC, "client-id": "cid",
                       "authorization": "Bearer " + token})


def test_ws_invalid_token_rejected():
    server = _make_ws()
    try:
        _run_auth(server, {"device-id": MAC, "client-id": "cid",
                           "authorization": "Bearer bad.token"})
    except AuthenticationError:
        return
    raise AssertionError("非法 token 通过了认证")


def test_ws_auth_disabled_allows_anyone():
    server = _make_ws(auth_enable=False)
    _run_auth(server, {"device-id": MAC})

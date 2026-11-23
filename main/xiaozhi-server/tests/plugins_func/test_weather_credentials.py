"""天气插件的凭据与缓存行为（#3472 / #3478 / #3483）。

不联网：httpx.AsyncClient 全部替换成假客户端，并记录请求次数。
"""
import httpx
import pytest

from plugins_func.functions import get_weather as weather_module


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", json_error=None):
        self.status_code = status_code
        self.payload = payload
        self.text = text
        self.json_error = json_error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeAsyncClient:
    requests = []
    responder = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, params=None, headers=None):
        FakeAsyncClient.requests.append({"url": url, "params": params})
        return FakeAsyncClient.responder(url, params)


class FakeConn:
    def __init__(self, plugins=None):
        self.config = {"plugins": plugins or {}}
        self.client_ip = None


@pytest.fixture
def fake_http(monkeypatch):
    FakeAsyncClient.requests = []
    FakeAsyncClient.responder = lambda url, params: FakeResponse(payload={"code": "200"})
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


@pytest.fixture(autouse=True)
def clean_weather_cache():
    from core.utils.cache.manager import cache_manager, CacheType

    cache_manager.clear(CacheType.WEATHER)
    yield
    cache_manager.clear(CacheType.WEATHER)


def _credential_config(api_key="k", api_host="h"):
    return {"get_weather": {"api_key": api_key, "api_host": api_host}}


# ---------------------------------------------------------------------------
# 没配凭据：给一句提示，不发请求，不写缓存
# ---------------------------------------------------------------------------


async def test_missing_credentials_returns_hint_without_request(fake_http):
    response = await weather_module.get_weather(
        FakeConn({"get_weather": {"api_key": "", "api_host": ""}}), location="杭州"
    )

    assert response.action == weather_module.Action.RESPONSE
    assert response.result is None
    assert "还没有配置好" in response.response
    assert fake_http.requests == []


async def test_missing_credentials_does_not_write_failure_cache(fake_http):
    from core.utils.cache.manager import cache_manager, CacheType

    await weather_module.get_weather(
        FakeConn({"get_weather": {"api_key": "", "api_host": ""}}), location="杭州"
    )

    assert cache_manager.get(CacheType.WEATHER, "failed_weather_杭州_zh_CN") is None
    assert cache_manager.get(CacheType.WEATHER, "full_weather_杭州_zh_CN") is None


# ---------------------------------------------------------------------------
# 失败缓存：带凭据指纹、只 5 分钟、能挡住重复请求
# ---------------------------------------------------------------------------


def test_failure_cache_key_changes_with_credentials():
    first = weather_module.credential_fingerprint("host", "key-a")
    second = weather_module.credential_fingerprint("host", "key-b")

    assert first != second
    assert len(first) == 8
    assert "key-a" not in first


async def test_failure_is_cached_and_short_circuits_next_call(fake_http, monkeypatch):
    calls = []

    async def fake_city_info(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(weather_module, "fetch_city_info", fake_city_info)

    conn = FakeConn(_credential_config())
    first = await weather_module.get_weather(conn, location="失败市")
    second = await weather_module.get_weather(conn, location="失败市")

    assert len(calls) == 1
    assert "天气服务不可用" in first.result
    assert second.result == first.result


async def test_new_credentials_bypass_old_failure_cache(fake_http, monkeypatch):
    calls = []

    async def fake_city_info(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(weather_module, "fetch_city_info", fake_city_info)

    await weather_module.get_weather(
        FakeConn(_credential_config(api_key="wrong")), location="换key市"
    )
    await weather_module.get_weather(
        FakeConn(_credential_config(api_key="right")), location="换key市"
    )

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# 网页降级：结构不对时不要抛异常
# ---------------------------------------------------------------------------


def test_parse_weather_info_returns_none_without_city_node():
    from bs4 import BeautifulSoup

    assert weather_module.parse_weather_info(BeautifulSoup("<html></html>", "html.parser")) is None


def test_parse_weather_info_skips_rows_without_date():
    from bs4 import BeautifulSoup

    html = (
        '<h1 class="c-submenu__location">杭州</h1>'
        '<div class="city-forecast-tabs__row"><span class="tmp-cont">'
        '<span class="temp">30</span></span></div>'
    )
    parsed = weather_module.parse_weather_info(BeautifulSoup(html, "html.parser"))

    assert parsed is not None
    assert parsed[0] == "杭州"
    assert parsed[3] == []


# ---------------------------------------------------------------------------
# 成功报告与失败提示要能区分开（提示词那条路只缓存前者）
# ---------------------------------------------------------------------------


def test_only_success_report_is_recognised():
    report = weather_module.build_weather_report(
        {"name": "杭州"}, {"now": {"text": "晴"}}, {"daily": []}
    )

    assert weather_module.is_weather_report(report) is True
    assert weather_module.is_weather_report("暂时查不到 杭州 的天气") is False
    assert weather_module.is_weather_report(None) is False
    assert weather_module.is_weather_report("") is False

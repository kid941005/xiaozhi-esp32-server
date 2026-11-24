import importlib

import config.logger as logger_module


def _version_with(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("APP_VERSION", value)
    return importlib.reload(logger_module).SERVER_VERSION


def test_server_version_reads_app_version_env(monkeypatch):
    assert _version_with(monkeypatch, "0.9.12") == "0.9.12"


def test_server_version_falls_back_to_dev(monkeypatch):
    assert _version_with(monkeypatch, None) == "dev"
    assert _version_with(monkeypatch, "   ") == "dev"


def test_logger_module_restored(monkeypatch):
    # 结束时恢复为无 APP_VERSION，避免影响同进程其它测试
    assert _version_with(monkeypatch, None) == "dev"

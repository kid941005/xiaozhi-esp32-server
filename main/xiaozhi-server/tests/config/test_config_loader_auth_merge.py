"""智控台模式下本地 auth 段与 cors 段不能被覆盖（#3456）"""
import asyncio

from config import config_loader


def test_local_auth_and_cors_survive_api_override(monkeypatch):
    local_config = {
        "server": {
            "ip": "0.0.0.0",
            "port": 8000,
            "http_port": 8003,
            "vision_explain": "http://127.0.0.1:8003/mcp/vision/explain",
            "auth_key": "local-secret",
            "auth": {
                "enabled": False,
                "allowed_devices": ["00:11:22:33:44:55"],
                "strict_ota": True,
                "protect_firmware_download": True,
            },
            "cors": {"allowed_origins": ["https://console.example"]},
        },
        "manager-api": {"url": "http://api", "secret": "s"},
        "prompt_template": "local-template",
    }
    api_payload = {"server": {"auth": {"enabled": True}}, "prompt_template": None}

    monkeypatch.setattr(config_loader, "init_service", lambda config: None)

    async def fake_get_server_config():
        return dict(api_payload)

    monkeypatch.setattr(config_loader, "get_server_config", fake_get_server_config)

    merged = asyncio.run(config_loader.get_config_from_api_async(local_config))

    assert merged["server"]["auth"]["enabled"] is True           # 智控台决定是否启用
    assert merged["server"]["auth"]["allowed_devices"] == ["00:11:22:33:44:55"]
    assert merged["server"]["auth"]["strict_ota"] is True
    assert merged["server"]["auth"]["protect_firmware_download"] is True
    assert merged["server"]["cors"]["allowed_origins"] == ["https://console.example"]

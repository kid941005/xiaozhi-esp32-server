from core.api.ota_handler import OTAHandler


def _config(auth):
    return {
        "server": {"auth": auth, "auth_key": "secret"},
        "firmware_cache_ttl": 30,
    }


def test_strict_ota_defaults_to_true():
    handler = OTAHandler(_config({"enabled": True}))
    assert handler.strict_ota is True


def test_strict_ota_can_be_disabled_explicitly():
    handler = OTAHandler(_config({"enabled": True, "strict_ota": False}))
    assert handler.strict_ota is False


def test_firmware_download_protection_defaults_to_false():
    handler = OTAHandler(_config({"enabled": True}))
    assert handler.protect_firmware_download is False

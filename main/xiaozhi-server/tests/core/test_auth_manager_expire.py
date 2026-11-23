"""#3448/#3456：token 有效期覆盖与未来时间戳校验"""
import time

from core.auth import AuthManager


def _manager(expire_seconds=100):
    return AuthManager(secret_key="unit-test-secret", expire_seconds=expire_seconds)


def test_default_expire_seconds_applies():
    auth = _manager(expire_seconds=100)
    token = auth.generate_token("client-1", "device-1")
    assert auth.verify_token(token, client_id="client-1", username="device-1") is True


def test_override_expire_accepts_old_token():
    auth = _manager(expire_seconds=10)
    # 构造一个 1000 秒前签发的 token
    old_ts = int(time.time()) - 1000
    token = f"{auth._sign(f'client-1|device-1|{old_ts}')}.{old_ts}"
    assert auth.verify_token(token, client_id="client-1", username="device-1") is False
    # 白名单设备放宽有效期后应当通过
    assert (
        auth.verify_token(
            token,
            client_id="client-1",
            username="device-1",
            expire_seconds=3600,
        )
        is True
    )


def test_wrong_client_id_or_user_rejected():
    auth = _manager()
    token = auth.generate_token("client-1", "device-1")
    assert auth.verify_token(token, client_id="client-2", username="device-1") is False
    assert auth.verify_token(token, client_id="client-1", username="device-2") is False


def test_future_timestamp_rejected():
    auth = _manager(expire_seconds=3600)
    future_ts = int(time.time()) + 3600
    token = f"{auth._sign(f'client-1|device-1|{future_ts}')}.{future_ts}"
    assert auth.verify_token(token, client_id="client-1", username="device-1") is False


def test_malformed_token_rejected():
    auth = _manager()
    assert auth.verify_token("not-a-token", client_id="c", username="d") is False

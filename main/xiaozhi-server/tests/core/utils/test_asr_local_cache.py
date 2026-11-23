import pytest

from core.utils import asr


@pytest.fixture(autouse=True)
def _clean_cache():
    asr.clear_local_cache()
    yield
    asr.clear_local_cache()


def test_same_config_reuses_instance():
    created = []

    def factory():
        instance = object()
        created.append(instance)
        return instance

    args = ({"model_dir": "models/SenseVoiceSmall", "language": "auto"}, True)
    first = asr.cached_local_instance("fun_local", factory, args, {})
    second = asr.cached_local_instance("fun_local", factory, args, {})
    assert first is second
    assert len(created) == 1


def test_different_config_creates_new_instance():
    created = []

    def factory():
        instance = object()
        created.append(instance)
        return instance

    a = asr.cached_local_instance("fun_local", factory, ({"model_dir": "/a"}, True), {})
    b = asr.cached_local_instance("fun_local", factory, ({"model_dir": "/b"}, True), {})
    assert a is not b
    assert len(created) == 2


def test_different_type_creates_new_instance():
    def factory():
        return object()

    a = asr.cached_local_instance("fun_local", factory, ({"model_dir": "/a"}, True), {})
    b = asr.cached_local_instance("vosk", factory, ({"model_dir": "/a"}, True), {})
    assert a is not b


class _BadStr:
    def __str__(self):
        raise ValueError("cannot stringify")


def test_unserializable_config_falls_back_to_new_instance():
    def factory():
        return object()

    args = ({"model_dir": _BadStr()}, True)
    a = asr.cached_local_instance("fun_local", factory, args, {})
    b = asr.cached_local_instance("fun_local", factory, args, {})
    assert a is not b


def test_local_types_cover_known_heavy_providers():
    assert "fun_local" in asr.LOCAL_ASR_TYPES
    assert "sherpa_onnx_local" in asr.LOCAL_ASR_TYPES

import os
import subprocess
import sys
import pathlib

import pathlib


def _find_server_root(start):
    path = pathlib.Path(start).resolve()
    for candidate in [path, *path.parents]:
        if (candidate / "app.py").is_file() and (candidate / "core" / "providers").is_dir():
            return candidate
    raise RuntimeError("找不到 xiaozhi-server 根目录")
ROOT = _find_server_root(__file__)
UTILS_FACTORIES = ["asr.py", "llm.py", "intent.py", "tts.py", "vad.py", "vllm.py"]


def _run(code: str, cwd) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    # 与 scripts/run_tests.sh 保持一致：Windows 上 opuslib_next 通过 PATH 找 opus.dll
    opus_dir = pathlib.Path.home() / ".cache" / "xiaozhi-opus"
    if opus_dir.is_dir():
        env["PATH"] = str(opus_dir) + os.pathsep + env.get("PATH", "")
    return subprocess.run([sys.executable, "-c", code], cwd=str(cwd),
                          capture_output=True, text=True, env=env, timeout=180)


def test_provider_factories_do_not_use_cwd_relative_paths():
    for name in UTILS_FACTORIES:
        source = (ROOT / "core/utils" / name).read_text(encoding="utf-8")
        assert "os.path.join('core'" not in source, f"{name} 仍在使用工作目录相对的 provider 路径"
        assert 'os.path.join("core"' not in source, f"{name} 仍在使用工作目录相对的 provider 路径"


def test_tts_factory_resolves_provider_when_cwd_is_elsewhere(tmp_path):
    code = (
        "from core.utils.tts import create_instance\n"
        "p = create_instance('openai', {'type': 'openai', 'api_key': 'k'}, False)\n"
        "print(type(p).__module__)\n"
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0, result.stderr[-1200:]
    assert "core.providers.tts.openai" in result.stdout

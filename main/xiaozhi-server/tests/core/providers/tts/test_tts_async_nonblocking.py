import ast
import pathlib

import pytest

import pathlib


def _find_server_root(start):
    path = pathlib.Path(start).resolve()
    for candidate in [path, *path.parents]:
        if (candidate / "app.py").is_file() and (candidate / "core" / "providers").is_dir():
            return candidate
    raise RuntimeError("找不到 xiaozhi-server 根目录")

ROOT = _find_server_root(__file__)
BLOCKING_CALLS = ("requests.", "time.sleep", "urlopen")

# 这些文件里的 async 方法过去直接调用 requests.* / time.sleep，会阻塞事件循环（#H8）
TARGETS = [
    "core/providers/tts/doubao.py",
    "core/providers/tts/aliyun.py",
    "core/providers/tts/custom.py",
    "core/providers/tts/openai.py",
    "core/providers/tts/tencent.py",
    "core/providers/tts/cozecn.py",
    "core/providers/tts/siliconflow.py",
    "core/providers/tts/fishspeech.py",
    "core/providers/tts/gpt_sovits_v2.py",
    "core/providers/tts/gpt_sovits_v3.py",
    "core/providers/asr/openai.py",
    "core/providers/asr/fun_local.py",
]


def _blocking_calls_in_async_functions(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    try:
                        target = ast.unparse(sub.func)
                    except Exception:  # pragma: no cover - 解析失败时忽略
                        continue
                    if any(token in target for token in BLOCKING_CALLS):
                        found.append((node.name, sub.lineno, target))
    return found


@pytest.mark.parametrize("relative_path", TARGETS)
def test_no_blocking_calls_inside_async_provider_methods(relative_path):
    path = ROOT / relative_path
    assert path.exists(), f"文件不存在: {path}"
    assert _blocking_calls_in_async_functions(path) == [], (
        f"{relative_path} 的 async 方法里仍有阻塞调用，需改为 await asyncio.to_thread(...)"
    )

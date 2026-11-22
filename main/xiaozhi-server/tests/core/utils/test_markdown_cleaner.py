"""MarkdownCleaner 不得把标识符/乘号里的 * 和 _ 当作斜体标记（issue #3554）。"""
from pathlib import Path

import pytest

# core.utils.tts 在 import 时会初始化 logger，需要 data/.config.yaml；
# 源码仓库默认不带该文件（部署时才创建），缺失时跳过而不是报错。
_CONFIG = Path(__file__).resolve().parents[3] / "data" / ".config.yaml"
if not _CONFIG.exists():
    pytest.skip("requires data/.config.yaml", allow_module_level=True)

from core.utils.tts import MarkdownCleaner


@pytest.mark.parametrize(
    "text,expected",
    [
        # 标识符中的下划线原样保留
        ("请调用 get_current_time 函数", "请调用 get_current_time 函数"),
        ("a_b_c 结束", "a_b_c 结束"),
        # 乘号不是斜体
        ("结果是 2*3*4 等于 24", "结果是 2*3*4 等于 24"),
        # 真正的 Markdown 斜体/粗体仍然生效
        ("*重点*", "重点"),
        ("_emphasis_", "emphasis"),
        ("**加粗**", "加粗"),
        ("__加粗__", "加粗"),
        # 数字之间的下划线仍按千分位去掉
        ("1_000_000", "1000000"),
        ("一共 1_280 元", "一共 1280 元"),
    ],
)
def test_clean_markdown_keeps_identifiers_and_math(text, expected):
    assert MarkdownCleaner.clean_markdown(text) == expected
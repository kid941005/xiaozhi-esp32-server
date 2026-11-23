import json

import pytest

from core.providers.llm.fastgpt import fastgpt as fastgpt_module


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_lines(self):
        return iter(self._lines)


def _provider():
    provider = fastgpt_module.LLMProvider.__new__(fastgpt_module.LLMProvider)
    provider.api_key = "k"
    provider.base_url = "http://localhost/fastgpt"
    provider.detail = False
    provider.variables = {}
    return provider


def _line(content):
    return b"data: " + json.dumps({"choices": [{"delta": {"content": content}}]},
                                  ensure_ascii=False).encode("utf-8")


def test_think_block_is_stripped_without_dropping_reply(monkeypatch):
    lines = [
        _line("<think>"),
        _line("内部思考内容"),
        _line("</think>你好"),
        _line("世界"),
        b"data: [DONE]",
    ]
    monkeypatch.setattr(fastgpt_module.requests, "post", lambda *a, **k: _FakeResponse(lines))

    output = list(_provider().response("sid", [{"role": "user", "content": "hi"}]))

    assert output == ["你好", "世界"]


def test_response_with_functions_degrades_instead_of_returning_none(monkeypatch):
    lines = [_line("你好"), b"data: [DONE]"]
    monkeypatch.setattr(fastgpt_module.requests, "post", lambda *a, **k: _FakeResponse(lines))

    generator = _provider().response_with_functions("sid", [{"role": "user", "content": "hi"}])

    assert generator is not None
    assert list(generator) == ["你好"]

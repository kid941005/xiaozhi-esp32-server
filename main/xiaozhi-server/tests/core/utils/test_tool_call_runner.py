"""ToolCallRunner：并发执行、超时取消、失败写入对话历史、上报容错。"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from core.utils.tool_call_runner import ToolCallRunner
from plugins_func.register import Action, ActionResponse


class _Logger:
    def __init__(self):
        self.messages = []

    def bind(self, **_kwargs):
        return self

    def _add(self, level, msg):
        self.messages.append((level, str(msg)))

    def debug(self, msg):
        self._add("debug", msg)

    def warning(self, msg):
        self._add("warning", msg)

    def error(self, msg):
        self._add("error", msg)


class _Dialogue:
    def __init__(self):
        self.messages = []

    def put(self, message):
        self.messages.append(message)


class _FuncHandler:
    def __init__(self, behaviour):
        self._behaviour = behaviour
        self.calls = []

    async def handle_llm_function_call(self, conn, tool_call_data):
        self.calls.append(tool_call_data)
        return await self._behaviour(tool_call_data)


@pytest.fixture
def loop():
    lp = asyncio.new_event_loop()
    thread = threading.Thread(target=lp.run_forever, daemon=True)
    thread.start()
    try:
        yield lp
    finally:
        lp.call_soon_threadsafe(lp.stop)
        thread.join(timeout=2)
        lp.close()


def _runner(loop, func_handler, dialogue, report=None, config=None):
    runner = ToolCallRunner(
        object(),
        loop=loop,
        func_handler=func_handler,
        dialogue=dialogue,
        config=config or {},
        logger=_Logger(),
        report_func=report,
    )
    runner.test_logger = runner.logger
    return runner


def test_successful_call_returns_result_and_reports_twice(loop):
    async def ok(tool_call_data):
        return ActionResponse(Action.RESPONSE, "r", "done")

    reports = []
    runner = _runner(
        loop,
        _FuncHandler(ok),
        _Dialogue(),
        report=lambda *args, **kwargs: reports.append((args, kwargs)),
    )

    results = runner.run([{"name": "t", "id": "id1", "arguments": '{"a": 1}'}])

    assert len(results) == 1
    response, data = results[0]
    assert response.action is Action.RESPONSE
    assert data["name"] == "t"
    assert len(reports) == 2
    assert reports[0][0][0] == "t"
    assert reports[0][0][1] == {"a": 1}
    assert reports[1][1].get("report_tool_call") is False


def test_timeout_cancels_task_and_writes_history(loop):
    cancelled = []
    started = threading.Event()

    async def slow(tool_call_data):
        started.set()
        try:
            # 用 asyncio.Event 等待：可被 Task.cancel() 打断，
            # 才能验证超时后确实取消了后台任务（conftest 会把 asyncio.sleep 换成空桩）
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    dialogue = _Dialogue()
    runner = _runner(loop, _FuncHandler(slow), dialogue, config={"tool_call_timeout": 1})

    results = runner.run([{"name": "write_file", "id": None, "arguments": "{}"}])

    assert results[0][0].action is Action.ERROR
    # 失败调用要写入 assistant(tool_calls) + tool 两条历史
    assert len(dialogue.messages) == 2
    assert dialogue.messages[0].role == "assistant"
    assert dialogue.messages[0].tool_calls[0]["function"]["name"] == "write_file"
    assert dialogue.messages[1].role == "tool"
    assert dialogue.messages[1].tool_call_id == dialogue.messages[0].tool_calls[0]["id"]
    # 协程已经开始执行，说明取消的不是「还没跑」的任务
    assert started.is_set()
    # 后台任务被取消（协程收到 CancelledError），取消在事件循环线程里异步生效
    for _ in range(50):
        if cancelled:
            break
        import time

        time.sleep(0.02)
    assert cancelled == [True]


def test_invalid_json_arguments_do_not_break_call(loop):
    async def ok(tool_call_data):
        return ActionResponse(Action.RESPONSE, None, "ok")

    reports = []
    runner = _runner(
        loop,
        _FuncHandler(ok),
        _Dialogue(),
        report=lambda *args, **kwargs: reports.append((args, kwargs)),
    )

    results = runner.run([{"name": "t", "id": "id1", "arguments": "not-json"}])

    assert results[0][0].action is Action.RESPONSE
    assert reports[0][0][1] == {}


def test_report_failure_does_not_break_execution(loop):
    async def ok(tool_call_data):
        return ActionResponse(Action.RESPONSE, None, "ok")

    def boom(*_args, **_kwargs):
        raise RuntimeError("report down")

    runner = _runner(loop, _FuncHandler(ok), _Dialogue(), report=boom)
    results = runner.run([{"name": "t", "id": "id1", "arguments": "{}"}])
    assert results[0][0].action is Action.RESPONSE


def test_multiple_calls_keep_input_order(loop):
    async def slow(tool_call_data):
        await asyncio.sleep(0.15 if tool_call_data["name"] == "slow" else 0)
        return ActionResponse(Action.RESPONSE, tool_call_data["name"], "ok")

    runner = _runner(loop, _FuncHandler(slow), _Dialogue())
    results = runner.run(
        [
            {"name": "slow", "id": "1", "arguments": "{}"},
            {"name": "fast", "id": "2", "arguments": "{}"},
        ]
    )
    assert [r[1]["name"] for r in results] == ["slow", "fast"]

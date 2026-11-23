"""工具调用执行器

把 connection.py 里「并发发起工具调用 + 超时取消 + 失败写入对话历史 + 结果上报」
这段流程抽出来，避免它继续膨胀在 ConnectionHandler 里（P1 结构拆分）。

行为与原来逐行一致：
- 参数不是合法 JSON 时按空对象调用，不中断整轮对话；
- 每个工具调用都用 asyncio.run_coroutine_threadsafe 提交到连接所在事件循环；
- 等待超过 tool_call_timeout 时取消后台任务，并把「调用 + 失败结果」写入对话历史，
  避免模型/用户误以为没调用过而重试（#3566）；
- 失败统一返回 Action.ERROR，由上层决定怎么回复用户。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.utils.dialogue import Message
from plugins_func.register import Action, ActionResponse


class ToolCallRunner:
    """并发执行一批 LLM 工具调用，统一处理超时、取消与对话历史。"""

    def __init__(
        self,
        conn,
        *,
        loop,
        func_handler,
        dialogue,
        config: Dict[str, Any],
        logger,
        speaker=None,
        report_func: Optional[Callable[..., None]] = None,
        default_timeout: int = 30,
    ):
        self.conn = conn
        self.loop = loop
        self.func_handler = func_handler
        self.dialogue = dialogue
        self.config = config
        self.logger = logger
        self.speaker = speaker
        self.report_func = report_func
        self.default_timeout = default_timeout

    # ------------------------------------------------------------------ 工具函数
    def _report(self, name: str, tool_input: Dict[str, Any], *args, **kwargs):
        if self.report_func is None:
            return
        try:
            self.report_func(name, tool_input, *args, **kwargs)
        except Exception as e:  # 上报失败不能影响工具调用主流程
            self.logger.bind(tag=__name__).warning(f"上报工具调用失败: {e}")

    def _parse_arguments(self, tool_call_data: Dict[str, Any]) -> Dict[str, Any]:
        raw = tool_call_data.get("arguments")
        try:
            tool_input = json.loads(raw or "{}")
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            self.logger.bind(tag=__name__).warning(
                f"工具参数不是合法JSON对象: {raw!r}, 错误: {e}"
            )
            return {}
        return tool_input if isinstance(tool_input, dict) else {}

    def _record_failed_call(
        self, tool_call_data: Dict[str, Any], timeout: int, error: Exception
    ) -> str:
        """把失败的调用写入对话历史，返回 tool_call_id。"""
        failed_tool_call_id = (
            str(uuid.uuid4())
            if tool_call_data["id"] is None
            else tool_call_data["id"]
        )
        self.dialogue.put(
            Message(
                role="assistant",
                tool_calls=[
                    {
                        "id": failed_tool_call_id,
                        "function": {
                            "arguments": tool_call_data["arguments"] or "{}",
                            "name": tool_call_data["name"],
                        },
                        "type": "function",
                        "index": 0,
                    }
                ],
            )
        )
        self.dialogue.put(
            Message(
                role="tool",
                tool_call_id=failed_tool_call_id,
                content=f"工具调用超时（{timeout}秒）或异常，后台任务已取消：{error}",
            )
        )
        return failed_tool_call_id

    # ------------------------------------------------------------------ 主流程
    def run(
        self, tool_calls_list: List[Dict[str, Any]]
    ) -> List[Tuple[ActionResponse, Dict[str, Any]]]:
        """执行全部工具调用，返回 [(结果, 原始调用数据)]，顺序与入参一致。"""
        futures_with_data = []
        for tool_call_data in tool_calls_list:
            self.logger.bind(tag=__name__).debug(
                f"function_name={tool_call_data['name']}, "
                f"function_id={tool_call_data['id']}, "
                f"function_arguments={tool_call_data['arguments']}"
            )
            tool_input = self._parse_arguments(tool_call_data)
            self._report(tool_call_data["name"], tool_input)

            future = asyncio.run_coroutine_threadsafe(
                self.func_handler.handle_llm_function_call(
                    self.conn, tool_call_data, speaker=self.speaker
                ),
                self.loop,
            )
            futures_with_data.append((future, tool_call_data, tool_input))

        tool_call_timeout = int(self.config.get("tool_call_timeout", self.default_timeout))
        tool_results: List[Tuple[ActionResponse, Dict[str, Any]]] = []

        for future, tool_call_data, tool_input in futures_with_data:
            try:
                result = future.result(timeout=tool_call_timeout)
                tool_results.append((result, tool_call_data))
                self._report(
                    tool_call_data["name"],
                    tool_input,
                    str(result.result) if result.result else None,
                    report_tool_call=False,
                )
            except Exception as e:
                # 超时/异常时必须取消后台任务，否则写操作会在超时后继续执行（#3566）
                cancelled = future.cancel()
                self.logger.bind(tag=__name__).error(
                    f"工具调用超时或异常: {tool_call_data['name']}, "
                    f"错误: {e}, 已取消后台任务: {cancelled}"
                )
                self._record_failed_call(tool_call_data, tool_call_timeout, e)
                tool_results.append(
                    (
                        ActionResponse(
                            action=Action.ERROR,
                            result="哎呀，网络遇到点问题，请稍后再试下！",
                        ),
                        tool_call_data,
                    )
                )
                self._report(
                    tool_call_data["name"],
                    tool_input,
                    str(e),
                    report_tool_call=False,
                )

        return tool_results

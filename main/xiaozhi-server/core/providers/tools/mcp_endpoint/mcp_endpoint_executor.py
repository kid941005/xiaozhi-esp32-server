"""MCP接入点工具执行器"""

from typing import Dict, Any, Optional
from ..base import ToolType, ToolDefinition, ToolExecutor
from plugins_func.register import Action, ActionResponse
from core.utils.voiceprint_provider import SpeakerIdentification
from .mcp_endpoint_handler import call_mcp_endpoint_tool
from .mcp_speaker import should_forward_speaker, speaker_call_meta

# 只接受协议允许的 action 枚举名；绝不能把未知字符串（如 turn_off）当枚举索引，
# 否则会在 xiaozhi 侧抛 KeyError 并被 TTS 直接念出英文动作名。
_ACTION_NAMES = {a.name for a in Action}


class MCPEndpointExecutor(ToolExecutor):
    """MCP接入点工具执行器"""

    def __init__(self, conn):
        self.conn = conn

    async def execute(
        self, conn, tool_name: str, arguments: Dict[str, Any], speaker: Optional[SpeakerIdentification] = None
    ) -> ActionResponse:
        """执行MCP接入点工具。speaker: 本轮说话人快照。"""
        if not hasattr(conn, "mcp_endpoint_client") or not conn.mcp_endpoint_client:
            return ActionResponse(
                action=Action.ERROR,
                response="MCP接入点客户端未初始化",
            )

        if not await conn.mcp_endpoint_client.is_ready():
            return ActionResponse(
                action=Action.ERROR,
                response="MCP接入点客户端未准备就绪",
            )

        try:
            # 转换参数为JSON字符串。说话人身份不写入参数，只放在 _meta。
            import json

            meta = None
            if speaker is not None and should_forward_speaker(
                getattr(conn, "config", None)
            ):
                meta = speaker_call_meta(speaker.speaker_id, speaker.name)

            args_str = json.dumps(arguments) if arguments else "{}"

            # 调用MCP接入点工具
            result = await call_mcp_endpoint_tool(
                conn.mcp_endpoint_client, tool_name, args_str, meta=meta
            )

            resultJson = None
            if isinstance(result, str):
                try:
                    resultJson = json.loads(result)
                except Exception as e:
                    pass

            # 视觉大模型不经过二次LLM处理；action 必须在协议枚举内，否则走 REQLLM
            if (
                resultJson is not None
                and isinstance(resultJson, dict)
                and "action" in resultJson
                and str(resultJson.get("action")) in _ACTION_NAMES
            ):
                response = resultJson.get("response", "")
                if not isinstance(response, str):
                    response = str(response)
                return ActionResponse(
                    action=Action[str(resultJson["action"])],
                    response=response,
                )

            # 未知/缺失 action 一律回退到 REQLLM，由 LLM 结合结果生成自然语言，
            # 不把内部字符串直接送入 TTS。
            fallback = resultJson if resultJson is not None else result
            return ActionResponse(
                action=Action.REQLLM,
                result=(
                    json.dumps(fallback, ensure_ascii=False)
                    if not isinstance(fallback, str)
                    else fallback
                ),
            )

        except ValueError:
            return ActionResponse(action=Action.NOTFOUND, response="未找到对应的 MCP 工具。")
        except Exception:
            return ActionResponse(action=Action.ERROR, response="调用 MCP 工具失败，请稍后再试。")

    def get_tools(self) -> Dict[str, ToolDefinition]:
        """获取所有MCP接入点工具"""
        if (
            not hasattr(self.conn, "mcp_endpoint_client")
            or not self.conn.mcp_endpoint_client
        ):
            return {}

        tools = {}
        mcp_tools = self.conn.mcp_endpoint_client.get_available_tools()

        for tool in mcp_tools:
            func_def = tool.get("function", {})
            tool_name = func_def.get("name", "")

            if tool_name:
                tools[tool_name] = ToolDefinition(
                    name=tool_name, description=tool, tool_type=ToolType.MCP_ENDPOINT
                )

        return tools

    def has_tool(self, tool_name: str) -> bool:
        """检查是否有指定的MCP接入点工具"""
        if (
            not hasattr(self.conn, "mcp_endpoint_client")
            or not self.conn.mcp_endpoint_client
        ):
            return False

        return self.conn.mcp_endpoint_client.has_tool(tool_name)

"""MCP接入点客户端定义"""

import asyncio
from concurrent.futures import Future
from core.utils.util import sanitize_tool_name
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class MCPEndpointClient:
    """MCP接入点客户端，用于管理MCP接入点状态和工具"""

    def __init__(self, conn=None):
        self.conn = conn
        self.tools = {}  # sanitized_name -> tool_data
        self.name_mapping = {}
        self.ready = False
        self.call_results = {}  # To store Futures for tool call responses
        # Handshake hardcodes id=1 (initialize) and id=2 (tools/list) in
        # mcp_endpoint_handler; tools/call must start at 3 to avoid id reuse.
        self.next_id = 3
        self.lock = asyncio.Lock()
        self._cached_available_tools = None  # Cache for get_available_tools
        self.websocket = None  # WebSocket连接
        self.mcp_endpoint_url = None  # 用于断线重连
        self.closed = False  # 主动关闭后不再重连
        self.reconnecting = False  # 防止重复启动重连任务
        self.reconnect_task = None  # 持有重连任务强引用，避免被 GC 回收

    def has_tool(self, name: str) -> bool:
        return name in self.tools

    def get_available_tools(self) -> list:
        # Check if the cache is valid
        if self._cached_available_tools is not None:
            return self._cached_available_tools

        # If cache is not valid, regenerate the list
        result = []
        for tool_name, tool_data in self.tools.items():
            function_def = {
                "name": tool_name,
                "description": tool_data["description"],
                "parameters": {
                    "type": tool_data["inputSchema"].get("type", "object"),
                    "properties": tool_data["inputSchema"].get("properties", {}),
                    "required": tool_data["inputSchema"].get("required", []),
                },
            }
            result.append({"type": "function", "function": function_def})

        self._cached_available_tools = result  # Store the generated list in cache
        return result

    async def is_ready(self) -> bool:
        async with self.lock:
            return self.ready

    async def set_ready(self, status: bool):
        async with self.lock:
            self.ready = status

    async def add_tool(self, tool_data: dict):
        async with self.lock:
            sanitized_name = sanitize_tool_name(tool_data["name"])
            self.tools[sanitized_name] = tool_data
            self.name_mapping[sanitized_name] = tool_data["name"]
            self._cached_available_tools = (
                None  # Invalidate the cache when a tool is added
            )

    async def get_next_id(self) -> int:
        async with self.lock:
            current_id = self.next_id
            self.next_id += 1
            return current_id

    async def register_call_result_future(self, id: int, future: Future):
        async with self.lock:
            self.call_results[id] = future

    async def resolve_call_result(self, id: int, result: any):
        async with self.lock:
            if id in self.call_results:
                future = self.call_results.pop(id)
                if not future.done():
                    future.set_result(result)

    async def reject_call_result(self, id: int, exception: Exception):
        async with self.lock:
            if id in self.call_results:
                future = self.call_results.pop(id)
                if not future.done():
                    future.set_exception(exception)

    async def cleanup_call_result(self, id: int):
        async with self.lock:
            if id in self.call_results:
                self.call_results.pop(id)

    async def fail_all_call_results(self, reason: str = "MCP接入点连接已断开"):
        """连接断开时唤醒所有等待中的调用，避免工具调用一直挂到超时。"""
        async with self.lock:
            pending = list(self.call_results.values())
            self.call_results.clear()
        for future in pending:
            if not future.done():
                future.set_exception(RuntimeError(reason))

    def set_websocket(self, websocket):
        """设置WebSocket连接"""
        self.websocket = websocket

    async def send_message(self, message: str):
        """发送消息到MCP接入点"""
        if self.websocket:
            await self.websocket.send(message)
        else:
            raise RuntimeError("WebSocket连接未建立")

    async def close(self):
        """关闭WebSocket连接（主动关闭后不再自动重连）"""
        self.closed = True
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

"""统一工具管理器

P1 结构优化：
1. 显式优先级：同名工具不再由注册顺序决定归属，而是按 ToolType 优先级保留高优先级的定义；
2. 冲突可观测：冲突双方来源（tool_type）都打印，并可通过 get_tool_conflicts() 查询；
3. 调用指标：按工具累计调用次数/失败次数/总耗时，慢调用单独告警，供 P2 可观测性使用。
"""

import time
from typing import Any, Dict, List, Optional

from config.logger import setup_logging
from plugins_func.register import Action, ActionResponse
from .base import ToolType, ToolDefinition, ToolExecutor

# 工具类型优先级：数值越大越优先。同名冲突时保留高优先级定义。
# 服务端插件是人工配置、经过测试的，优先于设备端/MCP 自动发现的同名工具。
TOOL_TYPE_PRIORITY: Dict[ToolType, int] = {
    ToolType.SERVER_PLUGIN: 100,
    ToolType.DEVICE_IOT: 80,
    ToolType.SERVER_MCP: 60,
    ToolType.DEVICE_MCP: 40,
    ToolType.MCP_ENDPOINT: 20,
}

# 超过该耗时（秒）的工具调用打告警日志
SLOW_TOOL_CALL_SECONDS = 2.0


class ToolManager:
    """统一工具管理器，管理所有类型的工具"""

    def __init__(self, conn):
        self.conn = conn
        self.logger = setup_logging()
        self.executors: Dict[ToolType, ToolExecutor] = {}
        self._cached_tools: Optional[Dict[str, ToolDefinition]] = None
        self._cached_function_descriptions: Optional[List[Dict[str, Any]]] = None
        self._tool_conflicts: List[Dict[str, str]] = []
        # 运行时指标：{工具名: {"calls", "failures", "total_ms", "max_ms"}}
        self._call_stats: Dict[str, Dict[str, float]] = {}

    def register_executor(self, tool_type: ToolType, executor: ToolExecutor):
        """注册工具执行器"""
        self.executors[tool_type] = executor
        self._invalidate_cache()
        self.logger.debug(f"注册工具执行器: {tool_type.value}")

    def _invalidate_cache(self):
        """使缓存失效"""
        self._cached_tools = None
        self._cached_function_descriptions = None
        self._tool_conflicts = []

    @staticmethod
    def _priority_of(tool_type: ToolType) -> int:
        return TOOL_TYPE_PRIORITY.get(tool_type, 0)

    def get_all_tools(self) -> Dict[str, ToolDefinition]:
        """获取所有工具定义；同名冲突按优先级保留，并记录冲突双方来源。"""
        if self._cached_tools is not None:
            return self._cached_tools

        # 高优先级先入表，后续低优先级同名工具直接让位
        ordered = sorted(
            self.executors.items(),
            key=lambda item: self._priority_of(item[0]),
            reverse=True,
        )

        all_tools: Dict[str, ToolDefinition] = {}
        owners: Dict[str, ToolType] = {}
        conflicts: List[Dict[str, str]] = []
        for tool_type, executor in ordered:
            try:
                tools = executor.get_tools()
                for name, definition in tools.items():
                    if name in all_tools:
                        kept = owners[name]
                        conflicts.append(
                            {
                                "name": name,
                                "kept": kept.value,
                                "ignored": tool_type.value,
                            }
                        )
                        self.logger.warning(
                            f"工具名称冲突: {name}，保留 {kept.value}"
                            f"（优先级 {self._priority_of(kept)}），"
                            f"忽略 {tool_type.value}"
                            f"（优先级 {self._priority_of(tool_type)}）"
                        )
                        continue
                    all_tools[name] = definition
                    owners[name] = tool_type
            except Exception as e:
                self.logger.error(f"获取{tool_type.value}工具时出错: {e}")

        self._tool_conflicts = conflicts
        self._cached_tools = all_tools
        return all_tools

    def get_tool_conflicts(self) -> List[Dict[str, str]]:
        """返回最近一次构建工具表时的名称冲突（name/kept/ignored）。"""
        # 触发一次构建，保证返回的是当前工具表的冲突
        self.get_all_tools()
        return list(self._tool_conflicts)

    def get_function_descriptions(self) -> List[Dict[str, Any]]:
        """获取所有工具的函数描述（OpenAI格式）

        返回缓存的浅拷贝，防止调用方就地修改污染缓存。
        """
        if self._cached_function_descriptions is not None:
            return list(self._cached_function_descriptions)

        descriptions = []
        tools = self.get_all_tools()
        for tool_definition in tools.values():
            descriptions.append(tool_definition.description)

        self._cached_function_descriptions = descriptions
        return list(descriptions)

    def has_tool(self, tool_name: str) -> bool:
        """检查是否存在指定工具"""
        tools = self.get_all_tools()
        return tool_name in tools

    def get_tool_type(self, tool_name: str) -> Optional[ToolType]:
        """获取工具类型"""
        tools = self.get_all_tools()
        tool_def = tools.get(tool_name)
        return tool_def.tool_type if tool_def else None

    def _record_call(self, tool_name: str, duration_ms: float, failed: bool):
        """记录单次工具调用指标。"""
        stats = self._call_stats.setdefault(
            tool_name,
            {"calls": 0, "failures": 0, "total_ms": 0.0, "max_ms": 0.0},
        )
        stats["calls"] += 1
        if failed:
            stats["failures"] += 1
        stats["total_ms"] += duration_ms
        if duration_ms > stats["max_ms"]:
            stats["max_ms"] = duration_ms

    def get_runtime_metrics(self) -> Dict[str, Dict[str, float]]:
        """返回工具调用指标快照（供可观测性/自检接口使用）。"""
        return {name: dict(stats) for name, stats in self._call_stats.items()}

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ActionResponse:
        """执行工具调用"""
        started = time.monotonic()
        failed = False
        try:
            # 查找工具类型
            tool_type = self.get_tool_type(tool_name)
            if not tool_type:
                failed = True
                return ActionResponse(
                    action=Action.NOTFOUND,
                    response=f"工具 {tool_name} 不存在",
                )

            # 获取对应的执行器
            executor = self.executors.get(tool_type)
            if not executor:
                failed = True
                return ActionResponse(
                    action=Action.ERROR,
                    response=f"工具类型 {tool_type.value} 的执行器未注册",
                )

            # 执行工具
            self.logger.info(f"执行工具: {tool_name}，参数: {arguments}")
            result = await executor.execute(self.conn, tool_name, arguments)
            self.logger.debug(f"工具执行结果: {result}")
            if result is not None and result.action in (Action.ERROR, Action.NOTFOUND):
                failed = True
            return result

        except Exception as e:
            failed = True
            self.logger.error(f"执行工具 {tool_name} 时出错: {e}")
            # 异常细节只进日志，不回给 TTS（避免把堆栈/英文异常念给用户）
            return ActionResponse(action=Action.ERROR, response="调用工具失败，请稍后再试。")
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            self._record_call(tool_name, duration_ms, failed)
            if duration_ms > SLOW_TOOL_CALL_SECONDS * 1000:
                self.logger.warning(
                    f"工具调用耗时过长: {tool_name} {duration_ms:.0f}ms"
                )

    def get_supported_tool_names(self) -> List[str]:
        """获取所有支持的工具名称"""
        tools = self.get_all_tools()
        return list(tools.keys())

    def refresh_tools(self):
        """刷新工具缓存"""
        self._invalidate_cache()
        self.logger.debug("工具缓存已刷新")

    def get_tool_statistics(self) -> Dict[str, int]:
        """获取工具统计信息"""
        stats = {}
        for tool_type, executor in self.executors.items():
            try:
                tools = executor.get_tools()
                stats[tool_type.value] = len(tools)
            except Exception as e:
                self.logger.error(f"获取{tool_type.value}工具统计时出错: {e}")
                stats[tool_type.value] = 0
        return stats

"""数据上下文填充：从配置的上下文源并发拉取数据，注入系统提示词。

设计要点（P1 结构优化）：
1. 并发拉取：多个上下文源用线程池并发请求，一轮总耗时不再随源数量线性增长；
2. 总超时：整轮拉取有统一截止时间，单个源卡住不会拖慢对话（原来每个源串行 3s）；
3. 连接复用：进程内共享一个 httpx.Client，避免每次对话重新建连；
4. 失败隔离：任一源异常/超时只丢该源数据，返回其余源内容。

调用方是连接初始化线程（core/connection.py::_init_prompt_enhancement），
因此这里保持同步接口，用线程池实现并发，不引入 async 桥接。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Dict, List, Optional

import httpx

from config.logger import setup_logging

TAG = __name__

# 单个上下文源的请求超时（秒）
DEFAULT_REQUEST_TIMEOUT = 3.0
# 一轮拉取的总超时（秒）
DEFAULT_TOTAL_TIMEOUT = 5.0
# 并发拉取的线程数上限
_MAX_WORKERS = 8
# 进程内共享线程池：避免每轮对话都新建线程
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="ctx-provider")


class ContextDataProvider:
    """数据上下文填充，负责从配置的API获取数据"""

    def __init__(self, config: Dict[str, Any], logger=None):
        self.config = config
        self.logger = logger or setup_logging()
        self.context_data = ""
        self.last_timeout_count = 0
        self._client: Optional[httpx.Client] = None
        self._client_lock = threading.Lock()

    # ------------------------------------------------------------------ HTTP
    def _get_client(self) -> httpx.Client:
        """懒加载共享 httpx.Client（连接池复用，线程安全）。"""
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is None:
                self._client = httpx.Client(
                    timeout=DEFAULT_REQUEST_TIMEOUT,
                    limits=httpx.Limits(
                        max_connections=16,
                        max_keepalive_connections=8,
                        keepalive_expiry=30.0,
                    ),
                    follow_redirects=True,
                )
        return self._client

    def close(self) -> None:
        """关闭共享连接池（进程退出/连接销毁时调用）。"""
        with self._client_lock:
            client, self._client = self._client, None
        if client is not None:
            try:
                client.close()
            except Exception as e:  # pragma: no cover - 关闭失败不影响主流程
                self.logger.bind(tag=TAG).debug(f"关闭上下文源连接池失败: {e}")

    # ------------------------------------------------------------------ 单个源
    def _fetch_one(
        self, url: str, headers: Any, device_id: str, request_timeout: float
    ) -> List[str]:
        """拉取单个上下文源，返回格式化后的行；失败返回空列表。"""
        lines: List[str] = []
        try:
            req_headers = headers.copy() if isinstance(headers, dict) else {}
            req_headers["device-id"] = device_id
            response = self._get_client().get(
                url, headers=req_headers, timeout=request_timeout
            )
            if response.status_code != 200:
                self.logger.bind(tag=TAG).warning(
                    f"API {url} 请求失败: {response.status_code}"
                )
                return lines
            result = response.json()
            if not isinstance(result, dict):
                self.logger.bind(tag=TAG).warning(f"API {url} 返回的不是JSON字典")
                return lines
            if result.get("code") != 0:
                self.logger.bind(tag=TAG).warning(
                    f"API {url} 返回错误码: {result.get('msg')}"
                )
                return lines
            data = result.get("data")
            if isinstance(data, dict):
                for k, v in data.items():
                    lines.append(f"- **{k}：** {v}")
            elif isinstance(data, list):
                for item in data:
                    lines.append(f"- {item}")
            else:
                lines.append(f"- {data}")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"获取上下文数据 {url} 失败: {e}")
        return lines

    # ------------------------------------------------------------------ 全部源
    @staticmethod
    def _positive_float(value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    def fetch_all(self, device_id: str) -> str:
        """并发获取所有配置的上下文数据；单源失败或整轮超时都不抛异常。"""
        providers = [
            p
            for p in (self.config.get("context_providers") or [])
            if isinstance(p, dict) and p.get("url")
        ]
        self.context_data = ""
        self.last_timeout_count = 0
        if not providers:
            return ""

        request_timeout = self._positive_float(
            self.config.get("context_providers_request_timeout"),
            DEFAULT_REQUEST_TIMEOUT,
        )
        total_timeout = self._positive_float(
            self.config.get("context_providers_total_timeout"), DEFAULT_TOTAL_TIMEOUT
        )

        futures = [
            _EXECUTOR.submit(
                self._fetch_one, p["url"], p.get("headers"), device_id, request_timeout
            )
            for p in providers
        ]
        done, not_done = wait(futures, timeout=total_timeout)

        formatted_lines: List[str] = []
        # 按配置顺序拼接，保证提示词稳定（并发完成顺序不影响结果）
        for future in futures:
            if future not in done:
                continue
            try:
                formatted_lines.extend(future.result())
            except Exception as e:  # pragma: no cover - _fetch_one 已兜底
                self.logger.bind(tag=TAG).error(f"读取上下文源结果失败: {e}")

        if not_done:
            self.last_timeout_count = len(not_done)
            for future in not_done:
                future.cancel()
            self.logger.bind(tag=TAG).warning(
                f"上下文源拉取超时（{total_timeout:g}s），"
                f"跳过 {len(not_done)}/{len(futures)} 个源"
            )

        self.context_data = "\n".join(formatted_lines)
        if self.context_data:
            self.logger.bind(tag=TAG).debug(f"已注入动态上下文数据:\n{self.context_data}")
        return self.context_data

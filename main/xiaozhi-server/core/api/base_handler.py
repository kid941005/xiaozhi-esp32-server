from aiohttp import web
from config.logger import setup_logging


class BaseHandler:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        # CORS 白名单（#3456 独立缺陷2）：
        # - 未配置 allowed_origins：不下发 Access-Control-Allow-Origin（仅同源可用）
        # - 含 "*"：回显请求 Origin，但不允许携带凭证（浏览器规范要求）
        # - 命中具体域名：回显该 Origin 并允许携带凭证
        cors_config = (config.get("server") or {}).get("cors") or {}
        origins = cors_config.get("allowed_origins") or []
        self._cors_origins = [str(o).strip() for o in origins if str(o).strip()]
        self._cors_wildcard = "*" in self._cors_origins
        if self._cors_wildcard:
            self.logger.warning(
                "CORS 配置包含通配符 *：仅回显请求 Origin 且不允许携带凭证，"
                "生产环境建议在 server.cors.allowed_origins 填写具体域名"
            )

    def _add_cors_headers(self, response, request=None):
        """添加CORS头信息"""
        response.headers["Access-Control-Allow-Headers"] = (
            "client-id, content-type, device-id, authorization"
        )
        origin = request.headers.get("Origin") if request is not None else None
        if not origin:
            return
        # 带 Origin 的响应必须声明 Vary，避免中间缓存把 A 站响应串给 B 站
        response.headers["Vary"] = "Origin"
        if self._cors_wildcard:
            response.headers["Access-Control-Allow-Origin"] = origin
            return
        if origin in self._cors_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            self.logger.debug(f"CORS 拒绝未授权来源: {origin}")

    async def handle_options(self, request):
        """处理OPTIONS请求，添加CORS头信息"""
        response = web.Response(body=b"", content_type="text/plain")
        self._add_cors_headers(response, request)
        # 添加允许的方法
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

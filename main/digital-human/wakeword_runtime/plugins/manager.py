import logging
from typing import Any

from .base import Plugin

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self) -> None:
        self._plugins: list[Plugin] = []
        self._by_name: dict[str, Plugin] = {}

    def register(self, *plugins: Plugin) -> None:
        for plugin in sorted(plugins, key=lambda item: getattr(item, "priority", 50)):
            if plugin in self._plugins:
                continue
            self._plugins.append(plugin)
            name = getattr(plugin, "name", "")
            if isinstance(name, str) and name:
                self._by_name[name] = plugin

    def get_plugin(self, name: str) -> Plugin | None:
        return self._by_name.get(name)

    def setup_all(self, app: Any) -> None:
        for plugin in list(self._plugins):
            plugin.setup(app)

    def start_all(self) -> None:
        started: list[Plugin] = []
        try:
            for plugin in list(self._plugins):
                plugin.start()
                started.append(plugin)
        except Exception:
            # 启动中途失败要把已经启动的插件按逆序停掉，
            # 否则先启动的麦克风采集流没人关（#3496）
            for plugin in reversed(started):
                try:
                    plugin.stop()
                except Exception:
                    logger.exception(
                        "plugin stop failed during start rollback: %s",
                        getattr(plugin, "name", plugin),
                    )
            raise

    def stop_all(self) -> None:
        for plugin in reversed(self._plugins):
            plugin.stop()

    def shutdown_all(self) -> None:
        for plugin in reversed(self._plugins):
            plugin.shutdown()

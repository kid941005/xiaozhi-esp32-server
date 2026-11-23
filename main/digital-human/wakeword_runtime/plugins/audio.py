import logging
from typing import Any

from ..core import MicrophoneListener
from .base import Plugin

logger = logging.getLogger(__name__)


class AudioPlugin(Plugin):
    name = "audio"
    priority = 10

    def __init__(self) -> None:
        self.app = None
        self.source: MicrophoneListener | None = None

    def setup(self, app: Any) -> None:
        self.app = app
        self.source = MicrophoneListener(app.config)
        self.app.audio_source = self.source

    def start(self) -> None:
        if self.source is None:
            logger.warning("audio source not initialized")
            return
        self.source.start()

    def stop(self) -> None:
        if self.source is not None:
            self.source.stop()

    def shutdown(self) -> None:
        # 丢引用之前先停采集流：stop_all() 没跑到的路径（启动中途失败、shutdown 直连）
        # 也要能关掉麦克风（#3496）
        if self.source is not None:
            try:
                self.source.stop()
            except Exception:
                logger.exception("failed to stop microphone listener during shutdown")
        if self.app is not None:
            self.app.audio_source = None
        self.source = None
        self.app = None

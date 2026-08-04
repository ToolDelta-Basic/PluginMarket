import logging
from ..channel_host import Library

_log = logging.getLogger(__name__)


class NetworkLibrary(Library):
    """多机器人网络管理。"""

    name = "network"
    version = "1.6.0"
    dependencies = ["ws_client", "config_store"]

    async def mount(self) -> None:
        config = self.services.get("config")
        enabled = config.get("多机器人.启用", False)
        if not enabled:
            return
        _log.info("多机器人网络已启用（骨架）")

    async def unmount(self) -> None:
        pass

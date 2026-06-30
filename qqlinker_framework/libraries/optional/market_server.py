import logging
from ..channel_host import Library

_log = logging.getLogger(__name__)


class MarketLibrary(Library):
    """模块市场 HTTP 服务。"""

    name = "market_server"
    version = "1.6.0"
    dependencies = ["config_store", "module_loader"]

    async def mount(self) -> None:
        config = self.services.get("config")
        enabled = config.get("模块市场.启用", False)
        if not enabled:
            _log.debug("模块市场未启用")
            return
        # TODO: 启动 HTTP 服务
        _log.info("模块市场已启用（骨架）")

    async def unmount(self) -> None:
        pass

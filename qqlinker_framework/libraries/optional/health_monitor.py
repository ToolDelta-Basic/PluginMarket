import logging
from ..channel_host import Library

_log = logging.getLogger(__name__)


class HealthLibrary(Library):
    """健康检查 + 看门狗。"""

    name = "health_monitor"
    version = "1.6.0"
    dependencies = ["module_loader"]

    async def mount(self) -> None:
        _log.debug("健康监控已挂载（骨架）")

    async def unmount(self) -> None:
        pass

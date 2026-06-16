"""调试引擎库 — 诊断工具（骨架）。

依赖: 无
"""
from ..channel_host import Library


class DebugLibrary(Library):
    """调试/诊断引擎。"""

    name = "debug_engine"
    version = "1.6.0"
    dependencies: list = []

    async def mount(self) -> None:
        pass

    async def unmount(self) -> None:
        pass

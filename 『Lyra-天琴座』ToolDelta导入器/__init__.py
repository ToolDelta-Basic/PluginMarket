"""『Lyra-天琴座』ToolDelta导入器"""

from tooldelta import Plugin, plugin_entry
from typing import TYPE_CHECKING

from . import basic, config
from .lyra_loader.common import block_converter


class LyraSystem(Plugin):
    """『Lyra-天琴座』ToolDelta导入器"""

    name = "『Lyra-天琴座』ToolDelta导入器"
    author = "style_天枢"
    version = (0, 0, 3)

    def __init__(self, frame) -> None:
        super().__init__(frame)
        self.config_mgr = config.Config(self)
        self.config_mgr.load_config()
        self.basic_mgr = basic.Basic(self)
        self.converter: block_converter.BlockConverter
        self.command_loader: object
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)

    def on_preload(self) -> None:
        pip = self.GetPluginAPI("pip")
        pip.install(["amulet-leveldb==1.0.7"])
        if TYPE_CHECKING:
            from pip模块支持 import PipSupport

            pip: PipSupport

    def on_active(self) -> None:
        self.converter = block_converter.BlockConverter.from_plugin(self)
        self.basic_mgr.entry()


entry = plugin_entry(LyraSystem, "『Lyra-天琴座』ToolDelta导入器")

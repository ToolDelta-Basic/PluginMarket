"""mcstructure导入器(测试版)"""

from tooldelta import Plugin, plugin_entry
from importlib import reload

from . import config
from . import core
from . import nbt_parser
from . import chunk_painter
from . import command_loader

reload(config)
reload(core)
reload(nbt_parser)
reload(chunk_painter)
reload(command_loader)


class MCStructureLoader(Plugin):
    name = "mcstructure导入器[可导入命令]"
    author = "style_天枢"
    version = (0, 0, 3)

    def __init__(self, frame) -> None:
        super().__init__(frame)
        self.config_mgr = config.Config(self)
        self.core = core.Core(self)
        self.config_mgr.load_config()
        self.ListenActive(self.on_active)

    def on_active(self) -> None:
        self.chunk_painter = chunk_painter.ChunkPainter(self)
        self.command_loader = command_loader.CommandLoader(self)
        self.core.entry()


entry = plugin_entry(MCStructureLoader, "mcstructure导入器[可导入命令]")

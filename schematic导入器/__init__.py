"""schematic导入器(测试版)"""

from tooldelta import Plugin, plugin_entry
from importlib import reload

from . import config
from . import core
from . import nbt_parser
from . import chunk_painter

reload(config)
reload(core)
reload(nbt_parser)
reload(chunk_painter)


class SchematicLoader(Plugin):
    name = "schematic导入器"
    author = "style_天枢"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.config_mgr = config.Config(self)
        self.core = core.Core(self)
        self.chunk_painter = chunk_painter.ChunkPainter(self)
        self.config_mgr.load_config()
        self.ListenActive(self.on_active)

    def on_active(self):
        self.core.entry()


entry = plugin_entry(SchematicLoader, "schematic导入器")

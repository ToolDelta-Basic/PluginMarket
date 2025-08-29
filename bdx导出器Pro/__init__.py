from tooldelta import (
    Plugin,
    plugin_entry,
)


class BDXExporter(Plugin):
    name = "bdx导出器Pro"
    author = "SuperScript"
    version = (0, 2, 0)

    def __init__(self, _):
        raise Exception("bdx导出器Pro: 此组件现已弃用, 请前往 [简单世界导出] 作为替代")


entry = plugin_entry(BDXExporter)

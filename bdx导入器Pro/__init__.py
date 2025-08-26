from tooldelta import Plugin, plugin_entry


class BDX_BDump(Plugin):
    name = "bdx导入器Pro"
    author = "SuperScript"
    version = (0, 2, 0)

    def __init__(self, _):
        raise Exception(
            "bdx导入器Pro: 此组件现已弃用, 请前往 https://github.com/TriM-Organization/merry-memory/releases/latest "
            + "获取 BDX 到 mcworld (存档) s的转换器, 然后使用 [简单世界导入] 插件导入转换所得产物"
        )


entry = plugin_entry(BDX_BDump)

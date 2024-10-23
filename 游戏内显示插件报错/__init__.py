from tooldelta import Plugin, plugins, ToolDelta

GN = "\n"

@plugins.add_plugin
class InGameError(Plugin):
    name = "游戏内显示插件报错"
    author = "System"
    version = (0, 0, 1)

    def __init__(self, frame: ToolDelta):
        self.frame = frame
        self.frame.on_plugin_err = self.call_err

    def call_err(self, plugin_name: str, exception: Exception, exc_str: str):
        self.game_ctrl.say_to("@a", f"§7[§cERROR§7] §4{plugin_name} 报错：")
        self.game_ctrl.say_to("@a", f" §c{f'{GN} '.join(exc_str.split(GN))}")

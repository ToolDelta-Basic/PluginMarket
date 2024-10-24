from tooldelta import Plugin, plugins, ToolDelta

GN = "\n"

@plugins.add_plugin
class InGameError(Plugin):
    name = "游戏内显示插件报错"
    author = "System"
    version = (0, 0, 3)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.game_avali = False
        self.frame = frame
        self._backup_onerr = self.frame.on_plugin_err
        self.frame.on_plugin_err = self.call_err
        self.frame.add_console_cmd_trigger(["error", "报错"], "[报错文本]", "测试游戏内报错显示", self.test_error)

    def on_inject(self):
        self.game_avali = True

    def call_err(self, plugin_name: str, exception: Exception, exc_str: str):
        if self.game_avali:
            try:
                self.game_ctrl.say_to("@a", f"§7[§cERROR§7] §4{plugin_name} 报错：")
                self.game_ctrl.say_to("@a", f" §c{f'{GN} '.join(exc_str.split(GN))}")
            except Exception:
                self._backup_onerr(plugin_name, exception, exc_str)

    def test_error(self, args):
        if len(args) == 0:
            return
        self.game_ctrl.sendcmd(f"w @s tooldelta.error.test {args[0]}")

    def on_player_message(self, player: str, msg: str):
        if player == self.game_ctrl.bot_name and msg.startswith("tooldelta.error.test "):
            raise AssertionError(msg.removeprefix("tooldelta.error.test "))

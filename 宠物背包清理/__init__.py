from tooldelta import Plugin, plugins, Config, Print


@plugins.add_plugin
class NewPlugin(Plugin):
    name = "宠物背包清理"
    author = "猫七街"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)

        self._default_cfg = {"提示词": "清理背包"}

        self._std_cfg = {"提示词": str}

        try:
            self._cfg, _ = Config.get_plugin_config_and_version(
                self.name, self._std_cfg, self._default_cfg, self.version
            )
        except Exception as e:
            Print.print_err(f"加载配置文件出错: {e}")
            self._cfg = self._default_cfg.copy()

    def on_player_message(self, player_name: str, msg: str):
        if msg == self._cfg["提示词"]:
            self.game_ctrl.sendwscmd(f"/a {player_name}")

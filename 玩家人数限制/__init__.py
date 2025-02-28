from tooldelta import Plugin, plugins, Config, game_utils


@plugins.add_plugin
class NewPlugin(Plugin):
    name = "玩家人数限制"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        CFG = {"最大人数限制": 20}
        cfg, _ = Config.get_plugin_config_and_version(
            self.name, Config.auto_to_std(CFG), CFG, self.version
        )
        self.maxinum_player = cfg["最大人数限制"]

    def on_player_join(self, playername: str):
        if len(
            self.game_ctrl.allplayers
        ) > self.maxinum_player and not game_utils.is_op(playername):
            self.game_ctrl.sendwocmd(f'kick "{playername}" 已达到租赁服最大人数限制')

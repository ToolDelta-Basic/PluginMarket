from tooldelta import Plugin, cfg as config, game_utils, Player, plugin_entry


class NewPlugin(Plugin):
    name = "玩家人数限制"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        CFG = {"最大人数限制": 20}
        cfg, _ = config.get_plugin_config_and_version(
            self.name, config.auto_to_std(CFG), CFG, self.version
        )
        self.maxinum_player = cfg["最大人数限制"]
        self.ListenPlayerJoin(self.on_player_join)

    def on_player_join(self, player: Player):
        playername = player.name
        xuid = player.xuid
        if len(
            self.game_ctrl.allplayers
        ) > self.maxinum_player and not game_utils.is_op(playername):
            self.game_ctrl.sendwocmd(f"kick {xuid} 已达到租赁服最大人数限制")


entry = plugin_entry(NewPlugin)

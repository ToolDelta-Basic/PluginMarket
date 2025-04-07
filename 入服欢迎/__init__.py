import time
from tooldelta import ToolDelta, cfg as config, utils, Player, Plugin, plugin_entry


class JoinWelcome(Plugin):
    name = "入服欢迎"
    author = "wling"
    version = (0, 0, 4)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        STD_BAN_CFG = {
            "登出时发送指令": list,
            "登录时发送指令": list,
            "登录时延迟发送": int,
        }
        DEFAULT_BAN_CFG: dict[str, list[str] | int] = {
            "登出时发送指令": [
                """/tellraw @a {\"rawtext\":[{\"text\":\"§a§lBye~ @[target_player]\"}]}"""
            ],
            "登录时发送指令": [
                """/tellraw [target_player] {\"rawtext\":[{\"text\":\"§a您可以使用在聊天栏发送 §b.help §a以调出系统面板§f.\"}]}"""
            ],
            "登录时延迟发送": 10,
        }
        self.cfg, _ = config.get_plugin_config_and_version(
            self.name,
            STD_BAN_CFG,
            DEFAULT_BAN_CFG,
            self.version,
        )
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)

    @utils.thread_func("入服欢迎")
    def on_player_join(self, player: Player) -> None:
        time.sleep(self.cfg["登录时延迟发送"])
        for i in self.cfg["登录时发送指令"]:
            self.game_ctrl.sendwocmd(i.replace("[target_player]", player.name))

    def on_player_leave(self, player: Player) -> None:
        for i in self.cfg["登出时发送指令"]:
            self.game_ctrl.sendwocmd(i.replace("[target_player]", player.name))


entry = plugin_entry(JoinWelcome)

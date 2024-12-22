from tooldelta import Frame, Plugin, Config, Print, Builtins, plugins, Utils, game_utils
import os
import time
import random


@plugins.add_plugin
class kill(Plugin):
    version = (0, 0, 1)
    name = "违规名称踢出"
    author = "大庆油田"
    description = "简单的违规名称踢出"

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.make_data_path()
        CFG_DEFAULT = {"踢出词": [], "原因": ""}
        self.cfg, _ = Config.get_plugin_config_and_version(
            self.name, {}, CFG_DEFAULT, self.version
        )
        self.ci = self.cfg["踢出词"]
        self.yy = self.cfg["原因"]

    @Utils.thread_func("踢出违禁词玩家")
    def killpl(self, player: str):
        for a in self.ci:
            if a in player:
                self.game_ctrl.sendcmd_with_resp(f"/kick {player} {self.yy}")

    def on_player_message(self, player: str, _):
        self.killpl(player)

    def on_player_join(self, player: str):
        self.killpl(player)

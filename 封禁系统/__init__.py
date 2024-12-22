import os
import time
from datetime import datetime
from typing import ClassVar

from tooldelta import Utils, Config, Frame, Plugin, Print, plugins


@plugins.add_plugin_as_api("封禁系统")
class BanSystem(Plugin):
    name = "封禁系统"
    author = "SuperScript"
    version = (0, 0, 5)
    description = "便捷美观地封禁玩家, 同时也是一个前置插件"
    BAN_DATA_DEFAULT: ClassVar[dict[str, str | float]] = {"BanTo": 0, "Reason": ""}

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.tmpjson = Utils.TMPJson
        STD_BAN_CFG = {"踢出玩家提示格式": str, "玩家被封禁的广播提示": str}
        DEFAULT_BAN_CFG = {
            "踢出玩家提示格式": "§c你因为 [ban原因]\n被系统封禁至 §6[日期时间]",
            "玩家被封禁的广播提示": "§6WARNING: §c[玩家名] 因为[ban原因] 被系统封禁至 §6[日期时间]",
        }
        self.cfg, _ = Config.getPluginConfigAndVersion(
            self.name, STD_BAN_CFG, DEFAULT_BAN_CFG, self.version
        )

    def on_def(self):
        self.chatbar = plugins.get_plugin_api("聊天栏菜单", (0, 0, 1))

    def on_inject(self):
        self.chatbar.add_trigger(
            ["ban", "封禁"],
            "[玩家名:可粗略] [原因, 不填为未知原因]",
            "封禁玩家",
            self.ban_who,
            lambda x: x in (1, 2),
            True,
        )
        for i in self.game_ctrl.allplayers:
            self.test_ban(i)

    # -------------- API --------------
    def ban(self, player: str, ban_to_time_ticks: float, reason: str = ""):
        """
        封禁玩家.
            player: 需要ban的玩家
            ban_to_time_ticks: 将其封禁直到(时间戳, 和time.time()一样)
            reason: 原因
        """
        ban_datas = self.BAN_DATA_DEFAULT.copy()
        ban_datas["BanTo"] = ban_to_time_ticks
        ban_datas["Reason"] = reason
        self.rec_ban_data(player, ban_datas)
        if player in self.game_ctrl.allplayers:
            self.test_ban(player)

    def unban(self, player: str):
        """
        解封玩家.
            player: 玩家名
        """
        self.del_ban_data(player)

    # ----------------------------------

    @Utils.thread_func
    def on_player_join(self, player: str):
        self.test_ban(player)

    def ban_who(self, caller: str, args: list[str]):
        target = args[0]
        if len(args) == 1:
            banto_time = -1
            reason = ""
        else:
            reason = args[0]
        all_matches = Utils.fuzzy_match(self.game_ctrl.allplayers, target)
        if all_matches == []:
            self.game_ctrl.say_to(
                caller, f"§c封禁系统: 无匹配名字关键词的玩家: {target}"
            )
        elif len(all_matches) > 1:
            self.game_ctrl.say_to(
                caller,
                f"§c封禁系统: 匹配到多个玩家符合要求: {', '.join(all_matches)}, 需要输入更详细一点",
            )
        else:
            self.ban(all_matches[0], banto_time, reason)
            self.game_ctrl.say_to(caller, "§c封禁系统: §f设置封禁成功.")

    def test_ban(self, player):
        ban_data = self.get_ban_data(player)
        ban_to, reason = ban_data["BanTo"], ban_data["Reason"]
        if ban_to > time.time():
            Print.print_inf(
                f"封禁系统: {player} 被封禁至 {datetime.fromtimestamp(ban_to)}"
            )
            self.game_ctrl.sendwocmd(
                f"/kick {player} {self.format_msg(player, ban_to, reason, '踢出玩家提示格式')}"
            )
            self.game_ctrl.say_to(
                "@a", self.format_msg(player, ban_to, reason, "玩家被封禁的广播提示")
            )
            # 防止出现敏感词封禁原因的指令
            self.game_ctrl.sendwocmd(f"/kick {player}")

    def format_bantime(self, banto_time: int):
        if banto_time == -1:
            return "永久"
        else:
            struct_time = time.localtime(banto_time)
            date_show = time.strftime("%Y年 %m月 %d日", struct_time)
            time_show = time.strftime("%H : %M : %S", struct_time)
        return date_show + "  " + time_show

    def format_msg(self, player: str, ban_to_sec: int, ban_reason: str, cfg_key: str):
        fmt_time = self.format_bantime(ban_to_sec)
        Print.print_inf(
            f"封禁系统使用的 当前时间: §6{datetime.fromtimestamp(time.time())}"
        )
        return Utils.SimpleFmt(
            {
                "[日期时间]": fmt_time,
                "[玩家名]": player,
                "[ban原因]": ban_reason or "未知",
            },
            self.cfg[cfg_key],
        )

    def rec_ban_data(self, player: str, data):
        Utils.JsonIO.writeFileTo(self.name, player + ".json", data)

    def del_ban_data(self, player: str):
        p = os.path.join(self.data_path, player + ".json")
        if os.path.isfile(os.path.isfile(p)):
            os.remove(p)

    def get_ban_data(self, player: str) -> dict:
        return Utils.JsonIO.readFileFrom(self.name, player + ".json", self.BAN_DATA_DEFAULT)

import os
import time
from datetime import datetime
from typing import ClassVar

from tooldelta import (
    utils,
    cfg,
    constants,
    Player,
    Plugin,
    fmts,
    game_utils,
    TYPE_CHECKING,
    Player,
    plugin_entry,
)


class BanSystem(Plugin):
    name = "封禁系统"
    author = "SuperScript"
    version = (0, 0, 11)
    description = "便捷美观地封禁玩家, 同时也是一个前置插件"
    BAN_DATA_DEFAULT: ClassVar[dict[str, str | float]] = {"BanTo": 0, "Reason": ""}

    def __init__(self, frame):
        super().__init__(frame)
        self.tmpjson = utils.tempjson
        STD_BAN_CFG = {"踢出玩家提示格式": str, "玩家被封禁的广播提示": str}
        DEFAULT_BAN_CFG = {
            "踢出玩家提示格式": "§c你因为 [ban原因]\n被系统封禁至 §6[日期时间]",
            "玩家被封禁的广播提示": "§6WARNING: §c[玩家名] 因为[ban原因] 被系统封禁至 §6[日期时间]",
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, STD_BAN_CFG, DEFAULT_BAN_CFG, self.version
        )
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPacket(constants.PacketIDS.PlayerList, self.on_packet_playerlist)

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单", (0, 0, 1))
        self.xuidm = self.GetPluginAPI("XUID获取")
        self.qqlink = self.GetPluginAPI("群服互通", force=False)
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu
            from 前置_玩家XUID获取 import XUIDGetter
            from 群服互通云链版 import QQLinker

            self.chatbar: ChatbarMenu
            self.xuidm: XUIDGetter
            self.qqlink: QQLinker

    def on_inject(self):
        self.chatbar.add_new_trigger(
            ["ban", "封禁"],
            [],
            "封禁玩家",
            self.on_chatbar_ban,
            True,
        )
        for i in self.game_ctrl.allplayers:
            self.test_ban(i)
        self.frame.add_console_cmd_trigger(
            ["ban", "封禁"], None, "封禁玩家", self.on_console_ban
        )
        self.frame.add_console_cmd_trigger(
            ["unban", "解封"], None, "解封玩家", self.on_console_unban
        )
        self.frame.add_console_cmd_trigger(
            ["offban", "离线封禁"], None, "离线封禁玩家", self.on_console_ban_offline
        )
        if self.qqlink:
            self.qqlink.add_trigger(
                ["ban", "封禁"],
                "[玩家名] [封禁时间(秒数)] [原因]",
                "封禁玩家",
                self.on_qq_ban,
                lambda x: x in (1, 2, 3),
                True,
            )
            self.qqlink.add_trigger(
                ["unban", "解封"],
                None,
                "解封玩家",
                self.on_qq_unban,
                op_only=True,
            )

    # -------------- API --------------
    def ban(self, playername: str, ban_time: float, reason: str = ""):
        """
        封禁玩家.
            player: 需要ban的玩家
            ban_to_time_ticks: 将其封禁直到(时间戳, 和time.time()一样)
            reason: 原因
        """
        ban_datas = self.BAN_DATA_DEFAULT.copy()
        if ban_time != -1:
            ban_datas["BanTo"] = time.time() + ban_time
        else:
            ban_datas["BanTo"] = -1
        ban_datas["Reason"] = reason
        self.rec_ban_data(playername, ban_datas)
        if playername in self.game_ctrl.allplayers:
            self.test_ban(playername)

    def unban(self, player: str):
        """
        解封玩家.
            player: 玩家名
        """
        self.del_ban_data(player)

    # ----------------------------------
    def on_packet_playerlist(self, pk: dict):
        is_joining = not pk["ActionType"]
        if is_joining:
            for entry_user in pk["Entries"]:
                username = entry_user["Username"]
                xuid = entry_user["XUID"]
                self.test_ban_core(username, xuid)
        return False

    @utils.thread_func("封禁系统测试 ban")
    def on_player_join(self, playerf: Player):
        player = playerf.name
        xuid = playerf.xuid
        self.test_ban_core(player, xuid)

    def on_console_ban(self, _):
        allplayers = self.game_ctrl.allplayers.copy()
        fmts.print_inf("选择一个玩家进行封禁：")
        for i, j in enumerate(allplayers):
            fmts.print_inf(f"{i + 1}: {j}")
        resp = utils.try_int(input(fmts.fmt_info("请输入序号：")))
        if resp and resp in range(1, len(allplayers) + 1):
            ban_player = allplayers[resp - 1]
            reason = input(fmts.fmt_info("请输入封禁理由：")) or "未知"
            self.ban(ban_player, -1, reason)
            fmts.print_suc(f"封禁成功: 已封禁 {ban_player}")
        else:
            fmts.print_err("输入有误")

    def on_console_unban(self, _):
        all_ban_player_xuids = os.listdir(self.data_path)
        all_ban_playernames: list[tuple[str, str]] = []
        for i in all_ban_player_xuids:
            xuid = i.replace(".json", "")
            try:
                all_ban_playernames.append(
                    (self.xuidm.get_name_by_xuid(xuid, allow_offline=True), xuid)
                )
            except ValueError:
                continue
        if all_ban_playernames == []:
            fmts.print_inf("没有封禁的玩家")
            return
        fmts.print_inf("选择一个玩家进行解封：")
        for i, (name, xuid) in enumerate(all_ban_playernames):
            fmts.print_inf(f"{i + 1}: {name}")
        resp = utils.try_int(input(fmts.fmt_info("请输入序号：")))
        if resp and resp in range(1, len(all_ban_playernames) + 1):
            unban_player = all_ban_playernames[resp - 1][0]
            self.del_ban_data(all_ban_playernames[resp - 1][0])
            fmts.print_suc(f"解封成功: 已解封 {unban_player}")
        else:
            fmts.print_err("输入有误")

    def on_console_ban_offline(self, _):
        name_part = input(fmts.fmt_info("请输入玩家名或部分玩家名: ")).strip()
        if name_part == "":
            fmts.print_err("输入不能为空")
            return
        players_xuids = utils.tempjson.load_and_read(
            self.xuidm.format_data_path("xuids.json")
        )
        matched_names_and_uuids: list[tuple[str, str]] = []
        for xuid, name in players_xuids.items():
            if name_part in name:
                matched_names_and_uuids.append((name, xuid))
        matched_names_and_uuids.sort(key=lambda x: x[0].count(name_part))
        fmts.print_inf("找到以下匹配的玩家名：")
        for i, (name, _) in enumerate(matched_names_and_uuids):
            fmts.print_inf(
                f" {i + 1}. {name.replace(name_part, '§b' + name_part + '§r')}"
            )
        resp = utils.try_int(input(fmts.fmt_info("请输入序号：")))
        if resp is None or resp not in range(1, len(matched_names_and_uuids) + 1):
            fmts.print_err("输入有误")
            return
        target, xuid = matched_names_and_uuids[resp - 1]
        ban_seconds = utils.try_int(
            input(fmts.fmt_info("请输入封禁时间(秒, 默认为永久)：") or "-1")
        )
        if ban_seconds is None or (ban_seconds < 0 and ban_seconds != -1):
            fmts.print_err("不合法的封禁时间")
            return
        reason = input(fmts.fmt_info("请输入封禁原因:")).strip() or "未知"
        self.ban(target, ban_seconds, reason)
        fmts.print_suc(
            f"封禁 {target} 成功, 封禁了 {self.format_date_zhcn(ban_seconds)}"
        )

    def on_qq_ban(self, qqid: int, args: list[str]):
        utils.fill_list_index(args, ["", "永久", "未知"])
        ban_who, ban_time, reason = args
        if ban_who not in self.game_ctrl.allplayers:
            self.qqlink.sendmsg(self.qqlink.linked_group, "此玩家不在线..")
            return
        if ban_time == "永久":
            ban_time = -1
        elif (ban_time := utils.try_int(ban_time)) is None or ban_time <= 0:
            self.qqlink.sendmsg(self.qqlink.linked_group, "封禁时间不正确..")
            return
        self.ban(ban_who, ban_time, reason)
        if ban_time > 0:
            self.qqlink.sendmsg(
                self.qqlink.linked_group,
                f"[CQ:at,qq={qqid}] 封禁 {ban_who} 成功， 封禁了 {self.format_date_zhcn(ban_time)}",
            )
        else:
            self.qqlink.sendmsg(
                self.qqlink.linked_group,
                f"[CQ:at,qq={qqid}] 封禁 {ban_who} 成功， 封禁至永久",
            )

    def on_qq_unban(self, qqid: int, _):
        all_ban_player_xuids = os.listdir(self.data_path)
        all_ban_playernames: list[tuple[str, str]] = []
        for i in all_ban_player_xuids:
            xuid = i.replace(".json", "")
            try:
                all_ban_playernames.append(
                    (self.xuidm.get_name_by_xuid(xuid, allow_offline=True), xuid)
                )
            except ValueError:
                continue
        if all_ban_playernames == []:
            self.qqlink.sendmsg(self.qqlink.linked_group, "没有封禁的玩家")
            return
        output_msg = "选择一个玩家进行解封："
        for i, (name, xuid) in enumerate(all_ban_playernames):
            output_msg += f"\n  {i + 1}: {name}"
        self.qqlink.sendmsg(self.qqlink.linked_group, output_msg + "\n请输入序号：")
        resp = utils.try_int(self.qqlink.waitMsg(qqid))
        if resp and resp in range(1, len(all_ban_playernames) + 1):
            unban_player = all_ban_playernames[resp - 1][0]
            self.del_ban_data(all_ban_playernames[resp - 1][0])
            self.qqlink.sendmsg(
                self.qqlink.linked_group, f"解封成功: 已解封 {unban_player}"
            )
        else:
            self.qqlink.sendmsg(self.qqlink.linked_group, "输入有误")

    def on_chatbar_ban(self, caller: Player, _):
        allplayers = self.game_ctrl.allplayers.copy()
        caller.show("§6选择一个玩家进行封禁：")
        for i, j in enumerate(allplayers):
            caller.show(f"{i + 1}: {j}")
        caller.show("§6请输入序号：")
        resp = utils.try_int(caller.input())
        if resp and resp in range(1, len(allplayers) + 1):
            ban_player = allplayers[resp - 1]
            if caller == ban_player:
                caller.show("§6看起来你不能封禁自己..")
                return
            self.ban(allplayers[resp - 1], -1)
            fmts.print_suc(f"封禁成功: 已封禁 {ban_player}")
        else:
            fmts.print_err("输入有误")

    # for compatibility
    def test_ban(self, playername: str):
        xuid = self.xuidm.get_xuid_by_name(playername, allow_offline=True)
        self.test_ban_core(playername, xuid)

    def test_ban_core(self, playername: str, xuid: str):
        ban_data = self.get_ban_data_from_xuid(xuid)
        ban_to, reason = ban_data["BanTo"], ban_data["Reason"]
        if ban_to == -1 or ban_to > time.time():
            fmts.print_inf(
                f"封禁系统: {playername} 被封禁至 {datetime.fromtimestamp(ban_to) if ban_to > 0 else '永久'}"
            )
            self.print(
                f"-> kick {playername} {self.format_msg(playername, ban_to, reason, '踢出玩家提示格式')}"
            )
            self.game_ctrl.sendwocmd(
                f"kick {xuid} {self.format_msg(playername, ban_to, reason, '踢出玩家提示格式')}"
            )
            self.game_ctrl.say_to(
                "@a",
                self.format_msg(playername, ban_to, reason, "玩家被封禁的广播提示"),
            )

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
        return utils.simple_fmt(
            {
                "[日期时间]": fmt_time,
                "[玩家名]": player,
                "[ban原因]": ban_reason or "未知",
            },
            self.cfg[cfg_key],
        )

    def rec_ban_data(self, player: str, data):
        utils.tempjson.load_and_write(
            path := self.format_data_path(
                self.xuidm.get_xuid_by_name(player, allow_offline=True) + ".json"
            ),
            data,
            need_file_exists=False,
        )
        utils.tempjson.flush(path)

    def del_ban_data(self, player: str):
        p = self.format_data_path(
            self.xuidm.get_xuid_by_name(player, allow_offline=True) + ".json"
        )
        if os.path.isfile(p):
            os.remove(p)

    # for compatibility
    def get_ban_data(self, player: str) -> dict:
        fname = self.xuidm.get_xuid_by_name(player, allow_offline=True)
        return self.get_ban_data_from_xuid(fname)

    def get_ban_data_from_xuid(self, xuid: str) -> dict:
        if os.path.isfile(self.format_data_path(f"{xuid}.json")):
            return utils.safe_json.read_from_plugin(
                self.name,
                xuid,
                default=self.BAN_DATA_DEFAULT,
            )
        else:
            return self.BAN_DATA_DEFAULT

    @staticmethod
    def format_date_zhcn(seconds: int):
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            return f"{seconds // 60}分钟{seconds % 60}秒"
        elif seconds < 86400:
            return f"{seconds // 3600}小时{seconds % 3600 // 60}分钟{seconds % 60}秒"
        else:
            return f"{seconds // 86400}天{seconds % 86400 // 3600}小时{seconds % 3600 // 60}分钟{seconds % 60}秒"


entry = plugin_entry(BanSystem, "封禁系统")

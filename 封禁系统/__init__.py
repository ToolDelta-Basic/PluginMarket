import os
import time
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal

from tooldelta import (
    utils,
    cfg,
    constants,
    Plugin,
    fmts,
    TYPE_CHECKING,
    Player,
    plugin_entry,
)


@dataclass
class BanData:
    playername: str
    xuid: str | None
    device_id: str | None
    ban_to: int | Literal[-1]
    reason: str

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            playername=data["playername"],
            xuid=data["xuid"],
            device_id=data.get("device_id"),
            ban_to=data["ban_to"],
            reason=data["reason"],
        )

    def to_dict(self):
        return {
            "playername": self.playername,
            "xuid": self.xuid,
            "device_id": self.device_id,
            "ban_to": self.ban_to,
            "reason": self.reason,
        }

    def in_ban(self):
        if self.ban_to == -1:
            return True
        else:
            return self.ban_to > time.time()

    def __lt__(self, other: "BanData"):
        if self.ban_to == -1:
            return False
        return self.ban_to < other.ban_to

    def __gt__(self, other: "BanData"):
        if self.ban_to == -1:
            return True
        return self.ban_to > other.ban_to


class BanSystem(Plugin):
    name = "封禁系统"
    author = "SuperScript"
    version = (1, 0, 6)
    description = "便捷美观地封禁玩家, 同时也是一个前置插件"

    def __init__(self, frame):
        super().__init__(frame)
        STD_BAN_CFG = {"踢出玩家提示格式": str, "玩家被封禁的广播提示": str}
        DEFAULT_BAN_CFG = {
            "踢出玩家提示格式": "§c你因为 [ban原因]\n被系统封禁至 §6[日期时间]",
            "玩家被封禁的广播提示": "§6WARNING: §c[玩家名] 因为[ban原因] 被系统封禁至 §6[日期时间]",
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, STD_BAN_CFG, DEFAULT_BAN_CFG, self.version
        )
        self.ban_player_data_db = self.data_path / "players_data.json"
        self.ban_datas_path = self.data_path / "封禁数据"
        os.makedirs(self.ban_datas_path, exist_ok=True)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPacket(constants.PacketIDS.PlayerList, self.on_preban)

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单", (0, 0, 1))
        self.xuidm = self.GetPluginAPI("XUID获取")
        self.qqlink = self.GetPluginAPI("群服互通", force=False)
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu
            from 前置_玩家XUID获取 import XUIDGetter
            from 群服互通云链版 import QQLinker  # type: ignore

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
        for player in self.game_ctrl.players:
            self.test_ban(player)
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
    def ban(
        self,
        player_or_name: Player | str,
        ban_time: int | Literal[-1],
        reason: str = "",
    ):
        """
        封禁玩家。

        Args:
            player_or_name (Player | str): 玩家对象 ~~或玩家名 (玩家名已被弃用)~~
            ban_time (int | Literal[-1]): 封禁多久, 秒数 (而不是到多久)
            reason (str, optional): 封禁原因, Defaults to "".
        """
        ban_to = int(time.time() + ban_time) if ban_time != -1 else -1
        if isinstance(player_or_name, Player):
            ban_data = BanData(
                player_or_name.name,
                player_or_name.xuid,
                player_or_name.device_id,
                ban_to,
                reason,
            )
            self.ban_player(player_or_name, ban_data)
        else:
            ban_data = BanData(player_or_name, None, None, ban_to, reason)
            self.ban_player_by_name(player_or_name, ban_data)

    def unban(self, player_or_name: Player | str):
        """
        解封玩家.
            player: 玩家名
        """
        if isinstance(player_or_name, Player):
            self.del_ban_data(player_or_name.xuid)
        else:
            try:
                xuid = self.xuidm.get_xuid_by_name(player_or_name)
                self.del_ban_data(xuid)
            except ValueError:
                self.del_ban_data(self.generate_virtual_xuid(player_or_name))

    # ----------------------------------
    def on_preban(self, pk: dict):
        is_joining = not pk["ActionType"]
        if is_joining:
            for entry_user in pk["Entries"]:
                username = entry_user["Username"]
                xuid = entry_user["XUID"]
                self.test_ban_core(username, xuid)
        return False

    @utils.thread_func("封禁系统测试 ban")
    def on_player_join(self, player: Player):
        self.test_ban(player)

    def on_console_ban(self, _):
        allplayers = list(self.game_ctrl.players)
        fmts.print_inf("选择一个玩家进行封禁：")
        for i, j in enumerate(allplayers):
            fmts.print_inf(f"{i + 1}: {j.name}")
        resp = utils.try_int(input(fmts.fmt_info("请输入序号：")))
        if resp is None or resp not in range(1, len(allplayers) + 1):
            fmts.print_err("输入有误")
            return
        ban_player = allplayers[resp - 1]
        ban_seconds = utils.try_int(
            input(fmts.fmt_info("请输入封禁时间(秒, 默认为永久)：")) or "-1"
        )
        if ban_seconds is None or (ban_seconds < 0 and ban_seconds != -1):
            fmts.print_err("不合法的封禁时间")
            return
        reason = input(fmts.fmt_info("请输入封禁理由：")) or "未知"
        self.ban(ban_player, ban_seconds, reason)
        fmts.print_suc(f"封禁成功: 已封禁 {ban_player.name}")

    def on_console_unban(self, _):
        all_ban_player_xuids = [
            x.removesuffix(".json") for x in os.listdir(self.ban_datas_path)
        ]
        all_ban_playernames: list[tuple[str, str]] = []
        db_data = self.read_db()
        for name, xuid in db_data["name2xuid"].items():
            if xuid in all_ban_player_xuids:
                all_ban_playernames.append((name, xuid))
        if all_ban_playernames == []:
            fmts.print_inf("没有封禁的玩家")
            return
        fmts.print_inf("选择一个玩家进行解封：")
        for i, (name, xuid) in enumerate(all_ban_playernames):
            fmts.print_inf(f"{i + 1}: {name}")
        resp = utils.try_int(input(fmts.fmt_info("请输入序号：")))
        if resp and resp in range(1, len(all_ban_playernames) + 1):
            unban_player, unban_player_xuid = all_ban_playernames[resp - 1]
            self.del_ban_data(unban_player_xuid)
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
        if not matched_names_and_uuids:
            fmts.print_war("找不到匹配的玩家名")
            return
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
            input(fmts.fmt_info("请输入封禁时间(秒, 默认为永久)：")) or "-1"
        )
        if ban_seconds is None or (ban_seconds < 0 and ban_seconds != -1):
            fmts.print_err("不合法的封禁时间")
            return
        reason = input(fmts.fmt_info("请输入封禁原因:")).strip() or "未知"
        self.ban(target, ban_seconds, reason)
        fmts.print_suc(
            f"封禁 {target} 成功, 封禁了{self.format_date_zhcn(ban_seconds)}"
        )
        self.test_ban_core(target, xuid)

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
        allplayers = list(self.game_ctrl.players)
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
            fmts.print_suc(f"封禁成功: 已封禁 {ban_player.name}")
        else:
            fmts.print_err("输入有误")

    def ban_player(self, player: Player, ban_data: BanData):
        """
        封禁玩家。

        Args:
            player (Player): 玩家类
            ban_data (BanData): 封禁数据
        """
        record = self.get_ban_data(player.xuid)
        if record is not None:
            ban_data = max(record, ban_data)  # 取时间最久的封禁数据
        self.record_ban_data(ban_data)
        self.test_ban(player)

    def ban_player_by_name(self, playername: str, ban_data: BanData):
        """
        根据玩家名封禁玩家。

        :Deprecated: 此方法已弃用。
        :Warning: 在万不得已的情况下最好不要这样做，因为玩家可能会更改玩家名来规避封禁问题。

        Args:
            playername (str): 玩家名
            ban_data (BanData): 封禁数据
        """
        try:
            player_xuid = self.xuidm.get_xuid_by_name(playername, allow_offline=True)
            self.add_player_name_to_db(player_xuid, playername)
        except ValueError:
            player_xuid = self.generate_virtual_xuid(playername)
            self.print(f"§6玩家 XUID 不在数据库中, 生成虚拟 XUID {player_xuid}")
        record = self.get_ban_data(player_xuid)
        if record is not None:
            ban_data = max(record, ban_data)  # 取时间最久的封禁数据
        self.record_ban_data(ban_data)
        if player := self.game_ctrl.players.getPlayerByName(playername):
            self.test_ban(player)

    # for compatibility
    def test_ban(self, player: Player):
        self.test_ban_core(player.name, player.xuid)

    def test_ban_core(self, playername: str, xuid: str):
        ban_data = self.get_ban_data(xuid)
        if ban_data is None:
            # if xuid is virtual
            ban_data = self.get_ban_data(self.generate_virtual_xuid(playername))
            if ban_data is None:
                return
        ban_to = ban_data.ban_to
        ban_reason = ban_data.reason
        if ban_to == -1 or ban_to > time.time():
            format_time = datetime.fromtimestamp(ban_to) if ban_to > 0 else "永久"
            fmts.print_inf(
                f"封禁系统: {playername} 因为 {ban_reason} 被封禁至 {format_time}"
            )
            self.game_ctrl.sendwocmd(
                f"kick {xuid} {self.format_msg(playername, ban_to, ban_reason, '踢出玩家提示格式')}"
            )
            self.game_ctrl.say_to(
                "@a",
                self.format_msg(playername, ban_to, ban_reason, "玩家被封禁的广播提示"),
            )

    def get_ban_data(self, ban_xuid: str):
        path = self.ban_datas_path / f"{ban_xuid}.json"
        if not path.is_file():
            return None
        else:
            content = utils.tempjson.load_and_read(path)
            return BanData.from_dict(content)

    def record_ban_data(self, ban_data: BanData):
        ban_data_xuid = ban_data.xuid or self.generate_virtual_xuid(ban_data.playername)
        self.add_player_name_to_db(ban_data_xuid, ban_data.playername)
        path = self.ban_datas_path / f"{ban_data_xuid}.json"
        utils.tempjson.load_and_write(path, ban_data.to_dict(), need_file_exists=False)
        utils.tempjson.flush(path)

    def del_ban_data(self, ban_xuid: str):
        try:
            os.remove(self.ban_datas_path / (ban_xuid + ".json"))
        except Exception as err:
            self.print(f"§6无法移除 XUID 为 {ban_xuid} 的封禁数据: {err}")

    def add_player_device_id_to_db(self, xuid: str, deviceID: str):
        old = utils.tempjson.load_and_read(
            self.ban_player_data_db,
            need_file_exists=False,
            default={"name2xuid": {}, "deviceID2xuid": {}},
        )
        old["deviceID2xuid"][deviceID] = xuid
        utils.tempjson.load_and_write(self.ban_player_data_db, old)

    def read_db(self):
        return utils.tempjson.load_and_read(
            self.ban_player_data_db,
            need_file_exists=False,
            default={"name2xuid": {}, "deviceID2xuid": {}},
        )

    def add_player_name_to_db(self, xuid: str, playername: str):
        old = utils.tempjson.load_and_read(
            self.ban_player_data_db,
            need_file_exists=False,
            default={"name2xuid": {}, "deviceID2xuid": {}},
        )
        old["name2xuid"][playername] = xuid
        utils.tempjson.load_and_write(self.ban_player_data_db, old)
        utils.tempjson.flush(self.ban_player_data_db)

    def format_msg(
        self, playername: str, ban_to_sec: int, ban_reason: str, cfg_key: str
    ):
        fmt_time = self.format_bantime(ban_to_sec)
        return utils.simple_fmt(
            {
                "[日期时间]": fmt_time,
                "[玩家名]": playername,
                "[ban原因]": ban_reason or "未知",
            },
            self.cfg[cfg_key],
        )

    @staticmethod
    def format_date_zhcn(seconds: int):
        if seconds == -1:
            return "普朗克秒"
        elif seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            return f"{seconds // 60}分钟{seconds % 60}秒"
        elif seconds < 86400:
            return f"{seconds // 3600}小时{seconds % 3600 // 60}分钟{seconds % 60}秒"
        else:
            return f"{seconds // 86400}天{seconds % 86400 // 3600}小时{seconds % 3600 // 60}分钟{seconds % 60}秒"

    @staticmethod
    def generate_virtual_xuid(playername: str):
        return sha256(playername.encode()).hexdigest()

    @staticmethod
    def format_bantime(banto_time: int):
        if banto_time == -1:
            return "永久"
        else:
            struct_time = time.localtime(banto_time)
            date_show = time.strftime("%Y年 %m月 %d日", struct_time)
            time_show = time.strftime("%H：%M：%S", struct_time)
        return date_show + "  " + time_show


entry = plugin_entry(BanSystem, "封禁系统")

"""『Orion System 猎户座』插件核心功能"""

from tooldelta import utils, fmts, game_utils, TYPE_CHECKING
from tooldelta.constants import PacketIDS
from typing import NoReturn, Literal, Any
import time
import json
import re
import os
import requests
import random
import base64

from ban_utils import OrionUtils

# 仅类型检查用
if TYPE_CHECKING:
    from __init__ import Orion_System


class OrionCore:
    """插件核心功能"""

    def __init__(self, plugin: "Orion_System") -> None:
        """
        初始化插件核心功能
        Args:
            plugin: 插件实例
        """
        self.plugin = plugin
        self.cfg = plugin.config_mgr
        self.utils = plugin.utils
        self.data_path = plugin.data_path
        self.xuid_dir = self.cfg.xuid_dir
        self.device_id_dir = self.cfg.device_id_dir
        self.player_data_file = self.cfg.player_data_file
        self.lock_ban_xuid = plugin.lock_ban_xuid
        self.lock_ban_device_id = plugin.lock_ban_device_id
        self.sendwocmd = plugin.game_ctrl.sendwocmd
        self.sendwscmd = plugin.game_ctrl.sendwscmd

    def entry(self) -> None:
        """插件核心功能的入口，挂起PlayerList和Text的监听器，在插件加载时立即执行"""
        self.plugin.ListenPacket(PacketIDS.IDPlayerList, self.on_PlayerList)
        self.plugin.ListenPacket(PacketIDS.IDText, self.on_Text)
        self.create_timer()
        self.delete_invalid_ban_data()

    def active_entry(self) -> None:
        """插件核心功能的active入口，当机器人进入租赁服后才执行"""
        self.check_online_player()
        self.create_ListenScore()

    def create_timer(self) -> None:
        """创建发言周期检测计时器"""
        if self.cfg.speak_speed_limit or self.cfg.repeat_message_limit:
            self.message_data = {}
            self.timer()

    def create_ListenScore(self) -> None:
        """创建记分板监听器，用于根据记分板踢出玩家以及修改玩家能力权限"""
        if self.cfg.is_ban_api_in_game:
            self.sendwocmd(
                f'/scoreboard objectives add "{self.cfg.ban_scoreboard_name}" dummy "{self.cfg.ban_scoreboard_dummy_name}"'
            )
        if self.cfg.is_permission_mgr and self.cfg.is_change_permission_by_scoreboard:
            self.sendwocmd(
                f'/scoreboard objectives add "{self.cfg.permission_scoreboard_name}" dummy "{self.cfg.permission_scoreboard_dummy_name}"'
            )
        if self.cfg.is_ban_api_in_game or (
            self.cfg.is_permission_mgr and self.cfg.is_change_permission_by_scoreboard
        ):
            self.ListenScore()

    @utils.thread_func("发言周期检测计时器")
    def timer(self) -> NoReturn:
        """发言周期检测计时器线程"""
        while True:
            with self.plugin.lock_timer:
                # 此处设置list是为了创建遍历字典的副本，防止在字典内删除键值对触发RuntimeError: dictionary changed size during iteration报错
                for k, v in list(self.message_data.items()):
                    if v["timer"] > 0:
                        v["timer"] -= 1
                    else:
                        self.message_data.pop(k, None)
            time.sleep(1)

    def on_PlayerList(self, packet: dict[Any, Any]) -> Literal[False]:
        """
        监听到PlayerList后的回调，执行玩家进服的相关封禁
        Args:
            packet (dict[Any, Any]): 监听到的dict型PlayerList数据包
        """
        if packet["ActionType"] == 0:
            Username = packet["Entries"][0]["Username"]
            xuid = packet["Entries"][0]["XUID"]
            PremiumSkin = packet["Entries"][0]["Skin"]["PremiumSkin"]
            Trusted = packet["Entries"][0]["Skin"]["Trusted"]
            GeometryDataEngineVersion = packet["Entries"][0]["Skin"][
                "GeometryDataEngineVersion"
            ]
            PersonaSkin = packet["Entries"][0]["Skin"]["PersonaSkin"]
            SkinID = packet["Entries"][0]["Skin"]["SkinID"]
            SkinImageWidth = packet["Entries"][0]["Skin"]["SkinImageWidth"]
            SkinImageHeight = packet["Entries"][0]["Skin"]["SkinImageHeight"]
            CapeImageWidth = packet["Entries"][0]["Skin"]["CapeImageWidth"]
            CapeImageHeight = packet["Entries"][0]["Skin"]["CapeImageHeight"]
            CapeData = packet["Entries"][0]["Skin"]["CapeData"]
            Animations = packet["Entries"][0]["Skin"]["Animations"]
            AnimationData = packet["Entries"][0]["Skin"]["AnimationData"]
            SkinData = packet["Entries"][0]["Skin"]["SkinData"]
            GrowthLevels = packet["GrowthLevels"][0]

            self.get_player_device_id(Username, xuid, SkinID)

            if self.utils.in_whitelist(Username) is False:
                self.change_permission_when_PlayerList(Username)
                self.ban_bot(Username, xuid, PremiumSkin, Trusted, packet)
                self.ban_abnormal_skin(
                    Username,
                    xuid,
                    SkinImageWidth,
                    SkinImageHeight,
                    SkinData,
                    CapeImageWidth,
                    CapeImageHeight,
                    CapeData,
                    Animations,
                    AnimationData,
                    packet,
                )
                self.ban_Steve_or_Alex(
                    Username, xuid, SkinID, GeometryDataEngineVersion, PersonaSkin
                )
                self.ban_4D_skin(Username, xuid, GeometryDataEngineVersion)
                self.ban_player_level_too_low(Username, xuid, GrowthLevels)
                self.ban_player_with_netease_banned_word(Username, xuid)
                self.ban_player_with_self_banned_word(Username, xuid)
                self.check_player_info(Username, xuid, GrowthLevels, packet)
                self.ban_player_when_PlayerList_by_xuid(Username, xuid)

        return False

    def on_Text(self, packet: dict[Any, Any]) -> Literal[False]:
        """
        监听到Text后的回调，执行玩家发言的相关封禁
        Args:
            packet (dict[Any, Any]): 监听到的dict型Text数据包
        """
        # "TextType"=7:监听到对机器人的私聊(tell,msg,w命令)
        if packet["TextType"] == 7:
            try:
                message = packet["Message"]
                sourcename = packet["SourceName"]
                xuid = self.plugin.xuid_getter.get_xuid_by_name(sourcename, True)
                if (
                    self.cfg.ban_private_chat
                    and not self.cfg.allow_chat_with_bot
                    and self.utils.in_whitelist(sourcename) is False
                ):
                    self.execute_ban(
                        sourcename,
                        xuid,
                        self.cfg.ban_time_private_chat,
                        self.cfg.info_private_chat,
                        (sourcename, xuid, "7(私聊数据包)"),
                    )
                self.message_handle(message, sourcename, xuid)
            except Exception as error:
                fmts.print_inf(f"§c在解析私聊数据包时出现错误: {error}")

        # "TextType"=10:监听到命令执行反馈
        elif packet["TextType"] == 10 and packet["XUID"] != "":
            try:
                message = packet["Message"]
                try:
                    message_loads = json.loads(message)
                except json.JSONDecodeError:
                    message_loads = json.loads(OrionUtils.fix_json(message))
                rawtext_list = message_loads["rawtext"]
                translate_list = []
                for i in rawtext_list:
                    if "translate" in i.keys():
                        translate_list.append(i["translate"])
                original_player = translate_list[0]
                commands_type = translate_list[1]
                xuid = self.plugin.xuid_getter.get_xuid_by_name(original_player, True)
                # "commands.message.display.outgoing":监听到游戏内私聊(tell,msg,w命令)
                if commands_type == "commands.message.display.outgoing":
                    for i in rawtext_list:
                        if "with" in i.keys():
                            with_rawtext = i["with"]["rawtext"]
                            target_player = with_rawtext[0]["text"]
                            msg_text = with_rawtext[1]["text"]
                            break
                    if (
                        self.cfg.ban_private_chat
                        and self.utils.in_whitelist(original_player) is False
                    ):
                        if self.cfg.allow_chat_with_bot:
                            if target_player != self.plugin.game_ctrl.bot_name:
                                self.execute_ban(
                                    original_player,
                                    xuid,
                                    self.cfg.ban_time_private_chat,
                                    self.cfg.info_private_chat,
                                    (original_player, xuid, "10(全局命令执行反馈)"),
                                )
                        else:
                            self.execute_ban(
                                original_player,
                                xuid,
                                self.cfg.ban_time_private_chat,
                                self.cfg.info_private_chat,
                                (original_player, xuid, "10(全局命令执行反馈)"),
                            )
                    self.message_handle(msg_text, original_player, xuid)
            except Exception as error:
                fmts.print_inf(f"§c在解析私聊数据包或某些命令数据包时出现错误: {error}")

        # "TextType"=1:监听到常规发言或me命令
        elif packet["TextType"] == 1:
            try:
                message = packet["Message"]
                sourcename = packet["SourceName"]
                # 判断为me命令
                if message.startswith("*") and sourcename == "":
                    message_split = message.split(" ", 2)
                    player = message_split[1]
                    msg_text = message_split[2]
                    xuid = self.plugin.xuid_getter.get_xuid_by_name(player, True)
                    if (
                        self.cfg.ban_me_command
                        and self.utils.in_whitelist(player) is False
                    ):
                        self.execute_ban(
                            player,
                            xuid,
                            self.cfg.ban_time_me_command,
                            self.cfg.info_me_command,
                            (player, xuid),
                        )
                    self.message_handle(msg_text, player, xuid)
                # 判断为常规发言
                elif sourcename != "" and packet["XUID"] == "":
                    # 处理会员名称发言
                    vip_sourcename_match = re.search(r"<([^>]*)><([^>]*)>", sourcename)
                    if vip_sourcename_match:
                        sourcename = vip_sourcename_match.group(2)
                    xuid = self.plugin.xuid_getter.get_xuid_by_name(sourcename, True)
                    self.message_handle(message, sourcename, xuid)
            except Exception as error:
                fmts.print_inf(f"§c在解析发言数据包或me命令时出现错误 {error}")

        return False

    @utils.thread_func("处理文本相关封禁")
    def message_handle(self, message: str, name: str, xuid: str) -> None:
        """
        处理文本相关封禁，如发言黑名单词，长度限制，频率限制和重复消息刷屏限制
        Args:
             message (str): 发言文本
             name (str): 玩家名称
             xuid (str): 玩家xuid
        """
        if self.utils.in_whitelist(name) is False:
            self.blacklist_word_detect(message, name, xuid)
            self.message_length_detect(message, name, xuid)
            self.message_cache_area(message, name, xuid)

    @utils.thread_func("踢出玩家和写入封禁数据")
    def execute_ban(
        self,
        name: str,
        xuid: str,
        ban_time: int | str,
        infos: dict[str, str | list[str]],
        infos_args: tuple[Any] = (),
    ) -> None:
        """
        踢出玩家和写入封禁数据
        Args:
            name (str): 玩家名称
            xuid (str): 玩家xuid
            ban_time (int | str): 封禁时间(来源于插件配置)
                - 包括以下格式:
                - -1 : 永久封禁
                - 0 : 仅踢出，不写入封禁数据
                - 正整数 : 封禁对应秒
                - 字符串 (0年0月5日6时7分8秒) : 封禁对应时间
            infos (dict[str, str | list[str]]): kick时的提示信息(来源于插件配置)
                - 一般包括:
                - <控制台信息> 显示在面板上
                - <游戏内信息> 通过/tellraw命令根据填入的目标选择器在游戏内进行广播
                - <对玩家信息> 显示给被/kick的玩家
            infos_args (tuple[Any]): 提示信息format占位符的替换元组
                - 传入的infos将共享同一个infos_args元组，请合理设置format占位符中的数字索引，默认配置已经设置好了
                - 什么？你不知道python的str.format语法？:
                - 假设infos["控制台"]="发现 {0} (xuid:{1}) 等级低于服务器准入等级({2}级)，正在制裁"
                - 那么合理的infos_args应该为(player, xuid, server_level)，这会把上面的{}按顺序替换成infos_args里的元素
        """
        self.utils.print_inf(infos, infos_args)
        reason = OrionUtils.text_format(infos.get("玩家"), infos_args)
        self.utils.kick(name, reason)
        self.ban_player_by_xuid(
            name, xuid, OrionUtils.ban_time_format(ban_time), reason
        )
        self.ban_player_by_device_id(
            name, xuid, OrionUtils.ban_time_format(ban_time), reason
        )

    @utils.thread_func("只踢出玩家，不写入封禁数据")
    def execute_only_kick(
        self, name: str, infos: dict[str, str | list[str]], infos_args: tuple[Any] = ()
    ) -> None:
        """
        只踢出玩家，不写入封禁数据
        Args:
            name (str): 玩家名称
            infos (dict[str, str | list[str]]): kick时的提示信息(来源于插件配置)
                - 一般包括:
                - <控制台信息> 显示在面板上
                - <游戏内信息> 通过/tellraw命令根据填入的目标选择器在游戏内进行广播
                - <对玩家信息> 显示给被/kick的玩家
            infos_args (tuple[Any]): 提示信息format占位符的替换元组
                - 传入的infos将共享同一个infos_args元组，请合理设置format占位符中的数字索引，默认配置已经设置好了
        """
        self.utils.print_inf(infos, infos_args)
        reason = OrionUtils.text_format(infos.get("玩家"), infos_args)
        self.utils.kick(name, reason)

    @utils.thread_func("新增封禁数据,xuid判据")
    def ban_player_by_xuid(
        self,
        player: str,
        xuid: str,
        ban_time: int | Literal["Forever"],
        ban_reason: str,
    ) -> None:
        """
        新增封禁数据,xuid判据
        Args:
            player (str): 玩家名称
            xuid (str): 玩家xuid
            ban_time (int | Literal["Forever"]): 封禁时间(秒)或者永久封禁
            ban_reason (str): 封禁原因
        """
        if self.cfg.is_ban_player_by_xuid and ban_time != 0:
            path = f"{self.data_path}/{self.xuid_dir}/{xuid}.json"
            with self.lock_ban_xuid:
                ban_player_data = OrionUtils.disk_read(path)
                (timestamp_now, date_now) = OrionUtils.now()
                (timestamp_end, date_end) = OrionUtils.calculate_ban_end_time(
                    ban_player_data, ban_time, timestamp_now
                )
                if timestamp_end:
                    OrionUtils.disk_write(
                        path,
                        {
                            "xuid": xuid,
                            "name": player,
                            "ban_start_real_time": date_now,
                            "ban_start_timestamp": timestamp_now,
                            "ban_end_real_time": date_end,
                            "ban_end_timestamp": timestamp_end,
                            "ban_reason": ban_reason,
                        },
                    )

    @utils.thread_func("新增封禁数据,device_id判据")
    def ban_player_by_device_id(
        self,
        player: str,
        xuid: str,
        ban_time: int | Literal["Forever"],
        ban_reason: str,
    ) -> None:
        """
        新增封禁数据,device_id判据
        Args:
            player (str): 玩家名称
            xuid (str): 玩家xuid
            ban_time (int | Literal["Forever"]): 封禁时间(秒)或者永久封禁
            ban_reason (str): 封禁原因
        """
        if self.cfg.is_ban_player_by_device_id and ban_time != 0:
            path_device_id = f"{self.data_path}/{self.cfg.player_data_file}"
            with self.lock_ban_device_id:
                device_id_record = OrionUtils.disk_read(path_device_id)
            # 收集本账号登录过的全部设备号
            device_id_list = []
            for k, v in device_id_record.items():
                if xuid in v.keys():
                    device_id_list.append(k)
            if device_id_list == []:
                fmts.print_inf(
                    f"§6警告：玩家 {player} 没有设备号记录，不能通过设备号执行封禁"
                )
                return
            for device_id in device_id_list:
                path_ban_time = (
                    f"{self.data_path}/{self.device_id_dir}/{device_id}.json"
                )
                with self.lock_ban_device_id:
                    ban_player_data = OrionUtils.disk_read(path_ban_time)
                    (timestamp_now, date_now) = OrionUtils.now()
                    (timestamp_end, date_end) = OrionUtils.calculate_ban_end_time(
                        ban_player_data, ban_time, timestamp_now
                    )
                    if timestamp_end:
                        OrionUtils.disk_write(
                            path_ban_time,
                            {
                                "device_id": device_id,
                                "xuid_and_player": {xuid: [player]},
                                "ban_start_real_time": date_now,
                                "ban_start_timestamp": timestamp_now,
                                "ban_end_real_time": date_end,
                                "ban_end_timestamp": timestamp_end,
                                "ban_reason": ban_reason,
                            },
                        )

    @utils.thread_func("踢出新加入游戏的被封禁者,xuid判据")
    def ban_player_when_PlayerList_by_xuid(self, player: str, xuid: str) -> None:
        """
        踢出新加入游戏的被封禁者,xuid判据
        Args:
            player (str): 玩家名称
            xuid (str): 玩家xuid
        """
        infos = self.cfg.info_banned_player
        path = f"{self.data_path}/{self.xuid_dir}/{xuid}.json"
        try:
            with self.lock_ban_xuid:
                ban_data = OrionUtils.disk_read_need_exists(path)
            if ban_data is None or ban_data == {}:
                os.remove(path)
                return
            ban_end_timestamp = ban_data.get("ban_end_timestamp")
            ban_end_real_time = ban_data.get("ban_end_real_time")
            ban_reason = ban_data.get("ban_reason")
            args = (player, xuid, ban_end_real_time, ban_reason)
            if isinstance(ban_end_timestamp, int):
                timestamp_now = int(time.time())
                if ban_end_timestamp > timestamp_now:
                    self.execute_only_kick(player, infos, args)
                else:
                    self.utils.print_inf(
                        self.cfg.info_delete_expire_xuid, [player, xuid]
                    )
                    os.remove(path)
                    return
            elif ban_end_timestamp == "Forever":
                self.execute_only_kick(player, infos, args)
        except FileNotFoundError:
            return

    @utils.thread_func("踢出新加入游戏的被封禁者,device_id判据")
    def ban_player_when_PlayerList_by_device_id(
        self, player: str, xuid: str, device_id: str
    ) -> None:
        """
        踢出新加入游戏的被封禁者,device_id判据
        Args:
            player (str): 玩家名称
            xuid (str): 玩家xuid
            device_id (str): 玩家设备号
        """
        infos = self.cfg.info_banned_device_id
        path = f"{self.data_path}/{self.device_id_dir}/{device_id}.json"
        try:
            with self.lock_ban_device_id:
                ban_data = OrionUtils.disk_read_need_exists(path)
            if ban_data is None or ban_data == {}:
                os.remove(path)
                return
            ban_start_real_time = ban_data.get("ban_start_real_time")
            ban_start_timestamp = ban_data.get("ban_start_timestamp")
            ban_end_timestamp = ban_data.get("ban_end_timestamp")
            ban_end_real_time = ban_data.get("ban_end_real_time")
            ban_reason = ban_data.get("ban_reason")
            args = (device_id, player, ban_end_real_time, ban_reason)
            if isinstance(ban_end_timestamp, int):
                timestamp_now = int(time.time())
                if ban_end_timestamp > timestamp_now:
                    self.execute_only_kick(player, infos, args)
                    if self.cfg.jointly_ban_player:
                        self.jointly_ban_xuid(
                            player,
                            xuid,
                            ban_start_real_time,
                            ban_start_timestamp,
                            ban_end_real_time,
                            ban_end_timestamp,
                            ban_reason,
                        )
                else:
                    self.utils.print_inf(
                        self.cfg.info_delete_expire_device_id, [device_id]
                    )
                    os.remove(path)
                    return
            elif ban_end_timestamp == "Forever":
                self.execute_only_kick(player, infos, args)
                if self.cfg.jointly_ban_player:
                    self.jointly_ban_xuid(
                        player,
                        xuid,
                        ban_start_real_time,
                        ban_start_timestamp,
                        ban_end_real_time,
                        ban_end_timestamp,
                        ban_reason,
                    )
        except FileNotFoundError:
            return

    @utils.thread_func("转移封禁数据至xuid")
    def jointly_ban_xuid(
        self,
        player: str,
        xuid: str,
        start_t: str,
        start_ts: int,
        end_t: str,
        end_ts: int,
        reason: str,
    ) -> None:
        """
        当发现被封禁的设备号进入游戏时，将封禁数据同步转移至其xuid
        Args:
            player (str): 玩家名称
            xuid (str): 玩家xuid
            start_t (str): 封禁开始时间
            start_ts (int): 封禁开始时间戳
            end_t (str): 封禁结束时间
            end_ts (int): 封禁结束时间戳
            reason (str): 封禁原因
        """
        path = f"{self.data_path}/{self.xuid_dir}/{xuid}.json"
        with self.lock_ban_xuid:
            ban_data = OrionUtils.disk_read(path)
            # 处理逻辑：如果xuid原本就为永久封禁，或者封禁结束时间晚于设备号，则不转移相关数据
            if ban_data:
                original_end = ban_data.get("ban_end_timestamp")
                if original_end == "Forever":
                    return
                if isinstance(original_end, int) and original_end >= end_ts:
                    return
            OrionUtils.disk_write(
                path,
                {
                    "xuid": xuid,
                    "name": player,
                    "ban_start_real_time": start_t,
                    "ban_start_timestamp": start_ts,
                    "ban_end_real_time": end_t,
                    "ban_end_timestamp": end_ts,
                    "ban_reason": reason,
                },
            )

    @utils.thread_func("反制机器人函数")
    def ban_bot(
        self,
        Username: str,
        xuid: str,
        PremiumSkin: bool,
        Trusted: bool,
        packet: dict[Any, Any],
    ) -> None:
        """
        反制机器人函数
        Args:
            Username (str): 玩家名称
            xuid (str): 玩家xuid
            PremiumSkin (bool):
            Trusted (bool):
            packet (dict[Any, Any]): dict型数据包
        """
        if self.cfg.is_detect_bot and (PremiumSkin is False or Trusted is False):
            self.utils.print_inf(self.cfg.info_collapse_packet, [packet])
            self.execute_ban(
                Username,
                xuid,
                self.cfg.ban_time_detect_bot,
                self.cfg.info_detect_bot,
                (Username, xuid),
            )

    @utils.thread_func("反制锁服函数(皮肤数据异常检查)")
    def ban_abnormal_skin(
        self,
        Username: str,
        xuid: str,
        SkinImageWidth: int,
        SkinImageHeight: int,
        SkinData: str,
        CapeImageWidth: int,
        CapeImageHeight: int,
        CapeData: str,
        Animations: list[Any],
        AnimationData: str,
        packet: dict[Any, Any],
    ) -> None:
        """
        反制锁服函数(皮肤数据异常检查)
        Args:
            Username (str): 玩家名称
            xuid (str): 玩家xuid
            SkinImageWidth (int):
            SkinImageHeight (int):
            SkinData (str):
            CapeImageWidth (int):
            CapeImageHeight (int):
            CapeData (str):
            Animations (list[Any]):
            AnimationData (str):
            packet (dict[Any, Any]): dict型数据包
        """
        if self.cfg.is_detect_abnormal_skin:
            try:
                if isinstance(SkinData, str):
                    decode_skinData = base64.b64decode(SkinData)
                elif isinstance(SkinData, bytes):
                    decode_skinData = SkinData
                SkinData_bytes_len = len(decode_skinData)
                if len(Animations) == 1:
                    Animations_info = Animations[0]
                elif len(Animations) == 0:
                    Animations_info = {}
                AnimationsImageWidth = Animations_info.get("ImageWidth", 0)
                AnimationsImageHeight = Animations_info.get("ImageHeight", 0)
                AnimationsImageData = Animations_info.get("ImageData", "")
                if isinstance(AnimationsImageData, str):
                    decode_AnimationsImageData = base64.b64decode(AnimationsImageData)
                elif isinstance(AnimationsImageData, bytes):
                    decode_AnimationsImageData = AnimationsImageData
                AnimationsImageData_bytes_len = len(decode_AnimationsImageData)
                if (
                    (SkinImageWidth * SkinImageHeight * 4 != SkinData_bytes_len)
                    or (SkinImageWidth not in (64, 128, 256, 512))
                    or (SkinImageHeight not in (64, 128, 256, 512))
                    or (CapeImageWidth != 0)
                    or (CapeImageHeight != 0)
                    or (CapeData != "")
                    or (len(Animations) not in (0, 1))
                    or (
                        AnimationsImageWidth * AnimationsImageHeight * 4
                        != AnimationsImageData_bytes_len
                    )
                    or (AnimationsImageWidth not in (0, 32))
                    or (AnimationsImageHeight not in (0, 64))
                    or (AnimationData != "")
                ):
                    self.utils.print_inf(self.cfg.info_broken_packet, [packet])
                    self.execute_ban(
                        Username,
                        xuid,
                        self.cfg.ban_time_detect_abnormal_skin,
                        self.cfg.info_detect_abnormal_skin,
                        (Username, xuid),
                    )
            except Exception:
                self.utils.print_inf(self.cfg.info_broken_packet, [packet])
                self.execute_ban(
                    Username,
                    xuid,
                    self.cfg.ban_time_detect_abnormal_skin,
                    self.cfg.info_detect_abnormal_skin,
                    (Username, xuid),
                )

    @utils.thread_func("反制Steve/Alex皮肤函数")
    def ban_Steve_or_Alex(
        self,
        Username: str,
        xuid: str,
        SkinID: str,
        GeometryDataEngineVersion: str,
        PersonaSkin: bool,
    ) -> None:
        """
        反制Steve/Alex皮肤函数
        Args:
            Username (str): 玩家名称
            xuid (str): 玩家xuid
            SkinID (str):
            GeometryDataEngineVersion (str):
            PersonaSkin (bool):
        """
        if self.cfg.is_ban_Steve_or_Alex and (
            SkinID
            in (
                "c18e65aa-7b21-4637-9b63-8ad63622ef01.Steve",
                "c18e65aa-7b21-4637-9b63-8ad63622ef01.Alex",
            )
            # Base64 解码：MS4xNC4w → 1.14.0
            or GeometryDataEngineVersion in ("MS4xNC4w", "1.14.0")
            or PersonaSkin is True
        ):
            self.execute_ban(
                Username,
                xuid,
                self.cfg.ban_time_Steve_or_Alex,
                self.cfg.info_Steve_or_Alex,
                (Username, xuid),
            )

    @utils.thread_func("反制4D皮肤函数")
    def ban_4D_skin(
        self, Username: str, xuid: str, GeometryDataEngineVersion: str
    ) -> None:
        """
        反制4D皮肤函数
        Args:
            Username (str):玩家名称
            xuid (str): 玩家xuid
            GeometryDataEngineVersion (str):
        """
        # Base64 解码：MS4yLjU= → 1.2.5
        if self.cfg.is_ban_4D_skin and GeometryDataEngineVersion in (
            "MS4yLjU=",
            "1.2.5",
        ):
            self.execute_ban(
                Username,
                xuid,
                self.cfg.ban_time_4D_skin,
                self.cfg.info_4D_skin,
                (Username, xuid),
            )

    @utils.thread_func("反制等级过低玩家函数")
    def ban_player_level_too_low(
        self, Username: str, xuid: str, GrowthLevels: int
    ) -> None:
        """
        反制等级过低玩家函数
        Args:
            Username (str): 玩家名称
            xuid (str): 玩家xuid
            GrowthLevels (int):
        """
        if self.cfg.is_level_limit and GrowthLevels < self.cfg.server_level:
            self.execute_ban(
                Username,
                xuid,
                self.cfg.ban_time_level_limit,
                self.cfg.info_level_limit,
                (Username, xuid, GrowthLevels, self.cfg.server_level),
            )

    @utils.thread_func("反制网易屏蔽词名称玩家函数")
    def ban_player_with_netease_banned_word(self, Username: str, xuid: str) -> None:
        """
        反制网易屏蔽词名称玩家函数
        Args:
            Username (str): 玩家名称
            xuid (str): 玩家xuid
        """
        if self.cfg.is_detect_netease_banned_word:
            try:
                self.sendwscmd(
                    f'/testfor @a[name="{Username}"]',
                    True,
                    self.cfg.detect_netease_banned_word_timeout,
                )
            except TimeoutError:
                self.execute_ban(
                    Username,
                    xuid,
                    self.cfg.ban_time_detect_netease_banned_word,
                    self.cfg.info_detect_netease_banned_word,
                    (Username, xuid),
                )

    @utils.thread_func("反制自定义违禁词名称玩家函数")
    def ban_player_with_self_banned_word(self, Username: str, xuid: str) -> None:
        """
        反制自定义违禁词名称玩家函数
        Args:
            Username (str): 玩家名称
            xuid (str): 玩家xuid
        """
        if self.cfg.is_detect_self_banned_word:
            Username_U = Username
            if self.cfg.is_distinguish_upper_or_lower_in_self_banned_word is False:
                Username_U = Username.upper()
            banned_word_set = set(self.cfg.banned_word_list)
            n = len(Username_U)
            for i in range(n):
                for j in range(i + 1, n + 1):
                    if Username_U[i:j] in banned_word_set:
                        self.execute_ban(
                            Username,
                            xuid,
                            self.cfg.ban_time_detect_self_banned_word,
                            self.cfg.info_detect_self_banned_word,
                            (Username, xuid, Username[i:j]),
                        )

    @utils.thread_func("网易MC客户端玩家信息检查函数")
    def check_player_info(
        self, Username: str, xuid: str, GrowthLevels: int, packet: dict[Any, Any]
    ) -> None:
        """
        网易MC客户端玩家信息检查函数
        Args:
            Username (str): 玩家名称
            xuid (str): 玩家xuid
            GrowthLevels (int):
            packet (dict[Any, Any]): dict型数据包
        """
        if self.cfg.is_check_player_info:
            try_time = 0
            url = "http://api.tooldelta.top/api/mc"
            headers = {"Content-Type": "application/json"}
            payload = {"type": "getUserInfo", "data": {"name": Username}}
            while True:
                try:
                    userdata_from_netease = requests.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=self.cfg.check_player_info_api_timeout,
                    )
                    try_time += 1
                    if userdata_from_netease.status_code == 404:
                        result = self.check_player_info_fail(
                            Username,
                            xuid,
                            try_time,
                            f"HTTP状态码[{userdata_from_netease.status_code}]",
                        )
                        if result:
                            return

                    elif userdata_from_netease.status_code == 200:
                        userdata_from_netease = userdata_from_netease.json()
                        data = userdata_from_netease["data"]
                        self.utils.print_inf(
                            self.cfg.info_search_success,
                            [Username, data["lv"], GrowthLevels],
                        )
                        if (
                            self.cfg.is_ban_player_if_different_level
                            and data["lv"] != GrowthLevels
                        ):
                            self.utils.print_inf(
                                self.cfg.info_tamper_level_packet, [packet]
                            )
                            self.execute_ban(
                                Username,
                                xuid,
                                self.cfg.ban_time_if_different_level,
                                self.cfg.info_if_different_level,
                                (Username, xuid, data["lv"], GrowthLevels),
                            )
                        return

                    else:
                        return

                except requests.exceptions.Timeout as timeout_error:
                    try_time += 1
                    result = self.check_player_info_fail(
                        Username,
                        xuid,
                        try_time,
                        f"请求网易MC客户端玩家信息超时：{timeout_error}",
                    )
                    if result:
                        return

                except requests.exceptions.HTTPError as http_error:
                    fmts.print_inf(f"HTTP异常信息：{http_error}")
                    return

                except requests.exceptions.RequestException as error:
                    fmts.print_inf(
                        f"请求网易MC客户端玩家信息失败(API请求失败或玩家数据json解析失败)：{error}"
                    )
                    return

    def check_player_info_fail(
        self, name: str, xuid: str, try_time: int, error: Any
    ) -> bool:
        """
        网易MC客户端玩家信息检查失败处理
        Args:
            name (str): 玩家名称
            xuid (str): 玩家xuid
            try_time (int): API尝试次数
            error (Any): 报错信息
        Returns:
            is_finished (bool): 是否结束查询(即API尝试达到最大次数)
        """
        if try_time >= self.cfg.check_player_info_api_try_time:
            self.utils.print_inf(
                self.cfg.info_search_fail_1,
                [name, error, try_time, self.cfg.check_player_info_api_try_time],
            )
            if self.cfg.is_ban_player_if_cannot_search:
                self.execute_ban(
                    name,
                    xuid,
                    self.cfg.ban_time_if_cannot_search,
                    self.cfg.info_if_cannot_search,
                    (name, xuid),
                )
            return True
        try_api_sleep_time = random.randint(3 * try_time, 6 * try_time)
        self.utils.print_inf(
            self.cfg.info_search_fail_2,
            [
                name,
                error,
                try_time,
                self.cfg.check_player_info_api_try_time,
                try_api_sleep_time,
            ],
        )
        time.sleep(try_api_sleep_time)
        return False

    @utils.thread_func("发言黑名单词检测函数")
    def blacklist_word_detect(self, message: str, player: str, xuid: str) -> None:
        """
        发言黑名单词检测函数
        Args:
            message (str): 发言文本
            player (str): 玩家名称
            xuid (str): 玩家xuid
        """
        if self.cfg.testfor_blacklist_word:
            message = message.replace(" ", "")
            if self.cfg.is_remove_double_s:
                message = OrionUtils.remove_double_s(message)
            if self.cfg.is_distinguish_upper_or_lower_on_chat is False:
                message = message.upper()
            blacklist_word_set = set(self.cfg.blacklist_word_list)
            n = len(message)
            for i in range(n):
                for j in range(i + 1, n + 1):
                    if message[i:j] in blacklist_word_set:
                        self.execute_ban(
                            player,
                            xuid,
                            self.cfg.ban_time_testfor_blacklist_word,
                            self.cfg.info_testfor_blacklist_word,
                            (player, xuid, message[i:j]),
                        )

    @utils.thread_func("发言字数检测函数")
    def message_length_detect(self, message: str, player: str, xuid: str) -> None:
        """
        发言字数检测函数
        Args:
            message (str): 发言文本
            player (str): 玩家名称
            xuid (str): 玩家xuid
        """
        if self.cfg.message_length_limit and len(message) > self.cfg.max_speak_length:
            self.execute_ban(
                player,
                xuid,
                self.cfg.ban_time_message_length_limit,
                self.cfg.info_message_length_limit,
                (player, xuid, self.cfg.max_speak_length),
            )

    @utils.thread_func("缓存玩家发言数据函数")
    def message_cache_area(self, message: str, player: str, xuid: str) -> None:
        """
        缓存玩家发言数据函数
        Args:
            message (str): 发言文本
            player (str): 玩家名称
            xuid (str): 玩家xuid
        """
        if self.cfg.speak_speed_limit or self.cfg.repeat_message_limit:
            message = message.replace(" ", "")
            if self.cfg.is_remove_double_s:
                message = OrionUtils.remove_double_s(message)
            if self.cfg.is_distinguish_upper_or_lower_on_chat is False:
                message = message.upper()
            with self.plugin.lock_timer:
                if self.message_data.get(player) is None:
                    self.message_data[player] = {}
                    self.message_data[player]["message"] = []
                    self.message_data[player]["timer"] = self.cfg.speak_detection_cycle
                self.message_data[player]["message"].append(message)
                self.speak_speed_detect(player, xuid)
                self.repeat_message_detect(player, xuid)

    @utils.thread_func("发言频率检测函数")
    def speak_speed_detect(self, player: str, xuid: str) -> None:
        """
        发言频率检测函数
        Args:
            player (str): 玩家名称
            xuid (str): 玩家xuid
        """
        if (
            self.cfg.speak_speed_limit
            and len(self.message_data[player]["message"]) > self.cfg.max_speak_count
        ):
            self.execute_ban(
                player,
                xuid,
                self.cfg.ban_time_speak_speed_limit,
                self.cfg.info_speak_speed_limit,
                (
                    player,
                    xuid,
                    self.cfg.max_speak_count,
                    self.cfg.speak_detection_cycle,
                ),
            )

    @utils.thread_func("重复消息刷屏检测函数")
    def repeat_message_detect(self, player: str, xuid: str) -> None:
        """
        重复消息刷屏检测函数
        Args:
            player (str): 玩家名称
            xuid (str): 玩家xuid
        """
        if self.cfg.repeat_message_limit:
            counts = {}
            for i in self.message_data[player]["message"]:
                counts[i] = counts.get(i, 0) + 1
            for v in counts.values():
                if v > self.cfg.max_repeat_count:
                    self.execute_ban(
                        player,
                        xuid,
                        self.cfg.ban_time_repeat_message_limit,
                        self.cfg.info_repeat_message_limit,
                        (
                            player,
                            xuid,
                            self.cfg.max_repeat_count,
                            self.cfg.speak_detection_cycle,
                        ),
                    )

    @utils.thread_func("玩家设备号获取函数")
    def get_player_device_id(self, player: str, xuid: str, SkinID: str) -> None:
        """
        玩家设备号获取函数
        · 设备号获取包括：
          1. PlayerList数据包的SkinID字段(快速获取)
          2. AddPlayer数据包的DeviceID字段(慢速获取)
        Args:
            player (str): 玩家名称
            xuid (str): 玩家xuid
            SkinID (str):
        """
        if self.cfg.is_get_device_id:
            # 设备号快速获取方式：即PlayerList数据包的SkinID字段，但该获取方式存在限制，故必须辅以慢速获取方式的AddPlayer的DeviceID字段进行获取
            device_id_from_SkinID = None
            re_match = re.search(r"(?:CustomSlim|Custom)(.*)$", SkinID)
            if re_match:
                match_str = re_match.group(1)
                if len(match_str) == 32:
                    # 设备号为32位UUID，由于SkinID来源和AddPlayer来源的设备号大小写可能不同，统一替换成大写
                    device_id_from_SkinID = match_str.upper()
                    self.utils.print_inf(
                        self.cfg.info_quick_get_device_success,
                        [player, device_id_from_SkinID],
                    )
                    time.sleep(0.1)
                    # 快速获取主要是为了快速踢出，记录设备号时会优先选择慢速获取方式
                    if self.utils.in_whitelist(player) is False:
                        self.ban_player_when_PlayerList_by_device_id(
                            player, xuid, device_id_from_SkinID
                        )
            if device_id_from_SkinID is None:
                self.utils.print_inf(self.cfg.info_quick_get_device_fail, [player])
            # 设备号慢速获取方式：即AddPlayer数据包的DeviceID字段
            with self.plugin.lock_get_device_id:
                try_time = 0
                time.sleep(0.5)
                device_id = None
                while True:
                    if player not in self.plugin.game_ctrl.allplayers.copy():
                        self.utils.print_inf(
                            self.cfg.info_slow_get_device_fail_3, [player]
                        )
                        break
                    time.sleep(3.5)
                    self.sendwocmd(
                        f'/execute at @a[name="{player}"] run tp @a[name="{self.plugin.game_ctrl.bot_name}"] ~ 500 ~'
                    )
                    time.sleep(0.5)
                    player_obj = self.plugin.game_ctrl.players.getPlayerByXUID(xuid)
                    try_time += 1
                    if (
                        (player_obj is None)
                        or (player_obj and player_obj.device_id == "")
                        or (player_obj and player_obj.device_id is None)
                    ):
                        args = [player, try_time, self.cfg.record_device_id_try_time]
                        if try_time >= self.cfg.record_device_id_try_time:
                            self.utils.print_inf(
                                self.cfg.info_slow_get_device_fail_1, args
                            )
                            break
                        self.utils.print_inf(self.cfg.info_slow_get_device_fail_2, args)
                    else:
                        device_id = player_obj.device_id.upper()
                        args = [player, device_id]
                        if device_id_from_SkinID and device_id_from_SkinID != device_id:
                            self.utils.print_inf(
                                self.cfg.info_slow_get_device_success_2, args
                            )
                        else:
                            self.utils.print_inf(
                                self.cfg.info_slow_get_device_success_1, args
                            )
                        break
            # 处理逻辑：
            # SkinID √  AddPlayer √   记录AddPlayer的设备号
            # SkinID ×  AddPlayer √   记录AddPlayer的设备号
            # SkinID √  AddPlayer ×   记录SkinID的设备号
            # SkinID ×  AddPlayer ×   无法记录
            if (not device_id) and (not device_id_from_SkinID):
                return
            if (not device_id) and device_id_from_SkinID:
                device_id = device_id_from_SkinID
            path = f"{self.data_path}/{self.player_data_file}"
            with self.lock_ban_device_id:
                device_id_record = OrionUtils.disk_read(path)
                if device_id not in device_id_record.keys():
                    device_id_record[device_id] = {}
                if device_id_record[device_id].get(xuid) is None:
                    device_id_record[device_id][xuid] = []
                device_id_record[device_id][xuid].append(player)
                device_id_record[device_id][xuid] = list(
                    set(device_id_record[device_id][xuid])
                )
                OrionUtils.disk_write(path, device_id_record)
            # 如果不能通过SkinID字段快速踢出，补偿慢速踢出
            if (self.utils.in_whitelist(player) is False) and (
                device_id_from_SkinID != device_id
            ):
                self.ban_player_when_PlayerList_by_device_id(player, xuid, device_id)

    @utils.thread_func("检查并踢出被封禁的在线玩家")
    def check_online_player(self) -> None:
        """检查并踢出被封禁的在线玩家，一般可能是由于玩家趁机器人掉线时溜进游戏"""
        time.sleep(0.5)
        players_list = self.plugin.frame.get_players().getAllPlayers()
        all_ban_xuids_json = os.listdir(f"{self.data_path}/{self.xuid_dir}")
        all_ban_xuids = []
        for i in all_ban_xuids_json:
            xuid = i.replace(".json", "")
            try:
                all_ban_xuids.append(xuid)
            except ValueError:
                continue
        all_ban_device_ids_json = os.listdir(f"{self.data_path}/{self.device_id_dir}")
        all_ban_device_ids = []
        path_device_id = f"{self.data_path}/{self.player_data_file}"
        with self.lock_ban_device_id:
            device_id_data = OrionUtils.disk_read(path_device_id)
        for i in all_ban_device_ids_json:
            device_id = i.replace(".json", "")
            try:
                all_ban_device_ids.append(
                    list(device_id_data.get(device_id, {}).keys())
                )
            except ValueError:
                continue
        # 将双层嵌套表结构转换为单个表
        all_ban_device_id_merge = []
        for li in all_ban_device_ids:
            for inner_xuid in li:
                all_ban_device_id_merge.append(inner_xuid)
        for player in players_list:
            if (self.utils.in_whitelist(player.name) is False) and (
                (player.xuid in all_ban_xuids)
                or (player.xuid in all_ban_device_id_merge)
            ):
                self.execute_only_kick(
                    player.name,
                    self.cfg.info_find_online_banned,
                    (player.name, player.xuid),
                )

    @utils.thread_func("记分板监听器")
    def ListenScore(self) -> NoReturn:
        """记分板监听器线程"""
        while True:
            time.sleep(self.cfg.scoreboard_detect_cycle)
            try:
                result = self.sendwscmd("/scoreboard players list @a", True).as_dict
            except TimeoutError:
                continue
            OutputMessages = result["OutputMessages"]
            scoreboard_dict = {}
            current_player = None
            entries_to_process = 0
            for i in OutputMessages:
                message = i["Message"]
                params = i["Parameters"]

                if message == "§a%commands.scoreboard.players.list.player.count":
                    # 开始新玩家的记分板数据
                    entry_count = int(params[0])
                    current_player = params[1]
                    entries_to_process = entry_count

                elif (
                    message == "commands.scoreboard.players.list.player.entry"
                    and current_player
                    and entries_to_process > 0
                ):
                    # 处理当前玩家的记分板条目
                    entries_to_process -= 1
                    score = int(params[0])
                    scoreboard_name = params[2]

                    # 更新记分板字典
                    if scoreboard_name not in scoreboard_dict:
                        scoreboard_dict[scoreboard_name] = {}
                    scoreboard_dict[scoreboard_name][current_player] = score

            self.ban_player_by_scoreboard(scoreboard_dict)
            self.change_permission_by_scoreboard(scoreboard_dict)

    @utils.thread_func("封禁专用记分板")
    def ban_player_by_scoreboard(
        self, scoreboard_dict: dict[str, dict[str, int]]
    ) -> None:
        """
        封禁专用记分板，用于将游戏内命令方块接入猎户座
        Args:
            scoreboard_dict (dict[str, dict[str, int]]): 全部在线玩家的全部记分板字典，格式为 {记分板名称: {玩家名称: 分数}}
        """
        if self.cfg.is_ban_api_in_game:
            self.sendwocmd(
                f'/scoreboard players reset @a "{self.cfg.ban_scoreboard_name}"'
            )
            for player, score in scoreboard_dict.get(
                self.cfg.ban_scoreboard_name, {}
            ).items():
                if self.utils.in_whitelist(player) is False:
                    xuid = self.plugin.xuid_getter.get_xuid_by_name(player, True)
                    if score < -1:
                        score = 0
                    self.execute_ban(
                        player,
                        xuid,
                        score,
                        self.cfg.info_ban_by_scoreboard,
                        (player, xuid),
                    )

    @utils.thread_func("玩家权限管理专用记分板")
    def change_permission_by_scoreboard(
        self, scoreboard_dict: dict[str, dict[str, int]]
    ) -> None:
        """
        玩家权限管理专用记分板
        Args:
            scoreboard_dict (dict[str, dict[str, int]]): 全部在线玩家的全部记分板字典，格式为 {记分板名称: {玩家名称: 分数}}
        """
        if self.cfg.is_permission_mgr and self.cfg.is_change_permission_by_scoreboard:
            for player, score in scoreboard_dict.get(
                self.cfg.permission_scoreboard_name, {}
            ).items():
                try:
                    if (player in self.cfg.whitelist) or (
                        game_utils.is_op(player) and self.cfg.permission_ignore_op
                    ):
                        continue
                except (ValueError, KeyError):
                    continue
                for k, v in self.cfg.scoreboard_permission_group.items():
                    if score == int(v):
                        self.permission_change(player, k)
                        break

    @utils.thread_func("玩家权限修改(当玩家进入游戏时)")
    def change_permission_when_PlayerList(self, Username: str) -> None:
        """
        玩家权限修改(当玩家进入游戏时)
        Args:
            Username (str): 玩家名称
        """
        if self.cfg.is_permission_mgr and self.cfg.is_change_permission_when_enter:
            try:
                if game_utils.is_op(Username) and self.cfg.permission_ignore_op:
                    return
            except (ValueError, KeyError):
                return
            self.permission_change(Username, self.cfg.enter_permission_group)

    @utils.thread_func("玩家权限修改执行")
    def permission_change(self, player: str, permission_group: str | int) -> None:
        """
        玩家权限修改执行
        Args:
            player (str): 玩家名称
            permission_group (str | int): 玩家能力权限组
        """
        player_obj = self.plugin.game_ctrl.players.getPlayerByName(player)
        player_abilities = player_obj.abilities
        if "1" in str(permission_group):
            player_abilities.build = True
        else:
            player_abilities.build = False
        if "2" in str(permission_group):
            player_abilities.mine = True
        else:
            player_abilities.mine = False
        if "3" in str(permission_group):
            player_abilities.doors_and_switches = True
        else:
            player_abilities.doors_and_switches = False
        if "4" in str(permission_group):
            player_abilities.open_containers = True
        else:
            player_abilities.open_containers = False
        if "5" in str(permission_group):
            player_abilities.attack_players = True
        else:
            player_abilities.attack_players = False
        if "6" in str(permission_group):
            player_abilities.attack_mobs = True
        else:
            player_abilities.attack_mobs = False
        if "7" in str(permission_group):
            player_abilities.operator_commands = True
        else:
            player_abilities.operator_commands = False
        if "8" in str(permission_group):
            player_abilities.teleport = True
        else:
            player_abilities.teleport = False
        player_obj.setAbilities(player_abilities)

    @utils.thread_func("移除无效的封禁数据")
    def delete_invalid_ban_data(self) -> None:
        """移除无效的封禁数据，包括到期的封禁数据或者由于用户意外修改或磁盘读取bug导致的文件缺损"""
        path_xuid_dir = f"{self.data_path}/{self.xuid_dir}"
        all_ban_xuids = os.listdir(path_xuid_dir)
        for i in all_ban_xuids:
            path_ban_xuid = f"{path_xuid_dir}/{i}"
            try:
                with self.lock_ban_xuid:
                    ban_xuid_data = OrionUtils.disk_read(path_ban_xuid)
                # 通过逐一访问键的方式判断有无缺损
                ban_xuid = ban_xuid_data["xuid"]
                ban_player = ban_xuid_data["name"]
                _ = ban_xuid_data["ban_start_real_time"]
                _ = ban_xuid_data["ban_start_timestamp"]
                _ = ban_xuid_data["ban_end_real_time"]
                ban_end_ts_xuid = ban_xuid_data["ban_end_timestamp"]
                _ = ban_xuid_data["ban_reason"]
                if ban_end_ts_xuid != "Forever" and ban_end_ts_xuid <= int(time.time()):
                    os.remove(path_ban_xuid)
                    self.utils.print_inf(
                        self.cfg.info_delete_expire_xuid, [ban_player, ban_xuid]
                    )
            except Exception:
                os.remove(path_ban_xuid)
                self.utils.print_inf(self.cfg.info_delete_broken_xuid, [path_ban_xuid])

        path_device_id_dir = f"{self.data_path}/{self.device_id_dir}"
        all_ban_device_ids = os.listdir(path_device_id_dir)
        for i in all_ban_device_ids:
            path_ban_device_id = f"{path_device_id_dir}/{i}"
            try:
                with self.lock_ban_device_id:
                    ban_device_id_data = OrionUtils.disk_read(path_ban_device_id)
                # 通过逐一访问键的方式判断有无缺损
                ban_device_id = ban_device_id_data["device_id"]
                _ = ban_device_id_data["xuid_and_player"]
                _ = ban_device_id_data["ban_start_real_time"]
                _ = ban_device_id_data["ban_start_timestamp"]
                _ = ban_device_id_data["ban_end_real_time"]
                ban_end_ts_device_id = ban_device_id_data["ban_end_timestamp"]
                _ = ban_device_id_data["ban_reason"]
                if ban_end_ts_device_id != "Forever" and ban_end_ts_device_id <= int(
                    time.time()
                ):
                    os.remove(path_ban_device_id)
                    self.utils.print_inf(
                        self.cfg.info_delete_expire_device_id, [ban_device_id]
                    )
            except Exception:
                os.remove(path_ban_device_id)
                self.utils.print_inf(
                    self.cfg.info_delete_broken_device_id, [path_ban_device_id]
                )

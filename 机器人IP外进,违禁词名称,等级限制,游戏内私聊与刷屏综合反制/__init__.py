from tooldelta import Plugin, plugin_entry, cfg, utils, fmts
from tooldelta.constants import PacketIDS
from tooldelta.utils import tempjson
from tooldelta.internal.launch_cli import FrameNeOmgAccessPoint
import time
import json
import re
import os


# 插件主类
class BattleEye(Plugin):
    name = "机器人IP外进,违禁词名称,等级限制,游戏内私聊与刷屏综合反制"
    author = "style_天枢"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        CONFIG_DEFAULT = {  # 首次生成的配置
            "是否启用机器人IP外进反制": True,
            "是否启用等级限制": True,
            "是否启用网易屏蔽词名称反制": True,
            "是否启用自定义违禁词名称反制": True,
            "名称违禁词列表": [
                "狂笑",
                "要猫",
                "药猫",
                "妖猫",
                "幺猫",
                "要儿",
                "药儿",
                "妖儿",
                "幺儿",
                "孙政",
                "guiwow",
                "吴旭淳",
                "九重天",
                "XTS",
                "天庭",
                "白墙",
                "跑路",
                "runaway",
                "导入",
                "busj",
                "万花筒",
                "购买",
                "出售",
            ],
            "反制白名单": ["style_天枢", "style_天璇", "..."],
            "服务器准入等级": 1,
            "<<提示>>如果您需要“禁止游戏内私聊(tell,msg,w命令)”，请将机器人踢出游戏后启用sendcommandfeedback，命令为/gamerule sendcommandfeedback true": None,
            "是否禁止游戏内私聊(tell,msg,w命令)": True,
            "禁止私聊时允许私聊机器人": True,
            "是否禁止游戏内me命令": True,
            "是否启用黑名单词检测": True,
            "黑名单词列表": ["白墙", "跑路", "runaway"],
            "发言检测周期(秒)": 10,
            "是否启用周期内发言频率检测": True,
            "周期内发言条数限制": 10,
            "是否启用发言字数检测(单条文本)": True,
            "发言字数限制": 200,
            "是否启用重复消息刷屏检测": True,
            "周期内重复消息刷屏数量限制": 3,
            "<<提示>>如果您需要在踢出玩家的同时将其封禁，请务必按照以下格式修改配置": None,
            "<<提示>>封禁时间=-1:永久封禁": None,
            "<<提示>>封禁时间=0:仅踢出游戏，不作封禁，玩家可以立即重进": None,
            "<<提示>>封禁时间=86400:封禁86400秒，即1日": None,
            '<<提示>>封禁时间="0年0月5日6时7分8秒":封禁5日6时7分8秒': None,
            '<<提示>>封禁时间="10年0月0日0时0分0秒":封禁10年': None,
            "封禁时间_机器人IP外进反制": -1,
            "封禁时间_等级限制": 0,
            "封禁时间_网易屏蔽词名称反制": 0,
            "封禁时间_自定义违禁词名称反制": 0,
            "封禁时间_游戏内私聊(tell,msg,w命令)": 60,
            "封禁时间_游戏内me命令": "0年0月0日0时1分0秒",
            "封禁时间_黑名单词检测": "0年0月0日0时0分60秒",
            "封禁时间_发言频率检测": "0年0月0日0时10分0秒",
            "封禁时间_发言字数检测": 60,
            "封禁时间_重复消息刷屏检测": "0年0月0日0时10分0秒",
        }
        CONFIG_STD = {  # 配置格式要求
            "是否启用机器人IP外进反制": bool,
            "是否启用等级限制": bool,
            "是否启用网易屏蔽词名称反制": bool,
            "是否启用自定义违禁词名称反制": bool,
            "名称违禁词列表": cfg.JsonList(str, len_limit=-1),
            "反制白名单": cfg.JsonList(str, len_limit=-1),
            "服务器准入等级": cfg.PInt,
            "是否禁止游戏内私聊(tell,msg,w命令)": bool,
            "禁止私聊时允许私聊机器人": bool,
            "是否禁止游戏内me命令": bool,
            "是否启用黑名单词检测": bool,
            "黑名单词列表": cfg.JsonList(str, len_limit=-1),
            "发言检测周期(秒)": cfg.PNumber,
            "是否启用周期内发言频率检测": bool,
            "周期内发言条数限制": cfg.PInt,
            "是否启用发言字数检测(单条文本)": bool,
            "发言字数限制": cfg.PInt,
            "是否启用重复消息刷屏检测": bool,
            "周期内重复消息刷屏数量限制": cfg.PInt,
            "封禁时间_机器人IP外进反制": [int, str],
            "封禁时间_等级限制": [int, str],
            "封禁时间_网易屏蔽词名称反制": [int, str],
            "封禁时间_自定义违禁词名称反制": [int, str],
            "封禁时间_游戏内私聊(tell,msg,w命令)": [int, str],
            "封禁时间_游戏内me命令": [int, str],
            "封禁时间_黑名单词检测": [int, str],
            "封禁时间_发言频率检测": [int, str],
            "封禁时间_发言字数检测": [int, str],
            "封禁时间_重复消息刷屏检测": [int, str],
        }
        # 调用配置
        config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.is_detect_bot = config["是否启用机器人IP外进反制"]
        self.is_level_limit = config["是否启用等级限制"]
        self.is_detect_netease_banned_word = config["是否启用网易屏蔽词名称反制"]
        self.is_detect_self_banned_word = config["是否启用自定义违禁词名称反制"]
        self.banned_word_list = config["名称违禁词列表"]
        self.whitelist = config["反制白名单"]
        self.server_level = config["服务器准入等级"]
        self.ban_private_chat = config["是否禁止游戏内私聊(tell,msg,w命令)"]
        self.allow_chat_with_bot = config["禁止私聊时允许私聊机器人"]
        self.ban_me_command = config["是否禁止游戏内me命令"]
        self.Testfor_blacklist_word = config["是否启用黑名单词检测"]
        self.blacklist_word_list = config["黑名单词列表"]
        self.speak_detection_cycle = config["发言检测周期(秒)"]
        self.speak_speed_limit = config["是否启用周期内发言频率检测"]
        self.max_speak_count = config["周期内发言条数限制"]
        self.message_length_limit = config["是否启用发言字数检测(单条文本)"]
        self.max_speak_length = config["发言字数限制"]
        self.repeat_message_limit = config["是否启用重复消息刷屏检测"]
        self.max_repeat_count = config["周期内重复消息刷屏数量限制"]
        self.ban_time_detect_bot = config["封禁时间_机器人IP外进反制"]
        self.ban_time_level_limit = config["封禁时间_等级限制"]
        self.ban_time_detect_netease_banned_word = config["封禁时间_网易屏蔽词名称反制"]
        self.ban_time_detect_self_banned_word = config["封禁时间_自定义违禁词名称反制"]
        self.ban_time_private_chat = config["封禁时间_游戏内私聊(tell,msg,w命令)"]
        self.ban_time_me_command = config["封禁时间_游戏内me命令"]
        self.ban_time_testfor_blacklist_word = config["封禁时间_黑名单词检测"]
        self.ban_time_speak_speed_limit = config["封禁时间_发言频率检测"]
        self.ban_time_message_length_limit = config["封禁时间_发言字数检测"]
        self.ban_time_repeat_message_limit = config["封禁时间_重复消息刷屏检测"]

        os.makedirs(f"{self.data_path}/玩家封禁时间数据", exist_ok=True)

        self.ListenActive(self.on_active)
        # 监听PlayerList数据包
        self.ListenPacket(PacketIDS.IDPlayerList, self.on_PlayerList)
        # 监听Text数据包
        self.ListenPacket(PacketIDS.IDText, self.on_Text)

        # 创建异步计时器，用于刷新“检测发言频率”和“检测重复刷屏”的缓存
        if self.speak_speed_limit or self.repeat_message_limit:
            self.data = {}

            @utils.thread_func("发言周期检测计时器")
            def timer():
                while True:
                    self.data = {}
                    time.sleep(self.speak_detection_cycle)

            timer()

    # 黑名单词检测函数封装
    def blacklist_word_detect(self, message, player):
        if self.Testfor_blacklist_word and player not in self.whitelist:
            blacklist_word_set = set(self.blacklist_word_list)
            n = len(message)
            for i in range(n):
                for j in range(i + 1, n + 1):
                    if message[i:j] in blacklist_word_set:
                        fmts.print_inf(
                            f"§c发现 {player} 发送的文本触发了黑名单词({message[i:j]})，正在踢出"
                        )
                        self.game_ctrl.sendwocmd(
                            f'/kick "{player}" 您发送的文本触发了黑名单词({message[i:j]})'
                        )
                        fmts.print_inf(
                            f"§a发现 {player} 发送的文本触发了黑名单词({message[i:j]})，已被踢出游戏"
                        )
                        self.ban_player_first_time(
                            player,
                            self.ban_time_testfor_blacklist_word,
                            f"您发送的文本触发了黑名单词({message[i:j]})",
                        )

    # 发言字数检测函数封装
    def message_length_detect(self, message, player):
        if (
            self.message_length_limit
            and len(message) > self.max_speak_length
            and player not in self.whitelist
        ):
            fmts.print_inf(
                f"§c发现 {player} 发送的文本长度超过{self.max_speak_length}，正在踢出"
            )
            self.game_ctrl.sendwocmd(f'/kick "{player}" 您发送的文本过长，请勿刷屏')
            fmts.print_inf(
                f"§a发现 {player} 发送的文本长度超过{self.max_speak_length}，已被踢出游戏"
            )
            self.ban_player_first_time(
                player,
                self.ban_time_message_length_limit,
                f"您发送的文本长度超过{self.max_speak_length}字符限制",
            )

    # 将发言玩家、文本添加至缓存区
    def message_cache_area(self, message, player):
        if self.speak_speed_limit or self.repeat_message_limit:
            if self.data.get(player) is None:
                self.data[player] = []
            self.data[player].append(message)
            self.speak_speed_detect(player)
            self.repeat_message_detect(player)

    # 发言频率检测函数封装
    def speak_speed_detect(self, player):
        if (
            self.speak_speed_limit
            and len(self.data[player]) > self.max_speak_count
            and player not in self.whitelist
        ):
            fmts.print_inf(
                f"§c发现 {player} 发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)，正在踢出"
            )
            self.game_ctrl.sendwocmd(f'/kick "{player}" 您发言过快，休息一下吧~')
            fmts.print_inf(
                f"§a发现 {player} 发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)，已被踢出游戏"
            )
            self.ban_player_first_time(
                player,
                self.ban_time_speak_speed_limit,
                f"您发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)",
            )

    # 重复消息刷屏检测函数封装
    def repeat_message_detect(self, player):
        if self.repeat_message_limit and player not in self.whitelist:
            counts = {}
            for i in self.data[player]:
                counts[i] = counts.get(i, 0) + 1
            for _, v in counts.items():
                if v > self.max_repeat_count:
                    fmts.print_inf(
                        f"§c发现 {player} 连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)，正在踢出"
                    )
                    self.game_ctrl.sendwocmd(
                        f'/kick "{player}" 您重复刷屏过快，休息一下吧~'
                    )
                    fmts.print_inf(
                        f"§a发现 {player} 连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)，已被踢出游戏"
                    )
                    self.ban_player_first_time(
                        player,
                        self.ban_time_repeat_message_limit,
                        f"您连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)",
                    )
                    break

    # 玩家封禁函数封装(开始封禁)
    def ban_player_first_time(self, player, ban_time, ban_reason):
        xuid = self.xuid_getter.get_xuid_by_name(player, True)
        timestamp_now = int(time.time())
        data_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
        path = f"{self.data_path}/玩家封禁时间数据/{xuid}.json"
        ban_player_data = tempjson.load_and_read(
            path, need_file_exists=False, timeout=2
        )

        if ban_player_data is None:
            pre_ban_timestamp = timestamp_now
        else:
            pre_ban_timestamp = ban_player_data["ban_until_timestamp"]

        if pre_ban_timestamp == "Forever":
            return

        # ban_time == -1:永久封禁
        if ban_time == -1:
            tempjson.load_and_write(
                path,
                {
                    "xuid": xuid,
                    "name": player,
                    "ban_start": data_now,
                    "ban_start_timestamp": timestamp_now,
                    "ban_until": "Forever",
                    "ban_until_timestamp": "Forever",
                    "reason": ban_reason,
                },
                need_file_exists=False,
                timeout=2,
            )
            tempjson.flush(path)

        # ban_time == 0:仅踢出游戏，不作封禁，玩家可以立即重进
        elif ban_time == 0:
            return

        # type(ban_time) == int and ban_time > 0:封禁玩家对应时间(单位:秒)
        elif type(ban_time) is int and ban_time > 0:
            timestamp_until = pre_ban_timestamp + ban_time
            data_until = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_until)
            )
            tempjson.load_and_write(
                path,
                {
                    "xuid": xuid,
                    "name": player,
                    "ban_start": data_now,
                    "ban_start_timestamp": timestamp_now,
                    "ban_until": data_until,
                    "ban_until_timestamp": timestamp_until,
                    "reason": ban_reason,
                },
                need_file_exists=False,
                timeout=2,
            )
            tempjson.flush(path)

        # type(ban_time) == str:如果输入的是字符串，对字符串进行解析，判断是否合法，提取时间信息
        elif type(ban_time) is str:
            ban_time = ban_time.replace(" ", "")
            matches_time_units = re.findall(r"(\d+)(年|月|日|时|分|秒)", ban_time)
            if not matches_time_units:
                print(
                    "执行封禁操作失败：封禁时间中无法匹配到任何时间单位，合法的时间单位为(年|月|日|时|分|秒)"
                )
                return

            ban_time_after_matched = "".join(
                f"{value}{unit}" for value, unit in matches_time_units
            )
            if ban_time_after_matched != ban_time:
                print("执行封禁操作失败：封禁时间中存在无法解析的字符")
                return

            time_units = {}
            for value_str, unit in matches_time_units:
                if unit in time_units:
                    print(f"执行封禁操作失败：封禁时间中存在重复的时间单位：{unit}")
                    return
                try:
                    value = int(value_str)
                    if value < 0:
                        print("执行封禁操作失败：封禁时间值不能为负数")
                        return
                except ValueError as error:
                    print(
                        f"执行封禁操作失败：封禁时间中存在无效的数值：{value_str} detail: {error!s}"
                    )
                    return

                time_units[unit] = value

            years = time_units.get("年", 0)
            months = time_units.get("月", 0)
            days = time_units.get("天", 0)
            hours = time_units.get("时", 0)
            minutes = time_units.get("分", 0)
            seconds = time_units.get("秒", 0)

            total_days = years * 360 + months * 30 + days
            total_seconds = (total_days * 86400) + hours * 3600 + minutes * 60 + seconds

            if total_seconds == 0:
                return

            timestamp_until = pre_ban_timestamp + total_seconds
            data_until = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_until)
            )
            tempjson.load_and_write(
                path,
                {
                    "xuid": xuid,
                    "name": player,
                    "ban_start": data_now,
                    "ban_start_timestamp": timestamp_now,
                    "ban_until": data_until,
                    "ban_until_timestamp": timestamp_until,
                    "reason": ban_reason,
                },
                need_file_exists=False,
                timeout=2,
            )
            tempjson.flush(path)

        # 封禁时间无法被解析
        else:
            print("执行封禁操作失败：无法解析您输入的封禁时间")
            return

    # 玩家封禁函数封装(被封禁者再次加入游戏)
    def ban_player_when_PlayerList(self, player):
        xuid = self.xuid_getter.get_xuid_by_name(player, True)
        path = f"{self.data_path}/玩家封禁时间数据/{xuid}.json"
        try:
            ban_player_data = tempjson.load_and_read(
                path, need_file_exists=True, timeout=2
            )
            if ban_player_data is None:
                os.remove(path)
                return
            ban_until_timestamp = ban_player_data["ban_until_timestamp"]
            ban_reason = ban_player_data["reason"]
            if type(ban_until_timestamp) is int:
                ban_until_date = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(ban_until_timestamp)
                )
                timestamp_now = int(time.time())
                if ban_until_timestamp > timestamp_now:
                    fmts.print_inf(
                        f"§c发现 {player} 被封禁，正在踢出，其解封时间为：{ban_until_date}"
                    )
                    self.game_ctrl.sendwocmd(
                        f'/kick "{player}" 由于{ban_reason}，您被系统封禁至：{ban_until_date}'
                    )
                    fmts.print_inf(f"§a发现 {player} 被封禁，已被踢出游戏")
                else:
                    os.remove(path)
            elif ban_until_timestamp == "Forever":
                fmts.print_inf(f"§c发现 {player} 被封禁，正在踢出，该玩家为永久封禁")
                self.game_ctrl.sendwocmd(
                    f'/kick "{player}" 由于{ban_reason}，您被系统封禁至：Forever'
                )
                fmts.print_inf(f"§a发现 {player} 被封禁，已被踢出游戏")
        except FileNotFoundError:
            return

    def on_active(self):
        assert isinstance(self.frame.launcher, FrameNeOmgAccessPoint), (
            "当前使用启动器不是 NeOmega 接入点"
        )
        self.bot_name = (
            self.frame.launcher.omega.get_bot_basic_info().BotName
        )  # 调用Omega的API，获取机器人名字，必须等待Omega框架加载完毕后才能运行
        self.xuid_getter = self.GetPluginAPI("XUID获取")
        fmts.print_inf(
            "§b如果您需要“禁止游戏内私聊(tell,msg,w命令)”，请将机器人踢出游戏后启用sendcommandfeedback，命令为/gamerule sendcommandfeedback true"
        )
        fmts.print_inf(
            '§e如果您想要解封玩家，请删除"插件数据文件/机器人IP外进,违禁词名称,等级限制,游戏内私聊与刷屏综合反制/玩家封禁时间数据/XUID.json"；如果您想要修改玩家封禁时间，请修改文件中的"ban_until_timestamp"，这是封禁结束时的时间戳，代表(UTC)1970年1月1日至此时的总秒数，您可以在各种时间戳转换网站上得到您需要的时间戳！注意，修改文件中的日期是无效的，您必须修改时间戳！'
        )

    def on_PlayerList(self, packet):
        if packet["ActionType"] == 0:
            Username = packet["Entries"][0]["Username"]
            PremiumSkin = packet["Entries"][0]["Skin"]["PremiumSkin"]
            Trusted = packet["Entries"][0]["Skin"]["Trusted"]
            CapeID = packet["Entries"][0]["Skin"]["CapeID"]
            GrowthLevels = packet["GrowthLevels"][0]

            if Username not in self.whitelist:
                if self.is_detect_bot and (
                    PremiumSkin is False or Trusted is False or CapeID is None
                ):
                    fmts.print_inf(f"§c发现 {Username} 可能为崩服机器人，正在制裁")
                    fmts.print_war(f"崩服机器人数据: {packet}")
                    self.game_ctrl.sendwocmd(
                        f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                    )
                    fmts.print_inf(f"§a发现 {Username} 可能为崩服机器人，制裁已完成")
                    self.ban_player_first_time(
                        Username,
                        self.ban_time_detect_bot,
                        "您必须通过 Microsoft 服务身份验证。",
                    )

                if self.is_level_limit and GrowthLevels < self.server_level:
                    fmts.print_inf(
                        f"§c发现 {Username} 等级低于服务器准入等级({self.server_level}级)，正在踢出"
                    )
                    self.game_ctrl.sendwocmd(
                        f'/kick "{Username}" 本服准入等级为{self.server_level}级，您的等级过低，请加油升级噢！'
                    )
                    fmts.print_inf(
                        f"§a发现 {Username} 等级低于服务器准入等级({self.server_level}级)，已被踢出游戏"
                    )
                    self.ban_player_first_time(
                        Username,
                        self.ban_time_level_limit,
                        f"您的等级低于服务器准入等级({self.server_level}级)",
                    )

                if self.is_detect_netease_banned_word:
                    try:
                        self.game_ctrl.sendcmd(f'/testfor "{Username}"', True, 2)
                    except TimeoutError:
                        fmts.print_inf(f"§c发现 {Username} 名称为网易屏蔽词，正在踢出")
                        self.game_ctrl.sendwocmd(
                            f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                        )
                        fmts.print_inf(
                            f"§a发现 {Username} 名称为网易屏蔽词，已被踢出游戏"
                        )
                        self.ban_player_first_time(
                            Username,
                            self.ban_time_detect_netease_banned_word,
                            "您的名称为网易屏蔽词",
                        )

                if self.is_detect_self_banned_word:
                    self.banned_word_set = set(self.banned_word_list)
                    n = len(Username)
                    for i in range(n):
                        for j in range(i + 1, n + 1):
                            if Username[i:j] in self.banned_word_set:
                                fmts.print_inf(
                                    f"§c发现 {Username} 名称为本服自定义违禁词({Username[i:j]})，正在踢出"
                                )
                                self.game_ctrl.sendwocmd(
                                    f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                                )
                                fmts.print_inf(
                                    f"§a发现 {Username} 名称为本服自定义违禁词({Username[i:j]})，已被踢出游戏"
                                )
                                self.ban_player_first_time(
                                    Username,
                                    self.ban_time_detect_self_banned_word,
                                    f"您的名称为本服自定义违禁词({Username[i:j]})",
                                )

                self.ban_player_when_PlayerList(Username)
        return False

    def on_Text(self, packet):
        # "TextType"=10:监听到命令执行反馈
        if packet["TextType"] == 10 and packet["XUID"] != "":
            try:
                rawtext_list = json.loads(packet["Message"])["rawtext"]
                translate_list = []
                for i in rawtext_list:
                    if "translate" in i:
                        translate_list.append(i["translate"])
                original_player = translate_list[0]
                commands_type = translate_list[1]
                # "commands.message.display.outgoing":监听到游戏内私聊(tell,msg,w命令)
                if (
                    commands_type == "commands.message.display.outgoing"
                    and original_player not in self.whitelist
                ):
                    for i in rawtext_list:
                        if "with" in i:
                            with_rawtext = i["with"]["rawtext"]
                            target_player = with_rawtext[0]["text"]
                            msg_text = with_rawtext[1]["text"]
                            break
                    if self.ban_private_chat:
                        if self.allow_chat_with_bot:
                            if target_player != self.bot_name:
                                fmts.print_inf(
                                    f"§c发现 {original_player} 尝试发送私聊(tell,msg,w命令)，正在踢出"
                                )
                                self.game_ctrl.sendwocmd(
                                    f'/kick "{original_player}" 禁止发送私聊(tell,msg,w命令)！'
                                )
                                fmts.print_inf(
                                    f"§a发现 {original_player} 尝试发送私聊(tell,msg,w命令)，已被踢出游戏"
                                )
                                self.ban_player_first_time(
                                    original_player,
                                    self.ban_time_private_chat,
                                    "您尝试发送私聊(tell,msg,w命令)",
                                )
                        else:
                            fmts.print_inf(
                                f"§c发现 {original_player} 尝试发送私聊(tell,msg,w命令)，正在踢出"
                            )
                            self.game_ctrl.sendwocmd(
                                f'/kick "{original_player}" 禁止发送私聊(tell,msg,w命令)！'
                            )
                            fmts.print_inf(
                                f"§a发现 {original_player} 尝试发送私聊(tell,msg,w命令)，已被踢出游戏"
                            )
                            self.ban_player_first_time(
                                original_player,
                                self.ban_time_private_chat,
                                "您尝试发送私聊(tell,msg,w命令)",
                            )
                    self.blacklist_word_detect(msg_text, original_player)
                    self.message_length_detect(msg_text, original_player)
                    self.message_cache_area(msg_text, original_player)
            except Exception as error:
                print(f"在解析私聊数据包或某些命令数据包时出现错误: {error!s}")

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
                    if self.ban_me_command and player not in self.whitelist:
                        fmts.print_inf(f"§c发现 {player} 尝试发送me命令，正在踢出")
                        self.game_ctrl.sendwocmd(f'/kick "{player}" 禁止发送me命令！')
                        fmts.print_inf(f"§a发现 {player} 尝试发送me命令，已被踢出游戏")
                        self.ban_player_first_time(
                            player, self.ban_time_me_command, "您尝试发送me命令"
                        )
                    self.blacklist_word_detect(msg_text, player)
                    self.message_length_detect(msg_text, player)
                    self.message_cache_area(msg_text, player)
                # 判断为常规发言
                elif sourcename != "":
                    self.blacklist_word_detect(message, sourcename)
                    self.message_length_detect(message, sourcename)
                    self.message_cache_area(message, sourcename)
            except Exception as error:
                print(f"在解析发言数据包或me命令时出现错误 {error!s}")


entry = plugin_entry(BattleEye, "BattleEye")

from tooldelta import Plugin, plugin_entry, cfg, utils, fmts
from tooldelta.constants import PacketIDS
from tooldelta.utils import tempjson
import time
import json
import re
import os
import requests
import random


# 插件主类
class BattleEye(Plugin):
    name = "机器人IP外进,违禁词名称,等级限制,游戏内私聊与刷屏综合反制"
    author = "style_天枢"
    version = (0, 0, 4)

    def __init__(self, frame):
        super().__init__(frame)
        CONFIG_DEFAULT = {  # 首次生成的配置
            "是否启用机器人IP外进反制": True,
            "是否启用等级限制": True,
            "是否启用网易屏蔽词名称反制": True,
            "--网易屏蔽词名称检测等待时间(秒)": 2,
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
            "是否自动记录玩家设备号(机器人在玩家登录时需tp至玩家处，请避免和巡逻插件一起使用)": True,
            "--如果记录玩家设备号，是否根据设备号来封禁违规玩家": True,
            "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)": 3,
            "是否检查玩家信息与网易启动器是否一致(可用于反制外挂篡改游戏内等级，注意：本API不稳定，当大量玩家同时进入游戏时可能出现404或超时)": True,
            "--如果在网易启动器无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新)": False,
            "--如果在网易启动器搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏": True,
            "--网易启动器检查API响应等待时间(秒)": 10,
            "--网易启动器检查API可尝试次数(最后一次尝试依然搜索失败即踢出)": 3,
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
            "--封禁时间_网易启动器无法搜索到玩家": 0,
            "--封禁时间_网易启动器搜到的玩家等级与游戏内等级不同": -1,
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
            "--网易屏蔽词名称检测等待时间(秒)": cfg.PNumber,
            "是否启用自定义违禁词名称反制": bool,
            "名称违禁词列表": cfg.JsonList(str, len_limit=-1),
            "是否自动记录玩家设备号(机器人在玩家登录时需tp至玩家处，请避免和巡逻插件一起使用)": bool,
            "--如果记录玩家设备号，是否根据设备号来封禁违规玩家": bool,
            "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)": cfg.PInt,
            "是否检查玩家信息与网易启动器是否一致(可用于反制外挂篡改游戏内等级，注意：本API不稳定，当大量玩家同时进入游戏时可能出现404或超时)": bool,
            "--如果在网易启动器无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新)": bool,
            "--如果在网易启动器搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏": bool,
            "--网易启动器检查API响应等待时间(秒)": cfg.PNumber,
            "--网易启动器检查API可尝试次数(最后一次尝试依然搜索失败即踢出)": cfg.PInt,
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
            "--封禁时间_网易启动器无法搜索到玩家": [int, str],
            "--封禁时间_网易启动器搜到的玩家等级与游戏内等级不同": [int, str],
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
        self.detect_netease_banned_word_timeout = config[
            "--网易屏蔽词名称检测等待时间(秒)"
        ]
        self.is_detect_self_banned_word = config["是否启用自定义违禁词名称反制"]
        self.banned_word_list = config["名称违禁词列表"]
        self.is_record_device_id = config[
            "是否自动记录玩家设备号(机器人在玩家登录时需tp至玩家处，请避免和巡逻插件一起使用)"
        ]
        self.is_ban_player_by_device_id = config[
            "--如果记录玩家设备号，是否根据设备号来封禁违规玩家"
        ]
        self.record_device_id_try_time = config[
            "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)"
        ]
        self.is_check_player_info = config[
            "是否检查玩家信息与网易启动器是否一致(可用于反制外挂篡改游戏内等级，注意：本API不稳定，当大量玩家同时进入游戏时可能出现404或超时)"
        ]
        self.is_ban_player_if_cannot_search = config[
            "--如果在网易启动器无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新)"
        ]
        self.is_ban_player_if_different_level = config[
            "--如果在网易启动器搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏"
        ]
        self.check_player_info_api_timeout = config[
            "--网易启动器检查API响应等待时间(秒)"
        ]
        self.check_player_info_api_try_time = config[
            "--网易启动器检查API可尝试次数(最后一次尝试依然搜索失败即踢出)"
        ]
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
        self.ban_time_if_cannot_search = config["--封禁时间_网易启动器无法搜索到玩家"]
        self.ban_time_if_different_level = config[
            "--封禁时间_网易启动器搜到的玩家等级与游戏内等级不同"
        ]
        self.ban_time_private_chat = config["封禁时间_游戏内私聊(tell,msg,w命令)"]
        self.ban_time_me_command = config["封禁时间_游戏内me命令"]
        self.ban_time_testfor_blacklist_word = config["封禁时间_黑名单词检测"]
        self.ban_time_speak_speed_limit = config["封禁时间_发言频率检测"]
        self.ban_time_message_length_limit = config["封禁时间_发言字数检测"]
        self.ban_time_repeat_message_limit = config["封禁时间_重复消息刷屏检测"]

        # 这是获取玩家设备号函数的线程锁，要求当多个玩家连续登录时逐个获取设备号，而不是连续tp最后啥也没得到
        # 当任意玩家进入游戏后，线程锁将变为False，其他device_id线程处于等待状态，直到获取到当前玩家设备号或超时后再执行下一个线程
        self.thread_lock_by_get_device_id = True

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

    def on_active(self):
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
                self.ban_bot(Username, PremiumSkin, Trusted, CapeID, packet)
                self.ban_player_level_too_low(Username, GrowthLevels)
                self.ban_player_with_netease_banned_word(Username)
                self.ban_player_with_self_banned_word(Username)
                self.check_player_info(Username, GrowthLevels, packet)
                self.ban_player_when_PlayerList_by_xuid(Username)
                self.ban_player_when_PlayerList_by_device_id(Username)

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
                    self.blacklist_word_detect(msg_text, original_player)
                    self.message_length_detect(msg_text, original_player)
                    self.message_cache_area(msg_text, original_player)
                    self.ban_time_format_and_first_execute(
                        original_player,
                        self.ban_time_private_chat,
                        "您尝试发送私聊(tell,msg,w命令)",
                    )
            except Exception as error:
                print(f"在解析私聊数据包或某些命令数据包时出现错误: {str(error)}")

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
                    self.blacklist_word_detect(msg_text, player)
                    self.message_length_detect(msg_text, player)
                    self.message_cache_area(msg_text, player)
                    self.ban_time_format_and_first_execute(
                        player, self.ban_time_me_command, "您尝试发送me命令"
                    )
                # 判断为常规发言
                elif sourcename != "":
                    self.blacklist_word_detect(message, sourcename)
                    self.message_length_detect(message, sourcename)
                    self.message_cache_area(message, sourcename)
            except Exception as error:
                print(f"在解析发言数据包或me命令时出现错误 {str(error)}")

    # 反制机器人函数封装

    @utils.thread_func("反制机器人函数")
    def ban_bot(self, Username, PremiumSkin, Trusted, CapeID, packet):
        if self.is_detect_bot and (
            PremiumSkin is False or Trusted is False or CapeID is None
        ):
            fmts.print_inf(f"§c发现 {Username} 可能为崩服机器人，正在制裁")
            fmts.print_war(f"崩服机器人数据: {packet}")
            self.game_ctrl.sendwocmd(
                f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
            )
            fmts.print_inf(f"§a发现 {Username} 可能为崩服机器人，制裁已完成")
            self.ban_time_format_and_first_execute(
                Username,
                self.ban_time_detect_bot,
                "您必须通过 Microsoft 服务身份验证。",
            )

    # 反制等级过低玩家函数封装

    @utils.thread_func("反制等级过低玩家函数")
    def ban_player_level_too_low(self, Username, GrowthLevels):
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
            self.ban_time_format_and_first_execute(
                Username,
                self.ban_time_level_limit,
                f"您的等级低于服务器准入等级({self.server_level}级)",
            )

    # 反制网易屏蔽词名称玩家函数封装

    @utils.thread_func("反制网易屏蔽词名称玩家函数")
    def ban_player_with_netease_banned_word(self, Username):
        if self.is_detect_netease_banned_word:
            try:
                self.game_ctrl.sendcmd(
                    f'/testfor "{Username}"',
                    True,
                    self.detect_netease_banned_word_timeout,
                )
            except TimeoutError:
                fmts.print_inf(f"§c发现 {Username} 名称为网易屏蔽词，正在踢出")
                self.game_ctrl.sendwocmd(
                    f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                )
                fmts.print_inf(f"§a发现 {Username} 名称为网易屏蔽词，已被踢出游戏")
                self.ban_time_format_and_first_execute(
                    Username,
                    self.ban_time_detect_netease_banned_word,
                    "您的名称为网易屏蔽词",
                )

    # 反制自定义违禁词名称玩家函数封装

    @utils.thread_func("反制自定义违禁词名称玩家函数")
    def ban_player_with_self_banned_word(self, Username):
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
                        self.ban_time_format_and_first_execute(
                            Username,
                            self.ban_time_detect_self_banned_word,
                            f"您的名称为本服自定义违禁词({Username[i:j]})",
                        )

    # 网易启动器玩家信息检查函数封装

    @utils.thread_func("网易启动器玩家信息检查函数")
    def check_player_info(self, Username, GrowthLevels, packet):
        if self.is_check_player_info:
            try_time = 0
            url = "http://api.tooldelta.top/api/mc"
            headers = {"Content-Type": "application/json"}
            payload = {"type": "searchUser", "data": {"name": f"{Username}"}}
            while True:
                try:
                    userdata_from_netease = requests.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=self.check_player_info_api_timeout,
                    )
                    try_time += 1

                    if userdata_from_netease.status_code == 404:
                        if try_time >= self.check_player_info_api_try_time:
                            fmts.print_inf(
                                f"§c在网易启动器搜索玩家 {Username} 失败，原因：状态码[{userdata_from_netease.status_code}]，当前尝试次数{try_time}/{self.check_player_info_api_try_time}，这是最后一次尝试"
                            )
                            if self.is_ban_player_if_cannot_search:
                                fmts.print_inf(
                                    f"§c由于我们无法在网易启动器搜索到玩家 {Username} ，正在踢出该玩家，这可能是由于“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新”等原因导致的"
                                )
                                self.game_ctrl.sendwocmd(
                                    f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                                )
                                fmts.print_inf(
                                    f"§a由于我们无法在网易启动器搜索到玩家 {Username} ，该玩家已被踢出游戏"
                                )
                                self.ban_time_format_and_first_execute(
                                    Username,
                                    self.ban_time_if_cannot_search,
                                    "您必须通过 Microsoft 服务身份验证。",
                                )
                            break

                        try_api_sleep_time = random.randint(
                            15 * try_time, 30 * try_time
                        )
                        fmts.print_inf(
                            f"§c在网易启动器搜索玩家 {Username} 失败，原因：状态码[{userdata_from_netease.status_code}]，当前尝试次数{try_time}/{self.check_player_info_api_try_time}，将在{try_api_sleep_time}秒后再次尝试搜索"
                        )
                        time.sleep(try_api_sleep_time)

                    elif userdata_from_netease.status_code == 200:
                        userdata_from_netease = userdata_from_netease.json()
                        for i in userdata_from_netease["data"]:
                            if i["nickname"] == Username:
                                fmts.print_inf(
                                    f"§a成功在网易启动器搜索到玩家 {Username} ，其启动器等级为{i['lv']}，游戏内等级为{GrowthLevels}"
                                )
                                if (
                                    self.is_ban_player_if_different_level
                                    and i["lv"] != GrowthLevels
                                ):
                                    fmts.print_inf(
                                        f"§c由于玩家 {Username} 的启动器等级和游戏内等级不匹配，正在踢出"
                                    )
                                    fmts.print_war(
                                        f"该玩家可能通过外挂篡改游戏内等级: {packet}"
                                    )
                                    self.game_ctrl.sendwocmd(
                                        f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                                    )
                                    fmts.print_inf(
                                        f"§a由于玩家 {Username} 的启动器等级和游戏内等级不匹配，已被踢出游戏"
                                    )
                                    self.ban_time_format_and_first_execute(
                                        Username,
                                        self.ban_time_if_different_level,
                                        "您必须通过 Microsoft 服务身份验证。",
                                    )
                        break

                    else:
                        break

                except requests.exceptions.Timeout as timeout_error:
                    try_time += 1
                    if try_time >= self.check_player_info_api_try_time:
                        fmts.print_inf(
                            f"§c在网易启动器搜索玩家 {Username} 失败，原因：请求网易启动器玩家信息超时：{timeout_error}，当前尝试次数{try_time}/{self.check_player_info_api_try_time}，这是最后一次尝试"
                        )
                        if self.is_ban_player_if_cannot_search:
                            fmts.print_inf(
                                f"§c由于我们无法在网易启动器搜索到玩家 {Username} ，正在踢出该玩家，这可能是由于“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新”等原因导致的"
                            )
                            self.game_ctrl.sendwocmd(
                                f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                            )
                            fmts.print_inf(
                                f"§a由于我们无法在网易启动器搜索到玩家 {Username} ，该玩家已被踢出游戏"
                            )
                            self.ban_time_format_and_first_execute(
                                Username,
                                self.ban_time_if_cannot_search,
                                "您必须通过 Microsoft 服务身份验证。",
                            )
                        break

                    try_api_sleep_time = random.randint(15 * try_time, 30 * try_time)
                    fmts.print_inf(
                        f"§c在网易启动器搜索玩家 {Username} 失败，原因：请求网易启动器玩家信息超时：{timeout_error}，当前尝试次数{try_time}/{self.check_player_info_api_try_time}，将在{try_api_sleep_time}秒后再次尝试搜索"
                    )
                    time.sleep(try_api_sleep_time)

                except requests.exceptions.HTTPError as http_error:
                    print(f"HTTP异常信息：{http_error}")
                    break

                except requests.exceptions.RequestException as error:
                    print(
                        f"请求网易启动器玩家信息失败(API请求失败或玩家数据json解析失败)：{error}"
                    )
                    break

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
                        self.ban_time_format_and_first_execute(
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
            self.ban_time_format_and_first_execute(
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
            self.ban_time_format_and_first_execute(
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
                    self.ban_time_format_and_first_execute(
                        player,
                        self.ban_time_repeat_message_limit,
                        f"您连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)",
                    )

    # 格式化玩家封禁时间并开始执行封禁
    def ban_time_format_and_first_execute(self, player, ban_time, ban_reason):
        # ban_time == 0:仅踢出游戏，不作封禁，玩家可以立即重进
        if ban_time != 0:
            xuid = self.xuid_getter.get_xuid_by_name(player, True)
            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
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
                        "ban_start": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_until": "Forever",
                        "ban_until_timestamp": "Forever",
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path)
                tempjson.unload_to_path(path)

            # type(ban_time) is int and ban_time > 0:封禁玩家对应时间(单位:秒)
            elif type(ban_time) is int and ban_time > 0:
                timestamp_until = pre_ban_timestamp + ban_time
                date_until = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_until)
                )
                tempjson.load_and_write(
                    path,
                    {
                        "xuid": xuid,
                        "name": player,
                        "ban_start": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_until": date_until,
                        "ban_until_timestamp": timestamp_until,
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path)
                tempjson.unload_to_path(path)

            # type(ban_time) is str:封禁时间为字符串，将尝试进行转换
            elif type(ban_time) is str:
                ban_time = ban_time.replace(" ", "")
                matches_time_units = re.findall(r"(\d+)(年|月|日|时|分|秒)", ban_time)
                if not matches_time_units:
                    print(
                        f"警告：封禁时间({ban_time})中无法匹配到任何时间单位，合法的时间单位为(年|月|日|时|分|秒)"
                    )
                    return

                ban_time_after_matched = "".join(
                    f"{value}{unit}" for value, unit in matches_time_units
                )
                if ban_time_after_matched != ban_time:
                    print(f"警告：封禁时间({ban_time})中存在无法解析的字符")
                    return

                time_units = {}
                for value_str, unit in matches_time_units:
                    if unit in time_units:
                        print(f"警告：封禁时间({ban_time})中存在重复的时间单位：{unit}")
                        return
                    try:
                        value = int(value_str)
                        if value < 0:
                            print(f'警告：封禁时间({ban_time})中的"{value}"值为负数')
                            return
                    except ValueError as error:
                        print(
                            f"警告：封禁时间({ban_time})中存在无效的数值：{value_str} detail: {str(error)}"
                        )
                        return

                    time_units[unit] = value

                years = time_units.get("年", 0)
                months = time_units.get("月", 0)
                days = time_units.get("日", 0)
                hours = time_units.get("时", 0)
                minutes = time_units.get("分", 0)
                seconds = time_units.get("秒", 0)

                total_days = years * 360 + months * 30 + days
                total_seconds = (
                    (total_days * 86400) + hours * 3600 + minutes * 60 + seconds
                )

                timestamp_until = pre_ban_timestamp + total_seconds
                date_until = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_until)
                )
                tempjson.load_and_write(
                    path,
                    {
                        "xuid": xuid,
                        "name": player,
                        "ban_start": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_until": date_until,
                        "ban_until_timestamp": timestamp_until,
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path)
                tempjson.unload_to_path(path)

            else:
                print("警告：无法解析您输入的封禁时间")

    # 玩家封禁函数封装(被封禁者再次加入游戏,通过xuid判断)
    def ban_player_when_PlayerList_by_xuid(self, player):
        xuid = self.xuid_getter.get_xuid_by_name(player, True)
        path = f"{self.data_path}/玩家封禁时间数据/{xuid}.json"
        try:
            ban_player_data = tempjson.load_and_read(
                path, need_file_exists=True, timeout=2
            )
            tempjson.unload_to_path(path)
            if ban_player_data is None:
                os.remove(path)
                return
            ban_until_timestamp = ban_player_data["ban_until_timestamp"]
            ban_reason = ban_player_data["ban_reason"]
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

    # 玩家封禁函数封装(被封禁者再次加入游戏,通过device_id判断)
    def ban_player_when_PlayerList_by_device_id(self, player):
        if self.is_record_device_id:
            while True:
                if self.thread_lock_by_get_device_id:
                    self.thread_lock_by_get_device_id = False
                    try_time = 0
                    while True:
                        time.sleep(3.5)
                        self.game_ctrl.sendwocmd(
                            f'/execute at "{player}" run tp "{self.bot_name}" ~ 320 ~'
                        )
                        time.sleep(0.5)
                        player_data = self.frame.launcher.omega.get_player_by_name(
                            player
                        )
                        try_time += 1
                        if player_data is None or (
                            player_data and player_data.device_id == ""
                        ):
                            if try_time >= self.record_device_id_try_time:
                                fmts.print_inf(
                                    f"§c获取玩家 {player} 设备号失败，这可能是因为玩家进服后秒退或者玩家暂未完全进入服务器，当前尝试次数{try_time}/{self.record_device_id_try_time}，这是最后一次尝试"
                                )
                                break
                            fmts.print_inf(
                                f"§c获取玩家 {player} 设备号失败，这可能是因为玩家进服后秒退或者玩家暂未完全进入服务器，当前尝试次数{try_time}/{self.record_device_id_try_time}，将在4秒后再次尝试查询"
                            )
                        else:
                            device_id = player_data.device_id
                            fmts.print_inf(f"§b玩家 {player} 的 设备号: {device_id}")
                            xuid = self.xuid_getter.get_xuid_by_name(player, True)
                            path_device_id = f"{self.data_path}/玩家设备号记录.json"
                            device_id_record = tempjson.load_and_read(
                                path_device_id,
                                need_file_exists=False,
                                default={},
                                timeout=2,
                            )
                            if device_id not in device_id_record:
                                device_id_record[device_id] = {}

                            device_id_record[device_id][xuid] = player
                            tempjson.load_and_write(
                                path_device_id,
                                device_id_record,
                                need_file_exists=False,
                                timeout=2,
                            )
                            tempjson.flush(path_device_id)
                            tempjson.unload_to_path(path_device_id)

                            if self.is_ban_player_by_device_id:
                                for k, v in device_id_record.items():
                                    if k == device_id:
                                        for x, n in v.items():
                                            if x != xuid:
                                                try:
                                                    path_ban_time = f"{self.data_path}/玩家封禁时间数据/{x}.json"
                                                    ban_record = tempjson.load_and_read(
                                                        path_ban_time,
                                                        need_file_exists=True,
                                                        timeout=2,
                                                    )
                                                    tempjson.unload_to_path(
                                                        path_ban_time
                                                    )
                                                    if ban_record is None:
                                                        os.remove(path_ban_time)
                                                    else:
                                                        ban_start = ban_record[
                                                            "ban_start"
                                                        ]
                                                        ban_start_timestamp = (
                                                            ban_record[
                                                                "ban_start_timestamp"
                                                            ]
                                                        )
                                                        ban_until = ban_record[
                                                            "ban_until"
                                                        ]
                                                        ban_until_timestamp = (
                                                            ban_record[
                                                                "ban_until_timestamp"
                                                            ]
                                                        )
                                                        ban_reason = ban_record[
                                                            "ban_reason"
                                                        ]

                                                        if (
                                                            type(ban_until_timestamp)
                                                            is int
                                                        ):
                                                            ban_until_date = time.strftime(
                                                                "%Y-%m-%d %H:%M:%S",
                                                                time.localtime(
                                                                    ban_until_timestamp
                                                                ),
                                                            )
                                                            timestamp_now = int(
                                                                time.time()
                                                            )
                                                            if (
                                                                ban_until_timestamp
                                                                > timestamp_now
                                                            ):
                                                                fmts.print_inf(
                                                                    f"§c发现 {player} 被封禁且尝试开小号进入游戏 (设备号:{device_id},曾登录此设备的玩家:{n}) ，正在踢出，其解封时间为：{ban_until_date}"
                                                                )
                                                                self.game_ctrl.sendwocmd(
                                                                    f'/kick "{player}" 由于{ban_reason}，您被系统封禁至：{ban_until_date}'
                                                                )
                                                                fmts.print_inf(
                                                                    f"§a发现 {player} 被封禁且尝试开小号进入游戏 (设备号:{device_id},曾登录此设备的玩家:{n}) ，已被踢出游戏"
                                                                )
                                                                time.sleep(2)
                                                                path_ban_player_by_device_id = f"{self.data_path}/玩家封禁时间数据/{xuid}.json"
                                                                tempjson.load_and_write(
                                                                    path_ban_player_by_device_id,
                                                                    {
                                                                        "xuid": xuid,
                                                                        "name": player,
                                                                        "ban_start": ban_start,
                                                                        "ban_start_timestamp": ban_start_timestamp,
                                                                        "ban_until": ban_until,
                                                                        "ban_until_timestamp": ban_until_timestamp,
                                                                        "ban_reason": ban_reason,
                                                                    },
                                                                    need_file_exists=False,
                                                                    timeout=2,
                                                                )
                                                                tempjson.flush(
                                                                    path_ban_player_by_device_id
                                                                )
                                                                tempjson.unload_to_path(
                                                                    path_ban_player_by_device_id
                                                                )
                                                                break

                                                            os.remove(path_ban_time)

                                                        elif (
                                                            ban_until_timestamp
                                                            == "Forever"
                                                        ):
                                                            fmts.print_inf(
                                                                f"§c发现 {player} 被封禁且尝试开小号进入游戏 (设备号:{device_id},曾登录此设备的玩家:{n}) ，正在踢出，该玩家为永久封禁"
                                                            )
                                                            self.game_ctrl.sendwocmd(
                                                                f'/kick "{player}" 由于{ban_reason}，您被系统封禁至：Forever'
                                                            )
                                                            fmts.print_inf(
                                                                f"§a发现 {player} 被封禁且尝试开小号进入游戏 (设备号:{device_id},曾登录此设备的玩家:{n}) ，已被踢出游戏"
                                                            )
                                                            time.sleep(2)
                                                            path_ban_player_by_device_id = f"{self.data_path}/玩家封禁时间数据/{xuid}.json"
                                                            tempjson.load_and_write(
                                                                path_ban_player_by_device_id,
                                                                {
                                                                    "xuid": xuid,
                                                                    "name": player,
                                                                    "ban_start": ban_start,
                                                                    "ban_start_timestamp": ban_start_timestamp,
                                                                    "ban_until": "Forever",
                                                                    "ban_until_timestamp": "Forever",
                                                                    "ban_reason": ban_reason,
                                                                },
                                                                need_file_exists=False,
                                                                timeout=2,
                                                            )
                                                            tempjson.flush(
                                                                path_ban_player_by_device_id
                                                            )
                                                            tempjson.unload_to_path(
                                                                path_ban_player_by_device_id
                                                            )
                                                            break

                                                except FileNotFoundError:
                                                    continue
                                        break
                            break

                    self.thread_lock_by_get_device_id = True
                    break

                time.sleep(1)


entry = plugin_entry(BattleEye, "BattleEye")

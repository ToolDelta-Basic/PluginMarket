from tooldelta import Plugin, Player, plugin_entry, cfg, utils, fmts, TYPE_CHECKING
from tooldelta.constants import PacketIDS
from tooldelta.utils import tempjson
import time
import json
import re
import os
import requests
import random
import math
import threading
import base64


# 插件主类
class Orion_System(Plugin):
    name = "『Orion System』违规与作弊行为综合反制系统"
    author = "style_天枢"
    version = (0, 2, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.CONFIG_DEFAULT = {  # 首次生成的配置
            "是否启用控制台封禁/解封系统": True,
            "是否启用游戏内封禁/解封系统": True,
            "控制台封禁系统触发词": ["ban", "封禁"],
            "游戏内封禁系统触发词": ["ban", "封禁"],
            "控制台解封系统触发词": ["unban", "解封"],
            "游戏内解封系统触发词": ["unban", "解封"],
            "控制台封禁/解封系统每页显示几项": 20,
            "游戏内封禁/解封系统每页显示几项": 20,
            "游戏内封禁/解封系统等待输入超时时间(秒)": 60,
            "<<提示>>游戏内封禁系统API：可将游戏内指令或命令方块通过记分板接入本封禁系统": None,
            "<<提示>>封禁记分板的分数为封禁时长(秒)；若分数为-1，则永久封禁；若分数为0，仅踢出游戏，不作封禁，玩家可以立即重进": None,
            "<<提示>>在封禁操作执行完毕后，对应玩家的封禁记分板分数将会重置": None,
            "是否启用游戏内封禁系统API": True,
            "--游戏内封禁记分板名称": "Ban_System",
            "--游戏内封禁记分板显示名称": "Ban_System",
            "--游戏内封禁记分板检查周期(秒)": 10,
            "是否显示租赁服IP和端口": False,
            "是否隐藏违规行为踢出提示(可将玩家踢出提示转换成***)": False,
            "是否启用机器人IP外进反制": True,
            "是否启用锁服反制(皮肤数据异常)": True,
            "是否启用Steve/Alex皮肤反制": False,
            "是否启用4D皮肤反制": False,
            "是否启用账号等级限制": True,
            "服务器准入等级": 1,
            "是否启用网易屏蔽词名称反制": True,
            "--网易屏蔽词名称检测等待时间(秒)": 2,
            "是否启用自定义违禁词名称反制": True,
            "--名称违禁词是否区分大小写英文字母": False,
            "名称违禁词列表": [
                "狂笑",
                "的蛇",
                "写散文",
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
                "吴旭",
                "旭淳",
                "川烈",
                "九重天",
                "五芒星",
                "南宫",
                "北境",
                "共协",
                "XTS",
                "SR",
                "TZRO",
                "STBY",
                "AFR",
                "SWI",
                "EXC",
                "DZR",
                "ATS",
                "WAD",
                "UBSR",
                "生存圈",
                "天庭",
                "天神之庭",
                "LunarHax",
                "白墙",
                "跑路",
                "走路科技",
                "runaway",
                "导入",
                "busj",
                "万花筒",
                "购买",
                "出售",
                "赞助",
                "充值",
                "氪金",
                "炸服",
                "锁服",
                "崩服",
                "毁服",
                "权威",
                "乐子",
                "户籍",
                "社工库",
                "身份证",
                "开盒",
                "恶俗",
                "esu",
            ],
            "是否自动记录玩家设备号/xuid/历史名称(机器人在玩家登录时需tp至玩家处，与巡逻插件一起使用有概率获取失败，若要根据设备号封禁玩家则必须开启该项)": True,
            "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)": 5,
            "是否检查玩家信息与网易MC客户端是否一致(可用于反制外挂篡改游戏内等级)": False,
            "--如果在网易MC客户端无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新)": False,
            "--如果在网易MC客户端搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏": True,
            "--网易MC客户端检查API响应等待时间(秒)": 10,
            "--网易MC客户端检查API可尝试次数(最后一次尝试依然搜索失败即放弃或踢出)": 3,
            "反制白名单": ["style_天枢", "..."],
            "<<提示>>如果您需要“禁止游戏内私聊(tell,msg,w命令)”，请将机器人踢出游戏后启用sendcommandfeedback，命令为/gamerule sendcommandfeedback true": None,
            "是否禁止游戏内私聊(tell,msg,w命令)": True,
            "--禁止私聊时允许私聊机器人": True,
            "是否禁止游戏内me命令": True,
            "发言反制是否区分大小写英文字母": False,
            "是否启用发言黑名单词检测": True,
            "发言黑名单词列表": [
                "白墙",
                "跑路",
                "runaway",
                "走路科技",
                "busj",
                "万花筒",
                "炸服",
                "锁服",
                "崩服",
                "毁服",
                "权威",
                "乐子",
                "户籍",
                "社工库",
                "身份证",
                "开盒",
                "恶俗",
                "esu",
            ],
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
            "是否根据xuid封禁玩家": True,
            "是否根据设备号封禁玩家": True,
            "--如果根据设备号封禁玩家，是否同时对其施加xuid封禁(由于每次查询设备号均需要一定时间，推荐开启该项)": True,
            "封禁时间_机器人IP外进反制": -1,
            "封禁时间_锁服反制(皮肤数据异常)": -1,
            "封禁时间_Steve/Alex皮肤反制": 0,
            "封禁时间_4D皮肤反制": 0,
            "封禁时间_账号等级限制": 0,
            "封禁时间_网易屏蔽词名称反制": 0,
            "封禁时间_自定义违禁词名称反制": 0,
            "封禁时间_网易MC客户端无法搜索到玩家": 0,
            "封禁时间_网易MC客户端搜到的玩家等级与游戏内等级不同": -1,
            "封禁时间_游戏内私聊(tell,msg,w命令)": 60,
            "封禁时间_游戏内me命令": "0年0月0日0时1分0秒",
            "封禁时间_发言黑名单词检测": "0年0月0日0时0分60秒",
            "封禁时间_发言频率检测": "0年0月0日0时10分0秒",
            "封禁时间_发言字数检测": 60,
            "封禁时间_重复消息刷屏检测": "0年0月0日0时10分0秒",
            "是否启用简约模式(开启该项后，本插件将不在控制台显示反制外挂提示、数据包信息、设备号获取失败和网易MC客户端查询失败提示)": False,
            "<<提示>>为了防止意外事件发生，请不要修改下面这一项！": None,
            "<<提示>>此项默认为True，当新版本插件首次启动时可能会按照新版本插件的要求更新数据文件的格式，并在插件数据文件更新完毕后自动调整为False": None,
            "插件数据文件更新按钮": True,
        }
        self.CONFIG_STD = {  # 配置格式要求
            "是否启用控制台封禁/解封系统": bool,
            "是否启用游戏内封禁/解封系统": bool,
            "控制台封禁系统触发词": cfg.JsonList(str, len_limit=-1),
            "游戏内封禁系统触发词": cfg.JsonList(str, len_limit=-1),
            "控制台解封系统触发词": cfg.JsonList(str, len_limit=-1),
            "游戏内解封系统触发词": cfg.JsonList(str, len_limit=-1),
            "控制台封禁/解封系统每页显示几项": cfg.PInt,
            "游戏内封禁/解封系统每页显示几项": cfg.PInt,
            "游戏内封禁/解封系统等待输入超时时间(秒)": cfg.PNumber,
            "是否启用游戏内封禁系统API": bool,
            "--游戏内封禁记分板名称": str,
            "--游戏内封禁记分板显示名称": str,
            "--游戏内封禁记分板检查周期(秒)": cfg.PNumber,
            "是否显示租赁服IP和端口": bool,
            "是否隐藏违规行为踢出提示(可将玩家踢出提示转换成***)": bool,
            "是否启用机器人IP外进反制": bool,
            "是否启用锁服反制(皮肤数据异常)": bool,
            "是否启用Steve/Alex皮肤反制": bool,
            "是否启用4D皮肤反制": bool,
            "是否启用账号等级限制": bool,
            "服务器准入等级": cfg.PInt,
            "是否启用网易屏蔽词名称反制": bool,
            "--网易屏蔽词名称检测等待时间(秒)": cfg.PNumber,
            "是否启用自定义违禁词名称反制": bool,
            "--名称违禁词是否区分大小写英文字母": bool,
            "名称违禁词列表": cfg.JsonList(str, len_limit=-1),
            "是否自动记录玩家设备号/xuid/历史名称(机器人在玩家登录时需tp至玩家处，与巡逻插件一起使用有概率获取失败，若要根据设备号封禁玩家则必须开启该项)": bool,
            "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)": cfg.PInt,
            "是否检查玩家信息与网易MC客户端是否一致(可用于反制外挂篡改游戏内等级)": bool,
            "--如果在网易MC客户端无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新)": bool,
            "--如果在网易MC客户端搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏": bool,
            "--网易MC客户端检查API响应等待时间(秒)": cfg.PNumber,
            "--网易MC客户端检查API可尝试次数(最后一次尝试依然搜索失败即放弃或踢出)": cfg.PInt,
            "反制白名单": cfg.JsonList(str, len_limit=-1),
            "是否禁止游戏内私聊(tell,msg,w命令)": bool,
            "--禁止私聊时允许私聊机器人": bool,
            "是否禁止游戏内me命令": bool,
            "发言反制是否区分大小写英文字母": bool,
            "是否启用发言黑名单词检测": bool,
            "发言黑名单词列表": cfg.JsonList(str, len_limit=-1),
            "发言检测周期(秒)": cfg.PNumber,
            "是否启用周期内发言频率检测": bool,
            "周期内发言条数限制": cfg.PInt,
            "是否启用发言字数检测(单条文本)": bool,
            "发言字数限制": cfg.PInt,
            "是否启用重复消息刷屏检测": bool,
            "周期内重复消息刷屏数量限制": cfg.PInt,
            "是否根据xuid封禁玩家": bool,
            "是否根据设备号封禁玩家": bool,
            "--如果根据设备号封禁玩家，是否同时对其施加xuid封禁(由于每次查询设备号均需要一定时间，推荐开启该项)": bool,
            "封禁时间_机器人IP外进反制": [int, str],
            "封禁时间_锁服反制(皮肤数据异常)": [int, str],
            "封禁时间_Steve/Alex皮肤反制": [int, str],
            "封禁时间_4D皮肤反制": [int, str],
            "封禁时间_账号等级限制": [int, str],
            "封禁时间_网易屏蔽词名称反制": [int, str],
            "封禁时间_自定义违禁词名称反制": [int, str],
            "封禁时间_网易MC客户端无法搜索到玩家": [int, str],
            "封禁时间_网易MC客户端搜到的玩家等级与游戏内等级不同": [int, str],
            "封禁时间_游戏内私聊(tell,msg,w命令)": [int, str],
            "封禁时间_游戏内me命令": [int, str],
            "封禁时间_发言黑名单词检测": [int, str],
            "封禁时间_发言频率检测": [int, str],
            "封禁时间_发言字数检测": [int, str],
            "封禁时间_重复消息刷屏检测": [int, str],
            "是否启用简约模式(开启该项后，本插件将不在控制台显示反制外挂提示、数据包信息、设备号获取失败和网易MC客户端查询失败提示)": bool,
            "插件数据文件更新按钮": bool,
        }

        # 加载插件配置文件，如果发现配置key名有误（一般是因为插件本体更新而配置未更新），将自动更新配置文件
        try:
            self.load_config()
        except cfg.ConfigKeyError as error:
            fmts.print_war(
                f"§e<『Orion System』违规与作弊行为综合反制系统> §6警告：发现插件配置文件中有{error}，这可能是因为插件本体已更新而插件配置文件未更新，已自动替换为新版配置文件"
            )
            os.remove(f"插件配置文件/{self.name}.json")
            self.load_config()

        # 这是获取玩家设备号函数的线程锁，要求当多个玩家连续登录时逐个获取设备号，而不是连续tp最后啥也没得到
        # 当连续多个玩家进入游戏后，只允许一个线程获取device_id，其他获取device_id的线程处于等待状态，直到获取到当前玩家设备号或超时后再执行下一个线程
        self.thread_lock_by_get_device_id = threading.Lock()

        # 这是玩家封禁函数的线程锁，要求在封禁玩家时如果有相同路径读取操作时逐一读取磁盘，防止出现冲突或报错
        self.thread_lock_ban_player_by_xuid = threading.Lock()
        self.thread_lock_ban_player_by_device_id = threading.Lock()

        # 这是用于刷新“检测发言频率”和“检测重复刷屏”缓存的计时器的线程锁，防止异步资源访问时出现冲突
        self.thread_lock_timer = threading.Lock()

        os.makedirs(f"{self.data_path}/玩家封禁时间数据(以xuid记录)", exist_ok=True)
        os.makedirs(f"{self.data_path}/玩家封禁时间数据(以设备号记录)", exist_ok=True)

        if self.is_distinguish_upper_or_lower_in_self_banned_word is False:
            self.banned_word_list = [word.upper() for word in self.banned_word_list]
        if self.is_distinguish_upper_or_lower_on_chat is False:
            self.blacklist_word_list = [
                word.upper() for word in self.blacklist_word_list
            ]

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        # 监听PlayerList数据包
        self.ListenPacket(PacketIDS.IDPlayerList, self.on_PlayerList)
        # 监听Text数据包
        self.ListenPacket(PacketIDS.IDText, self.on_Text)

        # 创建异步计时器，用于刷新“检测发言频率”和“检测重复刷屏”的缓存
        if self.speak_speed_limit or self.repeat_message_limit:
            self.message_data = {}
            self.timer()

        self.upgrade_plugin_data()
        self.remove_expire_ban_data()
        self.query_server_IP_and_port()

    # 调用配置
    def load_config(self):
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, self.CONFIG_STD, self.CONFIG_DEFAULT, self.version
        )
        config = self.config
        self.is_terminal_ban_system = config["是否启用控制台封禁/解封系统"]
        self.is_game_ban_system = config["是否启用游戏内封禁/解封系统"]
        self.terminal_ban_trigger_words = config["控制台封禁系统触发词"]
        self.game_ban_trigger_words = config["游戏内封禁系统触发词"]
        self.terminal_unban_trigger_words = config["控制台解封系统触发词"]
        self.game_unban_trigger_words = config["游戏内解封系统触发词"]
        self.terminal_items_per_page = config["控制台封禁/解封系统每页显示几项"]
        self.game_items_per_page = config["游戏内封禁/解封系统每页显示几项"]
        self.ban_player_by_game_timeout = config[
            "游戏内封禁/解封系统等待输入超时时间(秒)"
        ]
        self.is_ban_api_in_game = config["是否启用游戏内封禁系统API"]
        self.ban_scoreboard_name = config["--游戏内封禁记分板名称"]
        self.ban_scoreboard_dummy_name = config["--游戏内封禁记分板显示名称"]
        self.ban_scoreboard_detect_cycle = config["--游戏内封禁记分板检查周期(秒)"]
        self.is_query_IP_and_port = config["是否显示租赁服IP和端口"]
        self.is_hide_ban_info = config[
            "是否隐藏违规行为踢出提示(可将玩家踢出提示转换成***)"
        ]
        self.is_detect_bot = config["是否启用机器人IP外进反制"]
        self.is_detect_abnormal_skin = config["是否启用锁服反制(皮肤数据异常)"]
        self.is_ban_Steve_or_Alex = config["是否启用Steve/Alex皮肤反制"]
        self.is_ban_4D_skin = config["是否启用4D皮肤反制"]
        self.is_level_limit = config["是否启用账号等级限制"]
        self.server_level = config["服务器准入等级"]
        self.is_detect_netease_banned_word = config["是否启用网易屏蔽词名称反制"]
        self.detect_netease_banned_word_timeout = config[
            "--网易屏蔽词名称检测等待时间(秒)"
        ]
        self.is_detect_self_banned_word = config["是否启用自定义违禁词名称反制"]
        self.is_distinguish_upper_or_lower_in_self_banned_word = config[
            "--名称违禁词是否区分大小写英文字母"
        ]
        self.banned_word_list = config["名称违禁词列表"]
        self.is_get_device_id = config[
            "是否自动记录玩家设备号/xuid/历史名称(机器人在玩家登录时需tp至玩家处，与巡逻插件一起使用有概率获取失败，若要根据设备号封禁玩家则必须开启该项)"
        ]
        self.record_device_id_try_time = config[
            "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)"
        ]
        self.is_check_player_info = config[
            "是否检查玩家信息与网易MC客户端是否一致(可用于反制外挂篡改游戏内等级)"
        ]
        self.is_ban_player_if_cannot_search = config[
            "--如果在网易MC客户端无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新)"
        ]
        self.is_ban_player_if_different_level = config[
            "--如果在网易MC客户端搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏"
        ]
        self.check_player_info_api_timeout = config[
            "--网易MC客户端检查API响应等待时间(秒)"
        ]
        self.check_player_info_api_try_time = config[
            "--网易MC客户端检查API可尝试次数(最后一次尝试依然搜索失败即放弃或踢出)"
        ]
        self.whitelist = config["反制白名单"]
        self.ban_private_chat = config["是否禁止游戏内私聊(tell,msg,w命令)"]
        self.allow_chat_with_bot = config["--禁止私聊时允许私聊机器人"]
        self.ban_me_command = config["是否禁止游戏内me命令"]
        self.is_distinguish_upper_or_lower_on_chat = config[
            "发言反制是否区分大小写英文字母"
        ]
        self.Testfor_blacklist_word = config["是否启用发言黑名单词检测"]
        self.blacklist_word_list = config["发言黑名单词列表"]
        self.speak_detection_cycle = config["发言检测周期(秒)"]
        self.speak_speed_limit = config["是否启用周期内发言频率检测"]
        self.max_speak_count = config["周期内发言条数限制"]
        self.message_length_limit = config["是否启用发言字数检测(单条文本)"]
        self.max_speak_length = config["发言字数限制"]
        self.repeat_message_limit = config["是否启用重复消息刷屏检测"]
        self.max_repeat_count = config["周期内重复消息刷屏数量限制"]
        self.is_ban_player_by_xuid = config["是否根据xuid封禁玩家"]
        self.is_ban_player_by_device_id = config["是否根据设备号封禁玩家"]
        self.jointly_ban_player = config[
            "--如果根据设备号封禁玩家，是否同时对其施加xuid封禁(由于每次查询设备号均需要一定时间，推荐开启该项)"
        ]
        self.ban_time_detect_bot = config["封禁时间_机器人IP外进反制"]
        self.ban_time_detect_abnormal_skin = config["封禁时间_锁服反制(皮肤数据异常)"]
        self.ban_time_Steve_or_Alex = config["封禁时间_Steve/Alex皮肤反制"]
        self.ban_time_4D_skin = config["封禁时间_4D皮肤反制"]
        self.ban_time_level_limit = config["封禁时间_账号等级限制"]
        self.ban_time_detect_netease_banned_word = config["封禁时间_网易屏蔽词名称反制"]
        self.ban_time_detect_self_banned_word = config["封禁时间_自定义违禁词名称反制"]
        self.ban_time_if_cannot_search = config["封禁时间_网易MC客户端无法搜索到玩家"]
        self.ban_time_if_different_level = config[
            "封禁时间_网易MC客户端搜到的玩家等级与游戏内等级不同"
        ]
        self.ban_time_private_chat = config["封禁时间_游戏内私聊(tell,msg,w命令)"]
        self.ban_time_me_command = config["封禁时间_游戏内me命令"]
        self.ban_time_testfor_blacklist_word = config["封禁时间_发言黑名单词检测"]
        self.ban_time_speak_speed_limit = config["封禁时间_发言频率检测"]
        self.ban_time_message_length_limit = config["封禁时间_发言字数检测"]
        self.ban_time_repeat_message_limit = config["封禁时间_重复消息刷屏检测"]
        self.simplified_mode = config[
            "是否启用简约模式(开启该项后，本插件将不在控制台显示反制外挂提示、数据包信息、设备号获取失败和网易MC客户端查询失败提示)"
        ]
        self.upgrade_plugin_data_file = config["插件数据文件更新按钮"]

    # 创建发言周期检测计时器
    @utils.thread_func("发言周期检测计时器")
    def timer(self):
        while True:
            with self.thread_lock_timer:
                # 此处设置list是为了创建遍历字典的副本，防止在字典内删除键值对触发RuntimeError: dictionary changed size during iteration报错
                for k, v in list(self.message_data.items()):
                    if v["timer"] > 0:
                        v["timer"] -= 1
                    else:
                        self.message_data.pop(k, None)
            time.sleep(1)

    ##############################################！插件数据文件更新按钮作用域<HEAD>！
    ############################################## 本次更新内容：由于设备号快速获取方式需要，将数据文件中的设备号全部改为大写，将数据文件中的|换成丨以适应Windows系统
    def upgrade_plugin_data(self):
        if self.upgrade_plugin_data_file:
            old_data_path = f"{self.data_path}/玩家|设备号|xuid|历史名称|记录.json"
            path_device_id = f"{self.data_path}/玩家丨设备号丨xuid丨历史名称丨记录.json"
            if os.path.exists(old_data_path) and not os.path.exists(path_device_id):
                os.rename(old_data_path, path_device_id)
            with self.thread_lock_ban_player_by_device_id:
                device_id_data = tempjson.load_and_read(
                    path_device_id, need_file_exists=False, default={}, timeout=2
                )
                tempjson.unload_to_path(path_device_id)
                for old_device_id in list(device_id_data.keys()):
                    device_id_data[old_device_id.upper()] = device_id_data.pop(
                        old_device_id
                    )
                tempjson.load_and_write(
                    path_device_id,
                    device_id_data,
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path_device_id)
                tempjson.unload_to_path(path_device_id)
            path_ban_time = f"{self.data_path}/玩家封禁时间数据(以设备号记录)"
            for ban_file_name in os.listdir(path_ban_time):
                old_path = os.path.join(path_ban_time, ban_file_name)
                if ban_file_name.endswith(".json"):
                    main_name, ext_name = os.path.splitext(ban_file_name)
                    new_main_name = main_name.upper()
                    new_file_name = new_main_name + ext_name
                    new_path = os.path.join(path_ban_time, new_file_name)
                    if not os.path.exists(new_path):
                        os.rename(old_path, new_path)
            self.config["插件数据文件更新按钮"] = False
            cfg.upgrade_plugin_config(self.name, self.config, self.version)

    ##############################################！插件数据文件更新按钮作用域<END>！
    ##############################################

    def on_preload(self):
        self.xuid_getter = self.GetPluginAPI("XUID获取")
        if self.is_game_ban_system:
            self.chatbar = self.GetPluginAPI("聊天栏菜单")
        # 进行导入前置插件的类型检查，防止出现意外报错
        if TYPE_CHECKING:
            from 前置_玩家XUID获取 import XUIDGetter

            self.xuid_getter: XUIDGetter

            if self.is_game_ban_system:
                from 前置_聊天栏菜单 import ChatbarMenu

                self.chatbar: ChatbarMenu

    def on_active(self):
        if not self.simplified_mode:
            fmts.print_inf(
                "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
            )
            fmts.print_inf(
                "§l§d❐§f 『§6Orion System §d猎户座§f』 §b违规与作弊行为§e综合§a反制§d系统"
            )
            fmts.print_inf("§a❀ §b反制外挂の重要提示！")
            fmts.print_inf("§a❀ §e目前较为流行的锁服方法为 §b坐骑+传送锁服")
            fmts.print_inf(
                "§a❀ §d反制方法： §e请在您的租赁服的常加载区域设置 §b循环命令方块：/ride @a stop_riding"
            )
            fmts.print_inf(
                "§a❀ §d注意：§e由于性能原因，我们不建议通过机器人插件循环执行上述命令，§b请您在游戏中通过命令方块进行防御！"
            )
            fmts.print_inf(
                "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
            )
            fmts.print_inf(
                "§a❀ §e如果您需要“禁止游戏内私聊(tell,msg,w命令)”，§b请将机器人踢出游戏后启用sendcommandfeedback，命令为/gamerule sendcommandfeedback true"
            )

        # 在控制台菜单注册封禁/解封系统触发词
        if self.is_terminal_ban_system:
            self.frame.add_console_cmd_trigger(
                self.terminal_ban_trigger_words,
                [],
                "封禁系统-来自<『Orion System』违规与作弊行为综合反制系统>",
                self.ban_player_by_terminal,
            )
            self.frame.add_console_cmd_trigger(
                self.terminal_unban_trigger_words,
                [],
                "解封系统-来自<『Orion System』违规与作弊行为综合反制系统>",
                self.unban_player_by_terminal,
            )

        # 在游戏内聊天栏菜单注册封禁/解封系统触发词
        if self.is_game_ban_system:
            self.chatbar.add_new_trigger(
                self.game_ban_trigger_words,
                [],
                "封禁系统-来自<『Orion System』违规与作弊行为综合反制系统>",
                self.ban_player_by_game,
                op_only=True,
            )
            self.chatbar.add_new_trigger(
                self.game_unban_trigger_words,
                [],
                "解封系统-来自<『Orion System』违规与作弊行为综合反制系统>",
                self.unban_player_by_game,
                op_only=True,
            )

        self.ban_player_when_plugin_active()

        if self.is_ban_api_in_game:
            self.game_ctrl.sendwocmd(
                f'/scoreboard objectives add "{self.ban_scoreboard_name}" dummy "{self.ban_scoreboard_dummy_name}"'
            )
            self.ban_api_in_game()

    def on_PlayerList(self, packet):
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
            SkinData = packet["Entries"][0]["Skin"]["SkinData"]
            GrowthLevels = packet["GrowthLevels"][0]

            self.get_player_device_id(Username, xuid, SkinID)

            if Username not in self.whitelist:
                self.ban_bot(Username, xuid, PremiumSkin, Trusted, packet)
                self.ban_abnormal_skin(
                    Username, xuid, SkinImageWidth, SkinImageHeight, SkinData
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

    def on_Text(self, packet):
        xuid = packet["XUID"]
        # "TextType"=10:监听到命令执行反馈
        if packet["TextType"] == 10 and xuid != "":
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
                            if target_player != self.game_ctrl.bot_name:
                                fmts.print_inf(
                                    f"§c发现 {original_player} 尝试发送私聊(tell,msg,w命令)，正在踢出"
                                )
                                self.game_ctrl.sendwocmd(
                                    self.try_hide_ban_info(
                                        f'/kick "{original_player}" 禁止发送私聊(tell,msg,w命令)！'
                                    )
                                )
                                fmts.print_inf(
                                    f"§a发现 {original_player} 尝试发送私聊(tell,msg,w命令)，已被踢出游戏"
                                )
                                self.ban_player_by_xuid(
                                    original_player,
                                    xuid,
                                    self.ban_time_format(self.ban_time_private_chat),
                                    "您尝试发送私聊(tell,msg,w命令)",
                                )
                                self.ban_player_by_device_id(
                                    original_player,
                                    xuid,
                                    self.ban_time_format(self.ban_time_private_chat),
                                    "您尝试发送私聊(tell,msg,w命令)",
                                )
                        else:
                            fmts.print_inf(
                                f"§c发现 {original_player} 尝试发送私聊(tell,msg,w命令)，正在踢出"
                            )
                            self.game_ctrl.sendwocmd(
                                self.try_hide_ban_info(
                                    f'/kick "{original_player}" 禁止发送私聊(tell,msg,w命令)！'
                                )
                            )
                            fmts.print_inf(
                                f"§a发现 {original_player} 尝试发送私聊(tell,msg,w命令)，已被踢出游戏"
                            )
                            self.ban_player_by_xuid(
                                original_player,
                                xuid,
                                self.ban_time_format(self.ban_time_private_chat),
                                "您尝试发送私聊(tell,msg,w命令)",
                            )
                            self.ban_player_by_device_id(
                                original_player,
                                xuid,
                                self.ban_time_format(self.ban_time_private_chat),
                                "您尝试发送私聊(tell,msg,w命令)",
                            )
                    self.blacklist_word_detect(msg_text, original_player, xuid)
                    self.message_length_detect(msg_text, original_player, xuid)
                    self.message_cache_area(msg_text, original_player, xuid)
            except Exception as error:
                fmts.print_err(
                    f"在解析私聊数据包或某些命令数据包时出现错误: {str(error)}"
                )

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
                        self.game_ctrl.sendwocmd(
                            self.try_hide_ban_info(f'/kick "{player}" 禁止发送me命令！')
                        )
                        fmts.print_inf(f"§a发现 {player} 尝试发送me命令，已被踢出游戏")
                        self.ban_player_by_xuid(
                            player,
                            xuid,
                            self.ban_time_format(self.ban_time_me_command),
                            "您尝试发送me命令",
                        )
                        self.ban_player_by_device_id(
                            player,
                            xuid,
                            self.ban_time_format(self.ban_time_me_command),
                            "您尝试发送me命令",
                        )
                    self.blacklist_word_detect(msg_text, player, xuid)
                    self.message_length_detect(msg_text, player, xuid)
                    self.message_cache_area(msg_text, player, xuid)
                # 判断为常规发言
                elif sourcename != "" and xuid == "":
                    vip_sourcename_match = re.search(r"<([^>]*)><([^>]*)>", sourcename)
                    if vip_sourcename_match:
                        sourcename = vip_sourcename_match.group(2)
                    xuid = self.xuid_getter.get_xuid_by_name(sourcename, True)
                    self.blacklist_word_detect(message, sourcename, xuid)
                    self.message_length_detect(message, sourcename, xuid)
                    self.message_cache_area(message, sourcename, xuid)
            except Exception as error:
                fmts.print_err(f"在解析发言数据包或me命令时出现错误 {str(error)}")

        return False

    # 查询租赁服IP和端口函数封装

    @utils.thread_func("查询租赁服IP和端口函数")
    def query_server_IP_and_port(self):
        if self.is_query_IP_and_port:
            try:
                path_tooldelta_basic_config = "ToolDelta基本配置.json"
                tooldelta_basic_config = tempjson.load_and_read(
                    path_tooldelta_basic_config,
                    need_file_exists=True,
                    default={},
                    timeout=2,
                )
                tempjson.unload_to_path(path_tooldelta_basic_config)
                server_name = tooldelta_basic_config["NeOmega接入点启动模式"][
                    "服务器号"
                ]
                pwd = tooldelta_basic_config["NeOmega接入点启动模式"]["密码"]
                url = "http://198.44.179.197:5000/api/server_id"
                data = {"server_name": server_name, "pwd": pwd}
                result = requests.post(url, data=data)
                fmts.print_inf(f"§b服务器号:{server_name}，本{result.text}")
            except Exception as error:
                fmts.print_inf(f"§c查询租赁服IP和端口失败，原因：{error}")

    # 反制机器人函数封装

    @utils.thread_func("反制机器人函数")
    def ban_bot(self, Username, xuid, PremiumSkin, Trusted, packet):
        if self.is_detect_bot and (PremiumSkin is False or Trusted is False):
            fmts.print_inf(f"§c发现 {Username} 可能为崩服机器人，正在制裁")
            if not self.simplified_mode:
                fmts.print_war(f"崩服机器人数据: {packet}")
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(
                    f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                )
            )
            fmts.print_inf(f"§a发现 {Username} 可能为崩服机器人，制裁已完成")
            self.ban_player_by_xuid(
                Username,
                xuid,
                self.ban_time_format(self.ban_time_detect_bot),
                "您必须通过 Microsoft 服务身份验证。",
            )
            self.ban_player_by_device_id(
                Username,
                xuid,
                self.ban_time_format(self.ban_time_detect_bot),
                "您必须通过 Microsoft 服务身份验证。",
            )

    # 反制锁服函数封装(皮肤数据异常)

    @utils.thread_func("反制锁服函数(皮肤数据异常)")
    def ban_abnormal_skin(
        self, Username, xuid, SkinImageWidth, SkinImageHeight, SkinData
    ):
        if self.is_detect_abnormal_skin:
            try:
                decode_skinData = base64.b64decode(SkinData)
                SkinData_bytes_len = len(decode_skinData)
                if (
                    (SkinImageWidth * SkinImageHeight * 4 != SkinData_bytes_len)
                    or (SkinImageWidth not in (64, 128, 256, 512))
                    or (SkinImageHeight not in (64, 128, 256, 512))
                ):
                    fmts.print_inf(f"§c发现 {Username} 可能尝试锁服，正在制裁")
                    self.game_ctrl.sendwocmd(
                        self.try_hide_ban_info(
                            f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                        )
                    )
                    fmts.print_inf(f"§a发现 {Username} 可能尝试锁服，已被踢出游戏")
                    self.ban_player_by_xuid(
                        Username,
                        xuid,
                        self.ban_time_format(self.ban_time_detect_abnormal_skin),
                        "您必须通过 Microsoft 服务身份验证。",
                    )
                    self.ban_player_by_device_id(
                        Username,
                        xuid,
                        self.ban_time_format(self.ban_time_detect_abnormal_skin),
                        "您必须通过 Microsoft 服务身份验证。",
                    )
            except Exception:
                fmts.print_inf(f"§c发现 {Username} 皮肤数据异常，正在制裁")
                self.game_ctrl.sendwocmd(
                    self.try_hide_ban_info(
                        f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                    )
                )
                fmts.print_inf(f"§a发现 {Username} 皮肤数据异常，已被踢出游戏")
                self.ban_player_by_xuid(
                    Username,
                    xuid,
                    self.ban_time_format(self.ban_time_detect_abnormal_skin),
                    "您必须通过 Microsoft 服务身份验证。",
                )
                self.ban_player_by_device_id(
                    Username,
                    xuid,
                    self.ban_time_format(self.ban_time_detect_abnormal_skin),
                    "您必须通过 Microsoft 服务身份验证。",
                )

    # 反制Steve/Alex皮肤函数封装

    @utils.thread_func("反制Steve/Alex皮肤函数")
    def ban_Steve_or_Alex(
        self, Username, xuid, SkinID, GeometryDataEngineVersion, PersonaSkin
    ):
        if self.is_ban_Steve_or_Alex and (
            SkinID
            in (
                "c18e65aa-7b21-4637-9b63-8ad63622ef01.Steve",
                "c18e65aa-7b21-4637-9b63-8ad63622ef01.Alex",
            )
            # Base64 解码：MS4xNC4w → 1.14.0
            or GeometryDataEngineVersion == "MS4xNC4w"
            or PersonaSkin is True
        ):
            fmts.print_inf(f"§c发现 {Username} 皮肤为Steve/Alex，正在踢出")
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(
                    f'/kick "{Username}" 不要使用Steve/Alex皮肤噢，去换个更好的吧~'
                )
            )
            fmts.print_inf(f"§a发现 {Username} 皮肤为Steve/Alex，已被踢出游戏")
            self.ban_player_by_xuid(
                Username,
                xuid,
                self.ban_time_format(self.ban_time_Steve_or_Alex),
                "您必须通过 Microsoft 服务身份验证。",
            )
            self.ban_player_by_device_id(
                Username,
                xuid,
                self.ban_time_format(self.ban_time_Steve_or_Alex),
                "您必须通过 Microsoft 服务身份验证。",
            )

    # 反制4D皮肤函数封装

    @utils.thread_func("反制4D皮肤函数")
    def ban_4D_skin(self, Username, xuid, GeometryDataEngineVersion):
        # Base64 解码：MS4yLjU= → 1.2.5
        if self.is_ban_4D_skin and GeometryDataEngineVersion == "MS4yLjU=":
            fmts.print_inf(f"§c发现 {Username} 皮肤为4D皮肤，正在踢出")
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(
                    f'/kick "{Username}" 不要使用4D皮肤噢，去换一个吧~'
                )
            )
            fmts.print_inf(f"§a发现 {Username} 皮肤为4D皮肤，已被踢出游戏")
            self.ban_player_by_xuid(
                Username,
                xuid,
                self.ban_time_format(self.ban_time_4D_skin),
                "您必须通过 Microsoft 服务身份验证。",
            )
            self.ban_player_by_device_id(
                Username,
                xuid,
                self.ban_time_format(self.ban_time_4D_skin),
                "您必须通过 Microsoft 服务身份验证。",
            )

    # 反制等级过低玩家函数封装

    @utils.thread_func("反制等级过低玩家函数")
    def ban_player_level_too_low(self, Username, xuid, GrowthLevels):
        if self.is_level_limit and GrowthLevels < self.server_level:
            fmts.print_inf(
                f"§c发现 {Username} 等级低于服务器准入等级({self.server_level}级)，正在踢出"
            )
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(
                    f'/kick "{Username}" 本服准入等级为{self.server_level}级，您的等级过低，请加油升级噢！'
                )
            )
            fmts.print_inf(
                f"§a发现 {Username} 等级低于服务器准入等级({self.server_level}级)，已被踢出游戏"
            )
            self.ban_player_by_xuid(
                Username,
                xuid,
                self.ban_time_format(self.ban_time_level_limit),
                f"您的等级低于服务器准入等级({self.server_level}级)",
            )
            self.ban_player_by_device_id(
                Username,
                xuid,
                self.ban_time_format(self.ban_time_level_limit),
                f"您的等级低于服务器准入等级({self.server_level}级)",
            )

    # 反制网易屏蔽词名称玩家函数封装

    @utils.thread_func("反制网易屏蔽词名称玩家函数")
    def ban_player_with_netease_banned_word(self, Username, xuid):
        if self.is_detect_netease_banned_word:
            try:
                self.game_ctrl.sendcmd(
                    f'/testfor @a[name="{Username}"]',
                    True,
                    self.detect_netease_banned_word_timeout,
                )
            except TimeoutError:
                fmts.print_inf(f"§c发现 {Username} 名称为网易屏蔽词，正在踢出")
                self.game_ctrl.sendwocmd(
                    self.try_hide_ban_info(
                        f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                    )
                )
                fmts.print_inf(f"§a发现 {Username} 名称为网易屏蔽词，已被踢出游戏")
                self.ban_player_by_xuid(
                    Username,
                    xuid,
                    self.ban_time_format(self.ban_time_detect_netease_banned_word),
                    "您的名称为网易屏蔽词",
                )
                self.ban_player_by_device_id(
                    Username,
                    xuid,
                    self.ban_time_format(self.ban_time_detect_netease_banned_word),
                    "您的名称为网易屏蔽词",
                )

    # 反制自定义违禁词名称玩家函数封装

    @utils.thread_func("反制自定义违禁词名称玩家函数")
    def ban_player_with_self_banned_word(self, Username, xuid):
        if self.is_detect_self_banned_word:
            self.banned_word_set = set(self.banned_word_list)
            n = len(Username)
            for i in range(n):
                for j in range(i + 1, n + 1):
                    Username_change = Username
                    if self.is_distinguish_upper_or_lower_in_self_banned_word is False:
                        Username_change = Username.upper()
                    if Username_change[i:j] in self.banned_word_set:
                        fmts.print_inf(
                            f"§c发现 {Username} 名称包括本服自定义违禁词({Username[i:j]})，正在踢出"
                        )
                        self.game_ctrl.sendwocmd(
                            self.try_hide_ban_info(
                                f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                            )
                        )
                        fmts.print_inf(
                            f"§a发现 {Username} 名称包括本服自定义违禁词({Username[i:j]})，已被踢出游戏"
                        )
                        self.ban_player_by_xuid(
                            Username,
                            xuid,
                            self.ban_time_format(self.ban_time_detect_self_banned_word),
                            f"您的名称包括本服自定义违禁词({Username[i:j]})",
                        )
                        self.ban_player_by_device_id(
                            Username,
                            xuid,
                            self.ban_time_format(self.ban_time_detect_self_banned_word),
                            f"您的名称包括本服自定义违禁词({Username[i:j]})",
                        )

    # 网易MC客户端玩家信息检查函数封装

    @utils.thread_func("网易MC客户端玩家信息检查函数")
    def check_player_info(self, Username, xuid, GrowthLevels, packet):
        if self.is_check_player_info:
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
                        timeout=self.check_player_info_api_timeout,
                    )
                    try_time += 1

                    if userdata_from_netease.status_code == 404:
                        if try_time >= self.check_player_info_api_try_time:
                            if not self.simplified_mode:
                                fmts.print_inf(
                                    f"§c在网易MC客户端搜索玩家 {Username} 失败，原因：状态码[{userdata_from_netease.status_code}]，当前尝试次数{try_time}/{self.check_player_info_api_try_time}，这是最后一次尝试"
                                )
                            if self.is_ban_player_if_cannot_search:
                                fmts.print_inf(
                                    f"§c由于我们无法在网易MC客户端搜索到玩家 {Username} ，正在踢出该玩家，这可能是由于“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新”等原因导致的"
                                )
                                self.game_ctrl.sendwocmd(
                                    self.try_hide_ban_info(
                                        f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                                    )
                                )
                                fmts.print_inf(
                                    f"§a由于我们无法在网易MC客户端搜索到玩家 {Username} ，该玩家已被踢出游戏"
                                )
                                self.ban_player_by_xuid(
                                    Username,
                                    xuid,
                                    self.ban_time_format(
                                        self.ban_time_if_cannot_search
                                    ),
                                    "您必须通过 Microsoft 服务身份验证。",
                                )
                                self.ban_player_by_device_id(
                                    Username,
                                    xuid,
                                    self.ban_time_format(
                                        self.ban_time_if_cannot_search
                                    ),
                                    "您必须通过 Microsoft 服务身份验证。",
                                )
                            break

                        try_api_sleep_time = random.randint(
                            15 * try_time, 30 * try_time
                        )
                        if not self.simplified_mode:
                            fmts.print_inf(
                                f"§c在网易MC客户端搜索玩家 {Username} 失败，原因：状态码[{userdata_from_netease.status_code}]，当前尝试次数{try_time}/{self.check_player_info_api_try_time}，将在{try_api_sleep_time}秒后再次尝试搜索"
                            )
                        time.sleep(try_api_sleep_time)

                    elif userdata_from_netease.status_code == 200:
                        userdata_from_netease = userdata_from_netease.json()
                        data = userdata_from_netease["data"]
                        fmts.print_inf(
                            f"§a成功在网易MC客户端搜索到玩家 {Username} ，其客户端等级为{data['lv']}，游戏内等级为{GrowthLevels}"
                        )
                        if (
                            self.is_ban_player_if_different_level
                            and data["lv"] != GrowthLevels
                        ):
                            fmts.print_inf(
                                f"§c由于玩家 {Username} 的客户端等级和游戏内等级不匹配，正在踢出"
                            )
                            if not self.simplified_mode:
                                fmts.print_war(
                                    f"该玩家可能通过外挂篡改游戏内等级: {packet}"
                                )
                            self.game_ctrl.sendwocmd(
                                self.try_hide_ban_info(
                                    f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                                )
                            )
                            fmts.print_inf(
                                f"§a由于玩家 {Username} 的客户端等级和游戏内等级不匹配，已被踢出游戏"
                            )
                            self.ban_player_by_xuid(
                                Username,
                                xuid,
                                self.ban_time_format(self.ban_time_if_different_level),
                                "您必须通过 Microsoft 服务身份验证。",
                            )
                            self.ban_player_by_device_id(
                                Username,
                                xuid,
                                self.ban_time_format(self.ban_time_if_different_level),
                                "您必须通过 Microsoft 服务身份验证。",
                            )
                        break

                    else:
                        break

                except requests.exceptions.Timeout as timeout_error:
                    try_time += 1
                    if try_time >= self.check_player_info_api_try_time:
                        if not self.simplified_mode:
                            fmts.print_inf(
                                f"§c在网易MC客户端搜索玩家 {Username} 失败，原因：请求网易MC客户端玩家信息超时：{timeout_error}，当前尝试次数{try_time}/{self.check_player_info_api_try_time}，这是最后一次尝试"
                            )
                        if self.is_ban_player_if_cannot_search:
                            fmts.print_inf(
                                f"§c由于我们无法在网易MC客户端搜索到玩家 {Username} ，正在踢出该玩家，这可能是由于“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新”等原因导致的"
                            )
                            self.game_ctrl.sendwocmd(
                                self.try_hide_ban_info(
                                    f'/kick "{Username}" 您必须通过 Microsoft 服务身份验证。'
                                )
                            )
                            fmts.print_inf(
                                f"§a由于我们无法在网易MC客户端搜索到玩家 {Username} ，该玩家已被踢出游戏"
                            )
                            self.ban_player_by_xuid(
                                Username,
                                xuid,
                                self.ban_time_format(self.ban_time_if_cannot_search),
                                "您必须通过 Microsoft 服务身份验证。",
                            )
                            self.ban_player_by_device_id(
                                Username,
                                xuid,
                                self.ban_time_format(self.ban_time_if_cannot_search),
                                "您必须通过 Microsoft 服务身份验证。",
                            )
                        break

                    try_api_sleep_time = random.randint(15 * try_time, 30 * try_time)
                    if not self.simplified_mode:
                        fmts.print_inf(
                            f"§c在网易MC客户端搜索玩家 {Username} 失败，原因：请求网易MC客户端玩家信息超时：{timeout_error}，当前尝试次数{try_time}/{self.check_player_info_api_try_time}，将在{try_api_sleep_time}秒后再次尝试搜索"
                        )
                    time.sleep(try_api_sleep_time)

                except requests.exceptions.HTTPError as http_error:
                    fmts.print_err(f"HTTP异常信息：{http_error}")
                    break

                except requests.exceptions.RequestException as error:
                    fmts.print_err(
                        f"请求网易MC客户端玩家信息失败(API请求失败或玩家数据json解析失败)：{error}"
                    )
                    break

    # 发言黑名单词检测函数封装

    @utils.thread_func("发言黑名单词检测函数")
    def blacklist_word_detect(self, message, player, xuid):
        if self.Testfor_blacklist_word and player not in self.whitelist:
            blacklist_word_set = set(self.blacklist_word_list)
            n = len(message)
            for i in range(n):
                for j in range(i + 1, n + 1):
                    message_change = message
                    if self.is_distinguish_upper_or_lower_on_chat is False:
                        message_change = message.upper()
                    if message_change[i:j] in blacklist_word_set:
                        fmts.print_inf(
                            f"§c发现 {player} 发送的文本触发了黑名单词({message[i:j]})，正在踢出"
                        )
                        self.game_ctrl.sendwocmd(
                            self.try_hide_ban_info(
                                f'/kick "{player}" 您发送的文本触发了黑名单词({message[i:j]})'
                            )
                        )
                        fmts.print_inf(
                            f"§a发现 {player} 发送的文本触发了黑名单词({message[i:j]})，已被踢出游戏"
                        )
                        self.ban_player_by_xuid(
                            player,
                            xuid,
                            self.ban_time_format(self.ban_time_testfor_blacklist_word),
                            f"您发送的文本触发了黑名单词({message[i:j]})",
                        )
                        self.ban_player_by_device_id(
                            player,
                            xuid,
                            self.ban_time_format(self.ban_time_testfor_blacklist_word),
                            f"您发送的文本触发了黑名单词({message[i:j]})",
                        )

    # 发言字数检测函数封装

    @utils.thread_func("发言字数检测函数")
    def message_length_detect(self, message, player, xuid):
        if (
            self.message_length_limit
            and len(message) > self.max_speak_length
            and player not in self.whitelist
        ):
            fmts.print_inf(
                f"§c发现 {player} 发送的文本长度超过{self.max_speak_length}，正在踢出"
            )
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(f'/kick "{player}" 您发送的文本过长，请勿刷屏')
            )
            fmts.print_inf(
                f"§a发现 {player} 发送的文本长度超过{self.max_speak_length}，已被踢出游戏"
            )
            self.ban_player_by_xuid(
                player,
                xuid,
                self.ban_time_format(self.ban_time_message_length_limit),
                f"您发送的文本长度超过{self.max_speak_length}字符限制",
            )
            self.ban_player_by_device_id(
                player,
                xuid,
                self.ban_time_format(self.ban_time_message_length_limit),
                f"您发送的文本长度超过{self.max_speak_length}字符限制",
            )

    # 将发言玩家、文本添加至缓存区

    @utils.thread_func("缓存玩家发言数据函数")
    def message_cache_area(self, message, player, xuid):
        if self.speak_speed_limit or self.repeat_message_limit:
            if self.is_distinguish_upper_or_lower_on_chat is False:
                message = message.upper()
            with self.thread_lock_timer:
                if self.message_data.get(player) is None:
                    self.message_data[player] = {}
                    self.message_data[player]["message"] = []
                    self.message_data[player]["timer"] = self.speak_detection_cycle
                self.message_data[player]["message"].append(message)
                self.speak_speed_detect(player, xuid)
                self.repeat_message_detect(player, xuid)

    # 发言频率检测函数封装
    @utils.thread_func("发言频率检测函数")
    def speak_speed_detect(self, player, xuid):
        if (
            self.speak_speed_limit
            and len(self.message_data[player]["message"]) > self.max_speak_count
            and player not in self.whitelist
        ):
            fmts.print_inf(
                f"§c发现 {player} 发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)，正在踢出"
            )
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(f'/kick "{player}" 您发言过快，休息一下吧~')
            )
            fmts.print_inf(
                f"§a发现 {player} 发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)，已被踢出游戏"
            )
            self.ban_player_by_xuid(
                player,
                xuid,
                self.ban_time_format(self.ban_time_speak_speed_limit),
                f"您发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)",
            )
            self.ban_player_by_device_id(
                player,
                xuid,
                self.ban_time_format(self.ban_time_speak_speed_limit),
                f"您发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)",
            )

    # 重复消息刷屏检测函数封装

    @utils.thread_func("重复消息刷屏检测函数")
    def repeat_message_detect(self, player, xuid):
        if self.repeat_message_limit and player not in self.whitelist:
            counts = {}
            for i in self.message_data[player]["message"]:
                counts[i] = counts.get(i, 0) + 1
            for v in counts.values():
                if v > self.max_repeat_count:
                    fmts.print_inf(
                        f"§c发现 {player} 连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)，正在踢出"
                    )
                    self.game_ctrl.sendwocmd(
                        self.try_hide_ban_info(
                            f'/kick "{player}" 您重复刷屏过快，休息一下吧~'
                        )
                    )
                    fmts.print_inf(
                        f"§a发现 {player} 连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)，已被踢出游戏"
                    )
                    self.ban_player_by_xuid(
                        player,
                        xuid,
                        self.ban_time_format(self.ban_time_repeat_message_limit),
                        f"您连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)",
                    )
                    self.ban_player_by_device_id(
                        player,
                        xuid,
                        self.ban_time_format(self.ban_time_repeat_message_limit),
                        f"您连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)",
                    )

    # 格式化玩家封禁时间

    @staticmethod
    def ban_time_format(ban_time):
        # ban_time == -1:永久封禁
        if ban_time in (-1, "-1", "Forever"):
            return "Forever"

        # ban_time == 0:仅踢出游戏，不作封禁，玩家可以立即重进
        if ban_time in (0, "0", "") or ban_time is None:
            return 0

        # type(ban_time) is int and ban_time > 0:封禁玩家对应时间(单位:秒)
        if type(ban_time) is int and ban_time > 0:
            return ban_time

        # type(ban_time) is str:封禁时间为字符串，将尝试进行转换
        if type(ban_time) is str:
            try:
                if int(ban_time) > 0:
                    return int(ban_time)
                fmts.print_war("警告：无法解析您输入的封禁时间")
                return 0
            except ValueError:
                ban_time = ban_time.replace(" ", "")
                matches_time_units = re.findall(r"(\d+)(年|月|日|时|分|秒)", ban_time)
                if not matches_time_units:
                    fmts.print_war(
                        f"警告：封禁时间({ban_time})中无法匹配到任何时间单位，合法的时间单位为(年|月|日|时|分|秒)"
                    )
                    return 0

                ban_time_after_matched = "".join(
                    f"{value}{unit}" for value, unit in matches_time_units
                )
                if ban_time_after_matched != ban_time:
                    fmts.print_war(f"警告：封禁时间({ban_time})中存在无法解析的字符")
                    return 0

                time_units = {}
                for value_str, unit in matches_time_units:
                    if unit in time_units:
                        fmts.print_war(
                            f"警告：封禁时间({ban_time})中存在重复的时间单位：{unit}"
                        )
                        return 0
                    try:
                        value = int(value_str)
                        if value < 0:
                            fmts.print_war(
                                f'警告：封禁时间({ban_time})中的"{value}"值为负数'
                            )
                            return 0
                    except ValueError as error:
                        fmts.print_war(
                            f"警告：封禁时间({ban_time})中存在无效的数值：{value_str} detail: {str(error)}"
                        )
                        return 0

                    time_units[unit] = value

                years = time_units.get("年", 0)
                months = time_units.get("月", 0)
                days = time_units.get("日", 0)
                hours = time_units.get("时", 0)
                minutes = time_units.get("分", 0)
                seconds = time_units.get("秒", 0)

                total_days = years * 360 + months * 30 + days
                return (total_days * 86400) + hours * 3600 + minutes * 60 + seconds

        else:
            fmts.print_war("警告：无法解析您输入的封禁时间")
            return 0

    # 玩家封禁函数封装(开始执行封禁,通过xuid判断)

    @utils.thread_func("玩家封禁函数(开始执行封禁,通过xuid判断)")
    def ban_player_by_xuid(self, player, xuid, ban_time, ban_reason):
        if self.is_ban_player_by_xuid and ban_time != 0:
            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
            path = f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{xuid}.json"
            with self.thread_lock_ban_player_by_xuid:
                ban_player_data = tempjson.load_and_read(
                    path, need_file_exists=False, timeout=2
                )
                tempjson.unload_to_path(path)

                if ban_player_data is None:
                    pre_ban_timestamp = timestamp_now
                else:
                    if ban_player_data["ban_end_timestamp"] == "Forever":
                        return
                    if ban_player_data["ban_end_timestamp"] < timestamp_now:
                        pre_ban_timestamp = timestamp_now
                    else:
                        pre_ban_timestamp = ban_player_data["ban_end_timestamp"]

                if ban_time == "Forever":
                    timestamp_end = "Forever"
                    date_end = "Forever"
                else:
                    timestamp_end = pre_ban_timestamp + ban_time
                    date_end = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)
                    )
                tempjson.load_and_write(
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
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path)
                tempjson.unload_to_path(path)

    # 玩家封禁函数封装(被封禁者再次加入游戏,通过xuid判断)

    @utils.thread_func("玩家封禁函数(xuid判据)")
    def ban_player_when_PlayerList_by_xuid(self, player, xuid):
        path = f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{xuid}.json"
        try:
            with self.thread_lock_ban_player_by_xuid:
                ban_player_data = tempjson.load_and_read(
                    path, need_file_exists=True, timeout=2
                )
                tempjson.unload_to_path(path)
            if ban_player_data is None:
                os.remove(path)
                return
            ban_end_timestamp = ban_player_data["ban_end_timestamp"]
            ban_end_real_time = ban_player_data["ban_end_real_time"]
            ban_reason = ban_player_data["ban_reason"]
            if type(ban_end_timestamp) is int:
                timestamp_now = int(time.time())
                if ban_end_timestamp > timestamp_now:
                    fmts.print_inf(
                        f"§c发现玩家 {player} 被封禁，正在踢出，其解封时间为：{ban_end_real_time}"
                    )
                    self.game_ctrl.sendwocmd(
                        self.try_hide_ban_info(
                            f'/kick "{player}" 由于{ban_reason}，您被系统封禁至：{ban_end_real_time}'
                        )
                    )
                    fmts.print_inf(f"§a发现玩家 {player} 被封禁，已被踢出游戏")
                else:
                    fmts.print_inf(
                        f"§b发现 玩家 {player} ({xuid}) 的封禁已到期，已解除封禁"
                    )
                    os.remove(path)
            elif ban_end_timestamp == "Forever":
                fmts.print_inf(
                    f"§c发现玩家 {player} 被封禁，正在踢出，该玩家为永久封禁"
                )
                self.game_ctrl.sendwocmd(
                    self.try_hide_ban_info(
                        f'/kick "{player}" 由于{ban_reason}，您被系统封禁至：Forever'
                    )
                )
                fmts.print_inf(f"§a发现玩家 {player} 被封禁，已被踢出游戏")
        except FileNotFoundError:
            return

    # 玩家设备号获取函数封装

    @utils.thread_func("玩家设备号获取函数")
    def get_player_device_id(self, player, xuid, SkinID):
        if self.is_get_device_id:
            device_id_from_SkinID = None
            re_match = re.search(r"(?:CustomSlim|Custom)(.*)$", SkinID)
            if re_match:
                match_str = re_match.group(1)
                if len(match_str) == 32:
                    device_id_from_SkinID = match_str.upper()
                    fmts.print_inf(
                        f"§9玩家 {player} 的 设备号(快速获取方式): {device_id_from_SkinID}"
                    )
                    if player not in self.whitelist:
                        self.ban_player_when_PlayerList_by_device_id(
                            player, xuid, device_id_from_SkinID
                        )
            if (device_id_from_SkinID is None) and (not self.simplified_mode):
                fmts.print_inf(
                    f"§6获取玩家 {player} 设备号失败(快速获取方式)，这可能是因为玩家使用4D皮肤或Steve/Alex皮肤或玩家为机器人，可能是正常现象，稍后将尝试慢速获取方式"
                )
            with self.thread_lock_by_get_device_id:
                try_time = 0
                time.sleep(1)
                device_id = None
                while True:
                    if player not in self.game_ctrl.allplayers.copy():
                        if not self.simplified_mode:
                            fmts.print_inf(
                                f"§6发现玩家 {player} 已退出游戏，终止设备号获取线程(慢速获取方式)"
                            )
                        break
                    time.sleep(3.5)
                    self.game_ctrl.sendwocmd(
                        f'/execute at @a[name="{player}"] run tp @a[name="{self.game_ctrl.bot_name}"] ~ 500 ~'
                    )
                    time.sleep(0.5)
                    player_data = self.frame.launcher.omega.get_player_by_name(player)
                    try_time += 1
                    if player_data is None or (
                        player_data and player_data.device_id == ""
                    ):
                        if try_time >= self.record_device_id_try_time:
                            if not self.simplified_mode:
                                fmts.print_inf(
                                    f"§c获取玩家 {player} 设备号失败(慢速获取方式)，这可能是因为玩家进服后秒退或者玩家暂未完全进入服务器，当前尝试次数{try_time}/{self.record_device_id_try_time}，这是最后一次尝试"
                                )
                            break
                        if not self.simplified_mode:
                            fmts.print_inf(
                                f"§c获取玩家 {player} 设备号失败(慢速获取方式)，这可能是因为玩家进服后秒退或者玩家暂未完全进入服务器，当前尝试次数{try_time}/{self.record_device_id_try_time}，将在4秒后再次尝试查询"
                            )
                    else:
                        device_id = player_data.device_id.upper()
                        if device_id_from_SkinID and device_id_from_SkinID != device_id:
                            fmts.print_inf(
                                f"§b发现玩家 {player} 通过快速获取方式得到的设备号存在异常，已校正为(慢速获取方式): {device_id}"
                            )
                        else:
                            fmts.print_inf(
                                f"§b玩家 {player} 的 设备号(慢速获取方式): {device_id}"
                            )
                        break

            if (not device_id) and (not device_id_from_SkinID):
                return
            if (not device_id) and device_id_from_SkinID:
                device_id = device_id_from_SkinID
            path_device_id = f"{self.data_path}/玩家丨设备号丨xuid丨历史名称丨记录.json"
            with self.thread_lock_ban_player_by_device_id:
                device_id_record = tempjson.load_and_read(
                    path_device_id,
                    need_file_exists=False,
                    default={},
                    timeout=2,
                )
                tempjson.unload_to_path(path_device_id)
                if device_id not in device_id_record.keys():
                    device_id_record[device_id] = {}
                if device_id_record[device_id].get(xuid, None) is None:
                    device_id_record[device_id][xuid] = []
                device_id_record[device_id][xuid].append(player)
                device_id_record[device_id][xuid] = list(
                    set(device_id_record[device_id][xuid])
                )
                tempjson.load_and_write(
                    path_device_id,
                    device_id_record,
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path_device_id)
                tempjson.unload_to_path(path_device_id)

            if (player not in self.whitelist) and (device_id_from_SkinID != device_id):
                self.ban_player_when_PlayerList_by_device_id(player, xuid, device_id)

    # 玩家封禁函数封装(开始执行封禁,通过device_id判断)

    @utils.thread_func("玩家封禁函数(开始执行封禁,通过device_id判断)")
    def ban_player_by_device_id(self, player, xuid, ban_time, ban_reason):
        if self.is_ban_player_by_device_id and ban_time != 0:
            path_device_id = f"{self.data_path}/玩家丨设备号丨xuid丨历史名称丨记录.json"
            with self.thread_lock_ban_player_by_device_id:
                device_id_record = tempjson.load_and_read(
                    path_device_id,
                    need_file_exists=False,
                    default={},
                    timeout=2,
                )
                tempjson.unload_to_path(path_device_id)
            # 收集本账号登录过的全部设备号
            device_id_list = []
            for k, v in device_id_record.items():
                if xuid in v.keys():
                    device_id_list.append(k)
            if device_id_list == []:
                fmts.print_war(
                    f"警告：玩家 {player} 没有设备号记录，不能通过设备号执行封禁"
                )
                return

            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))

            for device_id in device_id_list:
                path_ban_time = (
                    f"{self.data_path}/玩家封禁时间数据(以设备号记录)/{device_id}.json"
                )
                with self.thread_lock_ban_player_by_device_id:
                    ban_player_data = tempjson.load_and_read(
                        path_ban_time, need_file_exists=False, timeout=2
                    )
                    tempjson.unload_to_path(path_ban_time)

                    if ban_player_data is None:
                        pre_ban_timestamp = timestamp_now
                    else:
                        if ban_player_data["ban_end_timestamp"] == "Forever":
                            return
                        if ban_player_data["ban_end_timestamp"] < timestamp_now:
                            pre_ban_timestamp = timestamp_now
                        else:
                            pre_ban_timestamp = ban_player_data["ban_end_timestamp"]

                    if ban_time == "Forever":
                        timestamp_end = "Forever"
                        date_end = "Forever"
                    else:
                        timestamp_end = pre_ban_timestamp + ban_time
                        date_end = time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)
                        )
                        tempjson.load_and_write(
                            path_ban_time,
                            {
                                "device_id": device_id,
                                "xuid(The latest joined in the server)": xuid,
                                "name(The latest joined in the server)": player,
                                "ban_start_real_time": date_now,
                                "ban_start_timestamp": timestamp_now,
                                "ban_end_real_time": date_end,
                                "ban_end_timestamp": timestamp_end,
                                "ban_reason": ban_reason,
                            },
                            need_file_exists=False,
                            timeout=2,
                        )
                        tempjson.flush(path_ban_time)
                        tempjson.unload_to_path(path_ban_time)

                time.sleep(0.2)

    # 玩家封禁函数封装(被封禁者再次加入游戏,通过device_id判断)

    @utils.thread_func("玩家封禁函数(device_id判据)")
    def ban_player_when_PlayerList_by_device_id(self, player, xuid, device_id):
        path = f"{self.data_path}/玩家封禁时间数据(以设备号记录)/{device_id}.json"
        try:
            with self.thread_lock_ban_player_by_device_id:
                ban_player_data = tempjson.load_and_read(
                    path, need_file_exists=True, timeout=2
                )
                tempjson.unload_to_path(path)
            if ban_player_data is None:
                os.remove(path)
                return
            ban_start_real_time = ban_player_data["ban_start_real_time"]
            ban_start_timestamp = ban_player_data["ban_start_timestamp"]
            ban_end_timestamp = ban_player_data["ban_end_timestamp"]
            ban_end_real_time = ban_player_data["ban_end_real_time"]
            ban_reason = ban_player_data["ban_reason"]
            if type(ban_end_timestamp) is int:
                timestamp_now = int(time.time())
                if ban_end_timestamp > timestamp_now:
                    fmts.print_inf(
                        f"§c发现设备号 {device_id} 被封禁(当前登录玩家：{player})，正在踢出，其解封时间为：{ban_end_real_time}"
                    )
                    self.game_ctrl.sendwocmd(
                        self.try_hide_ban_info(
                            f'/kick "{player}" 由于{ban_reason}，您被系统封禁至：{ban_end_real_time}'
                        )
                    )
                    fmts.print_inf(
                        f"§a发现设备号 {device_id} 被封禁(当前登录玩家：{player})，已被踢出游戏"
                    )
                    if self.jointly_ban_player:
                        path_ban_xuid = (
                            f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{xuid}.json"
                        )
                        with self.thread_lock_ban_player_by_xuid:
                            ban_xuid_data = tempjson.load_and_read(
                                path_ban_xuid, need_file_exists=False, timeout=2
                            )
                            tempjson.unload_to_path(path_ban_xuid)
                            if ban_xuid_data and (
                                ban_xuid_data["ban_end_timestamp"] == "Forever"
                                or ban_xuid_data["ban_end_timestamp"]
                                >= ban_end_timestamp
                            ):
                                return
                            tempjson.load_and_write(
                                path_ban_xuid,
                                {
                                    "xuid": xuid,
                                    "name": player,
                                    "ban_start_real_time": ban_start_real_time,
                                    "ban_start_timestamp": ban_start_timestamp,
                                    "ban_end_real_time": ban_end_real_time,
                                    "ban_end_timestamp": ban_end_timestamp,
                                    "ban_reason": ban_reason,
                                },
                                need_file_exists=False,
                                timeout=2,
                            )
                            tempjson.flush(path_ban_xuid)
                            tempjson.unload_to_path(path_ban_xuid)
                else:
                    fmts.print_inf(
                        f"§b发现 设备号 {device_id} 的封禁已到期，已解除封禁"
                    )
                    os.remove(path)
            elif ban_end_timestamp == "Forever":
                fmts.print_inf(
                    f"§c发现设备号 {device_id} 被封禁(当前登录玩家：{player})，正在踢出，该设备号为永久封禁"
                )
                self.game_ctrl.sendwocmd(
                    self.try_hide_ban_info(
                        f'/kick "{player}" 由于{ban_reason}，您被系统封禁至：Forever'
                    )
                )
                fmts.print_inf(
                    f"§a发现设备号 {device_id} 被封禁(当前登录玩家：{player})，已被踢出游戏"
                )
                if self.jointly_ban_player:
                    path_ban_xuid = (
                        f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{xuid}.json"
                    )
                    with self.thread_lock_ban_player_by_xuid:
                        tempjson.load_and_write(
                            path_ban_xuid,
                            {
                                "xuid": xuid,
                                "name": player,
                                "ban_start_real_time": ban_start_real_time,
                                "ban_start_timestamp": ban_start_timestamp,
                                "ban_end_real_time": "Forever",
                                "ban_end_timestamp": "Forever",
                                "ban_reason": ban_reason,
                            },
                            need_file_exists=False,
                            timeout=2,
                        )
                        tempjson.flush(path_ban_xuid)
                        tempjson.unload_to_path(path_ban_xuid)

        except FileNotFoundError:
            return

    # 检查并踢出被封禁的在线玩家

    @utils.thread_func("玩家封禁函数(当插件加载或重载完成时)")
    def ban_player_when_plugin_active(self):
        time.sleep(0.5)
        players_list = self.frame.get_players().getAllPlayers()

        all_ban_player_xuids = os.listdir(
            f"{self.data_path}/玩家封禁时间数据(以xuid记录)"
        )
        all_ban_xuid = []
        for i in all_ban_player_xuids:
            xuid = i.replace(".json", "")
            try:
                all_ban_xuid.append(xuid)
            except ValueError:
                continue

        all_ban_player_device_id = os.listdir(
            f"{self.data_path}/玩家封禁时间数据(以设备号记录)"
        )
        all_ban_device_id = []

        path_device_id = f"{self.data_path}/玩家丨设备号丨xuid丨历史名称丨记录.json"
        with self.thread_lock_ban_player_by_device_id:
            device_id_data = tempjson.load_and_read(
                path_device_id, need_file_exists=False, default={}, timeout=2
            )
            tempjson.unload_to_path(path_device_id)
        for i in all_ban_player_device_id:
            device_id = i.replace(".json", "")
            try:
                all_ban_device_id.append(list(device_id_data.get(device_id, {}).keys()))
            except ValueError:
                continue
        all_ban_device_id_merge = []
        for li in all_ban_device_id:
            for inner_xuid in li:
                all_ban_device_id_merge.append(inner_xuid)
        for player in players_list:
            if (player.name not in self.whitelist) and (
                (player.xuid in all_ban_xuid)
                or (player.xuid in all_ban_device_id_merge)
            ):
                fmts.print_inf(f"§c发现当前在线玩家 {player.name} 被封禁，正在踢出")
                self.game_ctrl.sendwocmd(
                    self.try_hide_ban_info(
                        f'/kick "{player.name}" 您必须通过 Microsoft 服务身份验证。'
                    )
                )
                fmts.print_inf(f"§a发现当前在线玩家 {player.name} 被封禁，已被踢出游戏")

    # 游戏内封禁系统API函数封装

    @utils.thread_func("游戏内封禁系统API")
    def ban_api_in_game(self):
        while True:
            players_list = self.frame.get_players().getAllPlayers()
            for player in players_list:
                if player.name not in self.whitelist:
                    try:
                        score = player.getScore(self.ban_scoreboard_name)
                        self.game_ctrl.sendwocmd(
                            f'/scoreboard players reset @a[name="{player.name}"] "{self.ban_scoreboard_name}"'
                        )
                        fmts.print_inf(
                            f"§c发现玩家 {player.name} 通过游戏内封禁系统API被封禁，正在踢出"
                        )
                        self.game_ctrl.sendwocmd(
                            self.try_hide_ban_info(
                                f'/kick "{player.name}" 您必须通过 Microsoft 服务身份验证。'
                            )
                        )
                        fmts.print_inf(
                            f"§a发现玩家 {player.name} 通过游戏内封禁系统API被封禁，已被踢出游戏"
                        )
                        if score == -1:
                            score = "Forever"
                        elif score < -1 or score == 0:
                            score = 0
                        self.ban_player_by_xuid(
                            player.name, player.xuid, score, "游戏内违规行为"
                        )
                        self.ban_player_by_device_id(
                            player.name, player.xuid, score, "游戏内违规行为"
                        )
                    except ValueError:
                        continue
                    except TimeoutError:
                        continue
            time.sleep(self.ban_scoreboard_detect_cycle)

    # 清除到期的封禁数据

    @utils.thread_func("清除到期的封禁数据")
    def remove_expire_ban_data(self):
        all_ban_player_xuids = os.listdir(
            f"{self.data_path}/玩家封禁时间数据(以xuid记录)"
        )
        for i in all_ban_player_xuids:
            path_ban_xuid = f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{i}"
            try:
                with self.thread_lock_ban_player_by_xuid:
                    ban_xuid_data = tempjson.load_and_read(
                        path_ban_xuid, need_file_exists=False, timeout=2
                    )
                    tempjson.unload_to_path(path_ban_xuid)
                ban_end_timestamp_xuid = ban_xuid_data["ban_end_timestamp"]
                ban_player = ban_xuid_data["name"]
                ban_xuid = ban_xuid_data["xuid"]
                if (
                    ban_end_timestamp_xuid != "Forever"
                    and ban_end_timestamp_xuid <= int(time.time())
                ):
                    os.remove(path_ban_xuid)
                    fmts.print_inf(
                        f"§b发现 玩家 {ban_player} (xuid:{ban_xuid}) 的封禁已到期，已解除封禁"
                    )
            except Exception:
                os.remove(path_ban_xuid)
                fmts.print_inf(
                    f"§6发现 封禁数据 ({path_ban_xuid}) 出现损坏，已自动移除"
                )
        all_ban_player_device_id = os.listdir(
            f"{self.data_path}/玩家封禁时间数据(以设备号记录)"
        )
        for i in all_ban_player_device_id:
            path_ban_device_id = f"{self.data_path}/玩家封禁时间数据(以设备号记录)/{i}"
            try:
                with self.thread_lock_ban_player_by_device_id:
                    ban_device_id_data = tempjson.load_and_read(
                        path_ban_device_id, need_file_exists=False, timeout=2
                    )
                    tempjson.unload_to_path(path_ban_device_id)
                ban_end_timestamp_device_id = ban_device_id_data["ban_end_timestamp"]
                ban_device_id = ban_device_id_data["device_id"]
                if (
                    ban_end_timestamp_device_id != "Forever"
                    and ban_end_timestamp_device_id <= int(time.time())
                ):
                    os.remove(path_ban_device_id)
                    fmts.print_inf(
                        f"§b发现 设备号 {ban_device_id} 的封禁已到期，已解除封禁"
                    )
            except Exception:
                os.remove(path_ban_device_id)
                fmts.print_inf(
                    f"§6发现 封禁数据 ({path_ban_device_id}) 出现损坏，已自动移除"
                )

    # 尝试隐藏违规行为踢出提示(可将玩家踢出提示转换成***)
    def try_hide_ban_info(self, ban_command):
        if self.is_hide_ban_info:
            return ban_command + "加Q"
        return ban_command

    # 控制台菜单封禁玩家函数封装
    def ban_player_by_terminal(self, _):
        fmts.print_inf(
            "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        fmts.print_inf("§l§d❐§f 『§6Orion System §d猎户座§f』 §b封禁§e管§a理 §d系统")
        fmts.print_inf("§l§b[ §e1§b ] §r§e根据在线玩家名称和xuid封禁")
        fmts.print_inf("§l§b[ §e2§b ] §r§e根据历史进服玩家名称和xuid封禁")
        fmts.print_inf("§l§b[ §e3§b ] §r§e根据历史进服玩家设备号封禁")
        fmts.print_inf(
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        fmts.print_inf("§a❀ §b输入 §e[1-3]§b 之间的数字以选择 封禁模式")
        resp_1 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

        if resp_1 == "1":
            allplayers = self.game_ctrl.allplayers.copy()
            page = 1
            while True:
                total_pages = math.ceil(len(allplayers) / self.terminal_items_per_page)
                start_index = (page - 1) * self.terminal_items_per_page + 1
                end_index = min(
                    start_index + self.terminal_items_per_page - 1, len(allplayers)
                )

                fmts.print_inf(
                    "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                fmts.print_inf("§l§b[ §a序号§b ] §r§a玩家名称 - xuid")
                for i in range(start_index, end_index + 1):
                    fmts.print_inf(
                        f"§l§b[ §e{i}§b ] §r§e{allplayers[i - 1]} - {self.xuid_getter.get_xuid_by_name(allplayers[i - 1])}"
                    )
                fmts.print_inf(
                    "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                fmts.print_inf(
                    f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                )
                fmts.print_inf(
                    f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的玩家和xuid"
                )
                fmts.print_inf("§a❀ §b输入 §d- §e转到上一页")
                fmts.print_inf("§a❀ §b输入 §d+ §e转到下一页")
                fmts.print_inf("§a❀ §b输入 §d正整数+页 §e转到对应页")
                resp_2 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

                if resp_2 in (".", "。"):
                    fmts.print_suc("§a❀ 已退出封禁系统")
                    return
                if resp_2 == "-":
                    if page > 1:
                        page -= 1
                    else:
                        fmts.print_war("§6❀ 已经是第一页啦~")
                elif resp_2 == "+":
                    if page < total_pages:
                        page += 1
                    else:
                        fmts.print_war("§6❀ 已经是最后一页啦~")
                elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                    page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                    if 1 <= page_num <= total_pages:
                        page = page_num
                    else:
                        fmts.print_war(f"§6❀ 不存在第{page_num}页！请重新输入！")
                else:
                    resp_2 = utils.try_int(resp_2)
                    if resp_2 and resp_2 in range(start_index, end_index + 1):
                        ban_player = allplayers[resp_2 - 1]
                        ban_xuid = self.xuid_getter.get_xuid_by_name(ban_player)
                        break
                    fmts.print_err("§c❀ 您的输入有误")
                    return

            if ban_player in self.whitelist:
                fmts.print_war(
                    f"§6❀ 发现 玩家 {ban_player} 位于反制白名单内，请先将其移出白名单！"
                )
                return
            fmts.print_suc(f"\n§a❀ 您选择了 玩家 {ban_player} (xuid:{ban_xuid})")
            fmts.print_inf("§a❀ §b请按照以下格式输入封禁时间：")
            fmts.print_inf("§6 · §f封禁时间 = -1  §e永久封禁")
            fmts.print_inf("§6 · §f封禁时间 = 正整数  §e封禁<正整数>秒")
            fmts.print_inf("§6 · §f封禁时间 = 0年0月5日6时7分8秒  §e封禁对应的时间")
            ban_time = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))
            if ban_time in (".", "。"):
                fmts.print_suc("§a❀ 已退出封禁系统")
                return
            ban_time = self.ban_time_format(ban_time)
            if ban_time == 0:
                fmts.print_err("§c❀ 您输入的封禁时间有误")
                return
            fmts.print_suc(f"\n§a❀ 您输入的封禁时间为 {ban_time}秒")
            fmts.print_inf("§a❀ §b请输入封禁原因：")
            ban_reason = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出")) or "未知原因"
            if ban_reason in (".", "。"):
                fmts.print_suc("§a❀ 已退出封禁系统")
                return

            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
            path_ban_time = (
                f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{ban_xuid}.json"
            )
            with self.thread_lock_ban_player_by_xuid:
                ban_player_data = tempjson.load_and_read(
                    path_ban_time, need_file_exists=False, timeout=2
                )
                tempjson.unload_to_path(path_ban_time)

                if ban_player_data is None:
                    pre_ban_timestamp = timestamp_now
                else:
                    if ban_player_data["ban_end_timestamp"] == "Forever":
                        fmts.print_war(
                            f"§6❀ 玩家 {ban_player} (xuid:{ban_xuid}) 已经为永久封禁，无需重复封禁"
                        )
                        return
                    if ban_player_data["ban_end_timestamp"] < timestamp_now:
                        pre_ban_timestamp = timestamp_now
                    else:
                        pre_ban_timestamp = ban_player_data["ban_end_timestamp"]

                if ban_time == "Forever":
                    timestamp_end = "Forever"
                    date_end = "Forever"
                else:
                    timestamp_end = pre_ban_timestamp + ban_time
                    date_end = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)
                    )
                tempjson.load_and_write(
                    path_ban_time,
                    {
                        "xuid": ban_xuid,
                        "name": ban_player,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path_ban_time)
                tempjson.unload_to_path(path_ban_time)
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(
                    f'/kick "{ban_player}" 由于{ban_reason}，您被系统封禁至：{date_end}'
                )
            )
            fmts.print_suc(
                f"\n§a❀ 封禁成功：已封禁玩家 {ban_player} (xuid:{ban_xuid}) 至 {date_end}"
            )

        elif resp_1 == "2":
            path_xuid = "插件数据文件/前置-玩家XUID获取/xuids.json"
            try:
                with self.thread_lock_ban_player_by_xuid:
                    xuid_data = tempjson.load_and_read(
                        path_xuid, need_file_exists=True, timeout=2
                    )
                    tempjson.unload_to_path(path_xuid)
            except FileNotFoundError:
                fmts.print_err("§c❀ 未查询到任何xuid记录")
                return
            except Exception as error:
                fmts.print_err(f"§c❀ 查询xuid失败，原因：{error}")
                return
            fmts.print_inf(
                "\n§a❀ §b请输入您想封禁的xuid、玩家名称或部分玩家名称，输入§elist或直接回车§b可查询当前服务器全部玩家名称与xuid记录"
            )
            name_or_xuid = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

            if name_or_xuid in (".", "。"):
                fmts.print_suc("§a❀ 已退出封禁系统")
                return

            if name_or_xuid == "list":
                if len(xuid_data) == 0:
                    fmts.print_err("§c❀ 未查询到任何xuid记录")
                    return

                page = 1
                while True:
                    total_pages = math.ceil(
                        len(xuid_data) / self.terminal_items_per_page
                    )
                    start_index = (page - 1) * self.terminal_items_per_page + 1
                    end_index = min(
                        start_index + self.terminal_items_per_page - 1, len(xuid_data)
                    )

                    fmts.print_inf(
                        "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    fmts.print_inf("§l§b[ §a序号§b ] §r§a玩家名称 - xuid")
                    for i in range(start_index, end_index + 1):
                        fmts.print_inf(
                            f"§l§b[ §e{i}§b ] §r§e{list(xuid_data.values())[i - 1]} - {list(xuid_data.keys())[i - 1]}"
                        )
                    fmts.print_inf(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    fmts.print_inf(
                        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                    )
                    fmts.print_inf(
                        f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的玩家和xuid"
                    )
                    fmts.print_inf("§a❀ §b输入 §d- §e转到上一页")
                    fmts.print_inf("§a❀ §b输入 §d+ §e转到下一页")
                    fmts.print_inf("§a❀ §b输入 §d正整数+页 §e转到对应页")
                    resp_2 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

                    if resp_2 in (".", "。"):
                        fmts.print_suc("§a❀ 已退出封禁系统")
                        return
                    if resp_2 == "-":
                        if page > 1:
                            page -= 1
                        else:
                            fmts.print_war("§6❀ 已经是第一页啦~")
                    elif resp_2 == "+":
                        if page < total_pages:
                            page += 1
                        else:
                            fmts.print_war("§6❀ 已经是最后一页啦~")
                    elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                        page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                        if 1 <= page_num <= total_pages:
                            page = page_num
                        else:
                            fmts.print_war(f"§6❀ 不存在第{page_num}页！请重新输入！")
                    else:
                        resp_2 = utils.try_int(resp_2)
                        if resp_2 and resp_2 in range(start_index, end_index + 1):
                            ban_player = list(xuid_data.values())[resp_2 - 1]
                            ban_xuid = list(xuid_data.keys())[resp_2 - 1]
                            break
                        fmts.print_err("§c❀ 您的输入有误")
                        return

            elif name_or_xuid in xuid_data.keys():
                ban_xuid = name_or_xuid
                ban_player = xuid_data[name_or_xuid]

            else:
                page = 1
                while True:
                    matched_player: list[tuple[str, str]] = []
                    for k, v in xuid_data.items():
                        if name_or_xuid in v:
                            matched_player.append((v, k))

                    if matched_player == []:
                        fmts.print_err("§c❀ 找不到您输入的玩家名称或xuid")
                        return

                    total_pages = math.ceil(
                        len(matched_player) / self.terminal_items_per_page
                    )
                    start_index = (page - 1) * self.terminal_items_per_page + 1
                    end_index = min(
                        start_index + self.terminal_items_per_page - 1,
                        len(matched_player),
                    )
                    fmts.print_inf("\n§a❀ 已匹配到以下玩家~")
                    fmts.print_inf(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    fmts.print_inf("§l§b[ §a序号§b ] §r§a玩家名称 - xuid")
                    for i in range(start_index, end_index + 1):
                        fmts.print_inf(
                            f"§l§b[ §e{i}§b ] §r§e{matched_player[i - 1][0].replace(name_or_xuid, f'§b{name_or_xuid}§e')} - {matched_player[i - 1][1]}"
                        )
                    fmts.print_inf(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    fmts.print_inf(
                        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                    )
                    fmts.print_inf(
                        f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的玩家和xuid，或者输入玩家名称再次尝试搜索"
                    )
                    fmts.print_inf("§a❀ §b输入 §d- §e转到上一页")
                    fmts.print_inf("§a❀ §b输入 §d+ §e转到下一页")
                    fmts.print_inf("§a❀ §b输入 §d正整数+页 §e转到对应页")
                    resp_2 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

                    if resp_2 in (".", "。"):
                        fmts.print_suc("§a❀ 已退出封禁系统")
                        return
                    if resp_2 == "-":
                        if page > 1:
                            page -= 1
                        else:
                            fmts.print_war("§6❀ 已经是第一页啦~")
                    elif resp_2 == "+":
                        if page < total_pages:
                            page += 1
                        else:
                            fmts.print_war("§6❀ 已经是最后一页啦~")
                    elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                        page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                        if 1 <= page_num <= total_pages:
                            page = page_num
                        else:
                            fmts.print_war(f"§6❀ 不存在第{page_num}页！请重新输入！")
                    else:
                        try:
                            resp_2 = int(resp_2)
                            if resp_2 and resp_2 in range(start_index, end_index + 1):
                                ban_player = matched_player[resp_2 - 1][0]
                                ban_xuid = matched_player[resp_2 - 1][1]
                                break
                            fmts.print_err("§c❀ 您的输入有误")
                            return
                        except ValueError:
                            name_or_xuid = resp_2
                            page = 1

            if ban_player in self.whitelist:
                fmts.print_war(
                    f"§6❀ 发现 玩家 {ban_player} 位于反制白名单内，请先将其移出白名单！"
                )
                return
            fmts.print_suc(f"\n§a❀ 您选择了 玩家 {ban_player} (xuid:{ban_xuid})")
            fmts.print_inf("§a❀ §b请按照以下格式输入封禁时间：")
            fmts.print_inf("§6 · §f封禁时间 = -1  §e永久封禁")
            fmts.print_inf("§6 · §f封禁时间 = 正整数  §e封禁<正整数>秒")
            fmts.print_inf("§6 · §f封禁时间 = 0年0月5日6时7分8秒  §e封禁对应的时间")
            ban_time = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))
            if ban_time in (".", "。"):
                fmts.print_suc("§a❀ 已退出封禁系统")
                return
            ban_time = self.ban_time_format(ban_time)
            if ban_time == 0:
                fmts.print_err("§c❀ 您输入的封禁时间有误")
                return
            fmts.print_suc(f"\n§a❀ 您输入的封禁时间为 {ban_time}秒")
            fmts.print_inf("§a❀ §b请输入封禁原因：")
            ban_reason = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出")) or "未知原因"
            if ban_reason in (".", "。"):
                fmts.print_suc("§a❀ 已退出封禁系统")
                return

            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
            path_ban_time = (
                f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{ban_xuid}.json"
            )
            with self.thread_lock_ban_player_by_xuid:
                ban_player_data = tempjson.load_and_read(
                    path_ban_time, need_file_exists=False, timeout=2
                )
                tempjson.unload_to_path(path_ban_time)

                if ban_player_data is None:
                    pre_ban_timestamp = timestamp_now
                else:
                    if ban_player_data["ban_end_timestamp"] == "Forever":
                        fmts.print_war(
                            f"§6❀ 玩家 {ban_player} (xuid:{ban_xuid}) 已经为永久封禁，无需重复封禁"
                        )
                        return
                    if ban_player_data["ban_end_timestamp"] < timestamp_now:
                        pre_ban_timestamp = timestamp_now
                    else:
                        pre_ban_timestamp = ban_player_data["ban_end_timestamp"]

                if ban_time == "Forever":
                    timestamp_end = "Forever"
                    date_end = "Forever"
                else:
                    timestamp_end = pre_ban_timestamp + ban_time
                    date_end = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)
                    )
                tempjson.load_and_write(
                    path_ban_time,
                    {
                        "xuid": ban_xuid,
                        "name": ban_player,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path_ban_time)
                tempjson.unload_to_path(path_ban_time)
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(
                    f'/kick "{ban_player}" 由于{ban_reason}，您被系统封禁至：{date_end}'
                )
            )
            fmts.print_suc(
                f"\n§a❀ 封禁成功：已封禁玩家 {ban_player} (xuid:{ban_xuid}) 至 {date_end}"
            )

        elif resp_1 == "3":
            path_device_id = f"{self.data_path}/玩家丨设备号丨xuid丨历史名称丨记录.json"
            try:
                with self.thread_lock_ban_player_by_device_id:
                    device_id_data = tempjson.load_and_read(
                        path_device_id, need_file_exists=True, default={}, timeout=2
                    )
                    tempjson.unload_to_path(path_device_id)
            except FileNotFoundError:
                fmts.print_err("§c❀ 未查询到任何设备号记录")
                return
            except Exception as error:
                fmts.print_err(f"§c❀ 查询设备号记录失败，原因：{error}")
                return
            fmts.print_inf(
                "\n§a❀ §b请输入您想封禁的设备号、玩家名称或部分玩家名称，输入§elist或直接回车§b可查询当前服务器全部设备号记录"
            )
            device_id = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

            if device_id in (".", "。"):
                fmts.print_suc("§a❀ 已退出封禁系统")
                return
            if device_id == "list":
                if len(device_id_data) == 0:
                    fmts.print_err("§c❀ 未查询到任何设备号记录")
                    return

                page = 1
                while True:
                    total_pages = math.ceil(
                        len(device_id_data) / self.terminal_items_per_page
                    )
                    start_index = (page - 1) * self.terminal_items_per_page + 1
                    end_index = min(
                        start_index + self.terminal_items_per_page - 1,
                        len(device_id_data),
                    )

                    fmts.print_inf(
                        "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    fmts.print_inf(
                        "§l§b[ §a序号§b ] §r§a设备号 - {xuid: [玩家名称与改名记录]}"
                    )
                    for i in range(start_index, end_index + 1):
                        fmts.print_inf(
                            f"§l§b[ §e{i}§b ] §r§e{list(device_id_data.keys())[i - 1]} - {list(device_id_data.values())[i - 1]}"
                        )
                    fmts.print_inf(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    fmts.print_inf(
                        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                    )
                    fmts.print_inf(
                        f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的设备号"
                    )
                    fmts.print_inf("§a❀ §b输入 §d- §e转到上一页")
                    fmts.print_inf("§a❀ §b输入 §d+ §e转到下一页")
                    fmts.print_inf("§a❀ §b输入 §d正整数+页 §e转到对应页")
                    resp_2 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

                    if resp_2 in (".", "。"):
                        fmts.print_suc("§a❀ 已退出封禁系统")
                        return
                    if resp_2 == "-":
                        if page > 1:
                            page -= 1
                        else:
                            fmts.print_war("§6❀ 已经是第一页啦~")
                    elif resp_2 == "+":
                        if page < total_pages:
                            page += 1
                        else:
                            fmts.print_war("§6❀ 已经是最后一页啦~")
                    elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                        page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                        if 1 <= page_num <= total_pages:
                            page = page_num
                        else:
                            fmts.print_war(f"§6❀ 不存在第{page_num}页！请重新输入！")
                    else:
                        resp_2 = utils.try_int(resp_2)
                        if resp_2 and resp_2 in range(start_index, end_index + 1):
                            ban_device_id = list(device_id_data.keys())[resp_2 - 1]
                            ban_player_and_xuid_data = list(device_id_data.values())[
                                resp_2 - 1
                            ]
                            break
                        fmts.print_err("§c❀ 您的输入有误")
                        return

            elif device_id in device_id_data.keys():
                ban_device_id = device_id
                ban_player_and_xuid_data = device_id_data[device_id]

            else:
                page = 1
                while True:
                    matched_player: list[tuple[str, str]] = []
                    for k, v in device_id_data.items():
                        for m in v.values():
                            for n in m:
                                if device_id in n:
                                    matched_player.append((k, v))
                                    break
                            else:
                                continue
                            break

                    if matched_player == []:
                        fmts.print_err("§c❀ 找不到您输入的玩家名称或设备号")
                        return

                    total_pages = math.ceil(
                        len(matched_player) / self.terminal_items_per_page
                    )
                    start_index = (page - 1) * self.terminal_items_per_page + 1
                    end_index = min(
                        start_index + self.terminal_items_per_page - 1,
                        len(matched_player),
                    )

                    fmts.print_inf("\n§a❀ 已匹配到以下玩家~")
                    fmts.print_inf(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    fmts.print_inf(
                        "§l§b[ §a序号§b ] §r§a设备号 - {xuid: [玩家名称与改名记录]}"
                    )
                    for i in range(start_index, end_index + 1):
                        colored_device_id_data = "{"
                        for k, v in matched_player[i - 1][1].items():
                            v = str(v).replace(device_id, f"§b{device_id}§e")
                            colored_device_id_data = (
                                colored_device_id_data + f"'{k}': {v}, "
                            )
                        colored_device_id_data = colored_device_id_data[:-2] + "}"
                        fmts.print_inf(
                            f"§l§b[ §e{i}§b ] §r§e{matched_player[i - 1][0]} - {colored_device_id_data}"
                        )
                    fmts.print_inf(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    fmts.print_inf(
                        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                    )
                    fmts.print_inf(
                        f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的设备号，或者输入玩家名称再次尝试搜索"
                    )
                    fmts.print_inf("§a❀ §b输入 §d- §e转到上一页")
                    fmts.print_inf("§a❀ §b输入 §d+ §e转到下一页")
                    fmts.print_inf("§a❀ §b输入 §d正整数+页 §e转到对应页")
                    resp_2 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

                    if resp_2 in (".", "。"):
                        fmts.print_suc("§a❀ 已退出封禁系统")
                        return
                    if resp_2 == "-":
                        if page > 1:
                            page -= 1
                        else:
                            fmts.print_war("§6❀ 已经是第一页啦~")
                    elif resp_2 == "+":
                        if page < total_pages:
                            page += 1
                        else:
                            fmts.print_war("§6❀ 已经是最后一页啦~")
                    elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                        page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                        if 1 <= page_num <= total_pages:
                            page = page_num
                        else:
                            fmts.print_war(f"§6❀ 不存在第{page_num}页！请重新输入！")
                    else:
                        try:
                            resp_2 = int(resp_2)
                            if resp_2 and resp_2 in range(start_index, end_index + 1):
                                ban_device_id = matched_player[resp_2 - 1][0]
                                ban_player_and_xuid_data = matched_player[resp_2 - 1][1]
                                break
                            fmts.print_err("§c❀ 您的输入有误")
                            return
                        except ValueError:
                            device_id = resp_2
                            page = 1

            ban_xuid_list = []
            for k in ban_player_and_xuid_data.keys():
                ban_xuid_list.append(k)

            fmts.print_suc(
                f"\n§a❀ 您选择了 设备号 {ban_device_id} (使用此设备加入游戏的玩家xuid和名称记录:{ban_player_and_xuid_data})"
            )
            fmts.print_inf("§a❀ §b请按照以下格式输入封禁时间：")
            fmts.print_inf("§6 · §f封禁时间 = -1  §e永久封禁")
            fmts.print_inf("§6 · §f封禁时间 = 正整数  §e封禁<正整数>秒")
            fmts.print_inf("§6 · §f封禁时间 = 0年0月5日6时7分8秒  §e封禁对应的时间")
            ban_time = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))
            if ban_time in (".", "。"):
                fmts.print_suc("§a❀ 已退出封禁系统")
                return
            ban_time = self.ban_time_format(ban_time)
            if ban_time == 0:
                fmts.print_err("§c❀ 您输入的封禁时间有误")
                return
            fmts.print_suc(f"\n§a❀ 您输入的封禁时间为 {ban_time}秒")
            fmts.print_inf("§a❀ §b请输入封禁原因：")
            ban_reason = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出")) or "未知原因"
            if ban_reason in (".", "。"):
                fmts.print_suc("§a❀ 已退出封禁系统")
                return

            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
            path_ban_time = (
                f"{self.data_path}/玩家封禁时间数据(以设备号记录)/{ban_device_id}.json"
            )
            with self.thread_lock_ban_player_by_device_id:
                ban_player_data = tempjson.load_and_read(
                    path_ban_time, need_file_exists=False, timeout=2
                )
                tempjson.unload_to_path(path_ban_time)

                if ban_player_data is None:
                    pre_ban_timestamp = timestamp_now
                else:
                    if ban_player_data["ban_end_timestamp"] == "Forever":
                        fmts.print_war(
                            f"§6❀ 设备号 {ban_device_id} 已经为永久封禁，无需重复封禁 (使用此设备加入游戏的玩家xuid和名称记录:{ban_player_and_xuid_data})"
                        )
                        return
                    if ban_player_data["ban_end_timestamp"] < timestamp_now:
                        pre_ban_timestamp = timestamp_now
                    else:
                        pre_ban_timestamp = ban_player_data["ban_end_timestamp"]

                if ban_time == "Forever":
                    timestamp_end = "Forever"
                    date_end = "Forever"
                else:
                    timestamp_end = pre_ban_timestamp + ban_time
                    date_end = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)
                    )
                tempjson.load_and_write(
                    path_ban_time,
                    {
                        "device_id": ban_device_id,
                        "xuid_and_player": ban_player_and_xuid_data,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path_ban_time)
                tempjson.unload_to_path(path_ban_time)
            for k in ban_xuid_list:
                self.game_ctrl.sendwocmd(
                    self.try_hide_ban_info(
                        f'/kick "{k}" 由于{ban_reason}，您被系统封禁至：{date_end}'
                    )
                )
            fmts.print_suc(
                f"\n§a❀ 封禁成功：已封禁设备号 {ban_device_id} 至 {date_end} (使用此设备加入游戏的玩家xuid和名称记录:{ban_player_and_xuid_data})"
            )

        elif resp_1 in (".", "。"):
            fmts.print_suc("§a❀ 已退出封禁系统")

        else:
            fmts.print_err("§c❀ 您的输入有误")

    # 控制台菜单解封玩家函数封装
    def unban_player_by_terminal(self, _):
        fmts.print_inf(
            "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        fmts.print_inf("§l§d❐§f 『§6Orion System §d猎户座§f』 §b解封§e管§a理 §d系统")
        fmts.print_inf("§l§b[ §e1§b ] §r§e根据玩家名称和xuid解封")
        fmts.print_inf("§l§b[ §e2§b ] §r§e根据设备号解封")
        fmts.print_inf(
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        fmts.print_inf("§a❀ §b输入 §e[1-2]§b 之间的数字以选择 解封模式")
        resp_1 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

        if resp_1 == "1":
            all_ban_player_xuids = os.listdir(
                f"{self.data_path}/玩家封禁时间数据(以xuid记录)"
            )
            all_ban_playernames: list[tuple[str, str]] = []
            for i in all_ban_player_xuids:
                xuid = i.replace(".json", "")
                try:
                    all_ban_playernames.append(
                        (
                            self.xuid_getter.get_name_by_xuid(xuid, allow_offline=True),
                            xuid,
                        )
                    )
                except ValueError:
                    continue
            if all_ban_playernames == []:
                fmts.print_war("§6❀ 目前没有正在封禁的玩家和xuid")
                return

            page = 1
            while True:
                total_pages = math.ceil(
                    len(all_ban_playernames) / self.terminal_items_per_page
                )
                start_index = (page - 1) * self.terminal_items_per_page + 1
                end_index = min(
                    start_index + self.terminal_items_per_page - 1,
                    len(all_ban_playernames),
                )

                fmts.print_inf(
                    "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                fmts.print_inf("§l§b[ §a序号§b ] §r§a玩家名称 - xuid")
                for i in range(start_index, end_index + 1):
                    fmts.print_inf(
                        f"§l§b[ §e{i}§b ] §r§e{all_ban_playernames[i - 1][0]} - {all_ban_playernames[i - 1][1]}"
                    )
                fmts.print_inf(
                    "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                fmts.print_inf(
                    f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                )
                fmts.print_inf(
                    f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 解封的玩家和xuid"
                )
                fmts.print_inf("§a❀ §b输入 §d- §e转到上一页")
                fmts.print_inf("§a❀ §b输入 §d+ §e转到下一页")
                fmts.print_inf("§a❀ §b输入 §d正整数+页 §e转到对应页")
                resp_2 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

                if resp_2 in (".", "。"):
                    fmts.print_suc("§a❀ 已退出解封系统")
                    return
                if resp_2 == "-":
                    if page > 1:
                        page -= 1
                    else:
                        fmts.print_war("§6❀ 已经是第一页啦~")
                elif resp_2 == "+":
                    if page < total_pages:
                        page += 1
                    else:
                        fmts.print_war("§6❀ 已经是最后一页啦~")
                elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                    page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                    if 1 <= page_num <= total_pages:
                        page = page_num
                    else:
                        fmts.print_war(f"§6❀ 不存在第{page_num}页！请重新输入！")
                else:
                    resp_2 = utils.try_int(resp_2)
                    if resp_2 and resp_2 in range(start_index, end_index + 1):
                        unban_player = all_ban_playernames[resp_2 - 1][0]
                        unban_xuid = all_ban_playernames[resp_2 - 1][1]
                        os.remove(
                            f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{unban_xuid}.json"
                        )
                        fmts.print_suc(
                            f"\n§a❀ 解封成功: 已解封玩家 {unban_player} (xuid:{unban_xuid})"
                        )
                        break
                    fmts.print_err("§c❀ 您的输入有误")
                    return

        elif resp_1 == "2":
            all_ban_player_device_id = os.listdir(
                f"{self.data_path}/玩家封禁时间数据(以设备号记录)"
            )
            all_ban_device_id: list[tuple[str, str]] = []

            path_device_id = f"{self.data_path}/玩家丨设备号丨xuid丨历史名称丨记录.json"
            try:
                with self.thread_lock_ban_player_by_device_id:
                    device_id_data = tempjson.load_and_read(
                        path_device_id, need_file_exists=True, default={}, timeout=2
                    )
                    tempjson.unload_to_path(path_device_id)
            except FileNotFoundError:
                fmts.print_err("§c❀ 未查询到任何设备号记录")
            except Exception as error:
                fmts.print_err(f"§c❀ 查询设备号记录失败，原因：{error}")

            for i in all_ban_player_device_id:
                device_id = i.replace(".json", "")
                try:
                    all_ban_device_id.append(
                        (device_id, device_id_data.get(device_id, ""))
                    )
                except ValueError:
                    continue
            if all_ban_device_id == []:
                fmts.print_war("§6❀ 目前没有正在封禁的设备号")
                return

            page = 1
            while True:
                total_pages = math.ceil(
                    len(all_ban_device_id) / self.terminal_items_per_page
                )
                start_index = (page - 1) * self.terminal_items_per_page + 1
                end_index = min(
                    start_index + self.terminal_items_per_page - 1,
                    len(all_ban_device_id),
                )

                fmts.print_inf(
                    "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                fmts.print_inf(
                    "§l§b[ §a序号§b ] §r§a设备号 - {xuid: [玩家名称与改名记录]}"
                )
                for i in range(start_index, end_index + 1):
                    fmts.print_inf(
                        f"§l§b[ §e{i}§b ] §r§e{all_ban_device_id[i - 1][0]} - {all_ban_device_id[i - 1][1]}"
                    )
                fmts.print_inf(
                    "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                fmts.print_inf(
                    f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                )
                fmts.print_inf(
                    f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 解封的设备号"
                )
                fmts.print_inf("§a❀ §b输入 §d- §e转到上一页")
                fmts.print_inf("§a❀ §b输入 §d+ §e转到下一页")
                fmts.print_inf("§a❀ §b输入 §d正整数+页 §e转到对应页")
                resp_2 = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))

                if resp_2 in (".", "。"):
                    fmts.print_suc("§a❀ 已退出解封系统")
                    return
                if resp_2 == "-":
                    if page > 1:
                        page -= 1
                    else:
                        fmts.print_war("§6❀ 已经是第一页啦~")
                elif resp_2 == "+":
                    if page < total_pages:
                        page += 1
                    else:
                        fmts.print_war("§6❀ 已经是最后一页啦~")
                elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                    page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                    if 1 <= page_num <= total_pages:
                        page = page_num
                    else:
                        fmts.print_war(f"§6❀ 不存在第{page_num}页！请重新输入！")
                else:
                    resp_2 = utils.try_int(resp_2)
                    if resp_2 and resp_2 in range(start_index, end_index + 1):
                        unban_device_id = all_ban_device_id[resp_2 - 1][0]
                        unban_device_id_data = all_ban_device_id[resp_2 - 1][1]
                        os.remove(
                            f"{self.data_path}/玩家封禁时间数据(以设备号记录)/{unban_device_id}.json"
                        )
                        fmts.print_suc(
                            f"\n§a❀ 解封成功: 已解封设备号 {unban_device_id} (使用此设备加入游戏的玩家xuid和名称记录:{unban_device_id_data})"
                        )
                        break
                    fmts.print_err("§c❀ 您的输入有误")
                    return

        elif resp_1 in (".", "。"):
            fmts.print_suc("§a❀ 已退出解封系统")

        else:
            fmts.print_err("§c❀ 您的输入有误")

    # 游戏内聊天栏菜单封禁玩家函数封装
    def ban_player_by_game(self, player: Player, _):
        player.show(
            "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        player.show("§l§d❐§f 『§6Orion System §d猎户座§f』 §b封禁§e管§a理 §d系统")
        player.show("§l§b[ §e1§b ] §r§e根据在线玩家名称和xuid封禁")
        player.show("§l§b[ §e2§b ] §r§e根据历史进服玩家名称和xuid封禁")
        player.show("§l§b[ §e3§b ] §r§e根据历史进服玩家设备号封禁")
        player.show(
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        player.show("§a❀ §b输入 §e[1-3]§b 之间的数字以选择 封禁模式")
        resp_1 = player.input(
            "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
        )

        if resp_1 == "1":
            allplayers = self.game_ctrl.allplayers.copy()
            page = 1
            while True:
                total_pages = math.ceil(len(allplayers) / self.game_items_per_page)
                start_index = (page - 1) * self.game_items_per_page + 1
                end_index = min(
                    start_index + self.game_items_per_page - 1, len(allplayers)
                )

                player.show(
                    "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                player.show("§l§b[ §a序号§b ] §r§a玩家名称 - xuid")
                for i in range(start_index, end_index + 1):
                    player.show(
                        f"§l§b[ §e{i}§b ] §r§e{allplayers[i - 1]} - {self.xuid_getter.get_xuid_by_name(allplayers[i - 1])}"
                    )
                player.show(
                    "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                player.show(
                    f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                )
                player.show(
                    f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的玩家和xuid"
                )
                player.show("§a❀ §b输入 §d- §e转到上一页")
                player.show("§a❀ §b输入 §d+ §e转到下一页")
                player.show("§a❀ §b输入 §d正整数+页 §e转到对应页")
                resp_2 = player.input(
                    "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                )

                if resp_2 is None:
                    player.show("§c❀ 回复超时！ 已退出封禁系统")
                    return
                if resp_2 in (".", "。"):
                    player.show("§a❀ 已退出封禁系统")
                    return
                if resp_2 == "-":
                    if page > 1:
                        page -= 1
                    else:
                        player.show("§6❀ 已经是第一页啦~")
                elif resp_2 == "+":
                    if page < total_pages:
                        page += 1
                    else:
                        player.show("§6❀ 已经是最后一页啦~")
                elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                    page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                    if 1 <= page_num <= total_pages:
                        page = page_num
                    else:
                        player.show(f"§6❀ 不存在第{page_num}页！请重新输入！")
                else:
                    resp_2 = utils.try_int(resp_2)
                    if resp_2 and resp_2 in range(start_index, end_index + 1):
                        ban_player = allplayers[resp_2 - 1]
                        ban_xuid = self.xuid_getter.get_xuid_by_name(ban_player)
                        break
                    player.show("§c❀ 您的输入有误")
                    return

            if ban_player in self.whitelist:
                player.show(
                    f"§6❀ 发现 玩家 {ban_player} 位于反制白名单内，请先将其移出白名单！"
                )
                return
            player.show(f"\n§a❀ 您选择了 玩家 {ban_player} (xuid:{ban_xuid})")
            player.show("§a❀ §b请按照以下格式输入封禁时间：")
            player.show("§6 · §f封禁时间 = -1  §e永久封禁")
            player.show("§6 · §f封禁时间 = 正整数  §e封禁<正整数>秒")
            player.show("§6 · §f封禁时间 = 0年0月5日6时7分8秒  §e封禁对应的时间")
            ban_time = player.input(
                "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
            )
            if ban_time in (".", "。"):
                player.show("§a❀ 已退出封禁系统")
                return
            if ban_time is None:
                player.show("§c❀ 回复超时！ 已退出封禁系统")
                return
            ban_time = self.ban_time_format(ban_time)
            if ban_time == 0:
                player.show("§c❀ 您输入的封禁时间有误")
                return
            player.show(f"\n§a❀ 您输入的封禁时间为 {ban_time}秒")
            player.show("§a❀ §b请输入封禁原因：")
            ban_reason = (
                player.input(
                    "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                )
                or "未知原因"
            )
            if ban_reason in (".", "。"):
                player.show("§a❀ 已退出封禁系统")
                return
            if ban_reason is None:
                player.show("§c❀ 回复超时！ 已退出封禁系统")
                return

            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
            path_ban_time = (
                f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{ban_xuid}.json"
            )
            with self.thread_lock_ban_player_by_xuid:
                ban_player_data = tempjson.load_and_read(
                    path_ban_time, need_file_exists=False, timeout=2
                )
                tempjson.unload_to_path(path_ban_time)

                if ban_player_data is None:
                    pre_ban_timestamp = timestamp_now
                else:
                    if ban_player_data["ban_end_timestamp"] == "Forever":
                        player.show(
                            f"§6❀ 玩家 {ban_player} (xuid:{ban_xuid}) 已经为永久封禁，无需重复封禁"
                        )
                        return
                    if ban_player_data["ban_end_timestamp"] < timestamp_now:
                        pre_ban_timestamp = timestamp_now
                    else:
                        pre_ban_timestamp = ban_player_data["ban_end_timestamp"]

                if ban_time == "Forever":
                    timestamp_end = "Forever"
                    date_end = "Forever"
                else:
                    timestamp_end = pre_ban_timestamp + ban_time
                    date_end = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)
                    )
                tempjson.load_and_write(
                    path_ban_time,
                    {
                        "xuid": ban_xuid,
                        "name": ban_player,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path_ban_time)
                tempjson.unload_to_path(path_ban_time)
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(
                    f'/kick "{ban_player}" 由于{ban_reason}，您被系统封禁至：{date_end}'
                )
            )
            player.show(
                f"\n§a❀ 封禁成功：已封禁玩家 {ban_player} (xuid:{ban_xuid}) 至 {date_end}"
            )
            fmts.print_suc(
                f"\n§a❀ [来自游戏内 {player.name} 的消息] 封禁成功：已封禁玩家 {ban_player} (xuid:{ban_xuid}) 至 {date_end}"
            )

        elif resp_1 == "2":
            path_xuid = "插件数据文件/前置-玩家XUID获取/xuids.json"
            try:
                with self.thread_lock_ban_player_by_xuid:
                    xuid_data = tempjson.load_and_read(
                        path_xuid, need_file_exists=True, timeout=2
                    )
                    tempjson.unload_to_path(path_xuid)
            except FileNotFoundError:
                player.show("§c❀ 未查询到任何xuid记录")
                return
            except Exception as error:
                player.show(f"§c❀ 查询xuid失败，原因：{error}")
                return
            player.show(
                "\n§a❀ §b请输入您想封禁的xuid、玩家名称或部分玩家名称，输入§elist或直接回车§b可查询当前服务器全部玩家名称与xuid记录"
            )
            name_or_xuid = player.input(
                "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
            )

            if name_or_xuid in (".", "。"):
                player.show("§a❀ 已退出封禁系统")
                return

            if name_or_xuid == "list":
                if len(xuid_data) == 0:
                    player.show("§c❀ 未查询到任何xuid记录")
                    return

                page = 1
                while True:
                    total_pages = math.ceil(len(xuid_data) / self.game_items_per_page)
                    start_index = (page - 1) * self.game_items_per_page + 1
                    end_index = min(
                        start_index + self.game_items_per_page - 1, len(xuid_data)
                    )

                    player.show(
                        "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    player.show("§l§b[ §a序号§b ] §r§a玩家名称 - xuid")
                    for i in range(start_index, end_index + 1):
                        player.show(
                            f"§l§b[ §e{i}§b ] §r§e{list(xuid_data.values())[i - 1]} - {list(xuid_data.keys())[i - 1]}"
                        )
                    player.show(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    player.show(
                        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                    )
                    player.show(
                        f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的玩家和xuid"
                    )
                    player.show("§a❀ §b输入 §d- §e转到上一页")
                    player.show("§a❀ §b输入 §d+ §e转到下一页")
                    player.show("§a❀ §b输入 §d正整数+页 §e转到对应页")
                    resp_2 = player.input(
                        "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                    )

                    if resp_2 is None:
                        player.show("§c❀ 回复超时！ 已退出封禁系统")
                        return
                    if resp_2 in (".", "。"):
                        player.show("§a❀ 已退出封禁系统")
                        return
                    if resp_2 == "-":
                        if page > 1:
                            page -= 1
                        else:
                            player.show("§6❀ 已经是第一页啦~")
                    elif resp_2 == "+":
                        if page < total_pages:
                            page += 1
                        else:
                            player.show("§6❀ 已经是最后一页啦~")
                    elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                        page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                        if 1 <= page_num <= total_pages:
                            page = page_num
                        else:
                            player.show(f"§6❀ 不存在第{page_num}页！请重新输入！")
                    else:
                        resp_2 = utils.try_int(resp_2)
                        if resp_2 and resp_2 in range(start_index, end_index + 1):
                            ban_player = list(xuid_data.values())[resp_2 - 1]
                            ban_xuid = list(xuid_data.keys())[resp_2 - 1]
                            break
                        player.show("§c❀ 您的输入有误")
                        return

            elif name_or_xuid is None:
                player.show("§c❀ 回复超时！ 已退出封禁系统")
                return

            elif name_or_xuid in xuid_data.keys():
                ban_xuid = name_or_xuid
                ban_player = xuid_data[name_or_xuid]

            else:
                page = 1
                while True:
                    matched_player: list[tuple[str, str]] = []
                    for k, v in xuid_data.items():
                        if name_or_xuid in v:
                            matched_player.append((v, k))

                    if matched_player == []:
                        player.show("§c❀ 找不到您输入的玩家名称或xuid")
                        return

                    total_pages = math.ceil(
                        len(matched_player) / self.game_items_per_page
                    )
                    start_index = (page - 1) * self.game_items_per_page + 1
                    end_index = min(
                        start_index + self.game_items_per_page - 1,
                        len(matched_player),
                    )
                    player.show("\n§a❀ 已匹配到以下玩家~")
                    player.show(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    player.show("§l§b[ §a序号§b ] §r§a玩家名称 - xuid")
                    for i in range(start_index, end_index + 1):
                        player.show(
                            f"§l§b[ §e{i}§b ] §r§e{matched_player[i - 1][0].replace(name_or_xuid, f'§b{name_or_xuid}§e')} - {matched_player[i - 1][1]}"
                        )
                    player.show(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    player.show(
                        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                    )
                    player.show(
                        f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的玩家和xuid，或者输入玩家名称再次尝试搜索"
                    )
                    player.show("§a❀ §b输入 §d- §e转到上一页")
                    player.show("§a❀ §b输入 §d+ §e转到下一页")
                    player.show("§a❀ §b输入 §d正整数+页 §e转到对应页")
                    resp_2 = player.input(
                        "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                    )

                    if resp_2 is None:
                        player.show("§c❀ 回复超时！ 已退出封禁系统")
                        return
                    if resp_2 in (".", "。"):
                        player.show("§a❀ 已退出封禁系统")
                        return
                    if resp_2 == "-":
                        if page > 1:
                            page -= 1
                        else:
                            player.show("§6❀ 已经是第一页啦~")
                    elif resp_2 == "+":
                        if page < total_pages:
                            page += 1
                        else:
                            player.show("§6❀ 已经是最后一页啦~")
                    elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                        page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                        if 1 <= page_num <= total_pages:
                            page = page_num
                        else:
                            player.show(f"§6❀ 不存在第{page_num}页！请重新输入！")
                    else:
                        try:
                            resp_2 = int(resp_2)
                            if resp_2 and resp_2 in range(start_index, end_index + 1):
                                ban_player = matched_player[resp_2 - 1][0]
                                ban_xuid = matched_player[resp_2 - 1][1]
                                break
                            player.show("§c❀ 您的输入有误")
                            return
                        except ValueError:
                            name_or_xuid = resp_2
                            page = 1

            if ban_player in self.whitelist:
                player.show(
                    f"§6❀ 发现 玩家 {ban_player} 位于反制白名单内，请先将其移出白名单！"
                )
                return
            player.show(f"\n§a❀ 您选择了 玩家 {ban_player} (xuid:{ban_xuid})")
            player.show("§a❀ §b请按照以下格式输入封禁时间：")
            player.show("§6 · §f封禁时间 = -1  §e永久封禁")
            player.show("§6 · §f封禁时间 = 正整数  §e封禁<正整数>秒")
            player.show("§6 · §f封禁时间 = 0年0月5日6时7分8秒  §e封禁对应的时间")
            ban_time = player.input(
                "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
            )
            if ban_time in (".", "。"):
                player.show("§a❀ 已退出封禁系统")
                return
            if ban_time is None:
                player.show("§c❀ 回复超时！ 已退出封禁系统")
                return
            ban_time = self.ban_time_format(ban_time)
            if ban_time == 0:
                player.show("§c❀ 您输入的封禁时间有误")
                return
            player.show(f"\n§a❀ 您输入的封禁时间为 {ban_time}秒")
            player.show("§a❀ §b请输入封禁原因：")
            ban_reason = (
                player.input(
                    "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                )
                or "未知原因"
            )
            if ban_reason in (".", "。"):
                player.show("§a❀ 已退出封禁系统")
                return
            if ban_reason is None:
                player.show("§c❀ 回复超时！ 已退出封禁系统")
                return

            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
            path_ban_time = (
                f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{ban_xuid}.json"
            )
            with self.thread_lock_ban_player_by_xuid:
                ban_player_data = tempjson.load_and_read(
                    path_ban_time, need_file_exists=False, timeout=2
                )
                tempjson.unload_to_path(path_ban_time)

                if ban_player_data is None:
                    pre_ban_timestamp = timestamp_now
                else:
                    if ban_player_data["ban_end_timestamp"] == "Forever":
                        player.show(
                            f"§6❀ 玩家 {ban_player} (xuid:{ban_xuid}) 已经为永久封禁，无需重复封禁"
                        )
                        return
                    if ban_player_data["ban_end_timestamp"] < timestamp_now:
                        pre_ban_timestamp = timestamp_now
                    else:
                        pre_ban_timestamp = ban_player_data["ban_end_timestamp"]

                if ban_time == "Forever":
                    timestamp_end = "Forever"
                    date_end = "Forever"
                else:
                    timestamp_end = pre_ban_timestamp + ban_time
                    date_end = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)
                    )
                tempjson.load_and_write(
                    path_ban_time,
                    {
                        "xuid": ban_xuid,
                        "name": ban_player,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path_ban_time)
                tempjson.unload_to_path(path_ban_time)
            self.game_ctrl.sendwocmd(
                self.try_hide_ban_info(
                    f'/kick "{ban_player}" 由于{ban_reason}，您被系统封禁至：{date_end}'
                )
            )
            player.show(
                f"\n§a❀ 封禁成功：已封禁玩家 {ban_player} (xuid:{ban_xuid}) 至 {date_end}"
            )
            fmts.print_suc(
                f"\n§a❀ [来自游戏内 {player.name} 的消息] 封禁成功：已封禁玩家 {ban_player} (xuid:{ban_xuid}) 至 {date_end}"
            )

        elif resp_1 == "3":
            path_device_id = f"{self.data_path}/玩家丨设备号丨xuid丨历史名称丨记录.json"
            try:
                with self.thread_lock_ban_player_by_device_id:
                    device_id_data = tempjson.load_and_read(
                        path_device_id, need_file_exists=True, default={}, timeout=2
                    )
                    tempjson.unload_to_path(path_device_id)
            except FileNotFoundError:
                player.show("§c❀ 未查询到任何设备号记录")
                return
            except Exception as error:
                player.show(f"§c❀ 查询设备号记录失败，原因：{error}")
                return
            player.show(
                "\n§a❀ §b请输入您想封禁的设备号、玩家名称或部分玩家名称，输入§elist或直接回车§b可查询当前服务器全部设备号记录"
            )
            device_id = player.input(
                "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
            )

            if device_id in (".", "。"):
                player.show("§a❀ 已退出封禁系统")
                return
            if device_id == "list":
                if len(device_id_data) == 0:
                    player.show("§c❀ 未查询到任何设备号记录")
                    return

                page = 1
                while True:
                    total_pages = math.ceil(
                        len(device_id_data) / self.game_items_per_page
                    )
                    start_index = (page - 1) * self.game_items_per_page + 1
                    end_index = min(
                        start_index + self.game_items_per_page - 1,
                        len(device_id_data),
                    )

                    player.show(
                        "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    player.show(
                        "§l§b[ §a序号§b ] §r§a设备号 - {xuid: [玩家名称与改名记录]}"
                    )
                    for i in range(start_index, end_index + 1):
                        player.show(
                            f"§l§b[ §e{i}§b ] §r§e{list(device_id_data.keys())[i - 1]} - {list(device_id_data.values())[i - 1]}"
                        )
                    player.show(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    player.show(
                        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                    )
                    player.show(
                        f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的设备号"
                    )
                    player.show("§a❀ §b输入 §d- §e转到上一页")
                    player.show("§a❀ §b输入 §d+ §e转到下一页")
                    player.show("§a❀ §b输入 §d正整数+页 §e转到对应页")
                    resp_2 = player.input(
                        "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                    )

                    if resp_2 is None:
                        player.show("§c❀ 回复超时！ 已退出封禁系统")
                        return
                    if resp_2 in (".", "。"):
                        player.show("§a❀ 已退出封禁系统")
                        return
                    if resp_2 == "-":
                        if page > 1:
                            page -= 1
                        else:
                            player.show("§6❀ 已经是第一页啦~")
                    elif resp_2 == "+":
                        if page < total_pages:
                            page += 1
                        else:
                            player.show("§6❀ 已经是最后一页啦~")
                    elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                        page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                        if 1 <= page_num <= total_pages:
                            page = page_num
                        else:
                            player.show(f"§6❀ 不存在第{page_num}页！请重新输入！")
                    else:
                        resp_2 = utils.try_int(resp_2)
                        if resp_2 and resp_2 in range(start_index, end_index + 1):
                            ban_device_id = list(device_id_data.keys())[resp_2 - 1]
                            ban_player_and_xuid_data = list(device_id_data.values())[
                                resp_2 - 1
                            ]
                            break
                        player.show("§c❀ 您的输入有误")
                        return

            elif device_id is None:
                player.show("§c❀ 回复超时！ 已退出封禁系统")
                return

            elif device_id in device_id_data.keys():
                ban_device_id = device_id
                ban_player_and_xuid_data = device_id_data[device_id]

            else:
                page = 1
                while True:
                    matched_player: list[tuple[str, str]] = []
                    for k, v in device_id_data.items():
                        for m in v.values():
                            for n in m:
                                if device_id in n:
                                    matched_player.append((k, v))
                                    break
                            else:
                                continue
                            break

                    if matched_player == []:
                        player.show("§c❀ 找不到您输入的玩家名称或设备号")
                        return

                    total_pages = math.ceil(
                        len(matched_player) / self.game_items_per_page
                    )
                    start_index = (page - 1) * self.game_items_per_page + 1
                    end_index = min(
                        start_index + self.game_items_per_page - 1,
                        len(matched_player),
                    )

                    player.show("\n§a❀ 已匹配到以下玩家~")
                    player.show(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    player.show(
                        "§l§b[ §a序号§b ] §r§a设备号 - {xuid: [玩家名称与改名记录]}"
                    )
                    for i in range(start_index, end_index + 1):
                        colored_device_id_data = "{"
                        for k, v in matched_player[i - 1][1].items():
                            v = str(v).replace(device_id, f"§b{device_id}§e")
                            colored_device_id_data = (
                                colored_device_id_data + f"'{k}': {v}, "
                            )
                        colored_device_id_data = colored_device_id_data[:-2] + "}"
                        player.show(
                            f"§l§b[ §e{i}§b ] §r§e{matched_player[i - 1][0]} - {colored_device_id_data}"
                        )
                    player.show(
                        "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                    )
                    player.show(
                        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                    )
                    player.show(
                        f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 封禁的设备号，或者输入玩家名称再次尝试搜索"
                    )
                    player.show("§a❀ §b输入 §d- §e转到上一页")
                    player.show("§a❀ §b输入 §d+ §e转到下一页")
                    player.show("§a❀ §b输入 §d正整数+页 §e转到对应页")
                    resp_2 = player.input(
                        "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                    )

                    if resp_2 is None:
                        player.show("§c❀ 回复超时！ 已退出封禁系统")
                        return
                    if resp_2 in (".", "。"):
                        player.show("§a❀ 已退出封禁系统")
                        return
                    if resp_2 == "-":
                        if page > 1:
                            page -= 1
                        else:
                            player.show("§6❀ 已经是第一页啦~")
                    elif resp_2 == "+":
                        if page < total_pages:
                            page += 1
                        else:
                            player.show("§6❀ 已经是最后一页啦~")
                    elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                        page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                        if 1 <= page_num <= total_pages:
                            page = page_num
                        else:
                            player.show(f"§6❀ 不存在第{page_num}页！请重新输入！")
                    else:
                        try:
                            resp_2 = int(resp_2)
                            if resp_2 and resp_2 in range(start_index, end_index + 1):
                                ban_device_id = matched_player[resp_2 - 1][0]
                                ban_player_and_xuid_data = matched_player[resp_2 - 1][1]
                                break
                            player.show("§c❀ 您的输入有误")
                            return
                        except ValueError:
                            device_id = resp_2
                            page = 1

            ban_xuid_list = []
            for k in ban_player_and_xuid_data.keys():
                ban_xuid_list.append(k)

            player.show(
                f"\n§a❀ 您选择了 设备号 {ban_device_id} (使用此设备加入游戏的玩家xuid和名称记录:{ban_player_and_xuid_data})"
            )
            player.show("§a❀ §b请按照以下格式输入封禁时间：")
            player.show("§6 · §f封禁时间 = -1  §e永久封禁")
            player.show("§6 · §f封禁时间 = 正整数  §e封禁<正整数>秒")
            player.show("§6 · §f封禁时间 = 0年0月5日6时7分8秒  §e封禁对应的时间")
            ban_time = player.input(
                "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
            )
            if ban_time in (".", "。"):
                player.show("§a❀ 已退出封禁系统")
                return
            if ban_time is None:
                player.show("§c❀ 回复超时！ 已退出封禁系统")
                return
            ban_time = self.ban_time_format(ban_time)
            if ban_time == 0:
                player.show("§c❀ 您输入的封禁时间有误")
                return
            player.show(f"\n§a❀ 您输入的封禁时间为 {ban_time}秒")
            player.show("§a❀ §b请输入封禁原因：")
            ban_reason = (
                player.input(
                    "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                )
                or "未知原因"
            )
            if ban_reason in (".", "。"):
                player.show("§a❀ 已退出封禁系统")
                return
            if ban_reason is None:
                player.show("§c❀ 回复超时！ 已退出封禁系统")
                return

            timestamp_now = int(time.time())
            date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
            path_ban_time = (
                f"{self.data_path}/玩家封禁时间数据(以设备号记录)/{ban_device_id}.json"
            )
            with self.thread_lock_ban_player_by_device_id:
                ban_player_data = tempjson.load_and_read(
                    path_ban_time, need_file_exists=False, timeout=2
                )
                tempjson.unload_to_path(path_ban_time)

                if ban_player_data is None:
                    pre_ban_timestamp = timestamp_now
                else:
                    if ban_player_data["ban_end_timestamp"] == "Forever":
                        player.show(
                            f"§6❀ 设备号 {ban_device_id} 已经为永久封禁，无需重复封禁 (使用此设备加入游戏的玩家xuid和名称记录:{ban_player_and_xuid_data})"
                        )
                        return
                    if ban_player_data["ban_end_timestamp"] < timestamp_now:
                        pre_ban_timestamp = timestamp_now
                    else:
                        pre_ban_timestamp = ban_player_data["ban_end_timestamp"]

                if ban_time == "Forever":
                    timestamp_end = "Forever"
                    date_end = "Forever"
                else:
                    timestamp_end = pre_ban_timestamp + ban_time
                    date_end = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)
                    )
                tempjson.load_and_write(
                    path_ban_time,
                    {
                        "device_id": ban_device_id,
                        "xuid_and_player": ban_player_and_xuid_data,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                    need_file_exists=False,
                    timeout=2,
                )
                tempjson.flush(path_ban_time)
                tempjson.unload_to_path(path_ban_time)
            for k in ban_xuid_list:
                self.game_ctrl.sendwocmd(
                    self.try_hide_ban_info(
                        f'/kick "{k}" 由于{ban_reason}，您被系统封禁至：{date_end}'
                    )
                )
            player.show(
                f"\n§a❀ 封禁成功：已封禁设备号 {ban_device_id} 至 {date_end} (使用此设备加入游戏的玩家xuid和名称记录:{ban_player_and_xuid_data})"
            )
            fmts.print_suc(
                f"\n§a❀ [来自游戏内 {player.name} 的消息] 封禁成功：已封禁设备号 {ban_device_id} 至 {date_end} (使用此设备加入游戏的玩家xuid和名称记录:{ban_player_and_xuid_data})"
            )

        elif resp_1 in (".", "。"):
            player.show("§a❀ 已退出封禁系统")

        elif resp_1 is None:
            player.show("§c❀ 回复超时！ 已退出封禁系统")

        else:
            player.show("§c❀ 您的输入有误")

    # 游戏内聊天栏菜单解封玩家函数封装
    def unban_player_by_game(self, player: Player, _):
        player.show(
            "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        player.show("§l§d❐§f 『§6Orion System §d猎户座§f』 §b解封§e管§a理 §d系统")
        player.show("§l§b[ §e1§b ] §r§e根据玩家名称和xuid解封")
        player.show("§l§b[ §e2§b ] §r§e根据设备号解封")
        player.show(
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        player.show("§a❀ §b输入 §e[1-2]§b 之间的数字以选择 解封模式")
        resp_1 = player.input(
            "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
        )

        if resp_1 == "1":
            all_ban_player_xuids = os.listdir(
                f"{self.data_path}/玩家封禁时间数据(以xuid记录)"
            )
            all_ban_playernames: list[tuple[str, str]] = []
            for i in all_ban_player_xuids:
                xuid = i.replace(".json", "")
                try:
                    all_ban_playernames.append(
                        (
                            self.xuid_getter.get_name_by_xuid(xuid, allow_offline=True),
                            xuid,
                        )
                    )
                except ValueError:
                    continue
            if all_ban_playernames == []:
                player.show("§6❀ 目前没有正在封禁的玩家和xuid")
                return

            page = 1
            while True:
                total_pages = math.ceil(
                    len(all_ban_playernames) / self.game_items_per_page
                )
                start_index = (page - 1) * self.game_items_per_page + 1
                end_index = min(
                    start_index + self.game_items_per_page - 1,
                    len(all_ban_playernames),
                )

                player.show(
                    "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                player.show("§l§b[ §a序号§b ] §r§a玩家名称 - xuid")
                for i in range(start_index, end_index + 1):
                    player.show(
                        f"§l§b[ §e{i}§b ] §r§e{all_ban_playernames[i - 1][0]} - {all_ban_playernames[i - 1][1]}"
                    )
                player.show(
                    "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                player.show(
                    f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                )
                player.show(
                    f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 解封的玩家和xuid"
                )
                player.show("§a❀ §b输入 §d- §e转到上一页")
                player.show("§a❀ §b输入 §d+ §e转到下一页")
                player.show("§a❀ §b输入 §d正整数+页 §e转到对应页")
                resp_2 = player.input(
                    "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                )

                if resp_2 is None:
                    player.show("§c❀ 回复超时！ 已退出解封系统")
                    return
                if resp_2 in (".", "。"):
                    player.show("§a❀ 已退出解封系统")
                    return
                if resp_2 == "-":
                    if page > 1:
                        page -= 1
                    else:
                        player.show("§6❀ 已经是第一页啦~")
                elif resp_2 == "+":
                    if page < total_pages:
                        page += 1
                    else:
                        player.show("§6❀ 已经是最后一页啦~")
                elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                    page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                    if 1 <= page_num <= total_pages:
                        page = page_num
                    else:
                        player.show(f"§6❀ 不存在第{page_num}页！请重新输入！")
                else:
                    resp_2 = utils.try_int(resp_2)
                    if resp_2 and resp_2 in range(start_index, end_index + 1):
                        unban_player = all_ban_playernames[resp_2 - 1][0]
                        unban_xuid = all_ban_playernames[resp_2 - 1][1]
                        os.remove(
                            f"{self.data_path}/玩家封禁时间数据(以xuid记录)/{unban_xuid}.json"
                        )
                        player.show(
                            f"\n§a❀ 解封成功: 已解封玩家 {unban_player} (xuid:{unban_xuid})"
                        )
                        fmts.print_suc(
                            f"\n§a❀ [来自游戏内 {player.name} 的消息] 解封成功: 已解封玩家 {unban_player} (xuid:{unban_xuid})"
                        )
                        break
                    player.show("§c❀ 您的输入有误")
                    return

        elif resp_1 == "2":
            all_ban_player_device_id = os.listdir(
                f"{self.data_path}/玩家封禁时间数据(以设备号记录)"
            )
            all_ban_device_id: list[tuple[str, str]] = []

            path_device_id = f"{self.data_path}/玩家丨设备号丨xuid丨历史名称丨记录.json"
            try:
                with self.thread_lock_ban_player_by_device_id:
                    device_id_data = tempjson.load_and_read(
                        path_device_id, need_file_exists=True, default={}, timeout=2
                    )
                    tempjson.unload_to_path(path_device_id)
            except FileNotFoundError:
                player.show("§c❀ 未查询到任何设备号记录")
            except Exception as error:
                player.show(f"§c❀ 查询设备号记录失败，原因：{error}")

            for i in all_ban_player_device_id:
                device_id = i.replace(".json", "")
                try:
                    all_ban_device_id.append(
                        (device_id, device_id_data.get(device_id, ""))
                    )
                except ValueError:
                    continue
            if all_ban_device_id == []:
                player.show("§6❀ 目前没有正在封禁的设备号")
                return

            page = 1
            while True:
                total_pages = math.ceil(
                    len(all_ban_device_id) / self.game_items_per_page
                )
                start_index = (page - 1) * self.game_items_per_page + 1
                end_index = min(
                    start_index + self.game_items_per_page - 1,
                    len(all_ban_device_id),
                )

                player.show(
                    "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                player.show(
                    "§l§b[ §a序号§b ] §r§a设备号 - {xuid: [玩家名称与改名记录]}"
                )
                for i in range(start_index, end_index + 1):
                    player.show(
                        f"§l§b[ §e{i}§b ] §r§e{all_ban_device_id[i - 1][0]} - {all_ban_device_id[i - 1][1]}"
                    )
                player.show(
                    "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
                )
                player.show(
                    f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]"
                )
                player.show(
                    f"§a❀ §b输入 §e[{start_index}-{end_index}]§b 之间的数字以选择 解封的设备号"
                )
                player.show("§a❀ §b输入 §d- §e转到上一页")
                player.show("§a❀ §b输入 §d+ §e转到下一页")
                player.show("§a❀ §b输入 §d正整数+页 §e转到对应页")
                resp_2 = player.input(
                    "§a❀ §b输入 §c. §b退出", timeout=self.ban_player_by_game_timeout
                )

                if resp_2 is None:
                    player.show("§c❀ 回复超时！ 已退出解封系统")
                    return
                if resp_2 in (".", "。"):
                    player.show("§a❀ 已退出解封系统")
                    return
                if resp_2 == "-":
                    if page > 1:
                        page -= 1
                    else:
                        player.show("§6❀ 已经是第一页啦~")
                elif resp_2 == "+":
                    if page < total_pages:
                        page += 1
                    else:
                        player.show("§6❀ 已经是最后一页啦~")
                elif bool(re.fullmatch(r"^[1-9]\d*页$", resp_2)):
                    page_num = int(re.fullmatch(r"^([1-9]\d*)页$", resp_2).group(1))
                    if 1 <= page_num <= total_pages:
                        page = page_num
                    else:
                        player.show(f"§6❀ 不存在第{page_num}页！请重新输入！")
                else:
                    resp_2 = utils.try_int(resp_2)
                    if resp_2 and resp_2 in range(start_index, end_index + 1):
                        unban_device_id = all_ban_device_id[resp_2 - 1][0]
                        unban_device_id_data = all_ban_device_id[resp_2 - 1][1]
                        os.remove(
                            f"{self.data_path}/玩家封禁时间数据(以设备号记录)/{unban_device_id}.json"
                        )
                        player.show(
                            f"\n§a❀ 解封成功: 已解封设备号 {unban_device_id} (使用此设备加入游戏的玩家xuid和名称记录:{unban_device_id_data})"
                        )
                        fmts.print_suc(
                            f"\n§a❀ [来自游戏内 {player.name} 的消息] 解封成功: 已解封设备号 {unban_device_id} (使用此设备加入游戏的玩家xuid和名称记录:{unban_device_id_data})"
                        )
                        break
                    player.show("§c❀ 您的输入有误")
                    return

        elif resp_1 in (".", "。"):
            player.show("§a❀ 已退出解封系统")

        elif resp_1 is None:
            player.show("§c❀ 回复超时！ 已退出解封系统")

        else:
            player.show("§c❀ 您的输入有误")


entry = plugin_entry(Orion_System, "Orion_System")

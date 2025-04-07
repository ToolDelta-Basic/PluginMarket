from tooldelta import Plugin, plugin_entry, cfg, utils, fmts
from tooldelta.constants import PacketIDS
import time
import json


class BattleEye(Plugin):  # 插件主类
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
            "名称违禁词列表": ["狂笑", "要猫", "药猫", "妖猫", "幺猫", "要儿", "药儿", "妖儿", "幺儿", "孙政", "guiwow", "吴旭淳", "九重天", "XTS", "天庭", "白墙", "跑路", "runaway", "导入", "busj", "万花筒", "购买", "出售"],
            "反制白名单": ["style_天枢", "style_天璇", "..."],
            "服务器准入等级": 1,
            "如果您需要“禁止游戏内私聊(tell,msg,w命令)”，请将机器人踢出游戏后启用sendcommandfeedback，命令为/gamerule sendcommandfeedback true": None,
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
            "周期内重复消息刷屏数量限制": 3
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
            "周期内重复消息刷屏数量限制": cfg.PInt
        }
        config, _ = cfg.get_plugin_config_and_version(  # 调用配置
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

        self.ListenActive(self.on_active)
        self.ListenPacket(PacketIDS.IDPlayerList, self.on_PlayerList)  # 监听PlayerList数据包
        self.ListenPacket(PacketIDS.IDText, self.on_Text)  # 监听Text数据包

        if self.speak_speed_limit or self.repeat_message_limit:  # 创建异步计时器，用于刷新“检测发言频率”和“检测重复刷屏”的缓存
            self.data = {}

            @utils.thread_func("发言周期检测计时器")
            def timer():
                while True:
                    self.data = {}
                    time.sleep(self.speak_detection_cycle)
            timer()

    def blacklist_word_detect(self, message, player):  # 黑名单词检测函数封装
        if self.Testfor_blacklist_word and player not in self.whitelist:
            blacklist_word_set = set(self.blacklist_word_list)
            n = len(message)
            for i in range(n):
                for j in range(i + 1, n + 1):
                    if message[i:j] in blacklist_word_set:
                        fmts.print_inf(f"§c发现 {player} 发送的文本触发了黑名单词({message[i:j]})，正在踢出")
                        self.game_ctrl.sendwocmd(f"/kick \"{player}\" 您发送的文本触发了黑名单词({message[i:j]})")
                        fmts.print_inf(f"§a发现 {player} 发送的文本触发了黑名单词({message[i:j]})，已被踢出游戏")

    def message_length_detect(self, message, player):  # 发言字数检测函数封装
        if self.message_length_limit and len(message) > self.max_speak_length and player not in self.whitelist:
            fmts.print_inf(f"§c发现 {player} 发送的文本长度超过{self.max_speak_length}，正在踢出")
            self.game_ctrl.sendwocmd(f"/kick \"{player}\" 您发送的文本过长，请勿刷屏")
            fmts.print_inf(f"§a发现 {player} 发送的文本长度超过{self.max_speak_length}，已被踢出游戏")

    def message_cache_area(self, message, player):  # 将发言玩家、文本添加至缓存区
        if self.speak_speed_limit or self.repeat_message_limit:
            if self.data.get(player) is None:
                self.data[player] = []
            self.data[player].append(message)
            self.speak_speed_detect(player)
            self.repeat_message_detect(player)

    def speak_speed_detect(self, player):  # 发言频率检测函数封装
        if self.speak_speed_limit and len(self.data[player]) > self.max_speak_count and player not in self.whitelist:
            fmts.print_inf(f"§c发现 {player} 发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)，正在踢出")
            self.game_ctrl.sendwocmd(f"/kick \"{player}\" 您发言过快，休息一下吧~")
            fmts.print_inf(f"§a发现 {player} 发送文本速度超过限制({self.max_speak_count}条/{self.speak_detection_cycle}秒)，已被踢出游戏")

    def repeat_message_detect(self, player):  # 重复消息刷屏检测函数封装
        if self.repeat_message_limit and player not in self.whitelist:
            counts = {}
            for i in self.data[player]:
                counts[i] = counts.get(i, 0) + 1
            for _, v in counts.items():
                if v > self.max_repeat_count:
                    fmts.print_inf(f"§c发现 {player} 连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)，正在踢出")
                    self.game_ctrl.sendwocmd(f"/kick \"{player}\" 您重复刷屏过快，休息一下吧~")
                    fmts.print_inf(f"§a发现 {player} 连续发送重复文本超出限制({self.max_repeat_count}条/{self.speak_detection_cycle}秒)，已被踢出游戏")
                    break

    def on_active(self):
        self.bot_name = self.frame.launcher.omega.get_bot_basic_info().BotName  # 调用Omega的API，获取机器人名字，必须等待Omega框架加载完毕后才能运行
        fmts.print_inf("§b如果您需要“禁止游戏内私聊(tell,msg,w命令)”，§e请将机器人踢出游戏后启用sendcommandfeedback，§b命令为/gamerule sendcommandfeedback true")

    def on_PlayerList(self, packet):

        if packet["ActionType"] == 0:
            Username = packet["Entries"][0]["Username"]
            PremiumSkin = packet["Entries"][0]["Skin"]["PremiumSkin"]
            Trusted = packet["Entries"][0]["Skin"]["Trusted"]
            CapeID = packet["Entries"][0]["Skin"]["CapeID"]
            GrowthLevels = packet["GrowthLevels"][0]

            if Username not in self.whitelist:

                if self.is_detect_bot and (PremiumSkin is False or Trusted is False or CapeID is None):
                    fmts.print_inf(f"§c发现 {Username} 可能为崩服机器人，正在制裁")
                    fmts.print_war(f"崩服机器人数据: {packet}")
                    self.game_ctrl.sendwocmd(f"/kick \"{Username}\" 您必须通过 Microsoft 服务身份验证。")
                    fmts.print_inf(f"§a发现 {Username} 可能为崩服机器人，制裁已完成")

                if self.is_level_limit and GrowthLevels < self.server_level:
                    fmts.print_inf(f"§c发现 {Username} 等级低于服务器准入等级，正在踢出")
                    self.game_ctrl.sendwocmd(f"/kick \"{Username}\" 本服准入等级为{self.server_level}级，您的等级过低，请加油升级噢！")
                    fmts.print_inf(f"§a发现 {Username} 等级低于服务器等级，已被踢出游戏")

                if self.is_detect_netease_banned_word:
                    try:
                        self.game_ctrl.sendcmd(f"/testfor \"{Username}\"", True, 2)
                    except TimeoutError:
                        fmts.print_inf(f"§c发现 {Username} 名称为屏蔽词，正在踢出")
                        self.game_ctrl.sendwocmd(f"/kick \"{Username}\" 您必须通过 Microsoft 服务身份验证。")
                        fmts.print_inf(f"§a发现 {Username} 名称为屏蔽词，已被踢出游戏")

                if self.is_detect_self_banned_word:
                    self.banned_word_set = set(self.banned_word_list)
                    n = len(Username)
                    for i in range(n):
                        for j in range(i + 1, n + 1):
                            if Username[i:j] in self.banned_word_set:
                                fmts.print_inf(f"§c发现 {Username} 名称为自定义违禁词({Username[i:j]})，正在踢出")
                                self.game_ctrl.sendwocmd(f"/kick \"{Username}\" 您必须通过 Microsoft 服务身份验证。")
                                fmts.print_inf(f"§a发现 {Username} 名称为自定义违禁词({Username[i:j]})，已被踢出游戏")

    def on_Text(self, packet):

        if packet["TextType"] == 10 and packet["XUID"] != "":  # "TextType"=10:监听到命令执行反馈
            try:
                rawtext_list = json.loads(packet["Message"])["rawtext"]
                translate_list = []
                for i in rawtext_list:
                    if "translate" in i:
                        translate_list.append(i["translate"])
                original_player = translate_list[0]
                commands_type = translate_list[1]
                if commands_type == "commands.message.display.outgoing" and original_player not in self.whitelist:  # "commands.message.display.outgoing":监听到游戏内私聊(tell,msg,w命令)
                    for i in rawtext_list:
                        if "with" in i:
                            with_rawtext = i["with"]["rawtext"]
                            target_player = with_rawtext[0]["text"]
                            msg_text = with_rawtext[1]["text"]
                            break
                    if self.ban_private_chat:
                        if self.allow_chat_with_bot:
                            if target_player != self.bot_name:
                                fmts.print_inf(f"§c发现 {original_player} 尝试发送私聊(tell,msg,w命令)，正在踢出")
                                self.game_ctrl.sendwocmd(f"/kick \"{original_player}\" 禁止发送私聊(tell,msg,w命令)！")
                                fmts.print_inf(f"§a发现 {original_player} 尝试发送私聊(tell,msg,w命令)，已被踢出游戏")
                        else:
                            fmts.print_inf(f"§c发现 {original_player} 尝试发送私聊(tell,msg,w命令)，正在踢出")
                            self.game_ctrl.sendwocmd(f"/kick \"{original_player}\" 禁止发送私聊(tell,msg,w命令)！")
                            fmts.print_inf(f"§a发现 {original_player} 尝试发送私聊(tell,msg,w命令)，已被踢出游戏")
                    self.blacklist_word_detect(msg_text, original_player)
                    self.message_length_detect(msg_text, original_player)
                    self.message_cache_area(msg_text, original_player)
            except Exception as error:
                print(f"在解析私聊数据包或某些命令数据包时出现错误: {str(error)}")

        elif packet["TextType"] == 1:  # "TextType"=1:监听到常规发言或me命令
            try:
                message = packet["Message"]
                sourcename = packet["SourceName"]
                if message.startswith("*") and sourcename == "":  # 判断为me命令
                    message_split = message.split(" ", 2)
                    player = message_split[1]
                    msg_text = message_split[2]
                    if self.ban_me_command and player not in self.whitelist:
                        fmts.print_inf(f"§c发现 {player} 尝试发送me命令，正在踢出")
                        self.game_ctrl.sendwocmd(f"/kick \"{player}\" 禁止发送me命令！")
                        fmts.print_inf(f"§a发现 {player} 尝试发送me命令，已被踢出游戏")
                    self.blacklist_word_detect(msg_text, player)
                    self.message_length_detect(msg_text, player)
                    self.message_cache_area(msg_text, player)
                elif sourcename != "":  # 判断为常规发言
                    self.blacklist_word_detect(message, sourcename)
                    self.message_length_detect(message, sourcename)
                    self.message_cache_area(message, sourcename)
            except Exception as error:
                print(f"在解析发言数据包或me命令时出现错误 {str(error)}")


entry = plugin_entry(BattleEye, "BattleEye")

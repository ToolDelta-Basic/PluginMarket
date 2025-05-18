from tooldelta import Plugin, fmts, cfg, plugin_entry, utils, Chat, Player


class AntiTooFastMessage_V2(Plugin):
    name = "发言频率限制v2"
    author = "SuperScript"
    version = (0, 1, 1)

    def __init__(self, frame):
        super().__init__(frame)
        CFG_DEFAULT = {
            "检测周期(秒)": 5,
            "检测周期内最多发送多少条消息": 5,
            "发言太快反制措施": [
                "kick [XUID] §c发言太快， 您已被踢出租赁服",
                "say §6[玩家名] §c因发言太快被踢出租赁服",
            ],
            "多少个换行判定为刷屏": 6,
            "多长的消息判定为刷屏": 100,
            cfg.KeyGroup(
                funckey
                := "自定义踢出逻辑lambda函数(玩家名:str,消息:str)->(违规消息:str,为空则视为不违规)"
            ): "lambda playername,msg:''",
        }

        config, _ = cfg.get_plugin_config_and_version(
            "发言频率限制", cfg.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, (0, 0, 5)
        )
        if funckey not in config.keys():
            config[funckey] = "lambda playername,msg:False"
            cfg.upgrade_plugin_config("发言频率限制", config, self.version)
            fmts.print_inf("发言频率限制 插件配置文件已更新")
        self.detect_time = config["检测周期(秒)"]
        self.msg_lmt = config["检测周期内最多发送多少条消息"]
        self.msg_lmt_anti = config["发言太快反制措施"]
        self.msg_length_limit = config["多长的消息判定为刷屏"]
        self.msg_lines_limit = config["多少个换行判定为刷屏"]
        try:
            self.invalid_msg_checker = eval(config[funckey])
        except Exception as e:
            fmts.print_err(f"{self.name} 插件配置文件自定义踢出逻辑函数格式错误: {e}")
            raise SystemExit
        if not callable(self.invalid_msg_checker):
            fmts.print_err(
                f"{self.name} 插件配置文件自定义踢出逻辑函数: 不是一个函数对象"
            )
            raise SystemExit
        self.last_msgs: dict[str, int] = {}

        self.ListenActive(self.on_active)
        self.ListenPlayerLeave(self.player_leave)
        self.ListenChat(self.player_msg)

    def on_active(self):
        utils.timer_event(self.detect_time, "发言频率限制v2")(self.clear_message_lmt)()

    def is_too_fast(self, player: Player) -> bool:
        return self.last_msgs.get(player.name, 0) > self.msg_lmt

    def clear_message_lmt(self):
        self.last_msgs.clear()

    def player_msg(self, msg_info: Chat):
        player = msg_info.player
        msg = msg_info.msg

        if player not in self.frame.get_players().getAllPlayers():
            return

        self.last_msgs.setdefault(player.name, 0)
        self.last_msgs[player.name] += 1
        if player.is_op():
            return

        if display_str := self.invalid_msg_checker(player.name, msg):
            self.game_ctrl.sendwocmd(f'kick "{player.name}" {display_str}')
            self.print(f"§6玩家 {player.name} 被违规消息检测函数检测到: {display_str}")
        elif len(msg) > self.msg_length_limit:
            self.game_ctrl.sendwocmd(
                f"kick {player.xuid} §c发言长度太长， 您已被踢出租赁服"
            )
            self.print(f"§6玩家 {player.name} 发言长度太长({len(msg)}), 已被踢出租赁服")
        elif (lines := msg.count("\n")) > self.msg_lines_limit:
            self.game_ctrl.sendwocmd(
                f"kick {player.xuid} §c发言行数太多， 您已被踢出租赁服"
            )
            self.print(f"§6玩家 {player.name} 发言行数太多({lines}), 已被踢出租赁服")
        elif self.is_too_fast(player):
            for cmd in self.msg_lmt_anti:
                self.game_ctrl.sendwocmd(
                    cmd.replace("[玩家名]", player.name).replace("[XUID]", player.xuid)
                )
            pass

    def player_leave(self, player: Player):
        if player.name in self.last_msgs:
            del self.last_msgs[player.name]
            self.print(f"{player.name} 离开服务器, 发言限制已重置")


entry = plugin_entry(AntiTooFastMessage_V2)

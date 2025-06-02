from tooldelta import ToolDelta, cfg as config, Chat, Plugin, plugin_entry


class AdminCommand(Plugin):
    name = "admin命令"
    author = "wling/Hadwin"
    version = (0, 0, 3)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        cmdarea = {"指令区坐标": {"x": int, "y": int, "z": int}}
        DEFAULT_CFG = {"指令区坐标": {"x": 0, "y": 0, "z": 0}}
        cfg, _ = config.get_plugin_config_and_version(
            self.name,
            cmdarea,
            DEFAULT_CFG,
            self.version,
        )
        self.cmdarea: dict[str, int] = cfg["指令区坐标"]
        self.ListenChat(self.on_chat)

    def on_chat(self, chat: Chat):
        player = chat.player
        playername = chat.player.name
        msg = chat.msg
        if not chat.player.is_op():
            return
        match msg:
            case ".admin" | ".admin ":  # 管理员可以使用的命令的帮助.
                player.show(
                    """§r输入§l§b.gm1§r改为创造模式\n输入§l§b.cmdarea§r前往指令区\n§r输入§l§b.inv§r获得隐身\n输入§l§b.nv§r获得夜视\n§r输入§l§b.ec§r清除药水"""
                )
                player.show(
                    """§r输入§l§b.clear§r清空背包\n§r输入§l§b.adminbag§r获取管理员物品\n§r输入§l§a.wt§r天气与时间控制菜单(§o§a开放§r)"""
                )
            case ".gm1" | ".gmc" | ".cz":  # 改创造模式
                self.game_ctrl.sendwscmd("/gamemode 1 " + playername)
                player.show("您的状态已刷新")
            case ".cmdarea" | ".cmdArea":  # 前往指令区
                self.game_ctrl.sendwscmd(
                    f"/tp {playername} {self.cmdarea.get('x')} {self.cmdarea.get('y')} {self.cmdarea.get('z')}"
                )
                player.show("§b已将您传送至指令区.")
            case ".inv" | ".INV":  # 改为隐身
                self.game_ctrl.sendwscmd(
                    f"effect {playername} invisibility 99999 1 true"
                )
                player.show("您的状态已刷新")
            case ".nv" | ".NV":  # 改为夜视
                self.game_ctrl.sendwscmd(
                    f"effect {playername} night_vision 99999 1 true"
                )
                player.show("您的状态已刷新")
            case ".ec" | ".EC":  # 清除药水效果
                self.game_ctrl.sendwscmd("/effect " + playername + " clear")
                player.show("您的状态已刷新")
            case ".clear" | ".CLEAR":  # 清空背包
                self.game_ctrl.sendwscmd("/clear " + playername + "")
                player.show("您的背包已清空")
            case ".adminbag" | ".adminbag":  # 获取管理员物品
                self.game_ctrl.sendwscmd("/give " + playername + " chain_command_block")
                self.game_ctrl.sendwscmd("/give " + playername + " deny")
                self.game_ctrl.sendwscmd("/give " + playername + " allow")
                self.game_ctrl.sendwscmd("/give " + playername + " border_block")
                self.game_ctrl.sendwscmd("/give " + playername + " barrier")
                self.game_ctrl.sendwscmd("/give " + playername + " structure_block")
                player.show(
                    "§b已给予:链命令方块|拒绝方块|允许方块|边界方块|屏障|结构方块",
                )
            case ".wt" | ".WT":  # 天气与时间控制菜单.
                player.show(
                    "§r§l§b天气与时间 帮助菜单\n§r========§l§e天气§r========\n输入§l§e.wclear晴天\n§r输入§l§b.wrain雨天\n§r输入§l§7.wtdr雷暴",
                )
                player.show(
                    "========§l§b时间§r========\n输入§l§6.tsr日出\n§r输入§l§e.tday白日\n§r输入§l§e.tn中午\n§r输入§l§6.tss日落\n§r输入§l§b.tnt夜晚\n§r输入§l§7.tmn深夜",
                )
            case ".wclear" | ".WCLEAR":  # 晴天
                self.game_ctrl.sendwscmd("/weather clear")
                self.game_ctrl.say_to(
                    "@a",
                    "已将天气设为§e晴天",
                )

            case ".wrain" | ".WRAIN":  # 雨天
                self.game_ctrl.sendwscmd("/weather rain")
                self.game_ctrl.say_to(
                    "@a",
                    "已将天气设为§b雨天",
                )
            case ".wtdr" | ".WTDR":  # 雷暴
                self.game_ctrl.sendwscmd("/weather thunder")
                self.game_ctrl.say_to(
                    "@a",
                    "已将天气设为§7雷暴.",
                )
            case ".tsr" | ".TSR":  # 日出
                self.game_ctrl.sendwscmd("/time set sunrise")
                self.game_ctrl.say_to(
                    "@a",
                    "已将时间设为§6日出.",
                )
            case ".tday" | ".TDAY":  # 白日
                self.game_ctrl.sendwscmd("/time set day")
                self.game_ctrl.say_to(
                    "@a",
                    "已将时间设为§e白日.",
                )
            case ".tn" | ".TN":  # 中午
                self.game_ctrl.sendwscmd("/time set noon")
                self.game_ctrl.say_to(
                    "@a",
                    "已将时间设为§e中午.",
                )
            case ".tss" | ".TSS":  # 日落
                self.game_ctrl.sendwscmd("/time set sunset")
                self.game_ctrl.say_to(
                    "@a",
                    "已将时间设为§6日落.",
                )
            case ".tnt" | ".TNT":  # 夜晚
                self.game_ctrl.sendwscmd("/time set night")
                self.game_ctrl.say_to(
                    "@a",
                    "已将时间设为§b夜晚.",
                )
            case ".tmn" | ".TMN":  # 深夜
                self.game_ctrl.sendwscmd("/time set midnight")
                self.game_ctrl.say_to(
                    "@a",
                    "已将时间设为§7深夜.",
                )


entry = plugin_entry(AdminCommand)

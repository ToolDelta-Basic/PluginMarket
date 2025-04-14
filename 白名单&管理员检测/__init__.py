from tooldelta import (
    Plugin,
    cfg,
    Print,
    game_utils,
    utils,
    Player,
    plugin_entry,
)

from tooldelta.internal.launch_cli import FrameNeOmgAccessPoint
import time


class whitelist_and_opcheck(Plugin):
    name = "白名单&管理员检测"
    author = "猫七街"
    version = (1, 1, 0)

    def __init__(self, frame):
        super().__init__(frame)
        self.bot = None
        self._default_cfg = {
            "检查时间（秒）": 60.0,
            "白名单": {
                "开启状态": False,
                "踢出提示词": "请先加入白名单",
                "白名单玩家": {"xuid1": "player_name1", "xuid2": "player_name2"},
            },
            "管理员检测": {
                "开启状态": False,
                "提示词": "你没有管理员权限",
                "管理员列表": {"xuid1": "player_name1", "xuid2": "player_name2"},
            },
        }
        self._std_cfg = {
            "检查时间（秒）": float,
            "白名单": {"开启状态": bool, "踢出提示词": str, "白名单玩家": {}},
            "管理员检测": {"开启状态": bool, "提示词": str, "管理员列表": {}},
        }
        try:
            self._cfg, _ = cfg.get_plugin_config_and_version(
                self.name, self._std_cfg, self._default_cfg, self.version
            )
        except Exception as e:
            Print.print_err(f"加载配置文件出错: {e}")
            self._cfg = self._default_cfg.copy()
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)

    def on_def(self):
        self.get_xuid = self.GetPluginAPI("XUID获取")

    def get_neomega(self):
        if isinstance(self.frame.launcher, FrameNeOmgAccessPoint):
            return self.frame.launcher.omega

        else:
            raise ValueError("此启动框架无法使用 NeOmega API")

    def on_player_join(self, player: Player):
        playername = player.name
        time.sleep(5)
        player_name = playername

        if self._cfg["白名单"]["开启状态"]:
            self.whitelist_check(player_name)

        if self._cfg["管理员检测"]["开启状态"]:
            self.operation_check(player_name)

    def whitelist_check(self, player_name: str | None):
        player = self.player(player_name)
        player_uuid = player[1]
        if player_name == self.bot.BotName:
            return

        if player_uuid not in self._cfg["白名单"]["白名单玩家"]:
            self.game_ctrl.sendwocmd(
                f'/kick "{player_name}" ' + self._cfg["白名单"]["踢出提示词"]
            )
            self.game_ctrl.sendwocmd(f'/kick "{player_name}"')
            return

        return

    def operation_check(self, player_name: str | None):
        player = self.player(player_name)
        player_uuid = player[1]
        if player_name == self.bot.BotName:
            return

        flag = game_utils.is_op(player_name)
        if flag:
            if player_uuid not in self._cfg["管理员检测"]["管理员列表"]:
                self.game_ctrl.sendwocmd(f"/say 检测到存在非法管理员：{player_name}")
                self.game_ctrl.sendwocmd(f"/deop {player_name}")
                self.game_ctrl.sendwocmd(
                    f"/tell {player_name} {self._cfg['管理员检测']['提示词']}"
                )
                return

        else:
            if player_uuid in self._cfg["管理员检测"]["管理员列表"]:
                self.game_ctrl.sendwocmd(f"/op {player_name}")
                return

        return

    def whitelist_console_set(self, args: list):
        Print.print_inf("选择你要进行的操作：", False)
        Print.print_inf("1. 添加玩家到白名单", False)
        Print.print_inf("2. 从白名单中移除玩家", False)
        Print.print_inf("q. 退出操作", False)
        while True:
            choice = input()
            if choice == "q":
                Print.print_inf("已退出操作", False)
                return

            if choice == "1":
                player_name = input(Print.fmt_info("请输入要添加的玩家昵称："))
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    Print.print_err("玩家未加入过服务器", False)
                    return

                if player_uuid in self._cfg["白名单"]["白名单玩家"]:
                    Print.print_inf("玩家已存在白名单中", False)
                    return

                self._cfg["白名单"]["白名单玩家"][player_uuid] = player_name
                cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
                Print.print_suc(f"已添加玩家{player_name}到白名单")
                return

            if choice == "2":
                player_name = input(Print.fmt_info("请输入玩家昵称："))
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    player_uuid = ""
                if player_uuid not in self._cfg["白名单"]["白名单玩家"]:
                    Print.print_inf("玩家不存在白名单中", False)
                    return

                self._cfg["白名单"]["白名单玩家"].pop(player_uuid)
                cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
                Print.print_suc(f"已从白名单中移除玩家{player_name}")
                return

            Print.print_err("无效的选项", False)
            Print.print_inf("选择你要进行的操作：", False)
            Print.print_inf("1. 添加玩家到白名单", False)
            Print.print_inf("2. 从白名单中移除玩家", False)
            Print.print_inf("q. 退出操作", False)

    def operation_console(self, args: list):
        Print.print_inf("选择你要进行的操作：", False)
        Print.print_inf("1. 添加OP", False)
        Print.print_inf("2. 移除OP", False)
        Print.print_inf("q. 退出操作", False)
        while True:
            choice = input()
            if choice == "q":
                Print.print_inf("已退出操作", False)
                return

            if choice == "1":
                player_name = input(Print.fmt_info("请输入要添加的玩家昵称："))
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    Print.print_err("玩家未加入过服务器", False)
                    return

                if player_uuid in self._cfg["管理员检测"]["管理员列表"]:
                    Print.print_err("玩家已经是OP", False)
                    return

                self._cfg["管理员检测"]["管理员列表"][player_uuid] = player_name
                cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
                Print.print_suc(f"已添加玩家{player_name}为OP")
                return

            if choice == "2":
                player_name = input(Print.fmt_info("请输入玩家昵称："))
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    player_uuid = ""

                if player_uuid not in self._cfg["管理员检测"]["管理员列表"]:
                    Print.print_inf("玩家不是OP", False)
                    return

                self._cfg["管理员检测"]["管理员列表"].pop(player_uuid)
                cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
                Print.print_inf(f"已将玩家{player_name}从OP中移除")
                return
            Print.print_err("无效的选项", False)
            Print.print_inf("选择你要进行的操作：", False)
            Print.print_inf("1. 添加OP", False)
            Print.print_inf("2. 移除OP", False)
            Print.print_inf("q. 退出操作", False)

    def auto_check(self):
        while True:
            time.sleep(self._cfg["检查时间（秒）"])
            players = self.game_ctrl.players_uuid
            for name, uuid in players.items():
                if self._cfg["白名单"]["开启状态"]:
                    self.whitelist_check(name)

                if self._cfg["管理员检测"]["开启状态"]:
                    self.operation_check(name)

    def player(self, player_name: str | None = None, player_uuid: str | None = None):
        if player_name is not None:
            player = [player_name, None]
            try:
                player_uuid = self.get_xuid.get_xuid_by_name(
                    player_name, allow_offline=True
                )
            except Exception as e:
                # 增强异常处理：避免 KeyError
                if player_name in self.game_ctrl.players_uuid:
                    player_uuid = self.game_ctrl.players_uuid[player_name]
                else:
                    Print.print_err(f"玩家 {player_name} 未在线或不存在")
                    player_uuid = ""
            player[1] = player_uuid
            return player
        elif player_uuid is not None:
            player = [None, player_uuid]
            try:
                player_name = self.get_xuid.get_name_by_xuid(player_uuid)
            except Exception as e:
                # 增强异常处理：避免 AttributeError
                if hasattr(self, "neomega"):
                    player_name = self.neomega.get_player_by_uuid(player_uuid).name
                else:
                    Print.print_err(f"无效的 UUID: {player_uuid}")
                    player_name = ""
            player[0] = player_name
            return player
        else:
            Print.print_err("player() 方法需要至少一个参数")
            return [None, None]

    def on_inject(self):
        neomega = self.get_neomega()
        self.neomega = self.get_neomega()
        self.bot = neomega.get_bot_basic_info()
        self.frame.add_console_cmd_trigger(
            ["白名单"],
            None,
            "在控制台修改白名单（需要玩家先登录一次服务器）",
            self.whitelist_console_set,
        )
        self.frame.add_console_cmd_trigger(
            ["OP操作"],
            None,
            "在控制台修改服务器OP（需要玩家先登录一次服务器）",
            self.operation_console,
        )
        self.auto_check_task = utils.createThread(
            self.auto_check, (), "循环检测白名单和管理员"
        )


entry = plugin_entry(whitelist_and_opcheck)

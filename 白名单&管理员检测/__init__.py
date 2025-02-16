from tooldelta import Plugin, plugins, Config, Print, Frame, game_utils, Utils
from tooldelta.launch_cli import FrameNeOmgAccessPoint
import time, json


@plugins.add_plugin
class whitelist_and_opcheck(Plugin):
    name = "白名单&管理员检测"
    author = "猫七街"
    version = (1, 0, 0)

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
            self._cfg, _ = Config.get_plugin_config_and_version(
                self.name, self._std_cfg, self._default_cfg, self.version
            )
        except Exception as e:
            Print.print_err(f"加载配置文件出错: {e}")
            self._cfg = self._default_cfg.copy()

    def on_def(self):
        try:
            self.get_xuid = plugins.get_plugin_api("XUID获取")
        except Exception as e:
            raise RuntimeError("请先安装前置插件：XUID获取") from e

    def get_neomega(self):
        if isinstance(self.frame.launcher, FrameNeOmgAccessPoint):
            return self.frame.launcher.omega

        else:
            raise ValueError("此启动框架无法使用 NeOmega API")

    def on_player_join(self, playername: str):
        time.sleep(5)
        player_name = playername
        player_uuid = self.game_ctrl.players_uuid.get(player_name)
        bot_info = self.bot
        bot_uuid = bot_info.BotUUIDStr if bot_info else None
        if player_uuid == bot_uuid:
            return

        if self._cfg["白名单"]["开启状态"]:
            self.whitelist_change(player_name, player_uuid)
            self.whitelist_check(player_uuid, player_name)

        if self._cfg["管理员检测"]["开启状态"]:
            self.operation_change(player_name, player_uuid)
            self.operation_check(player_uuid)

    def whitelist_check(self, player_uuid: str, player_name: str):
        if player_uuid not in self._cfg["白名单"]["白名单玩家"]:
            self.game_ctrl.sendwocmd(
                f"/kick {player_name} " + self._cfg["白名单"]["踢出提示词"]
            )
            return

        return

    def operation_check(self, player_uuid: str):
        player = self.get_neomega().get_player_by_uuid(player_uuid)
        player_name = player.name
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
        Print.print_inf("选择你要进行的操作：")
        Print.print_inf("1. 添加玩家到白名单")
        Print.print_inf("2. 从白名单中移除玩家")
        Print.print_inf("q. 退出操作")
        while True:
            choice = input()
            if choice == "q":
                Print.print_inf("已退出操作")
                return

            now_whitelist = self._cfg["白名单"]["白名单玩家"]
            if choice == "1":
                Print.print_inf("请输入要添加的玩家昵称：")
                player_name = input()
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    player_uuid = ""

                if player_uuid in now_whitelist:
                    Print.print_inf("玩家已存在白名单中")
                    return

                with open("add_whitelist.txt", "r+", encoding="utf-8") as f:
                    temp = f.read()
                    temp = temp.split(" ")
                    for i in range(len(temp)):
                        if temp[i] == player_name:
                            Print.print_inf("玩家已存在白名单中")
                            return

                    f.write(f"{player_name} ")
                    Print.print_inf(f"已添加玩家{player_name}到白名单")
                return

            if choice == "2":
                player_name = input("请输入玩家昵称：")
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    player_uuid = ""

                if player_uuid not in now_whitelist:
                    Print.print_inf("玩家不存在白名单中")
                    return

                self._cfg["白名单"]["白名单玩家"].pop(player_uuid)
                Print.print_inf(f"已从白名单中移除玩家{player_name}")
                return

            Print.print_err("无效的选项")
            Print.print_inf("选择你要进行的操作：")
            Print.print_inf("1. 添加玩家到白名单")
            Print.print_inf("2. 从白名单中移除玩家")
            Print.print_inf("q. 退出操作")

    def operation_console(self, args: list):
        Print.print_inf("选择你要进行的操作：")
        Print.print_inf("1. 添加OP")
        Print.print_inf("2. 移除OP")
        Print.print_inf("q. 退出操作")
        while True:
            choice = input()
            if choice == "q":
                Print.print_inf("已退出操作")
                return

            now_op = self._cfg["管理员检测"]["管理员列表"]
            if choice == "1":
                Print.print_inf("请输入要添加的玩家昵称：")
                player_name = input()
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    player_uuid = ""

                if player_uuid in now_op:
                    Print.print_inf("玩家已经是OP")
                    return

                with open("add_op.txt", "r+", encoding="utf-8") as f:
                    temp = f.read()
                    temp = temp.split(" ")
                    for i in range(len(temp)):
                        if temp[i] == player_name:
                            Print.print_inf("玩家已经是OP")
                            return

                    f.write(f"{player_name} ")
                    Print.print_inf(f"已添加玩家{player_name}为OP")
                return

            if choice == "2":
                player_name = input("请输入玩家昵称：")
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    player_uuid = ""

                if player_uuid not in now_op:
                    Print.print_inf("玩家不是OP")
                    return

                self._cfg["管理员检测"]["管理员列表"].pop(player_uuid)
                Print.print_inf(f"已降玩家{player_name}从OP中移除")
                return

            Print.print_err("无效的选项")
            Print.print_inf("选择你要进行的操作：")
            Print.print_inf("1. 添加OP")
            Print.print_inf("2. 移除OP")
            Print.print_inf("q. 退出操作")

    def auto_check(self):
        while True:
            time.sleep(self._cfg["检查时间（秒）"])
            players = self.game_ctrl.players_uuid
            for player_name, player_uuid in players.items():
                if self._cfg["白名单"]["开启状态"]:
                    self.whitelist_check(player_uuid, player_name)

                if self._cfg["管理员检测"]["开启状态"]:
                    self.operation_check(player_uuid)

    def whitelist_change(self, planyer_name: str, player_uuid: str):
        with open("add_whitelist.txt", "r+", encoding="utf-8") as f:
            temp = f.read()
            temp = temp.split(" ")
            for i in range(len(temp)):
                if temp[i] == planyer_name:
                    self._cfg["白名单"]["白名单玩家"][player_uuid] = planyer_name
                    temp.pop(i)
                    f.write(" ".join(temp))
                    return

        return

    def operation_change(self, planyer_name: str, player_uuid: str):
        with open("add_op.txt", "r+", encoding="utf-8") as f:
            temp = f.read()
            temp = temp.split(" ")
            for i in range(len(temp)):
                if temp[i] == planyer_name:
                    self._cfg["管理员检测"]["管理员列表"][player_uuid] = planyer_name
                    temp.pop(i)
                    f.write(" ".join(temp))
                    return

        return

    def on_inject(self):
        neomega = self.get_neomega()
        self.bot = neomega.get_bot_basic_info()

        self.frame.add_console_cmd_trigger(
            ["白名单"], None, "在控制台修改白名单", self.whitelist_console_set
        )
        self.frame.add_console_cmd_trigger(
            ["OP操作"], None, "在控制台修改服务器OP", self.operation_console
        )
        self.auto_check_task = Utils.createThread(
            self.auto_check, (), "循环检测白名单和管理员"
        )

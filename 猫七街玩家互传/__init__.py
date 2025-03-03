from tooldelta import Plugin, plugins, Config, game_utils, Utils, Print, TYPE_CHECKING
import time


@plugins.add_plugin
class NewPlugin(Plugin):
    name = "玩家互传"
    author = "猫七街"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.config = {
            "触发词": ".tpa",
            "传送超时时间（秒）": 180,
            "菜单头": "§b>>>>>>>>>>>>玩家互传<<<<<<<<<<<",
            "传送成功提示": "§b传送成功！",
            "无在线玩家提示": "§c当前没有在线玩家！",
            "传送失败提示": "§c传送失败！",
            "请求超时提示": "§c请求超时！",
        }

        self.config, v = Config.get_plugin_config_and_version(
            self.name, {}, self.config, self.version
        )

        self.tpa = {}

    def on_inject(self):
        Utils.createThread(self.timeout_check, (), "玩家互传超时检查")

    def on_player_message(self, player_name: str, msg: str):
        if msg.startswith(self.config["触发词"]):
            self.game_ctrl.say_to(player_name, self.config["菜单头"])
            self.game_ctrl.say_to(
                player_name, "1. 进入传送菜单\n2. 进入接受菜单\nq. 退出"
            )
            while True:
                choice = game_utils.waitMsg(player_name)
                if choice == "1":
                    self.add_tpa(player_name)
                    return

                if choice == "2":
                    self.tpa_accept(player_name)
                    return

                if choice == "q":
                    game_utils.tellrawText(player_name, "已退出")
                    return

                if choice == None:
                    self.game_ctrl.say_to(player_name, "§c超时，已退出菜单")
                    return

                self.game_ctrl.say_to(player_name, "无效输入, 请重新输入")

    def on_player_leave(self, player_name: str):
        for player, v in self.tpa.items():
            if player_name == player:
                self.game_ctrl.say_to(v[1], "§b发起人已下线，自动取消请求")
                self.tpa.pop(player)
                return

            if player_name == v[1]:
                self.game_ctrl.say_to(player, "§b目标已下线，自动取消请求")
                self.tpa.pop(player)
                return

    def add_tpa(self, player_name: str):
        bot_name = self.game_ctrl.bot_name
        players = self.game_ctrl.allplayers.copy()
        players.remove(player_name)
        players.remove(bot_name)
        if len(players) == 0:
            self.game_ctrl.say_to(player_name, self.config["菜单头"])
            self.game_ctrl.say_to(player_name, self.config["无在线玩家提示"])
            return

        self.game_ctrl.say_to(player_name, self.config["菜单头"])
        if player_name in self.tpa:
            target_player = self.tpa[player_name][1]
            self.game_ctrl.say_to(player_name, self.config["菜单头"])
            self.game_ctrl.say_to(
                player_name,
                f"§c你已经向 {target_player} 发送了请求，输入 q 取消请求，输入其他退出菜单",
            )
            choice = game_utils.waitMsg(player_name, 30)
            if choice == "q":
                self.game_ctrl.say_to(player_name, f"§c取消了对 {target_player} 的请求")
                try:
                    self.game_ctrl.say_to(
                        target_player, f"§c{player_name} 取消了对你的传送请求"
                    )
                except:
                    pass
                self.tpa.pop(player_name)
                return
            else:
                self.game_ctrl.say_to(player_name, "§c已退出玩家互传")
                return

        temp = 1
        for player in players:
            self.game_ctrl.say_to(player_name, f"{temp}. {player}")
            temp += 1

        while True:
            choice = game_utils.waitMsg(player_name)
            if choice is None:
                self.game_ctrl.say_to(player_name, self.config["超时提示"])
                return

            if choice.isdigit() and int(choice) in range(1, temp):
                break

            else:
                self.game_ctrl.say_to(player_name, self.config["请重新选择玩家"])

        choice = int(choice)
        target_player = players[choice - 1]
        self.tpa[player_name] = [
            time.time() + int(self.config["传送超时时间（秒）"]),
            target_player,
        ]
        self.game_ctrl.say_to(player_name, "§a已向对方发送传送请求")
        try:
            self.game_ctrl.say_to(
                target_player,
                f"{player_name} 请求传送到你,输入{self.config['触发词']} 进入传送菜单进行操作",
            )

        except:
            self.game_ctrl.say_to(player_name, "§c目标玩家不在线")

        return

    def tpa_accept(self, player_name: str):
        if len(self.tpa) == 0:
            self.game_ctrl.say_to(player_name, "§c没有对你发起的请求")
            return

        temp = 1
        temp2 = []
        self.game_ctrl.say_to(player_name, self.config["菜单头"])
        self.game_ctrl.say_to(player_name, "§a以下玩家请求传送到你身边:")
        for player, v in self.tpa.items():
            if v[1] == player_name:
                self.game_ctrl.say_to(player_name, f"{temp}. {player}")
                temp += 1
                temp2.append(player)

        self.game_ctrl.say_to(player_name, "§a选择一名玩家进行操作，输入q取消")
        while True:
            choice = game_utils.waitMsg(player_name)
            if choice is None:
                self.game_ctrl.say_to(player_name, "§c操作超时，已取消")
                return

            if choice == "q":
                self.game_ctrl.say_to(player_name, "§a已取消操作请求")
                return

            if choice.isdigit() and int(choice) in range(1, len(temp2) + 1):
                target_player = temp2[int(choice) - 1]
                break

        self.game_ctrl.say_to(player_name, self.config["菜单头"])
        self.game_ctrl.say_to(
            player_name, f"§b是否接受玩家 {target_player} 的传送？（y/n）"
        )
        while True:
            choice = game_utils.waitMsg(player_name)
            if choice is None:
                self.game_ctrl.say_to(player_name, "§c选择超时！")
                return

            if choice.lower() == "y" or choice.lower() == "yes":
                self.game_ctrl.say_to(
                    player_name, f"§a已接受 {target_player} 的传送请求"
                )
                self.game_ctrl.say_to(
                    target_player, f"§a玩家 {player_name} 已接受你的传送请求"
                )
                self.tpa.pop(target_player)
                self.game_ctrl.sendwocmd(f"tp {target_player} {player_name}")
                return

            if choice.lower() == "n" or choice.lower() == "no":
                self.game_ctrl.say_to(
                    player_name, f"§c已拒绝 {target_player} 的传送请求"
                )
                self.game_ctrl.say_to(
                    target_player, f"§c玩家 {player_name} 已拒绝你的传送请求"
                )
                self.tpa.pop(target_player)
                return

            self.game_ctrl.say_to(player_name, f"§c请重新选择")

    def timeout_check(self):
        for player, v in self.tpa.items():
            if time.time() > v[1]:
                try:
                    self.game_ctrl.say_to(player, f"§c传送请求已超时")
                    self.tpa.pop(player)

                except:
                    self.tpa.pop(player)

                try:
                    self.game_ctrl.say_to(
                        v[1], f"§c{player}对你发起的传送请求已超时，自动取消"
                    )

                except:
                    pass

        time.sleep(1)

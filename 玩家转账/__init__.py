from tooldelta import (
    Plugin,
    cfg,
    game_utils,
    Utils,
    Print,
    TYPE_CHECKING,
    Chat,
    plugin_entry,
)


class NewPlugin(Plugin):
    name = "玩家转账"
    author = "猫七街"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        config = {
            "货币计分板名称": "coin",
            "转账提示词": "转账",
            "转账头": "§a========转账菜单========",
            "转账成功提示": "§a转账成功",
            "转账失败提示": "§c转账失败",
            "余额不足提示": "§c余额不足",
        }
        self.config, version = cfg.get_plugin_config_and_version(
            self.name, {}, config, self.version
        )
        if version != self.version:
            self.config["转账头"] = "§a========转账菜单========"
            cfg.upgrade_plugin_config(self.name, self.config, self.version)
        self.ListenChat(self.on_player_message)

    def on_player_message(self, chat: Chat):
        player_name = chat.player.name
        msg = chat.msg

        if msg == self.config["转账提示词"]:
            players = self.game_ctrl.allplayers.copy()
            players.remove(self.game_ctrl.bot_name)
            players.remove(player_name)
            self.game_ctrl.say_to(player_name, self.config["转账头"])
            if len(players) == 0:
                self.game_ctrl.say_to(player_name, "§c没有其他玩家在线")
                return
            temp = 1
            for player in players:
                self.game_ctrl.say_to(player_name, f"§a{temp} {player}")
                temp += 1
            while True:
                self.game_ctrl.say_to(player_name, "§a请输入转账玩家序号：")
                choice = game_utils.waitMsg(player_name)
                if choice is None:
                    self.game_ctrl.say_to(player_name, "§c选择超时，取消转账")
                    return
                elif choice.isdigit() and int(choice) in range(1, len(players) + 1):
                    break
                else:
                    self.game_ctrl.say_to(player_name, "§c输入错误，请重新输入")
            while True:
                self.game_ctrl.say_to(player_name, "§a请输入转账金额：")
                money = game_utils.waitMsg(player_name)
                if money is None:
                    self.game_ctrl.say_to(player_name, "§c选择超时，取消转账")
                    return
                elif money.isdigit() and int(money) > 0:
                    break
                else:
                    self.game_ctrl.say_to(player_name, "§c输入错误，请重新输入")
            try:
                have_money = game_utils.getScore(
                    self.config["货币计分板名称"], player_name
                )
            except:
                have_money = 0
            money = int(money)
            if have_money < money:
                self.game_ctrl.say_to(player_name, self.config["余额不足提示"])
                return
            player_to_transfer = players[int(choice) - 1]
            flag = game_utils.isCmdSuccess(
                f"/scoreboard players add {player_to_transfer} {self.config['货币计分板名称']} {money}"
            )
            if flag:
                self.game_ctrl.say_to(player_name, self.config["转账成功提示"])
                self.game_ctrl.say_to(
                    player_to_transfer,
                    f"§a{player_name} 给你转账 {money} {self.config['货币计分板名称']}",
                )
                self.game_ctrl.sendwocmd(
                    f"/scoreboard players remove {player_name} {self.config['货币计分板名称']} {money}"
                )
                return
            self.game_ctrl.say_to(player_name, "对方已下线")
            return


entry = plugin_entry(NewPlugin)

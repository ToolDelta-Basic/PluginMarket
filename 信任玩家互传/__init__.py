from tooldelta import Plugin, game_utils, utils, fmts, plugin_entry, Chat, cfg
from tooldelta.utils import tempjson
import os

class NewPlugin(Plugin):
    name = "信任玩家传送"
    author = "Ka3mora"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.trust_file = os.path.join(self.data_path, "trust_list.json")
        self.tpa = {}
        self.trust_list = self.load_trust_list()
        self.ListenChat(self.on_chat)
        config = {
            "发起传送触发词": "。传送",
            "信任触发词": "。信任",
            "取消信任触发词": "。取消信任",
            "传送选择器": "@a",
            "信任选择器": "@a"
        }
        self.config, version = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(config), config, self.version
        )
        if version != self.version:
            cfg.upgrade_plugin_config(self.name, self.config, self.version)
      
    def load_trust_list(self):
        #读取加载
        return tempjson.load_and_read(
            self.trust_file,
            need_file_exists=False,
            default={}
        )

    def save_trust_list(self):
        #缓存
        tempjson.load_and_write(self.trust_file, self.trust_list)
        #立即写入
        tempjson.flush(self.trust_file)

    def check_trust(self, player_name: str, target_name: str) -> int:
        trust_list = self.load_trust_list()
        trust_list_player = trust_list.get(target_name, [])
        if player_name in trust_list_player:
            return 1  #在
        else:
            return 2  #不在

    def on_chat(self, chat: Chat):
        player_name = chat.player.name
        message = chat.msg
        if message.startswith(self.config["发起传送触发词"]):
            parts = message.split(" ")
            if len(parts) == 1:
                self.teleport_request(player_name)
            elif len(parts) == 2:
                target_name = parts[1]
                self.game_ctrl.sendwocmd(f"tp {player_name} {target_name}")
        elif message.startswith(self.config["信任触发词"]):
            parts = message.split(" ")
            if len(parts) == 1:
                self.trust_request(player_name)
            elif len(parts) == 2:
                target_name = parts[1]
                self.add_trust(player_name, target_name)
        elif message.startswith(self.config["取消信任触发词"]):
            parts = message.split(" ")
            if len(parts) == 1:
                self.game_ctrl.say_to(player_name, "§4§l·§a§l取消信任步骤需要指定取消信任的玩家！")
            elif len(parts) == 2:
                target_name = parts[1]
                self.remove_trust(player_name, target_name)
        elif message == "y" and player_name in self.tpa.values():
            self.tpa_accept(player_name)
        elif message == "q" and player_name in self.tpa.values():
            self.tpa_cancel(player_name)

    def teleport_request(self, player_name: str):
        online_players = game_utils.getTarget(self.config["传送选择器"])
        if len(online_players) < 2:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l在线玩家不足，无法传送")
            return

        self.game_ctrl.say_to(player_name, "§4§l·§a§l您想传送至哪位玩家？")
        for idx, p in enumerate(online_players, start=1):
            self.game_ctrl.say_to(player_name, f"{idx}. {p}")

        while True:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l请输入玩家序号：")
            choice = game_utils.waitMsg(player_name, timeout=10)
            if choice is None:
                self.game_ctrl.say_to(player_name, "§4§l·§a§l操作超时，取消传送")
                return
              
            elif choice.isdigit() and 1 <= int(choice) <= len(online_players):
                target_player = online_players[int(choice) - 1]
                self.tpa[player_name] = target_player
                result_len1 = self.check_trust(player_name, target_player)
                if result_len1 == 1:
                    self.game_ctrl.say_to(player_name, f"§4§l·§a§l你在对方的信任清单！正在传送您至 {target_player}...")
                    self.game_ctrl.sendwocmd(f"tp {player_name} {target_player}")
                    self.game_ctrl.say_to(player_name, f"§4§l·§a§l传送成功！")
                    self.game_ctrl.say_to(target_player, f"§4§l·§a§l {player_name} 已传送至您身边")
                    return
                else:
                    self.game_ctrl.say_to(target_player, f"§4§l·§a§l {player_name} 请求传送至您。输入 'y' 接受，输入 'q' 拒绝")
                return
              
            else:
                self.game_ctrl.say_to(player_name, "§4§l·§a§l无效的序号，请重新输入")

    def tpa_accept(self, player_name: str):
        for requester, target in list(self.tpa.items()):
            if target == player_name:
                self.game_ctrl.sendwocmd(f"tp {requester} {player_name}")
                self.game_ctrl.say_to(requester, f"§4§l·§a§l您已成功传送到 {player_name}")
                self.game_ctrl.say_to(player_name, f"§4§l·§a§l {requester} 已传送到您这里")
                del self.tpa[requester]
                return

    def tpa_cancel(self, player_name: str):
        for requester, target in list(self.tpa.items()):
            if target == player_name:
                self.game_ctrl.say_to(requester, f"§4§l·§a§l {player_name} 拒绝了您的传送请求")
                del self.tpa[requester]
                return
              
    def teleport_player_to_target(self, player_name: str, target_name: str):
        online_players = game_utils.getTarget(self.config["传送选择器"])
        result_len2 = self.check_trust(player_name, target_name)
        if target_name not in online_players:
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l玩家 {target_name} 不在线或不存在")
            return
          
        if result_len2 == 1:
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l你在对方的信任清单！正在传送您至 {target_name}...")
            self.game_ctrl.sendwocmd(f"tp {player_name} {target_name}")
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l传送成功！")
            self.game_ctrl.say_to(target_name, f"§4§l·§a§l {player_name} 已传送至您身边")
            return
        self.game_ctrl.say_to(player_name, f"§4§l·§a§l您请求传送至玩家 {target_name}")
        self.game_ctrl.say_to(target_name, f"§4§l·§a§l {player_name} 请求传送至您。输入 'y' 接受，输入 'q' 拒绝")

        while True:
            response = game_utils.waitMsg(target_name, timeout=20)
            if response is None:
                self.game_ctrl.say_to(player_name, "§4§l·§a§l操作超时，取消传送")
                self.game_ctrl.say_to(target_name, "§4§l·§a§l传送请求已超时")
                return
            elif response.lower() == 'y':
                self.game_ctrl.say_to(player_name, f"§4§l·§a§l正在传送您至 {target_name}...")
                self.game_ctrl.sendwocmd(f"tp {player_name} {target_name}")
                self.game_ctrl.say_to(player_name, f"§4§l·§a§l传送成功！")
                self.game_ctrl.say_to(target_name, f"§4§l·§a§l {player_name} 已传送至您身边")
                return
            elif response.lower() == 'q':
                self.game_ctrl.say_to(player_name, "§4§l·§a§l传送请求已被拒绝")
                self.game_ctrl.say_to(target_name, "§4§l·§a§l您已拒绝传送请求")
                return          

    def add_trust(self, player_name: str, target_name: str):
        if player_name not in self.trust_list:
            self.trust_list[player_name] = []
        if target_name not in self.trust_list[player_name]:
            self.trust_list[player_name].append(target_name)
            self.save_trust_list()
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l已将 {target_name} 添加到信任列表中")
        else:
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l {target_name} 已经在信任列表中")

    def remove_trust(self, player_name: str, target_name: str):
        if player_name in self.trust_list:
            if target_name in self.trust_list[player_name]:
                self.trust_list[player_name].remove(target_name)
                self.save_trust_list()
                self.game_ctrl.say_to(player_name, f"§4§l·§a§l已将 {target_name} 从信任列表中移除")
            else:
                self.game_ctrl.say_to(player_name, f"§4§l·§a§l {target_name} 不在信任列表中")
        else:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l您的信任列表为空")

    def trust_request(self, player_name: str):
        online_players = game_utils.getTarget(self.config["信任选择器"])
        if len(online_players) < 2:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l在线玩家不足，无法添加信任")
            return
          
        self.game_ctrl.say_to(player_name, "§4§l·§a§l请选择要信任的玩家：")
        for idx, p in enumerate(online_players, start=1):
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l{idx}. {p}")

        while True:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l请输入玩家序号：")
            choice = game_utils.waitMsg(player_name, timeout=20)
            if choice is None:
                self.game_ctrl.say_to(player_name, "§4§l·§a§l操作超时，取消信任操作")
                return
            elif choice.isdigit() and 1 <= int(choice) <= len(online_players):
                target_player = online_players[int(choice) - 1]
                if player_name not in self.trust_list:
                    self.trust_list[player_name] = []
                if target_player not in self.trust_list[player_name]:
                    self.trust_list[player_name].append(target_player)
                    self.save_trust_list()
                    self.game_ctrl.say_to(player_name, f"§4§l·§a§l已将 {target_player} 添加到信任列表中")
                else:
                    self.game_ctrl.say_to(player_name, f"§4§l·§a§l{target_player} 已经在信任列表中")
                return
            else:
                self.game_ctrl.say_to(player_name, "§4§l·§a§l无效的序号，请重新输入")

entry = plugin_entry(NewPlugin)
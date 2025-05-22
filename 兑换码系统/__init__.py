from tooldelta import (Plugin, plugin_entry, Player, Chat, fmts)
import json
from typing import Dict
import threading
#一定要阅读下面的文字
#本插件的所有修改都在数据文件
#如果你要修改或者添加，请在数据文件中修改添加
#先点击数据文件，再点击兑换码系统，再点击第一个
#完成以上步骤之后，你会发现里面会有两个默认兑换码
#如果你想要的话，可以留下来，不想要的话，可以删除
#同样可以仿照里面的格式制作新的兑换码
#如果本插件有任何bug，请向插件开发者提交，会在一个工作日日内修改回复

class RedeemCodeSystem(Plugin):
    name = "兑换码系统"
    author = "权威 - 马牛逼"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.lock = threading.Lock()
        self.redeem_data: Dict[str, dict] = {}
        self.player_redeem_record: Dict[str, Dict[str, int]] = {} 
        self.make_data_path()
        self.load_redeem_codes()
        self.load_player_redeem_records()
        self.ListenChat(self.handle_redeem_command)

    def load_redeem_codes(self):
        file_path = self.format_data_path("codes.json")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.redeem_data = json.load(f)
        except FileNotFoundError:
            self.redeem_data = {
                "VIP666": {
                    "奖励": "give [player] diamond 10",
                    "剩余次数": 50,
                    "描述": "新手礼包",
                    "每人最大兑换次数": 1
                },
                "SUMMER2024": {
                    "奖励": "give [player] emerald 5",
                    "剩余次数": 30,
                    "描述": "夏季限时码",
                    "每人最大兑换次数": 1
                }
            }
            self.save_redeem_codes()

    def save_redeem_codes(self):
        file_path = self.format_data_path("codes.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.redeem_data, f, indent=4, ensure_ascii=False)

    def load_player_redeem_records(self):
        file_path = self.format_data_path("player_redeem_records.json")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.player_redeem_record = json.load(f)
        except FileNotFoundError:
            self.player_redeem_record = {}
            self.save_player_redeem_records()

    def save_player_redeem_records(self):
        file_path = self.format_data_path("player_redeem_records.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.player_redeem_record, f, indent=4, ensure_ascii=False)

    def handle_redeem_command(self, chat: Chat):
        player = chat.player
        msg = chat.msg.strip()
        if not msg.startswith(".dh "): return
        redeem_code = msg[4:].upper()
        with self.lock:
            code_info = self.redeem_data.get(redeem_code)
            if not code_info:
                self.game_ctrl.say_to(player.name, "§c错误：无效的兑换码！")
                return
            if code_info["剩余次数"] <= 0:
                self.game_ctrl.say_to(player.name, "§c错误：兑换码已失效或次数用尽！")
                return
            player_name = player.name
            if player_name not in self.player_redeem_record:
                self.player_redeem_record[player_name] = {}
            player_redeem_count = self.player_redeem_record[player_name].get(redeem_code, 0)
            max_redeem_count = code_info.get("每人最大兑换次数", 1)
            if player_redeem_count >= max_redeem_count:
                self.game_ctrl.say_to(player.name, "§c错误：你已达到此兑换码的最大兑换次数！")
                return
            reward_cmd = code_info["奖励"].replace("[player]", player.name)
            try:
                self.game_ctrl.sendwocmd(reward_cmd)
                code_info["剩余次数"] -= 1
                self.player_redeem_record[player_name][redeem_code] = player_redeem_count + 1
                self.game_ctrl.say_to(player.name, f"§a兑换成功！{code_info['描述']}\n剩余次数：{code_info['剩余次数']}")
                self.save_redeem_codes()
                self.save_player_redeem_records()
            except Exception as e:
                fmts.print_err(f"兑换失败：{str(e)}")
                self.game_ctrl.say_to(player.name, "§c错误：兑换失败，请联系管理员！")

entry = plugin_entry(RedeemCodeSystem)
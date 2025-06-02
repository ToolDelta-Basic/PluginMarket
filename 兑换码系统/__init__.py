from tooldelta import (Plugin, plugin_entry, Player, Chat, fmts)
import json
import threading
import time

class RedeemCodeSystem(Plugin):
    name = "兑换码系统"
    author = "权威 - 马牛逼"
    version = (0, 0, 3) 

    def __init__(self, frame):
        super().__init__(frame)
        self.lock = threading.Lock()
        self.兑换码数据 = {}
        self.玩家兑换记录 = {}
        self.兑换日志 = {}
        self.load_redeem_codes()
        self.load_player_redeem_records()
        self.load_redeem_logs()
        self.ListenChat(self.handle_redeem_command)

    def load_redeem_codes(self):
        文件路径 = self.format_data_path("兑换码数据.json")
        try:
            with open(文件路径, encoding="utf-8") as f:
                self.兑换码数据 = json.load(f)
        except FileNotFoundError:
            self.兑换码数据 = {
                "VIP666": {"奖励": "give [player] diamond 10", "剩余次数": 50, "描述": "新手礼包", "每人最大兑换次数": 1, "使用完是否删除": False},
                "SUMMER2024": {"奖励": "give [player] emerald 5", "剩余次数": 30, "描述": "夏季限时码", "每人最大兑换次数": 1, "使用完是否删除": True}
            }
            self.save_redeem_codes()

    def handle_redeem_command(self, chat: Chat):
        玩家 = chat.player
        消息 = chat.msg.strip()
        if not 消息.startswith(".dh "): return
        
        with self.lock:
            兑换码 = 消息[4:].upper()
            码信息 = self.兑换码数据.get(兑换码)
            if not 码信息:
                self.game_ctrl.say_to(玩家.name, "§c错误：无效的兑换码！")
                return
            
            if 码信息["剩余次数"] <= 0:
                if 码信息.get("使用完是否删除", False):
                    self.delete_redeem_code(兑换码)
                    self.game_ctrl.say_to(玩家.name, "§c提示：该兑换码已过期并删除")
                else:
                    self.game_ctrl.say_to(玩家.name, "§c错误：兑换码已失效或次数用尽！")
                return
            
            玩家名 = 玩家.name
            if 玩家名 not in self.玩家兑换记录:
                self.玩家兑换记录[玩家名] = {}
            次数 = self.玩家兑换记录[玩家名].get(兑换码, 0)
            if 次数 >= 码信息.get("每人最大兑换次数", 1):
                self.game_ctrl.say_to(玩家.name, f"§c错误：你已达到此兑换码的最大兑换次数！")
                return
            
            try:
                奖励指令 = 码信息["奖励"].replace("[player]", 玩家名)
                self.game_ctrl.sendwocmd(奖励指令)
                码信息["剩余次数"] -= 1
                self.玩家兑换记录[玩家名][兑换码] = 次数 + 1
                
                if 码信息["剩余次数"] <= 0 and 码信息.get("使用完是否删除", False):
                    self.delete_redeem_code(兑换码)
                
                self.game_ctrl.say_to(玩家.name, 
                    f"§a兑换成功！{码信息['描述']}\n剩余次数：{码信息['剩余次数']}"
                )
                
                时间戳 = time.strftime("%Y-%m-%d %H:%M:%S")
                self.兑换日志.setdefault(玩家名, []).append(f"[{时间戳}] {玩家名} 输入: {消息}")
                self.save_redeem_logs()
                
            except Exception as e:
                fmts.print_err(f"兑换失败：{str(e)}")
                self.game_ctrl.say_to(玩家.name, "§c错误：兑换失败，请联系管理员！")

    def load_redeem_logs(self):
        文件路径 = self.format_data_path("兑换日志.json")
        try:
            with open(文件路径, encoding="utf-8") as f:
                self.兑换日志 = json.load(f)
        except FileNotFoundError:
            self.兑换日志 = {}
            self.save_redeem_logs()

    def save_redeem_logs(self):
        文件路径 = self.format_data_path("兑换日志.json")
        with open(文件路径, "w", encoding="utf-8") as f:
            json.dump(self.兑换日志, f, indent=4, ensure_ascii=False)

    def delete_redeem_code(self, 码):
        with self.lock:
            if 码 in self.兑换码数据:
                del self.兑换码数据[码]
                self.save_redeem_codes()
                self.clean_player_records(码)

    def clean_player_records(self, 码):
        with self.lock:
            for 记录 in self.玩家兑换记录.values():
                记录.pop(码, None)
            self.save_player_redeem_records()

    def save_redeem_codes(self):
        文件路径 = self.format_data_path("兑换码数据.json")
        with open(文件路径, "w", encoding="utf-8") as f:
            json.dump(self.兑换码数据, f, indent=4, ensure_ascii=False)

    def load_player_redeem_records(self):
        文件路径 = self.format_data_path("玩家兑换记录.json")
        try:
            with open(文件路径, encoding="utf-8") as f:
                self.玩家兑换记录 = json.load(f)
        except FileNotFoundError:
            self.玩家兑换记录 = {}
            self.save_player_redeem_records()

    def save_player_redeem_records(self):
        文件路径 = self.format_data_path("玩家兑换记录.json")
        with open(文件路径, "w", encoding="utf-8") as f:
            json.dump(self.玩家兑换记录, f, indent=4, ensure_ascii=False)

entry = plugin_entry(RedeemCodeSystem)

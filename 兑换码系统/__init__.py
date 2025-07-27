from tooldelta import (Plugin, plugin_entry, Chat, fmts, cfg)
import json
import threading
import time
import random
import string
from datetime import datetime

class RedeemCodeSystem(Plugin):
    name = "兑换码系统"
    author = "法老༂"
    version = (1, 2, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.lock = threading.Lock()
        self.code_groups = {}
        self.redeem_logs = {}
        self.redeem_cooldowns = {}
        self.config = {
            "命令前缀": ".dh",
            "管理员命令前缀": ".dhadmin",
            "成功_兑换成功": "§a兑换成功！{描述}\n下次可兑换时间：{冷却时间}后",
            "成功_生成兑换码": "§a成功生成{新增数量}个兑换码（共请求{总数量}个），已添加到组「{组名}」",
            "错误_无效兑换码": "§c错误：该兑换码无效或已被使用！",
            "错误_不在有效期": "§c错误：该兑换码不在有效期内！\n有效期：{生效时间} 至 {过期时间}",
            "错误_冷却中": "§c错误：该兑换码仍在冷却中！\n剩余时间：{剩余时间}",
            "错误_命令格式": "§c命令格式错误：.dhadmin gen 组名 数量 前缀 [长度]",
            "错误_参数错误": "§c参数错误：数量和长度必须为数字",
            "错误_组不存在": "§c错误：兑换码组「{组名}」不存在",
            "错误_奖励发放失败": "§c部分奖励发放失败，请稍后重试（兑换码未消耗）",
            "错误_兑换失败": "§c错误：兑换失败，请联系管理员！"
        }
        self.load_config()
        self.load_code_groups()
        self.load_redeem_logs()
        self.load_redeem_cooldowns()
        self.ListenChat(self.handle_commands)

    def load_config(self):
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, {}, self.config, self.version
        )
        self.command_prefix = self.config["命令前缀"].strip()
        self.admin_prefix = self.config["管理员命令前缀"].strip()
        for key, default in self.config.items():
            if key not in self.config:
                self.config[key] = default
        cfg.upgrade_plugin_config(self.name, self.config, self.version)

    def load_code_groups(self):
        file_path = self.format_data_path("兑换码组数据.json")
        try:
            with open(file_path, encoding="utf-8") as f:
                self.code_groups = json.load(f)
        except FileNotFoundError:
            self.code_groups = {
                "新手礼包组": {
                    "兑换码列表": ["VIP666", "VIP888", "新手福利123"],
                    "奖励命令列表": [
                        "give [player] diamond 10",
                        "give [player] iron_ingot 20",
                        "xp add [player] 500 points"
                    ],
                    "描述": "新手专属礼包（每日可兑换一次）",
                    "生效时间": "2025-01-01 00:00:00",
                    "过期时间": "2025-12-31 23:59:59",
                    "冷却时间(秒)": 86400
                },
                "夏季活动组": {
                    "兑换码列表": ["夏日2025", "炎热福利2026"],
                    "奖励命令列表": [
                        "give [player] emerald 5",
                        "give [player] ice 10"
                    ],
                    "描述": "夏季限时礼包（每小时可兑换一次）",
                    "生效时间": "2025-06-01 00:00:00",
                    "过期时间": "2025-08-31 23:59:59",
                    "冷却时间(秒)": 3600
                }
            }
            self.save_code_groups()

    def save_code_groups(self):
        file_path = self.format_data_path("兑换码组数据.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.code_groups, f, indent=4, ensure_ascii=False)

    def find_code_in_group(self, code):
        code_upper = code.upper()
        for group_id, group_info in self.code_groups.items():
            for idx, c in enumerate(group_info["兑换码列表"]):
                if c.upper() == code_upper:
                    return group_id, group_info, idx
        return None, None, -1

    def load_redeem_cooldowns(self):
        file_path = self.format_data_path("兑换冷却记录.json")
        try:
            with open(file_path, encoding="utf-8") as f:
                self.redeem_cooldowns = json.load(f)
        except FileNotFoundError:
            self.redeem_cooldowns = {}
            self.save_redeem_cooldowns()

    def save_redeem_cooldowns(self):
        file_path = self.format_data_path("兑换冷却记录.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.redeem_cooldowns, f, indent=4, ensure_ascii=False)

    def is_code_valid_in_time(self, group_info):
        try:
            current_time = datetime.now()
            start_time = datetime.strptime(group_info["生效时间"], "%Y-%m-%d %H:%M:%S")
            end_time = datetime.strptime(group_info["过期时间"], "%Y-%m-%d %H:%M:%S")
            return start_time <= current_time <= end_time
        except Exception as e:
            fmts.print_err(f"时间校验失败：{str(e)}")
            return False

    def check_cooldown(self, player_name, code, cooldown_seconds):
        if player_name not in self.redeem_cooldowns:
            self.redeem_cooldowns[player_name] = {}
        last_use = self.redeem_cooldowns[player_name].get(code, 0)
        current_time = time.time()
        if current_time - last_use < cooldown_seconds:
            remaining = cooldown_seconds - (current_time - last_use)
            return False, remaining
        return True, 0

    def format_remaining_time(self, seconds):
        days = int(seconds // 86400)
        seconds %= 86400
        hours = int(seconds // 3600)
        seconds %= 3600
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}时")
        if minutes > 0:
            parts.append(f"{minutes}分")
        parts.append(f"{seconds}秒")
        return "".join(parts)

    def generate_codes(self, prefix, count, length=8):
        codes = []
        chars = string.ascii_uppercase + string.digits
        for _ in range(count):
            suffix = ''.join(random.choices(chars, k=length))
            code = f"{prefix}-{suffix}"
            codes.append(code)
        return codes

    def handle_admin_command(self, chat: Chat):
        玩家 = chat.player
        if not 玩家.is_op():
            return

        消息 = chat.msg.strip()
        if 消息.startswith(f"{self.admin_prefix} gen "):
            parts = 消息.split()
            if len(parts) < 5:
                self.game_ctrl.say_to(玩家.name, self.config["错误_命令格式"])
                return

            组名 = parts[2]
            try:
                数量 = int(parts[3])
                前缀 = parts[4]
                长度 = int(parts[5]) if len(parts) > 5 else 8
            except ValueError:
                self.game_ctrl.say_to(玩家.name, self.config["错误_参数错误"])
                return

            if 组名 not in self.code_groups:
                self.game_ctrl.say_to(玩家.name, self.config["错误_组不存在"].format(组名=组名))
                return

            新兑换码 = self.generate_codes(前缀, 数量, 长度)
            现有码 = set(self.code_groups[组名]["兑换码列表"])
            新增数量 = 0
            for code in 新兑换码:
                if code not in 现有码:
                    self.code_groups[组名]["兑换码列表"].append(code)
                    现有码.add(code)
                    新增数量 += 1

            self.save_code_groups()
            self.game_ctrl.say_to(玩家.name, self.config["成功_生成兑换码"].format(
                新增数量=新增数量, 总数量=数量, 组名=组名
            ))

    def handle_redeem_command(self, chat: Chat):
        玩家 = chat.player
        消息 = chat.msg.strip()
        if not 消息.startswith(f"{self.command_prefix} "):
            return

        with self.lock:
            兑换码 = 消息[len(self.command_prefix) + 1:].strip()
            组ID, 组信息, 码索引 = self.find_code_in_group(兑换码)

            if not 组信息 or 码索引 == -1:
                self.game_ctrl.say_to(玩家.name, self.config["错误_无效兑换码"])
                return

            if not self.is_code_valid_in_time(组信息):
                self.game_ctrl.say_to(玩家.name, self.config["错误_不在有效期"].format(
                    生效时间=组信息["生效时间"], 过期时间=组信息["过期时间"]
                ))
                return

            玩家名 = 玩家.name
            冷却时间 = 组信息.get("冷却时间(秒)", 0)
            冷却通过, 剩余时间 = self.check_cooldown(玩家名, 兑换码, 冷却时间)
            if not 冷却通过:
                self.game_ctrl.say_to(玩家名, self.config["错误_冷却中"].format(
                    剩余时间=self.format_remaining_time(剩余时间)
                ))
                return

            try:
                所有命令成功 = True
                for 命令 in 组信息["奖励命令列表"]:
                    替换后命令 = 命令.replace("[player]", 玩家名)
                    if not self.game_ctrl.sendwocmd(替换后命令):
                        所有命令成功 = False
                        fmts.print_war(f"命令执行失败：{替换后命令}")

                if 所有命令成功:
                    self.redeem_cooldowns[玩家名][兑换码] = time.time()
                    self.save_redeem_cooldowns()

                    self.game_ctrl.say_to(玩家名, self.config["成功_兑换成功"].format(
                        描述=组信息["描述"], 冷却时间=self.format_remaining_time(冷却时间)
                    ))

                    时间戳 = time.strftime("%Y-%m-%d %H:%M:%S")
                    self.redeem_logs.setdefault(玩家名, []).append(
                        f"[{时间戳}] 使用兑换码 {兑换码} 兑换了 {组ID}（{len(组信息['奖励命令列表'])}条命令）"
                    )
                    self.save_redeem_logs()
                else:
                    self.game_ctrl.say_to(玩家.name, self.config["错误_奖励发放失败"])

            except Exception as e:
                fmts.print_err(f"兑换失败：{str(e)}")
                self.game_ctrl.say_to(玩家.name, self.config["错误_兑换失败"])

    def handle_commands(self, chat: Chat):
        self.handle_admin_command(chat)
        self.handle_redeem_command(chat)

    def load_redeem_logs(self):
        file_path = self.format_data_path("兑换日志.json")
        try:
            with open(file_path, encoding="utf-8") as f:
                self.redeem_logs = json.load(f)
        except FileNotFoundError:
            self.redeem_logs = {}
            self.save_redeem_logs()

    def save_redeem_logs(self):
        file_path = self.format_data_path("兑换日志.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.redeem_logs, f, indent=4, ensure_ascii=False)

entry = plugin_entry(RedeemCodeSystem)

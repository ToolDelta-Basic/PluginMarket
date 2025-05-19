from tooldelta import (
    Plugin,
    plugin_entry,
    Player,
    Chat,
    fmts,
)
import json
from typing import Dict
import threading


class RedeemCodeSystem(Plugin):
    name = "兑换码系统"  # 插件名称
    author = "权威-马牛逼"  # 作者
    version = (0, 0, 1)  # 版本号

    def __init__(self, frame):
        super().__init__(frame)
        self.lock = threading.Lock()  # 线程锁
        self.redeem_data: Dict[str, dict] = {}  # 兑换码数据

        # 初始化数据文件（自动创建文件夹）
        self.make_data_path()  # 创建数据文件夹
        self.load_redeem_codes()  # 加载兑换码数据

        # 监听聊天指令
        self.ListenChat(self.handle_redeem_command)

    def load_redeem_codes(self):
        """从数据文件加载兑换码"""
        file_path = self.format_data_path("codes.json")  # 生成数据文件路径
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.redeem_data = json.load(f)
        except FileNotFoundError:
            # 初始化默认兑换码（可自行修改）
            self.redeem_data = {
                "VIP666": {
                    "奖励": "give [player] diamond 10",
                    "剩余次数": 50,
                    "描述": "新手礼包",
                },
                "SUMMER2024": {
                    "奖励": "give [player] emerald 5",
                    "剩余次数": 30,
                    "描述": "夏季限时码",
                },
            }
            self.save_redeem_codes()  # 保存默认数据

    def save_redeem_codes(self):
        """保存兑换码数据到文件"""
        file_path = self.format_data_path("codes.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.redeem_data, f, indent=4, ensure_ascii=False)

    def handle_redeem_command(self, chat: Chat):
        """处理兑换码指令"""
        player = chat.player
        msg = chat.msg.strip()

        # 解析指令格式：.dh 兑换码
        if not msg.startswith(".dh "):
            return

        redeem_code = msg[4:].upper()  # 转为大写确保一致性

        with self.lock:
            code_info = self.redeem_data.get(redeem_code)

            if not code_info:
                player.show("§c错误：无效的兑换码！")
                return

            if code_info["剩余次数"] <= 0:
                player.show("§c错误：兑换码已失效或次数用尽！")
                return

            # 执行奖励指令
            reward_cmd = code_info["奖励"].replace("[player]", player.name)
            try:
                self.game_ctrl.sendwocmd(reward_cmd)
                code_info["剩余次数"] -= 1
                player.show(
                    f"§a兑换成功！{code_info['描述']}\n剩余次数：{code_info['剩余次数']}"
                )
                self.save_redeem_codes()  # 保存数据变更
            except Exception as e:
                fmts.print_err(f"兑换失败：{str(e)}")
                player.show("§c错误：兑换失败，请联系管理员！")


# 插件入口
entry = plugin_entry(RedeemCodeSystem)

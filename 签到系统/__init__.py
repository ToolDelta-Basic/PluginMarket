import json
import time
import random
from tooldelta import (
    Plugin,
    plugin_entry,
    Player,
    cfg,
    utils,
    fmts,
)


class SignInSystem(Plugin):
    name = "每日签到"
    author = "权威-马牛逼"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        default_config = {
            "每日奖励": "give [player] bread 5",
            "签到间隔时间（分钟）": 1440,
            "签到语列表": [
                "§a今日份签到已完成，奖励已发放~",
                "§b坚持签到，欧气满满！",
                "§c今日奖励已领取，明天再来哦~",
                "§a美好的一天从签到开始，奖励已到手！",
                "§b签到成功，今天也要元气满满~",
                "§c恭喜完成签到，小礼物请收好~",
                "§a又一次签到打卡，你是最棒的！",
                "§b坚持就是胜利，签到奖励已送达~",
                "§c今日份签到成就达成，继续加油！",
                "§a签到不缺席，幸运常伴你~",
                "§b每天一签，快乐无限~",
                "§c成功签到，开启精彩的一天！",
                "§a签到小标兵，奖励属于你~",
                "§b新的一天，从签到收获奖励开始~",
                "§c恭喜你，签到奖励已入账~",
                "§a持续签到，惊喜不断~",
                "§b你的坚持，终将美好，签到成功！",
                "§c签到成功，愿你今天好运连连~",
                "§a勤劳的你已签到，奖励请查收~",
                "§b每日签到，积累属于你的财富~",
                "§c完成签到，为你的坚持点赞！",
                "§a签到已完成，今天也要活力满满~",
                "§b坚持签到，你就是最靓的仔~",
                "§c恭喜获得签到奖励，继续冲！",
                "§a新的一天，新的签到，新的奖励~",
                "§b签到不停，收获不止~",
                "§c成功签到，祝你今天心情愉悦~",
                "§a你的每一次签到都值得被奖励~",
                "§b签到成功，开启幸运的一天~",
                "§c每日一签，幸福常伴~",
                "§a勤劳签到，快乐收获~",
                "§b坚持签到的你，超酷的！",
                "§c恭喜获得今日签到奖励~",
                "§a签到打卡，好运加载中~",
                "§b每天签到，生活更美好~",
                "§c成功签到，愿你一切顺利~",
                "§a签到小达人，奖励来啦~",
                "§b新的签到，新的希望，新的奖励~",
                "§c恭喜完成今日签到任务~",
                "§a持续签到，未来可期~",
                "§b你的努力，从签到开始展现~",
                "§c签到成功，愿你收获满满~",
                "§a勤劳的小蜜蜂已签到~",
                "§b每日签到，积攒能量~",
                "§c恭喜获得签到小惊喜~",
                "§a签到已完成，快乐一整天~",
                "§b坚持签到，好运不缺席~",
                "§c成功签到，开启元气满满的一天~",
                "§a你的每一次签到都是进步的脚印~",
                "§b签到不停歇，奖励不间断~",
                "§c恭喜获得今日份签到福利~",
                "§a签到打卡，开启幸运之旅~",
                "§b每天签到，遇见更好的自己~",
                "§c成功签到，祝你事事顺心~",
                "§a勤劳签到，幸福相伴~",
                "§b坚持签到的你，运气不会差~",
                "§c恭喜获得签到奖励，开心每一天~",
                "§a签到已完成，活力满满出发~",
                "§b每日签到，收获快乐与奖励~",
                "§c成功签到，愿你心想事成~",
                "§a你的坚持签到，终将换来惊喜~",
                "§b签到不停，好运不止~",
                "§c恭喜获得今日签到好礼~",
                "§a签到打卡，好运连连来~",
                "§b每天签到，生活充满阳光~",
                "§c成功签到，祝你拥有好心情~",
                "§a勤劳签到，快乐加倍~",
                "§b坚持签到的你，超厉害的！",
                "§c恭喜获得签到小宝藏~",
                "§a签到已完成，开启美好的一天~",
                "§b持续签到，好运常相随~",
                "§c成功签到，愿你平安喜乐~",
                "§a你的每一次签到都是对自己的奖励~",
                "§b签到不停步，奖励不迟到~",
                "§c恭喜获得今日签到惊喜~",
                "§a签到打卡，幸运在等你~",
                "§b每天签到，梦想更近一步~",
                "§c成功签到，祝你一帆风顺~",
                "§a勤劳签到，收获满满~",
                "§b坚持签到的你，未来一片光明~",
                "§c恭喜获得签到奖励，继续加油哦~",
                "§a签到已完成，能量已加满~",
                "§b每日签到，快乐常相伴~",
                "§c成功签到，愿你幸福安康~",
                "§a你的坚持签到，是最棒的选择~",
                "§b签到不停，精彩不断~",
                "§c恭喜获得今日签到福利大礼包~",
                "§a签到打卡，开启幸运模式~",
                "§b每天签到，遇见幸运的自己~",
                "§c成功签到，祝你一切如意~",
                "§a勤劳签到，好运常伴~",
                "§b坚持签到的你，值得拥有奖励~",
                "§c恭喜获得签到小惊喜大礼包~",
                "§a签到已完成，向着目标前进~",
                "§b每日签到，积累无限可能~",
                "§c成功签到，愿你美梦成真~",
                "§a你的每一次签到都是成长的见证~",
                "§b签到不停歇，快乐永相随~",
                "§c恭喜获得今日签到超级奖励~",
            ],
            "已签到提示": "§a你今天已经签到过了，冷却剩余：{remaining}分钟",
            "签到成功提示": "{sign_msg} 获得奖励：{reward_desc}",
        }
        config_schema = {
            "每日奖励": str,
            "签到间隔时间（分钟）": int,
            "签到语列表": cfg.JsonList(str),
            "已签到提示": str,
            "签到成功提示": str,
        }
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, config_schema, default_config, self.version
        )
        self.sign_in_data_file = self.format_data_path("sign_in_data.json")
        self.sign_in_data = {}
        self.load_sign_in_data()
        self.ListenChat(self.handle_sign_in)

    def load_sign_in_data(self):
        try:
            with open(self.sign_in_data_file, "r") as f:
                self.sign_in_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.sign_in_data = {}
            self.save_sign_in_data()

    def save_sign_in_data(self):
        try:
            with open(self.sign_in_data_file, "w") as f:
                json.dump(self.sign_in_data, f, indent=2)
        except:
            fmts.print_err("保存签到数据失败")

    def handle_sign_in(self, chat):
        player = chat.player
        message = chat.msg.strip()
        if message != "#签到":
            return
        current_time = int(time.time())
        player_data = self.sign_in_data.get(player.uuid, {})
        last_sign_time = player_data.get("last_sign_time", 0)
        elapsed_minutes = (current_time - last_sign_time) // 60
        remaining_minutes = max(
            0, self.config["签到间隔时间（分钟）"] - elapsed_minutes
        )
        if last_sign_time and remaining_minutes > 0:
            tellraw_msg = f'{{"rawtext": [{{"text": "{self.config["已签到提示"].format(remaining=remaining_minutes)}"}}]}}'
            self.game_ctrl.sendwocmd(f"tellraw {player.name} {tellraw_msg}")
            return
        self.sign_in_data[player.uuid] = {
            "last_sign_time": current_time,
            "last_sign_date": time.strftime("%Y-%m-%d", time.localtime(current_time)),
        }
        self.save_sign_in_data()
        reward_command = self.config["每日奖励"].replace("[player]", player.name)
        reward_desc = reward_command.split()[-2:]
        reward_desc = f"{reward_desc[1]} {reward_desc[0]}"
        sign_msg = random.choice(self.config["签到语列表"])
        try:
            self.game_ctrl.sendwocmd(reward_command)
            tellraw_success_msg = f'{{"rawtext": [{{"text": "{self.config["签到成功提示"].format(sign_msg=sign_msg, reward_desc=reward_desc)}"}}]}}'
            self.game_ctrl.sendwocmd(f"tellraw {player.name} {tellraw_success_msg}")
        except Exception as e:
            fmts.print_err(f"签到奖励发放失败：{str(e)}")
            tellraw_error_msg = '{"rawtext": [{"text": "§c签到失败，请联系管理员"}]}'
            self.game_ctrl.sendwocmd(f"tellraw {player.name} {tellraw_error_msg}")


entry = plugin_entry(SignInSystem)

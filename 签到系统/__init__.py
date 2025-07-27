from tooldelta import (Plugin, plugin_entry, Chat, fmts, cfg, game_utils)
import json
import time
import random
from datetime import datetime, timedelta


class SignInSystem(Plugin):
    name = "每日签到"
    author = "权威-马牛逼"
    version = (1, 0, 0)

    def __init__(self, frame):
        super().__init__(frame)
        self.default_config = {
            "签到命令": "#签到",
            "查询命令": "#签到查询",
            "排行命令": "#签到排行",
            "补签命令": "#补签",
            "每日重置时间": "00:00",
            "基础每日奖励": ["give [player] bread 5"],
            "连续签到阶梯奖励": {
                "3": ["give [player] iron_ingot 20"],
                "7": ["give [player] gold_ingot 10", "xp add [player] 500"],
                "30": ["give [player] diamond 5", "title [player] title {\"text\":\"签到达人\"}"]
            },
            "概率奖池": {
                "10": ["give [player] emerald 3"],
                "5": ["give [player] enchanted_golden_apple 1"],
                "0.5": ["give [player] nether_star 1"]
            },
            "补签所需道具": "paper",
            "补签所需数量": 1,
            "最大补签天数": 7,
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
            "已签到提示": "§c你今天已签到！距离明天0点重置还剩{remaining_hours}小时{remaining_minutes}分钟",
            "签到成功提示": "{sign_msg}\n§6基础奖励：{base_reward}\n{extra_reward}",
            "连续签到提示": "§a恭喜！已连续签到{days}天，额外奖励：{reward}",
            "概率奖励提示": "§6触发概率奖励：{reward}（幸运值+1）",
            "补签成功提示": "§a补签{date}成功！消耗{count}个{item}",
            "补签失败提示": "§c补签失败：{reason}",
            "查询提示": "§6你的签到数据：\n总签到天数：{total}\n当前连续签到：{continuous}天\n下次连续奖励：{next_continuous}天（奖励：{next_reward}）"
        }
        
        self.config_schema = {
            "签到命令": str,
            "查询命令": str,
            "排行命令": str,
            "补签命令": str,
            "每日重置时间": str,
            "基础每日奖励": cfg.JsonList(str),
            "连续签到阶梯奖励": cfg.AnyKeyValue(cfg.JsonList(str)),
            "概率奖池": cfg.AnyKeyValue(cfg.JsonList(str)),
            "补签所需道具": str,
            "补签所需数量": cfg.PInt,
            "最大补签天数": cfg.PInt,
            "签到语列表": cfg.JsonList(str),
            "已签到提示": str,
            "签到成功提示": str,
            "连续签到提示": str,
            "概率奖励提示": str,
            "补签成功提示": str,
            "补签失败提示": str,
            "查询提示": str
        }
        
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, self.config_schema, self.default_config, self.version
        )
        self.sign_data_file = self.format_data_path("sign_data.json")
        self.sign_data = {}
        self.load_sign_data()
        self.ListenChat(self.handle_chat)

    def load_sign_data(self):
        try:
            with open(self.sign_data_file, "r", encoding="utf-8") as f:
                self.sign_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.sign_data = {}
            self.save_sign_data()

    def save_sign_data(self):
        try:
            with open(self.sign_data_file, "w", encoding="utf-8") as f:
                json.dump(self.sign_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            fmts.print_err(f"保存签到数据失败：{e}")

    def get_today(self):
        return datetime.now().strftime("%Y-%m-%d")

    def get_reset_time(self):
        reset_h, reset_m = map(int, self.config["每日重置时间"].split(":"))
        now = datetime.now()
        reset_time = datetime(now.year, now.month, now.day, reset_h, reset_m)
        if now > reset_time:
            reset_time += timedelta(days=1)
        return reset_time.timestamp()

    def get_remaining_time(self):
        reset_ts = self.get_reset_time()
        now_ts = time.time()
        remaining_sec = max(0, reset_ts - now_ts)
        return int(remaining_sec // 3600), int((remaining_sec % 3600) // 60)

    def parse_reward_desc(self, command):
        parts = command.strip().split()
        if len(parts) < 4 or parts[0] != "give":
            return "未知奖励"
        return f"{parts[3]}个{parts[2]}"

    def execute_commands(self, commands, player_name):
        success_rewards = []
        for cmd in commands:
            cmd = cmd.replace("[player]", player_name)
            if cmd.split()[0].lower() in {"give", "xp", "title", "scoreboard"}:
                if game_utils.isCmdSuccess(cmd):
                    success_rewards.append(self.parse_reward_desc(cmd))
                else:
                    fmts.print_err(f"奖励命令执行失败：{cmd}")
            else:
                fmts.print_err(f"拦截危险命令：{cmd}")
        return success_rewards

    def handle_sign_in(self, player):
        today = self.get_today()
        player_data = self.sign_data.get(player.uuid, {
            "last_date": "",
            "total": 0,
            "continuous": 0,
            "missed_dates": []
        })

        if player_data["last_date"] == today:
            h, m = self.get_remaining_time()
            msg = self.config["已签到提示"].format(remaining_hours=h, remaining_minutes=m)
            self.game_ctrl.say_to(player.name, msg)
            return

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if player_data["last_date"] == yesterday:
            player_data["continuous"] += 1
        else:
            if player_data["last_date"] and player_data["last_date"] != today:
                player_data["missed_dates"].append(player_data["last_date"])
                player_data["missed_dates"] = player_data["missed_dates"][-30:]
            player_data["continuous"] = 1

        player_data["last_date"] = today
        player_data["total"] += 1
        self.sign_data[player.uuid] = player_data
        self.save_sign_data()

        base_commands = self.config["基础每日奖励"]
        base_rewards = self.execute_commands(base_commands, player.name)
        base_reward_desc = "、".join(base_rewards) if base_rewards else "无"

        extra_reward = ""
        continuous_str = str(player_data["continuous"])
        if continuous_str in self.config["连续签到阶梯奖励"]:
            continuous_commands = self.config["连续签到阶梯奖励"][continuous_str]
            continuous_rewards = self.execute_commands(continuous_commands, player.name)
            if continuous_rewards:
                reward_desc = "、".join(continuous_rewards)
                extra_reward = self.config["连续签到提示"].format(
                    days=player_data["continuous"], reward=reward_desc
                )

        prob_reward = ""
        if self.config["概率奖池"]:
            total_prob = sum(float(k) for k in self.config["概率奖池"].keys())
            if random.random() * 100 <= total_prob:
                rand = random.random() * 100
                cumulative = 0
                for prob_str, cmds in self.config["概率奖池"].items():
                    cumulative += float(prob_str)
                    if rand <= cumulative:
                        prob_rewards = self.execute_commands(cmds, player.name)
                        if prob_rewards:
                            prob_reward = self.config["概率奖励提示"].format(
                                reward="、".join(prob_rewards)
                            )
                        break

        sign_msg = random.choice(self.config["签到语列表"])
        final_extra = "\n".join([msg for msg in [extra_reward, prob_reward] if msg])
        success_msg = self.config["签到成功提示"].format(
            sign_msg=sign_msg,
            base_reward=base_reward_desc,
            extra_reward=final_extra if final_extra else "§7无额外奖励"
        )
        self.game_ctrl.say_to(player.name, success_msg)

    def handle_sign_in_query(self, player):
        player_data = self.sign_data.get(player.uuid, {
            "total": 0,
            "continuous": 0
        })
        total = player_data["total"]
        continuous = player_data["continuous"]

        next_continuous = None
        next_reward = "无"
        for days_str in sorted(self.config["连续签到阶梯奖励"].keys(), key=int):
            if int(days_str) > continuous:
                next_continuous = days_str
                next_reward_commands = self.config["连续签到阶梯奖励"][days_str]
                next_reward = "、".join([
                    self.parse_reward_desc(cmd) for cmd in next_reward_commands
                ])
                break

        msg = self.config["查询提示"].format(
            total=total,
            continuous=continuous,
            next_continuous=next_continuous or "无",
            next_reward=next_reward
        )
        self.game_ctrl.say_to(player.name, msg)

    def handle_ranking(self):
        players = [(k, v) for k, v in self.sign_data.items() if v.get("total", 0) > 0]
        if not players:
            self.game_ctrl.say("§c暂无签到数据")
            return

        sorted_by_total = sorted(players, key=lambda x: -x[1]["total"])[:10]
        rank_msg = "§6签到总天数排行：\n"
        for i, (uuid, data) in enumerate(sorted_by_total, 1):
            player_name = self.game_ctrl.get_player_name_by_uuid(uuid) or f"玩家{uuid[:8]}"
            rank_msg += f"§a{i}. {player_name}：{data['total']}天\n"

        sorted_by_continuous = sorted(players, key=lambda x: -x[1]["continuous"])[:10]
        rank_msg += "§6连续签到天数排行：\n"
        for i, (uuid, data) in enumerate(sorted_by_continuous, 1):
            player_name = self.game_ctrl.get_player_name_by_uuid(uuid) or f"玩家{uuid[:8]}"
            rank_msg += f"§b{i}. {player_name}：{data['continuous']}天\n"

        self.game_ctrl.say(rank_msg)

    def handle_makeup_sign(self, player):
        player_data = self.sign_data.get(player.uuid, {})
        missed_dates = player_data.get("missed_dates", [])
        if not missed_dates:
            self.game_ctrl.say_to(player.name, self.config["补签失败提示"].format(reason="无漏签记录"))
            return

        max_days = self.config["最大补签天数"]
        earliest_allowed = (datetime.now() - timedelta(days=max_days)).strftime("%Y-%m-%d")
        available_dates = [d for d in missed_dates if d >= earliest_allowed]
        if not available_dates:
            self.game_ctrl.say_to(player.name, self.config["补签失败提示"].format(
                reason=f"仅支持补签近{max_days}天的记录"
            ))
            return

        required_item = self.config["补签所需道具"]
        required_count = self.config["补签所需数量"]
        has_item = self.game_ctrl.has_item(player.name, required_item, required_count)
        if not has_item:
            self.game_ctrl.say_to(player.name, self.config["补签失败提示"].format(
                reason=f"缺少{required_count}个{required_item}"
            ))
            return

        makeup_date = available_dates[0]
        player_data["missed_dates"].remove(makeup_date)
        player_data["total"] += 1
        self.sign_data[player.uuid] = player_data
        self.save_sign_data()

        self.game_ctrl.sendwocmd(f"clear {player.name} {required_item} {required_count}")
        self.game_ctrl.say_to(player.name, self.config["补签成功提示"].format(
            date=makeup_date, count=required_count, item=required_item
        ))

    def handle_chat(self, chat: Chat):
        player = chat.player
        msg = chat.msg.strip()

        if msg == self.config["签到命令"]:
            self.handle_sign_in(player)
        elif msg == self.config["查询命令"]:
            self.handle_sign_in_query(player)
        elif msg == self.config["排行命令"]:
            self.handle_ranking()
        elif msg == self.config["补签命令"]:
            self.handle_makeup_sign(player)


entry = plugin_entry(SignInSystem)

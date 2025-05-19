from tooldelta import (
    Plugin,
    Chat,
    plugin_entry,
    Player,
    cfg,
    utils,
    fmts,
)
import time
import threading


class SleepPlugin(Plugin):
    name = "睡觉统计"
    author = "权威-马牛逼"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        default_config = {
            "op_list": ["OP1", "OP2"],
            "banned_players": ["禁止玩家1", "禁止玩家2"],
        }
        config_schema = {
            "op_list": cfg.JsonList(str),
            "banned_players": cfg.JsonList(str),
        }
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, config_schema, default_config, self.version
        )
        self.lock = threading.Lock()
        self.player_scores = {}
        self.online_players = set()
        self.daily_reset_time = None

    def on_plugin_activate(self):
        utils.createThread(func=self.check_night_skip, usage="黑夜检查线程")
        utils.createThread(func=self.daily_reset_scores, usage="每日积分重置线程")

    def on_player_join(self, player: Player):
        with self.lock:
            self.online_players.add(player.name)

    def on_player_leave(self, player: Player):
        with self.lock:
            if player.name in self.online_players:
                self.online_players.remove(player.name)

    def on_chat_message(self, chat: Chat):
        if chat.msg.startswith("玩家") and "正在床上睡觉。" in chat.msg:
            player_name = chat.msg[2 : chat.msg.index("正在床上睡觉。")]
            self.handle_sleep_event(player_name)

    def handle_sleep_event(self, player_name: str):
        with self.lock:
            if player_name in set(self.config["banned_players"]):
                return
            self.player_scores[player_name] = self.player_scores.get(player_name, 0) + 1

    def check_night_skip(self):
        while True:
            time.sleep(5)
            with self.lock:
                op_set = set(self.config["op_list"])
                valid_players = [p for p in self.online_players if p not in op_set]
                if len(valid_players) == 0:
                    self.execute_skip_command()
                    self.reset_scores()

    def daily_reset_scores(self):
        while True:
            current_hour = time.localtime().tm_hour
            if current_hour == 4:
                with self.lock:
                    self.player_scores.clear()
            time.sleep(3600)

    def reset_scores(self):
        with self.lock:
            self.player_scores.clear()

    def execute_skip_command(self):
        try:
            message = "§a检测到所有非OP玩家离线，已跳过黑夜，积分已重置"
            json_message = f'{{"text":"{message}"}}'
            self.game_ctrl.sendwocmd(f"tellraw @a {json_message}")
            self.game_ctrl.sendwocmd("time set day")
        except Exception as e:
            fmts.print_err(f"跳过黑夜失败：{e}")


entry = plugin_entry(SleepPlugin)

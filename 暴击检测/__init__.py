import time
from collections import defaultdict

from tooldelta import Config, Plugin, plugin_entry, fmts
from tooldelta.constants import PacketIDS


class CritLimit(Plugin):
    name = "暴击限制"
    author = "果_k"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPacket(PacketIDS.Animate, self.Onpack)
        CONFIG_DEFAULT = {
            "检测周期": 3,
            "周期内触发阈值": 6,
            "踢出理由": "暴击次数太多了，休息一下吧",
        }
        CONFIG_STD = {
            "检测周期": Config.NNInt,
            "周期内触发阈值": Config.NNInt,
            "踢出理由": str,
        }
        cfg, cfg_version = Config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.MONITOR_CONFIG = {
            "interval": cfg["检测周期"],
            "threshold": cfg["周期内触发阈值"],
        }
        self.kick_reason = cfg["踢出理由"]
        self.message_stats = defaultdict(lambda: defaultdict(lambda: []))

    def Onpack(self, packet):
        try:
            action_type = packet["ActionType"]
            unique_id = packet["AttackerEntityUniqueID"]
            if action_type == 4 and unique_id is not None:
                current_time = time.time()  # 获取时间
                stats = self.message_stats[action_type][unique_id]
                stats.append(current_time)

                interval = self.MONITOR_CONFIG["interval"]
                cutoff = current_time - interval  # 阈值判断
                stats = [t for t in stats if t >= cutoff]

                self.message_stats[action_type][unique_id] = stats
                recent_hits = len(stats)

                if recent_hits >= self.MONITOR_CONFIG["threshold"]:  # 触发判断
                    players = self.frame.get_players()
                    kick_player = players.getPlayerByUniqueID(unique_id)
                    kick_player_name = kick_player.name
                    fmts.print_war(f"玩家{kick_player_name}暴击次数过多 已踢出")
                    self.game_ctrl.sendwocmd(
                        f'/kick "{kick_player_name}" {self.kick_reason}'
                    )
                    self.game_ctrl.say_to(
                        "@a", f"玩家{kick_player_name}暴击次数过多 已踢出"
                    )

                    self.message_stats[action_type][unique_id] = []
                    self.game_ctrl.sendwocmd(f'/kick "{kick_player_name}"')
        except Exception as e:
            pass


entry = plugin_entry(CritLimit)

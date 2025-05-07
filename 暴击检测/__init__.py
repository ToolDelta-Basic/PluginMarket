import threading
import time
from tooldelta import Config, Plugin, plugin_entry, fmts
from tooldelta.constants import PacketIDS


class CritLimit(Plugin):
    name = "暴击限制"
    author = "果_k"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)

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
        cfg, _ = Config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )

        self.MONITOR_CONFIG = {
            "interval": cfg["检测周期"],
            "threshold": cfg["周期内触发阈值"],
        }
        self.kick_reason = cfg["踢出理由"]

        self.message_stats_mu = threading.Lock()
        self.message_stats: dict[int, list[float]] = {}

        self.ListenPacket(PacketIDS.Animate, self.on_animate)

    def on_animate(self, packet: dict) -> bool:
        self.message_stats_mu.acquire()
        self._on_animate(packet)
        self.message_stats_mu.release()
        return False

    def _on_animate(self, packet: dict):
        if "ActionType" not in packet or "AttackerEntityUniqueID" not in packet:
            return

        action_type: int = packet["ActionType"]
        unique_id: int = packet["AttackerEntityUniqueID"]

        if action_type == 4:
            # 初始化
            current_time = time.time()
            players = self.frame.get_players()

            # 清理已下线玩家
            new_message_stats: dict[int, list[float]] = {}
            for player in players.getAllPlayers():
                temp = player.unique_id
                if player.unique_id in self.message_stats:
                    new_message_stats[temp] = self.message_stats[temp]
            self.message_stats = new_message_stats

            # 取得当前玩家的 stats
            stats: list[float] = []
            if unique_id not in self.message_stats:
                stats = [current_time]
            else:
                stats = self.message_stats[unique_id]
                stats.append(current_time)

            interval = self.MONITOR_CONFIG["interval"]
            cutoff = current_time - interval  # 阈值判断
            stats = [t for t in stats if t >= cutoff]

            self.message_stats[unique_id] = stats
            recent_hits = len(stats)

            if recent_hits >= self.MONITOR_CONFIG["threshold"]:  # 触发判断
                kick_player = players.getPlayerByUniqueID(unique_id)
                if kick_player is None:
                    del self.message_stats[unique_id]
                    return

                kick_player_name = kick_player.name
                kick_player_xuid = kick_player.xuid

                fmts.print_war(f"玩家 {kick_player_name} 暴击次数过多，已踢出")
                self.game_ctrl.sendwocmd(f"kick {kick_player_xuid} {self.kick_reason}")
                self.game_ctrl.say_to(
                    "@a", f"玩家 {kick_player_name} 暴击次数过多，已踢出"
                )

                del self.message_stats[unique_id]


entry = plugin_entry(CritLimit)

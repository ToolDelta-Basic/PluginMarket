from tooldelta import Plugin, plugin_entry, Player, Chat, FrameExit, cfg, game_utils, utils, fmts, TYPE_CHECKING
from tooldelta.constants import PacketIDS
import time
from tooldelta import Config
import threading
from collections import defaultdict

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
            "检查间隔": 1,
            "踢出理由": "暴击次数太多了，休息一下吧",
        }
        CONFIG_STD = {
            "检测周期": Config.NNInt,
            "周期内触发阈值": Config.NNInt,
            "检查间隔": Config.NNInt,
            "踢出理由": str,
        }
        cfg, cfg_version = Config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.MONITOR_CONFIG = {
            "interval": cfg["检测周期"],
            "threshold": cfg["周期内触发阈值"],
            "check_interval": cfg["检查间隔"]
        }
        self.kick_reason = cfg["踢出理由"]
        self.message_stats = defaultdict(
            lambda: defaultdict(lambda: {'times': [], 'count': 0})
        )
        self.cleanup_thread = utils.createThread(self.cleanup_loop,usage="暴击检测定时") #更换为td的线程
    def Onpack(self,packet):
        try:
            action_type = packet['ActionType']
            unique_id = packet['AttackerEntityUniqueID']
            if action_type == 4 and unique_id is not None:
                current_time = time.time() #获取时间
                stats = self.message_stats[action_type][unique_id]
                stats['times'].append(current_time)
                stats['count'] = len(stats['times'])
            
                cutoff = current_time - self.MONITOR_CONFIG["interval"] #阈值判断
                recent_hits = sum(1 for t in stats['times'] if t >= cutoff)
                
                if recent_hits >= self.MONITOR_CONFIG["threshold"]:  #触发判断
                    players = self.frame.get_players()
                    kick_player = players.getPlayerByUniqueID(unique_id)
                    kick_player_name = kick_player.name
                    print(f"玩家{kick_player_name}暴击次数过多 已踢出")
                    self.game_ctrl.sendcmd(f"/kick {kick_player_name} {self.kick_reason}")
                    timestamps = ", ".join(f"{t:.2f}" for t in stats['times'])
                    
                    stats['times'] = [current_time] #重置
                    stats['count'] = 1
        except Exception as e:
            pass
                  
    def cleanup_loop(self):
        while True:
            time.sleep(self.MONITOR_CONFIG["check_interval"])
            current_time = time.time()
            for action_type, unique_ids in list(self.message_stats.items()):
                for unique_id, data in list(unique_ids.items()):
                    cutoff = current_time - self.MONITOR_CONFIG["interval"]
                    new_times = []
                    valid_count = 0
                    
                    for t in data['times']:  #过期的时间戳
                        if t >= cutoff:
                            new_times.append(t)
                            valid_count += 1
                    data['times'] = new_times #更新数据
                    data['count'] = valid_count
entry = plugin_entry(NewPlugin)

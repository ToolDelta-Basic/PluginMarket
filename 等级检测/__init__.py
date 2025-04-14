from tooldelta import Plugin, plugin_entry, Player, Chat, FrameExit, cfg, game_utils, utils, fmts
from tooldelta.constants import PacketIDS
from tooldelta import Config
import time
class Levelcheck(Plugin):
    name = "等级限制"
    author = "果_k"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        CONFIG_DEFAULT = {
            "踢出理由": "等级过低,无法加入服务器",
            "延迟踢出时间": 3,
            "最低限制等级": 12,
        }
        CONFIG_STD = {
            "踢出理由": str,
            "延迟踢出时间": Config.NNInt,
            "最低限制等级": Config.NNInt,
        }
        cfg, cfg_version = Config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.min_level = cfg["最低限制等级"]
        self.kick_reason = cfg["踢出理由"]
        self.kick_time = cfg["延迟踢出时间"]
        self.ListenPacket(PacketIDS.PlayerList, self.on_playerlist)

    def on_playerlist(self, packet):
        if not packet['GrowthLevels']: #离开服务器
            fmts.print_err("GrowthLevels 不存在")
            return
        level_player = packet['GrowthLevels'][0]
        if not level_player:
            fmts.print_err("level_player 不存在")
            return
        if 'Entries' in packet and isinstance(packet['Entries'], list):
            for entry_user in packet['Entries']:
                username = self.get_username(entry_user)  # 获取玩家名
                if username is None:
                    continue
        self.kick_player(username,level_player)
    def get_username(self,entry_user):
        if 'Username' in entry_user:
            return entry_user['Username']
        else:
            fmts.print_err("没有 Username 数据")
            return None
    def kick_player(self,username,level_player):
        if level_player < self.min_level:
            fmts.print_war(f"玩家 {username} 的等级 {level_player} 低于最小等级 {self.min_level}，进行踢出")
            time.sleep(self.kick_time)
            self.game_ctrl.sendwocmd(f'/kick "{username}" {self.kick_reason}')
            self.game_ctrl.sendwocmd(f'/kick "{username}"')
        
entry = plugin_entry(Levelcheck)

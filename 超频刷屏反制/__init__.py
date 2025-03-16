from tooldelta import cfg as config, utils, ToolDelta, plugin_entry, Plugin, Player
from tooldelta.constants import PacketIDS
from tooldelta.game_utils import get_all_player


class HighRateChatAnti(Plugin):
    name = "超频发言反制"
    author = "SuperScript"
    version = (0, 0, 4)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        CFG_DEFAULT = {
            "检测周期(秒)": 5,
            "检测周期内最多发送多少条消息": 10,
            "反制措施": {"封禁时间(天数)": 1},
        }
        cfg, _ = config.get_plugin_config_and_version(
            "超频发言限制", config.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, (0, 0, 5)
        )
        self.detect_time = cfg["检测周期(秒)"]
        self.msg_lmt = cfg["检测周期内最多发送多少条消息"]
        self.ban_days = cfg["反制措施"]["封禁时间(天数)"] * 86400
        self.ListenPreload(self.on_def)
        self.ListenPacket(PacketIDS.Text, self.on_text_packet)
        self.last_msgs: dict[str, int] = {}

    def on_def(self):
        self.ban = self.GetPluginAPI("封禁系统")

    def on_inject(self):
        @utils.timer_event(self.detect_time, "重置刷屏检测时长")
        def clear_message_lmt():
            self.last_msgs.clear()

        clear_message_lmt()

    def on_text_packet(self, pk: dict):
        if pk["TextType"] in (1, 7):
            if pk["SourceName"] == "":
                try:
                    self.on_chat(pk["Message"].split()[1])
                except IndexError:
                    self.print("[WARN] 无法从当前发言获取发送者")
            else:
                self.on_chat(pk["SourceName"])
        return False

    def on_chat(self, playername: str):
        if playername not in get_all_player():
            return

        self.last_msgs.setdefault(playername, 0)
        self.last_msgs[playername] += 1
        if self.is_too_fast(playername):
            self.ban.ban(playername, self.ban_days, "超频刷屏")

    def is_too_fast(self, player: str) -> bool:
        return self.last_msgs.get(player, 0) > self.msg_lmt

    def player_leave(self, player: Player):
        if player.name in self.last_msgs:
            del self.last_msgs[player.name]


entry = plugin_entry(HighRateChatAnti)

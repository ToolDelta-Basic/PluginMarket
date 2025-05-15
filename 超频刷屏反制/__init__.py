from tooldelta import cfg as config, utils, Plugin, Player, Chat, TYPE_CHECKING, plugin_entry


class HighRateChatAnti(Plugin):
    name = "超频发言反制"
    author = "SuperScript"
    version = (0, 0, 5)

    def __init__(self, frame):
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
        self.ban_time = cfg["反制措施"]["封禁时间(天数)"] * 86400
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenChat(self.on_chat)
        self.last_msgs: dict[Player, int] = {}

    def on_def(self):
        self.ban = self.GetPluginAPI("封禁系统")
        if TYPE_CHECKING:
            from 封禁系统 import BanSystem
            self.ban: BanSystem

    def on_inject(self):
        @utils.timer_event(self.detect_time, "重置刷屏检测时长")
        def clear_message_lmt():
            self.last_msgs.clear()

        clear_message_lmt()

    def on_chat(self, chat: Chat):
        player = chat.player
        self.last_msgs.setdefault(player, 0)
        self.last_msgs[player] += 1
        if self.is_too_fast(player):
            self.ban.ban(player, self.ban_time, "超频刷屏")

    def is_too_fast(self, player: Player) -> bool:
        return self.last_msgs.get(player, 0) > self.msg_lmt

    def player_leave(self, player: Player):
        if player.name in self.last_msgs:
            del self.last_msgs[player.name]


entry = plugin_entry(HighRateChatAnti)

from tooldelta import (
    cfg as config,
    constants,
    utils,
    Plugin,
    Player,
    Chat,
    TYPE_CHECKING,
    plugin_entry,
)
from tooldelta.utils.packet_transition import get_playername_and_msg_from_text_packet


class HighRateChatAnti(Plugin):
    name = "超频发言反制"
    author = "SuperScript"
    version = (0, 0, 7)

    def __init__(self, frame):
        super().__init__(frame)
        CFG_DEFAULT = {
            "检测周期(秒)": 5,
            "检测周期内最多发送多少条消息": 10,
            "反制措施": {"封禁时间(天数)": 1},
            "是否忽略玩家发言合法性进行封禁": True,
        }
        CFG_STD = config.auto_to_std(CFG_DEFAULT)
        CFG_STD[config.KeyGroup("是否忽略玩家发言合法性进行封禁")] = CFG_STD[  # type: ignore
            "是否忽略玩家发言合法性进行封禁"
        ]
        del CFG_STD["是否忽略玩家发言合法性进行封禁"] # type: ignore
        cfg, _ = config.get_plugin_config_and_version(
            "超频发言限制", CFG_STD, CFG_DEFAULT, self.version
        )
        if cfg.get("是否忽略玩家发言合法性进行封禁") is None:
            cfg["是否忽略玩家发言合法性进行封禁"] = True
            config.upgrade_plugin_config(self.name, cfg, self.version)
            self.print("配置文件已更新")
        self.detect_time = cfg["检测周期(秒)"]
        self.msg_lmt = cfg["检测周期内最多发送多少条消息"]
        self.ban_time = cfg["反制措施"]["封禁时间(天数)"] * 86400
        allow_invalid_chat = cfg["是否忽略玩家发言合法性进行封禁"]
        if not allow_invalid_chat:
            self.ListenChat(self.on_chat)
        else:
            self.ListenPacket(constants.PacketIDS.Text, self.on_text)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
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

    def on_text(self, pk: dict):
        playername, msg, _ = get_playername_and_msg_from_text_packet(self.frame, pk)
        if not playername or msg is None:
            return False
        if p := self.game_ctrl.players.getPlayerByName(playername):
            self.on_chat(Chat(p, msg))
        else:
            self.print(f"§6无法通过数据包获得玩家发言: {pk}")
        return False

    def is_too_fast(self, player: Player) -> bool:
        return self.last_msgs.get(player, 0) > self.msg_lmt

    def player_leave(self, player: Player):
        if player.name in self.last_msgs:
            del self.last_msgs[player.name]


entry = plugin_entry(HighRateChatAnti)

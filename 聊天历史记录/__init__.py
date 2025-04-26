from io import TextIOWrapper
from datetime import datetime
from tooldelta import Plugin, plugin_entry, Player
from tooldelta.constants import PacketIDS
from tooldelta.utils import packet_transition


class ChatbarHistory(Plugin):
    name = "聊天历史记录"
    author = "ToolDelta"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenPacket(PacketIDS.Text, self.parse_text)
        self._logger_fp: TextIOWrapper | None = None
        self.make_data_path()

    def on_player_join(self, player: Player):
        self.log(f"{player.name} (XUID:{player.xuid}) 进入游戏")

    def on_player_leave(self, player: Player):
        self.log(f"{player.name} 退出游戏")

    def parse_text(self, pk: dict):
        playername, msg, can_be_trusted = (
            packet_transition.get_playername_and_msg_from_text_packet(self.frame, pk)
        )
        if playername is None:
            # 忽略 tellraw 等消息
            return False
        if can_be_trusted:
            self.log(f"{playername}: {msg}")
        else:
            self.log(f"{playername} (可能为伪造消息) 发送了消息: {msg}")
        return False

    def log(self, line: str):
        line = f"{datetime.now().strftime('%m-%d %H:%M:%S')} {line}"
        self._get_fp().write(line + "\n")
        self._get_fp().flush()

    def _get_fp(self):
        if self._logger_fp is None:
            self._logger_fp = open(
                self.format_data_path("聊天记录.log"), "a", encoding="utf-8"
            )
        return self._logger_fp


entry = plugin_entry(ChatbarHistory)

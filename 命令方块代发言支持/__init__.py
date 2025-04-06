from tooldelta import Plugin, plugin_entry, Chat, constants
from tooldelta.utils import packet_transition

class NewPlugin(Plugin):
    name = "命令方块代发言支持"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPacket(constants.PacketIDS.Text, self.on_chat_pk)

    def on_chat_pk(self, pk: dict):
        sender, msg, verified = packet_transition.get_playername_and_msg_from_text_packet(self.frame, pk)
        if sender is None or msg is None or sender not in self.game_ctrl.allplayers:
            return False
        player = self.frame.get_players().getPlayerByName(sender)
        if player is None:
            return False
        if not verified:
            self.frame.plugin_group.execute_chat(Chat(player, msg), self.frame.on_plugin_err)
        return False


entry = plugin_entry(NewPlugin)

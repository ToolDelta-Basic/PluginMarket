from tooldelta import Plugin, plugin_entry
from tooldelta.constants import PacketIDS


class NewPlugin(Plugin):
    name = "机器人发言"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.on_inject)

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["say"],
            "[msg]",
            "发言",
            lambda ms: self.bot_say(" ".join(ms)),
        )

    def bot_say(self, msg):
        self.game_ctrl.sendPacket(
            PacketIDS.Text,
            {
                "TextType": 1,
                "NeedsTranslation": False,
                "SourceName": "",
                "Message": msg,
                "Parameters": [],
                "XUID": self.game_ctrl.players_uuid[self.game_ctrl.bot_name][-8:],
                "PlatformChatID": "",
            },
        )


entry = plugin_entry(NewPlugin)

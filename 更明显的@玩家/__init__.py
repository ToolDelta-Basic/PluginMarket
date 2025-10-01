from tooldelta import Plugin, Chat, ToolDelta, plugin_entry

display = "§a§l@提醒 §7>>> §r"


def find_mentions(text, player_list):
    return [player for player in player_list if f"@{player}" in text]


class AtPlayer(Plugin):
    name = "@玩家"
    author = "wling"
    version = (0, 0, 5)
    description = "当有人提及你时，会收到提醒"

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenChat(self.on_chat)

    def on_chat(self, chat: Chat):
        message = chat.msg
        playername = chat.player.name
        # 如果文字包含@
        if "@" in message:
            mentioned_players = find_mentions(message, self.game_ctrl.allplayers)
            for i in mentioned_players:
                self.game_ctrl.say_to(i, display + "§l§a有人提及了你！")
                self.game_ctrl.player_title(i, "§b§l有人提及了你")
                self.game_ctrl.player_subtitle(i, f"§7{playername} > §e§l{message}")
                self.game_ctrl.sendcmd(
                    r"""/execute """
                    + i
                    + """ ~ ~ ~ playsound block.bell.hit @s ~ ~ ~ 1 1 1"""
                )


entry = plugin_entry(AtPlayer)

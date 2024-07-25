from tooldelta.plugin_load.injected_plugin import player_message, player_message_info
from tooldelta.game_utils import (
    rawText,
    sendcmd,
    get_all_player,
)


__plugin_meta__ = {
    "name": "@玩家",
    "version": "0.0.4",
    "description": "当有人提及你时，会收到提醒",
    "author": "wling",
}

display = "§a§l@提醒 §7>>> §r"


def find_mentions(text, player_list):
    return [player for player in player_list if f"@{player}" in text]


@player_message()
async def _(playerinfo: player_message_info):
    message = playerinfo.message
    playername = playerinfo.playername
    # 如果文字包含@
    if "@" in message:
        mentioned_players = find_mentions(message, get_all_player())
        for i in mentioned_players:
            rawText(i, display + "§l§a有人提及了你！")
            sendcmd(f"""/title {i} title §b§l有人提及了你""")
            sendcmd(f'''/title {i} subtitle "§7{playername} > §e§l{message}"''')
            sendcmd(
                r"""/execute """
                + i
                + """ ~ ~ ~ playsound block.bell.hit @s ~ ~ ~ 1 1 1"""
            )

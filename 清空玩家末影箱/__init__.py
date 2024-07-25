from tooldelta.plugin_load.injected_plugin import player_message, player_message_info
from tooldelta.game_utils import (
    tellrawText,
    sendwscmd,
    getTarget,
    is_op,
)

__plugin_meta__ = {
    "name": "清空玩家末影箱",
    "version": "0.0.5",
    "author": "wling",
}


@player_message()
async def _(playermessage: player_message_info):
    playername = playermessage.playername
    message = playermessage.message
    if message.startswith(".encl"):
        sendwscmd(f"/tellraw {playername} §l§cERROR§r §c指令不存在！")
        if is_op(playername):
            player_entity_clear = message.split(" ")[1]
            for i in getTarget("@a"):
                if player_entity_clear == i:
                    for i in range(0, 27):
                        sendwscmd(
                            f"/replaceitem entity {player_entity_clear} slot.enderchest {i!s} air"
                        )
                    tellrawText(playername, text="§l§a清空末影箱  成功")
                    return

            tellrawText(playername, "§l§cERROR§r", "§c目标玩家不存在！")
        else:
            tellrawText(playername, "§l§cERROR§r", "§c权限不足.")

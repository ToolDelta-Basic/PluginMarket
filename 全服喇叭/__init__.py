from tooldelta.plugin_load.injected_plugin import player_message, player_message_info
from tooldelta.plugin_load.injected_plugin.movent import (
    is_op,
    rawText,
    sendwscmd,
    tellrawText,
)
from tooldelta import plugins

__plugin_meta__ = {
    "name": "全服喇叭",
    "version": "0.0.2",
    "author": "wling",
}

plugins.get_plugin_api("聊天栏菜单").add_trigger(
    ["喇叭"], "[消息]", "管理广播消息", None, op_only=True
)


@player_message()
async def onPlayerChat(plyerinfomessage: player_message_info):
    msg, playername = plyerinfomessage.message, plyerinfomessage.playername
    if msg.startswith(".喇叭"):
        if is_op(playername):
            rawText(
                playername,
                f'§l§b{playername} §r§7>>> §l§b{msg.replace(".喇叭", "").strip()}',
            )
            sendwscmd(f"title @a title §l§b{playername}§f:")
            sendwscmd(f'title @a subtitle §l§e{msg.replace(".喇叭", "").strip()}')
            sendwscmd("execute as @a run playsound firework.launch @s ~~~ 10")

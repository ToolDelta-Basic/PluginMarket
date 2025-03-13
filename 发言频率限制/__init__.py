import time
from tooldelta.frame import cfg
from tooldelta.plugin_load.injected_plugin import (
    player_left,
    player_message,
    player_message_info,
    player_name,
)
from tooldelta.game_utils import get_all_player, is_op
from tooldelta import tooldelta


__plugin_meta__ = {
    "name": "发言频率",
    "version": "0.0.5",
    "author": "wling/7912",
}

STD_BAN_CFG = {"时间内": int, "在时间内达到多少条": int}
DEFAULT_BAN_CFG = {
    "时间内": 3,
    "在时间内达到多少条": 6,
}

cfg, cfg_version = cfg.get_plugin_config_and_version(
    __plugin_meta__["name"],
    STD_BAN_CFG,
    DEFAULT_BAN_CFG,
    __plugin_meta__["version"].split("."), # type: ignore
)

playerMsgTimeDict = {}
msgSendNunMaxPerTime = cfg["时间内"]
msgSendNumMax = cfg["在时间内达到多少条"]
ban_plugin = tooldelta.plugin_group.get_plugin_api("封禁系统")
ban = ban_plugin.ban


@player_message()
async def _(playermessage: player_message_info):
    playername = playermessage.playername
    if is_op(playername) and playername in get_all_player():
        msgSendTime = time.time()
        if playername not in playerMsgTimeDict:
            playerMsgTimeDict[playername] = []
        for i in playerMsgTimeDict[playername][:]:
            if i <= msgSendTime - msgSendNunMaxPerTime:
                playerMsgTimeDict[playername].remove(i)
        playerMsgTimeDict[playername].append(msgSendTime)
        if len(playerMsgTimeDict[playername]) >= msgSendNumMax:
            # 生成时间戳，比现在多五分钟，传参给
            # ban(playername, int(time.time()) + 300, "发信息过快")
            ban(playername, int(time.time()) + 300, "发信息过快")
            playerMsgTimeDict[playername] = []


@player_left()
async def _(playermessage: player_name):
    playername = playermessage.playername
    if playername in playerMsgTimeDict:
        del playerMsgTimeDict[playername]

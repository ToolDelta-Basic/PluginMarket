import asyncio
from tooldelta.plugin_load.injected_plugin import (
    player_join,
    player_left,
    player_name,
)
from tooldelta.game_utils import sendwscmd
from tooldelta import cfg as config

__plugin_meta__ = {
    "name": "入服欢迎",
    "version": "0.0.3",
    "author": "wling",
}


STD_BAN_CFG = {"登出时发送指令": list, "登录时发送指令": list, "登录时延迟发送": int}
DEFAULT_BAN_CFG: dict[str, list[str] | int] = {
    "登出时发送指令": [
        """/tellraw @a {\"rawtext\":[{\"text\":\"§a§lBye~ @[target_player]\"}]}"""
    ],
    "登录时发送指令": [
        """/tellraw [target_player] {\"rawtext\":[{\"text\":\"§a您可以使用在聊天栏发送 §b.help §a以调出系统面板§f.\"}]}"""
    ],
    "登录时延迟发送": 10,
}

cfg, cfg_version = config.get_plugin_config_and_version(
    __plugin_meta__["name"],
    STD_BAN_CFG,
    DEFAULT_BAN_CFG,
    __plugin_meta__["version"].split("."),
)


@player_join()
async def _(playerNameData: player_name) -> None:
    player = playerNameData.playername
    await asyncio.sleep(10)
    for i in cfg["登录时发送指令"]:
        sendwscmd(i.replace("[target_player]", player))


@player_left()
async def _(playerNameData: player_name) -> None:
    player = playerNameData.playername
    for i in cfg["登出时发送指令"]:
        sendwscmd(i.replace("[target_player]", player))

from tooldelta import Config, Print, plugins
from tooldelta.plugin_load.injected_plugin import (
    player_left,
    player_message,
    repeat,
    player_message_info,
    player_name,
)
from tooldelta.game_utils import get_all_player, is_op, sendwocmd


__plugin_meta__ = {
    "name": "发言频率限制",
    "version": "0.0.5",
    "author": "SuperScript",
}

CFG_DEFAULT = {
    "检测周期(秒)": 5,
    "检测周期内最多发送多少条消息": 10,
    "反制措施": {
        "封禁时间(天数)": 1
    },
}

cfg, _ = Config.get_plugin_config_and_version(
    "发言频率限制", Config.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, (0, 0, 5)
)

ban = plugins.get_plugin_api("封禁系统")

detect_time = cfg["检测周期(秒)"]
msg_lmt = cfg["检测周期内最多发送多少条消息"]
ban_days = cfg["反制措施"]["封禁时间(天数)"] * 86400

last_msgs: dict[str, int] = {}


def is_too_fast(player: str) -> bool:
    return last_msgs.get(player, 0) > msg_lmt


@repeat(detect_time)
async def clear_message_lmt():
    last_msgs.clear()


@player_message()
async def player_msg(msg_info: player_message_info):
    player = msg_info.playername

    if player not in get_all_player():
        return

    last_msgs.setdefault(player, 0)
    last_msgs[player] += 1
    if is_too_fast(player):
        ban(player, ban_days, "超频刷屏")


@player_left()
async def player_leave(player_name: player_name):
    if player_name.playername in last_msgs:
        del last_msgs[player_name.playername]

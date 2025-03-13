from tooldelta import cfg, Print
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
    "检测周期内最多发送多少条消息": 5,
    "发言太快反制措施": [
        'kick "[玩家名]" §c发言太快， 您已被踢出租赁服',
        "say §6[玩家名] §c因发言太快被踢出租赁服",
    ],
}

cfg, _ = cfg.get_plugin_config_and_version(
    "发言频率限制", cfg.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, (0, 0, 5)
)
detect_time = cfg["检测周期(秒)"]
msg_lmt = cfg["检测周期内最多发送多少条消息"]
msg_lmt_anti = cfg["发言太快反制措施"]

last_msgs: dict[str, int] = {}


def is_too_fast(player: str) -> bool:
    return last_msgs.get(player, 0) > msg_lmt


@repeat(detect_time)
async def clear_message_lmt():
    last_msgs.clear()


@player_message()
async def player_msg(msg_info: player_message_info):
    player = msg_info.playername
    msg = msg_info.message

    if player not in get_all_player():
        return

    last_msgs.setdefault(player, 0)
    last_msgs[player] += 1
    if is_op(player):
        return
    if len(msg) > 60:
        sendwocmd(f'kick "{player}" §c发言长度太长， 您已被踢出租赁服')
        Print.print_war(f"玩家 {player} 发言长度太长({len(msg)}), 已被踢出租赁服")
    elif is_too_fast(player):
        for cmd in msg_lmt_anti:
            sendwocmd(cmd.replace("[玩家名]", player))
        pass


@player_left()
async def player_leave(player_name: player_name):
    if player_name.playername in last_msgs:
        del last_msgs[player_name.playername]
        Print.print_inf(f"{player_name.playername} 离开服务器, 发言限制已重置")

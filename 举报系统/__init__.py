import logging
from datetime import datetime, timedelta
from tooldelta import cfg as config
from tooldelta.plugin_load.injected_plugin import player_message, player_message_info
from tooldelta.game_utils import sendwscmd, rawText
from tooldelta.game_utils import get_all_player, is_op
import asyncio

__plugin_meta__ = {
    "name": "report_system",
    "version": "0.0.1",
    "author": "帥気的男主角",
}

# 举报数达到多少次后踢出玩家
number_of_players = 3
number_of_players -= 1

# 记录日志
logging.basicConfig(filename='report_system.log', level=logging.INFO)

# 存储报告和时间戳
reports = {}
report_timestamps = {}

def log_report(playername, reported_player):
    logging.info(f"{datetime.now()} - {playername} reported: {reported_player}")

def log_kick(reported_player):
    logging.info(f"{datetime.now()} - {reported_player} was kicked out of the game")

@player_message()
async def _(playermessage: player_message_info):
    msg = playermessage.message
    playername = playermessage.playername

    if msg == ".r":
        players = get_all_players()  # 获取所有在线玩家的列表
        player_list = "\n".join([f"{i+1}. {p}" for i, p in enumerate(players)])
        rawText(playername, f"玩家列表:\n{player_list}\n请输入要举报的玩家序号 (输入0取消):")
        report_timestamps[playername] = datetime.now()
        await asyncio.sleep(30)  # 等待 30 秒
        if playername in report_timestamps and (datetime.now() - report_timestamps[playername]).seconds >= 30:
            del report_timestamps[playername]
            rawText(playername, "举报超时，已取消")
    elif playername in report_timestamps:
        if msg == "0":
            del report_timestamps[playername]
            rawText(playername, "举报已取消")
        elif (datetime.now() - report_timestamps[playername]).seconds < 60:
            try:
                index = int(msg) - 1
                players = get_all_players()
                if 0 <= index < len(players):
                    reported_player = players[index]
                    if is_op(reported_player):
                        rawText(playername, "举报管理员干什么，食不食油饼")
                    else:
                        if reported_player not in reports:
                            reports[reported_player] = set()
                        if playername not in reports[reported_player]:
                            reports[reported_player].add(playername)
                            log_report(playername, reported_player)
                            rawText(playername, "举报成功")
                            if len(reports[reported_player]) > number_of_players:
                                sendwscmd(f"/kick {reported_player}")
                                rawText("@a", f"玩家 {reported_player} 被踢出游戏，原因: 被多次举报")
                                log_kick(reported_player)
                            else:
                                rawText(playername, "您已经举报过该玩家")
                        del report_timestamps[playername]  # Cancel listening after input
                else:
                    rawText(playername, "无效的玩家序号")
            except ValueError:
                rawText(playername, "请输入有效的玩家序号")
        else:
            rawText(playername, "举报超时，请重新输入 .r 进行举报")

def get_all_players():
    # This function returns a list of all online player names
    return get_all_player()
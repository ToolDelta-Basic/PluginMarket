import logging
import time
from datetime import datetime
from tooldelta import ToolDelta,  utils, Plugin, plugin_entry, Chat

# 举报数达到多少次后踢出玩家
number_of_players = 3
number_of_players -= 1

# 记录日志
logging.basicConfig(filename="report_system.log", level=logging.INFO)

# 存储报告和时间戳
reports = {}
report_timestamps: dict[str, datetime] = {}


def log_report(playername, reported_player):
    logging.info(f"{datetime.now()} - {playername} reported: {reported_player}")


def log_kick(reported_player):
    logging.info(f"{datetime.now()} - {reported_player} was kicked out of the game")


class ReportSystem(Plugin):
    name = "举报系统"
    author = "帥氣的男主角"
    version = (0, 0, 2)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenChat(self.on_chat)

    @utils.thread_func("举报系统: 玩家发言")
    def on_chat(self, chat: Chat):
        player = chat.player
        msg = chat.msg
        playername = chat.player.name

        if msg == ".r":
            players = self.frame.get_players().getAllPlayers()  # 获取所有在线玩家的列表
            player_list = "\n".join(
                [f"{i + 1}. {p.name}" for i, p in enumerate(players)]
            )
            player.show(
                f"玩家列表:\n{player_list}\n请输入要举报的玩家序号 (输入0取消):"
            )
            report_timestamps[playername] = datetime.now()
            time.sleep(30)  # 等待 30 秒
            if (
                playername in report_timestamps
                and (datetime.now() - report_timestamps[playername]).seconds >= 30
            ):
                del report_timestamps[playername]
                player.show("举报超时，已取消")
        elif playername in report_timestamps:
            if msg == "0":
                del report_timestamps[playername]
                player.show("举报已取消")
            elif (datetime.now() - report_timestamps[playername]).seconds < 60:
                try:
                    index = int(msg) - 1
                    players = self.frame.get_players().getAllPlayers()
                    if 0 <= index < len(players):
                        reported_player_instance = players[index]
                        if reported_player_instance.is_op():
                            player.show("举报管理员干什么，食不食油饼")
                        else:
                            if reported_player_instance.name not in reports:
                                reports[reported_player_instance.name] = set()
                            if playername not in reports[reported_player_instance.name]:
                                reports[reported_player_instance.name].add(playername)
                                log_report(playername, reported_player_instance.name)
                                player.show("举报成功")
                                if (
                                    len(reports[reported_player_instance.name])
                                    > number_of_players
                                ):
                                    self.game_ctrl.sendwocmd(
                                        f'/kick "{reported_player_instance.name}"'
                                    )
                                    self.game_ctrl.say_to(
                                        "@a",
                                        f"玩家 {reported_player_instance.name} 被踢出游戏，原因: 被多次举报",
                                    )
                                    log_kick(reported_player_instance.name)
                                else:
                                    player.show("您已经举报过该玩家")
                            del report_timestamps[
                                playername
                            ]  # Cancel listening after input
                    else:
                        player.show("无效的玩家序号")
                except ValueError:
                    player.show("请输入有效的玩家序号")
            else:
                player.show("举报超时，请重新输入 .r 进行举报")


entry = plugin_entry(ReportSystem)

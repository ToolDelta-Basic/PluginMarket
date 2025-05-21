import time
from tooldelta import (
    InternalBroadcast,
    Player,
    Plugin,
    game_utils,
    Chat,
)
from tooldelta.utils import tempjson, ToolDeltaThread

from .world_backup import WorldBackupMain
from .recover import WorldBackupRecover
from .define import WorldBackupBase
import contextlib


class WorldBackupOnChat:
    world_backup_base: WorldBackupBase
    world_backup_main: WorldBackupMain
    world_backup_recover: WorldBackupRecover

    def __init__(self, main: WorldBackupMain, recover: WorldBackupRecover) -> None:
        self.world_backup_main = main
        self.world_backup_recover = recover
        self.world_backup_base = self.world_backup_recover.base()

    def base(self) -> WorldBackupBase:
        return self.world_backup_base

    def plugin(self) -> Plugin:
        return self.base().plugin

    def question_and_get_resp(self, player: Player, question: str) -> str:
        player.show(question)
        resp = game_utils.waitMsg(player.name)
        if resp is None:
            raise Exception(f"question_and_get_resp: Question time out (player={player.name})")  # noqa: TRY002
        return resp

    def on_chat(self, chat: Chat) -> None:
        with contextlib.suppress(Exception):
            self._on_chat(chat)

    def _on_chat(self, chat: Chat) -> None:  # noqa: C901, PLR0912, PLR0915
        message = chat.msg
        player = chat.player

        if not message.strip().startswith(self.base().recover_trigger_str):
            return

        if player.name not in self.base().ops_list:
            player.show(
                "§c你不是有效的管理员，操作失败\n(如果您是管理员则请联系有关人员修改配置文件)"
            )
            return

        cmd_config: dict = {
            "path": self.plugin().format_data_path(self.base().db_name),
            "output": self.plugin().format_data_path("mcw"),
            "use-range": "false",
            "range-start-x": "0",
            "range-start-z": "0",
            "range-end-x": "0",
            "range-end-z": "0",
            "range-dimension": "0",
            "provided-unix-time": str(int(time.time()) + 86400),
            "ensure-exist-one": "true",
        }
        player.show("§b已进入命令行模式，现在将引导您恢复数据库为 MC 存档")

        if "y" in self.question_and_get_resp(
            player, "§e1.1 要指定 MC 存档的文件夹名字吗 (yes/no): "
        ):
            cmd_config["output"] = self.plugin().format_data_path(
                self.question_and_get_resp(player, "§e1.2 请给出存档的文件夹名字: ")
            )

        if "n" in self.question_and_get_resp(
            player,
            "§e2.1 要恢复整个数据库为 MC 存档还是选定一个范围 (yes-整个,no-范围; 指定范围可以现场恢复区域): ",  # noqa: E501
        ):
            cmd_config["use-range"] = "true"

            cmd_config["range-start-x"] = self.question_and_get_resp(
                player, "§e2.2.1 请给出目标范围的起始 X 整数坐标: "
            )
            cmd_config["range-start-z"] = self.question_and_get_resp(
                player, "§e2.2.2 请给出目标范围的起始 Z 整数坐标: "
            )
            cmd_config["range-end-x"] = self.question_and_get_resp(
                player, "§e2.2.3 请给出目标范围的终止 X 整数坐标: "
            )
            cmd_config["range-end-z"] = self.question_and_get_resp(
                player, "§e2.2.4 请给出目标范围的终止 Z 整数坐标: "
            )

            if "n" in self.question_and_get_resp(
                player, "§e2.2.5.1 这些区域是否位于主世界 (yes/no): "
            ):
                cmd_config["range-dimension"] = self.question_and_get_resp(
                    player,
                    "§e2.2.5.2 请告诉我这些区域在哪个维度，请给我维度数字 ID (下界=1，末地=2): ",
                )

        if "n" in self.question_and_get_resp(
            player, "§e3.1 要恢复到最新的版本还是指定一个时间 (yes-最新,no-指定时间): "
        ):
            while True:
                player.show(
                    "§e3.2.0 接下来你需要给我一个时间，然后我们将恢复到距离这个时间及以前中最近的一个版本"  # noqa: E501
                )

                year = self.question_and_get_resp(player, "§e3.2.1 请告诉我时间的年份: ")
                month = self.question_and_get_resp(player, "§e3.2.2 请告诉我时间的月份: ")
                day = self.question_and_get_resp(player, "§e3.2.3 请告诉我时间的日期: ")

                hour = self.question_and_get_resp(player, "§e3.2.4 请告诉我时间的小时: ")
                minute = self.question_and_get_resp(player, "§e3.2.5 请告诉我时间的分钟: ")
                second = self.question_and_get_resp(player, "§e3.2.5 请告诉我时间的秒钟: ")

                if "n" in self.question_and_get_resp(
                    player,
                    f"§e3.2.5 我们将恢复到距离 {year}/{month}/{day} {hour}:{minute}:{second} 及以前的最新版本，你确定吗? (yes/no): ",  # noqa: E501
                ):
                    continue

                try:
                    time_get = time.mktime(
                        time.strptime(
                            f"{year}-{month}-{day}T{hour}:{minute}:{second}",
                            "%Y-%m-%dT%H:%M:%S",
                        )
                    )
                    cmd_config["provided-unix-time"] = str(int(time_get))
                except ValueError:
                    player.show("§e3.2.6 你给出的时间格式有误，请重试")

                if "n" in self.question_and_get_resp(
                    player,
                    "§e3.3 可能有的区块不满足这个时间限制(目标时间及以前)，那允许我们选择距离这个时间最近的一个吗? (yes/no): ",  # noqa: E501
                ):
                    cmd_config["ensure-exist-one"] = "false"

                break

        cmd_config_path = self.plugin().format_data_path("cmd_config.json")
        tempjson.load_and_write(cmd_config_path, cmd_config, need_file_exists=False)
        tempjson.flush(cmd_config_path)

        if "y" in self.question_and_get_resp(
            player,
            "§e4. 要重启 ToolDelta 后再进行恢复还是现在立即恢复? (yes-重启,no-现在立即; 重启后恢复将需要您手动调用简单世界恢复来进行恢复): ",  # noqa: E501
        ):
            player.show(
                "§a好的，ToolDelta 将会关闭，但本插件不支持重启，所以请您确保 ToolDelta 在关闭后可以打开，然后恢复程序将会开始工作"  # noqa: E501
            )
            ToolDeltaThread(
                self.plugin().frame.system_exit,
                ("世界备份第二世代: 重启",),
                usage="世界备份第二世代: 重启",
                thread_level=ToolDeltaThread.SYSTEM,
            )
        else:
            self.world_backup_main.do_close()
            mcworld_path, use_range, range_start, range_end = self.world_backup_recover.recover()
            self.world_backup_main.on_inject()
            self.base().should_close = False

            if len(mcworld_path) == 0 or not use_range:
                return

            if "y" in self.question_and_get_resp(
                player, "§e5.1 要现在调用简单世界恢复插件恢复对应区域吗? (yes/no):"
            ):
                _ = self.question_and_get_resp(
                    player,
                    "§e5.2 请手动将机器人传送到目标维度 (完成后回答任意内容即可)",
                )
                self.plugin().BroadcastEvent(
                    InternalBroadcast(
                        "swr:recover_request",
                        [
                            mcworld_path,
                            range_start,
                            range_end,
                        ],
                    )
                )
                player.show("§a恢复进程已启动，请坐和放宽 :)")

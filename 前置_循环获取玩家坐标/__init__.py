import time
import ujson
import dataclasses
from tooldelta import plugins, Plugin, Print, Utils

@plugins.add_plugin_as_api("循环获取玩家坐标")
class RepeatGetPlayerPos(Plugin):
    name = "前置-循环获取玩家坐标"
    author = "ToolDelta"
    version = (0, 0, 1)

    CYCLE = 1

    @dataclasses.dataclass
    class PlayerPosData:
        x: float
        y: float
        z: float
        yRot: float
        dimension: int

    def on_inject(self):
        self.player_posdata: dict[str, "RepeatGetPlayerPos.PlayerPosData"] = {}
        self._main_thread()

    # ----------------------- API ----------------------------------

    def get_player_posdata(self, playername: str):
        """
        获取玩家的坐标信息

        Args:
            playername (str): 玩家名

        Returns:
            PlayerPosData: 玩家坐标信息
        """
        return self.player_posdata[playername]

    def set_cycle(self, cycle: float):
        """
        更改获取坐标的周期时间

        Args:
            cycle (float): 新的获取周期时间
        """
        self.CYCLE = cycle

    # --------------------------------------------------------------

    @Utils.thread_func("循环获取玩家坐标")
    def _main_thread(self):
        while 1:
            uuid2player = {v: k for k, v in self.game_ctrl.players_uuid.items()}
            try:
                result = self.game_ctrl.sendcmd_with_resp("/querytarget @a")
                if result.SuccessCount == 0:
                    Print.print_err(f"获取玩家坐标: 无法获取坐标: {result.OutputMessages[0].Message}")
            except TimeoutError:
                Print.print_war("获取玩家坐标: 获取指令返回超时")
                continue
            content = ujson.loads(result.OutputMessages[0].Parameters[0])
            for i in content:
                content_pos = i["position"]
                self.player_posdata[uuid2player[i["uniqueId"]]] = self.PlayerPosData(
                    content_pos["x"],
                    content_pos["y"],
                    content_pos["z"],
                    i["yRot"],
                    i["dimension"]
                )
            time.sleep(self.CYCLE)

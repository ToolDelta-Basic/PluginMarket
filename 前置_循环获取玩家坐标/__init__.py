import time
import json
from tooldelta import InternalBroadcast, Plugin, fmts, utils, plugin_entry


class GlobalGetPlayerPos(Plugin):
    name = "前置-循环获取玩家坐标"
    author = "ToolDelta"
    version = (0, 0, 2)
    CYCLE = 1

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.on_inject)
        self.ListenInternalBroadcast("ggpp:set_crycle", self.set_cycle)

    def on_inject(self):
        self.player_posdata: dict[str, dict] = {}
        self._main_thread()

    def set_cycle(self, event: InternalBroadcast):
        """
        API (ggpp:set_crycle): 更改获取坐标的周期时间

        调用方式:
            ```
            InternalBroadcast(
                "ggpp:set_crycle",
                {"cycle": float(...)},
            )
            ```
        """
        if "cycle" in event.data:
            self.CYCLE = float(event.data["cycle"])

    def publish_position(self):
        """
        API (ggpp:publish_player_position): 发布玩家坐标信息

        Event data 示例:
            ```
            {
                "Happy2018new": {
                    "x": float(...),
                    "y": float(...)
                    "z": float(...),
                    "yRot": float(...),
                    "dimension": int(...)
                },
                "SuperScript": {
                    "x": float(...),
                    "y": float(...)
                    "z": float(...),
                    "yRot": float(...),
                    "dimension": int(...)
                },
                ...
            }
            ```
        """
        self.BroadcastEvent(
            InternalBroadcast("ggpp:publish_player_position", self.player_posdata)
        )

    @utils.thread_func("循环获取玩家坐标")
    def _main_thread(self):
        while 1:
            uuid2player = {v: k for k, v in self.game_ctrl.players_uuid.items()}
            try:
                result = self.game_ctrl.sendcmd_with_resp("/querytarget @a")
                if result.SuccessCount == 0:
                    fmts.print_err(
                        f"获取玩家坐标: 无法获取坐标: {result.OutputMessages[0].Message}"
                    )
            except TimeoutError:
                fmts.print_war("获取玩家坐标: 获取指令返回超时")
                continue
            content = json.loads(result.OutputMessages[0].Parameters[0])
            for i in content:
                player_name = uuid2player[i["uniqueId"]]
                self.player_posdata[player_name] = {
                    "x": i["position"]["x"],
                    "y": i["position"]["y"],
                    "z": i["position"]["z"],
                    "yRot": i["yRot"],
                    "dimension": int(i["dimension"]),
                }
            self.publish_position()
            time.sleep(self.CYCLE)


entry = plugin_entry(GlobalGetPlayerPos, "循环获取玩家坐标")

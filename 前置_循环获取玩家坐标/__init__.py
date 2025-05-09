import time
import json
from tooldelta import InternalBroadcast, Plugin, fmts, utils, plugin_entry


class GlobalGetPlayerPos(Plugin):
    name = "前置-循环获取玩家坐标"
    author = "ToolDelta"
    version = (0, 0, 4)
    CYCLE = 1

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.on_inject)
        self.ListenInternalBroadcast("ggpp:force_update", self.force_update)
        self.ListenInternalBroadcast("ggpp:set_crycle", self.set_cycle)

    def on_inject(self):
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

    def force_update(self, _: InternalBroadcast):
        """
        API (ggpp:force_update): 立即请求并广播玩家坐标数据

        调用方式:
            ```
            InternalBroadcast(
                "ggpp:force_update",
                {},
            )
            ```
        """
        self.get_and_publish_player_position()

    def publish_position(self, play_pos_data: dict):
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
            InternalBroadcast("ggpp:publish_player_position", play_pos_data)
        )

    def get_and_publish_player_position(self):
        uuid2player = {v: k for k, v in self.game_ctrl.players_uuid.items()}
        player_posdata = {}

        try:
            result = self.game_ctrl.sendcmd_with_resp("/querytarget @a")
            if result.SuccessCount == 0:
                fmts.print_err(
                    f"获取玩家坐标: 无法获取坐标: {result.OutputMessages[0].Message}"
                )
                return
        except TimeoutError:
            fmts.print_war("获取玩家坐标: 获取指令返回超时")
            return

        params = result.OutputMessages[0].Parameters
        if not params:
            fmts.print_war("获取玩家坐标: 指令返回异常.")
            return

        content = json.loads(params[0])
        for i in content:
            player_name = uuid2player[i["uniqueId"]]
            player_posdata[player_name] = {
                "x": i["position"]["x"],
                "y": i["position"]["y"],
                "z": i["position"]["z"],
                "yRot": i["yRot"],
                "dimension": int(i["dimension"]),
            }
        self.publish_position(player_posdata)

    @utils.thread_func("循环获取玩家坐标")
    def _main_thread(self):
        while 1:
            self.get_and_publish_player_position()
            time.sleep(self.CYCLE)


entry = plugin_entry(GlobalGetPlayerPos, "循环获取玩家坐标")

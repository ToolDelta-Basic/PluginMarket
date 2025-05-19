import time
import json
from tooldelta import Plugin, plugin_entry


class MCCommandDebugger(Plugin):
    name = "指令调试器"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.frame.add_console_cmd_trigger(
            ["d/"], "[指令]", "测试普通指令", self.test_common_command
        )
        self.frame.add_console_cmd_trigger(
            ["dw/"], "[指令]", "测试WebSocket指令", self.test_websocket_command
        )

    def test_common_command(self, args: list[str]):
        cmd = " ".join(args)
        sendtime = time.time()
        try:
            res = self.game_ctrl.sendwscmd_with_resp(cmd).as_dict
        except TimeoutError:
            self.print("§c指令返回获取超时")
            return
        use_time = time.time() - sendtime
        extra_msg = ("§c失败§r", "§a成功§r")[res["SuccessCount"] > 0]
        self.print(f"指令结果返回 ({cmd}) | {extra_msg} | 用时 {use_time:.2f}s:")
        self.print(json.dumps(res, indent=4, ensure_ascii=False))

    def test_websocket_command(self, args: list[str]):
        cmd = " ".join(args)
        sendtime = time.time()
        try:
            res = self.game_ctrl.sendwscmd_with_resp(cmd).as_dict
        except TimeoutError:
            self.print("§c指令返回获取超时")
            return
        use_time = time.time() - sendtime
        extra_msg = ("§c失败§r", "§a成功§r")[res["SuccessCount"] > 0]
        self.print(f"指令结果返回 ({cmd}) | {extra_msg} | 用时 {use_time:.2f}s:")
        self.print(json.dumps(res, indent=4, ensure_ascii=False))


entry = plugin_entry(MCCommandDebugger)

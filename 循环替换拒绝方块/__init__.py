from tooldelta import Plugin, plugin_entry, utils, fmts, constants
import time


class AutoReplaceBedrock(Plugin):
    name = "防冒险破坏"
    author = "心海"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.is_running = False

        # 同款刷屏拦截
        def on_filter(packet) -> bool:
            return packet["TextType"] == 10  # 拦截TextType=10的刷屏包

        self.ListenPacket(constants.PacketIDS.Text, on_filter)
        self.ListenActive(self._command_loop)
        self.ListenFrameExit(self.exit)

    @utils.thread_func("基岩填充")
    def _command_loop(self):
        while self.is_running:
            try:
                # 核心命令：替换玩家下方基岩
                self.game_ctrl.sendwocmd(
                    "/execute as @a at @s positioned ~ -64 ~ if block ~~~ bedrock run "
                    "fill ~-10 ~ ~-10 ~10 ~ ~10 deny 0 replace bedrock 0"
                )
            except Exception as e:
                fmts.print_err(f"命令执行失败: {e}")
            time.sleep(0.1)  # 固定0.1秒间隔

    def exit(self, _):
        self.is_running = False

entry = plugin_entry(AutoReplaceBedrock, "基岩替换")

from tooldelta import Plugin, Print, FrameExit, plugin_entry


class CommandSenderMonitor(Plugin):
    name = "命令发送监管器"
    author = "ToolDelta"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenFrameExit(self.on_frame_exit)

    def on_def(self):
        self.instant_monitor = False
        self.is_injected = False
        self.cached_sendcmd = self.game_ctrl.sendcmd
        self.cached_sendwscmd = self.game_ctrl.sendwscmd
        self.cached_sendwocmd = self.game_ctrl.sendwocmd
        self.frame.add_console_cmd_trigger(
            ["cmdt"], None, "打开/关闭指令监视器", self.on_menu
        )

    def enable_monitor(self):
        self.game_ctrl.sendcmd = self.special_monitor_sendcmd
        self.game_ctrl.sendwscmd = self.special_monitor_sendwscmd
        self.game_ctrl.sendwocmd = self.special_monitor_sendwocmd
        self.is_injected = True

    def disable_monitor(self):
        if self.is_injected:
            self.game_ctrl.sendcmd = self.cached_sendcmd
            self.game_ctrl.sendwscmd = self.cached_sendwscmd
            self.game_ctrl.sendwocmd = self.cached_sendwocmd

    def on_menu(self, _):
        self.instant_monitor = not self.instant_monitor
        if self.instant_monitor:
            self.enable_monitor()
        else:
            self.disable_monitor()
        Print.print_suc(f"已{['关闭', '打开'][self.instant_monitor]}指令监测器")

    def special_monitor_sendcmd(
        self, cmd: str, waitForResp: bool = False, timeout: float = 30
    ):
        if self.instant_monitor:
            Print.print_with_info(
                f"发送§a普通§r 指令{'<有返回>' if waitForResp else ''}: {cmd}",
                "§b SCMD §r",
            )
        return self.cached_sendcmd(cmd, waitForResp, timeout)

    def special_monitor_sendwscmd(
        self, cmd: str, waitForResp: bool = False, timeout: float = 30
    ):
        if self.instant_monitor:
            Print.print_with_info(
                f"发送 §bWS§r 指令{'<有返回>' if waitForResp else ''}: {cmd}",
                "§b SCMD §r",
            )
        return self.cached_sendwscmd(cmd, waitForResp, timeout)

    def special_monitor_sendwocmd(self, cmd: str):
        if self.instant_monitor:
            Print.print_with_info(f"发送 §dWO§r 指令: {cmd}", "§b SCMD §r")
        self.cached_sendwocmd(cmd)

    def on_frame_exit(self, evt: FrameExit):
        _ = evt.signal
        _2s = evt.reason

        self.disable_monitor()


entry = plugin_entry(CommandSenderMonitor)

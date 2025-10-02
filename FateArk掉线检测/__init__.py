import time
from tooldelta import Plugin, plugin_entry, utils, fmts


class FateArkBotAliveChecker(Plugin):
    name = "FateArk掉线检测"
    author = "渊思"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.Start)

    def Start(self):
        utils.createThread(self.Check, (), "Fateark掉线检测")

    def Check(self):
        while True:
            try:
                _ = self.game_ctrl.sendwscmd("testfor @a", waitForResp=True, timeout=10)
                time.sleep(8)
            except TimeoutError:
                fmts.print_war("指令检测超时，正在进行二次检测")
                try:
                    _ = self.game_ctrl.sendwscmd(
                        "testfor @a", waitForResp=True, timeout=10
                    )
                except TimeoutError:
                    fmts.print_war("指令检测超时，正在进行三次检测")
                    try:
                        _ = self.game_ctrl.sendwscmd(
                            "testfor @a", waitForResp=True, timeout=10
                        )
                    except TimeoutError:
                        fmts.print_war("FateArk接入点机器人已掉线")
                        self.frame.system_exit("FateArk接入点机器人已掉线")


entry = plugin_entry(FateArkBotAliveChecker)

from tooldelta import Plugin, plugin_entry, fmts
from threading import Thread
import time

"""
先叠甲
这个插件写的很草率，但是能用
目的为了FateArk接入点机器人掉线
但是我认为这样的情况不会出现太久
这也就是这坨的由来
"""



class NewPlugin(Plugin):
    name = "FateArk掉线检测"
    author = "渊思"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.Start)
        self.stop = False
        self.ListenFrameExit(self.Stop)

    def Stop(self,_):
        self.stop = True
    def Start(self):
        
        global thread
        thread = Thread(target=self.Check)
        thread.start()

    def Check(self):
        while self.stop == False:
            try:
                res = self.game_ctrl.sendwscmd("testfor @a", waitForResp=True, timeout=10)
                time.sleep(8)
            except TimeoutError:
                fmts.print_war("指令检测超时，正在进行二次检测")
                try:
                    res = self.game_ctrl.sendwscmd("testfor @a", waitForResp=True, timeout=10)
                except TimeoutError:
                    fmts.print_war("指令检测超时，正在进行三次检测")
                    try:
                        res = self.game_ctrl.sendwscmd("testfor @a", waitForResp=True, timeout=10)
                    except TimeoutError:
                        fmts.print_war("FateArk接入点机器人已掉线")
                        self.frame.system_exit("FateArk接入点机器人已掉线")

entry = plugin_entry(NewPlugin)
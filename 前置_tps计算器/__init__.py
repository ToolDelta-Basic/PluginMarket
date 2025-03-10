import time
from tooldelta import Plugin, constants, plugin_entry


class TPSCalculator(Plugin):
    name = "前置-TPS计算器"
    author = "SuperScript"
    version = (0, 0, 1)
    lt = time.time()
    lt1 = 0
    _tps = 20

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPacket(constants.PacketIDS.IDTickSync, self.listener)

    def listener(self, pkt):
        self.calc_tps(pkt)
        return False

    def calc_tps(self, pkt):
        ntime = time.time()
        servert = pkt["ServerReceptionTimestamp"]
        self._tps = min(20, (servert - self.lt1) / (ntime - self.lt))
        self.lt = ntime
        self.lt1 = servert

    def get_tps(self):
        if time.time() - self.lt > 40:
            # server maybe dead
            return 0
        else:
            return self._tps


entry = plugin_entry(TPSCalculator, "tps计算器")

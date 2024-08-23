import time
from tooldelta import plugins, Plugin, constants


@plugins.add_plugin_as_api("tps计算器")
class TPSCalculator(Plugin):
    name = "前置-TPS计算器"
    author = "SuperScript"
    version = (0, 0, 1)

    lt = time.time()
    lt1 = 0

    @plugins.add_packet_listener(constants.PacketIDS.IDTickSync)
    def listener(self, pkt):
        self.calc_tps(pkt)
        return False

    def calc_tps(self, pkt):
        ntime = time.time()
        servert = pkt["ServerReceptionTimestamp"]
        self._tps = (servert - self.lt1) / (ntime - self.lt)
        self.lt = ntime
        self.lt1 = servert

    def get_tps(self):
        if time.time() - self.lt > 40:
            # server maybe dead
            return 0
        else:
            return self._tps

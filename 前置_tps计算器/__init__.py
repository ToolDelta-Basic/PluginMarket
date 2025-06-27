import time
from tooldelta import Plugin, constants, plugin_entry


class TPSCalculator(Plugin):
    name = "前置-TPS计算器"
    author = "SuperScript"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPacket(constants.PacketIDS.IDSetTime, self.listener)
        self.last_time = time.time()
        self.last_server_time = 0
        self._tps = 20
        self._real_tps = 20
        self._warned = False

    def listener(self, pkt):
        self.calc_tps(pkt)
        return False

    def calc_tps(self, pkt):
        ntime = time.time()
        server_time = pkt["Time"]
        server_time_delta = server_time - self.last_server_time
        real_time_delta = ntime - self.last_time
        if server_time_delta == 0:
            if not self._warned:
                self._warned = True
                self.print("§6警告: 无法正确取得租赁服 tps。你需要在设置中将§e昼夜更替§6打开。")
            return
        self._real_tps = server_time_delta / real_time_delta
        self._tps = min(20, server_time_delta / self._real_tps)
        self.last_time = ntime
        self.last_server_time = server_time


    def get_tps(self):
        if time.time() - self.last_time > 40:
            # server maybe dead
            return 0
        else:
            return self._tps


entry = plugin_entry(TPSCalculator, "tps计算器")

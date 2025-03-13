import time
from dataclasses import dataclass
from tooldelta import Plugin, game_utils, utils, Print, cfg, plugin_entry
from tooldelta.constants import PacketIDS


@dataclass
class AntiPistonPos:
    x: int
    y: int
    z: int
    r: int

    def check(self, x, y, z):
        return ((x - self.x) ** 2 + (y - self.y) ** 2 + (z - self.z) ** 2) < self.r**2


class PistonLmt(Plugin):
    name = "活塞限速"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.piston_lmt: dict[str, int] = {}
        self.anti_pistons: list[AntiPistonPos] = []
        CFG_DEFAULT = {
            "根据服内tps动态计算限速值": True,
            "限速速度(推/拉每10秒)": 40,
            "反制指令": [
                "/say §c位于§6([x], [y], [z])§c的活塞已超速， 已破坏， 最近玩家： §e[最近玩家]\n§6当前限速值： §a[限速值]",
                "/setblock [x] [y] [z] air 0 destroy",
            ],
            "这些地方完全无法使用活塞": [{"x": -64, "y": 106, "z": -32, "半径": 100}],
        }
        cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, self.version
        )
        for dat in cfg["这些地方完全无法使用活塞"]:
            self.anti_pistons.append(
                AntiPistonPos(dat["x"], dat["y"], dat["z"], dat["半径"])
            )
        self.is_dyna = cfg["根据服内tps动态计算限速值"]
        self.lmt = cfg["限速速度(推/拉每10秒)"]
        self.exec_cmds = cfg["反制指令"]
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPacket(PacketIDS.IDBlockActorData, self.on_piston_pkt)

    def on_def(self):
        self.get_tps = self.GetPluginAPI("tps计算器").get_tps

    def on_inject(self):
        self.clear_sum()

    @utils.thread_func("活塞限速计时器重置")
    def clear_sum(self):
        Print.print_inf("活塞限速计时器已启动")
        while 1:
            for _ in range(20):
                time.sleep(0.5)
            self.piston_lmt.clear()

    def get_speed_lmt(self) -> int:
        LMT = self.lmt
        if self.is_dyna:
            return int(LMT / (20 / self.get_tps()))
        else:
            return self.lmt

    def on_piston_pkt(self, jsonPkt):
        if jsonPkt["NBTData"].get("id") != "PistonArm":
            return False
        x, y, z = jsonPkt["Position"]
        pid = f"{x},{y},{z}"
        if any(i.check(x, y, z) for i in self.anti_pistons):
            self.zhicai(x, y, z, pid, 0)
            return False
        self.piston_lmt[pid] = self.piston_lmt.get(pid, 0) + 1
        if self.piston_lmt[pid] > self.get_speed_lmt():
            self.zhicai(x, y, z, pid, self.get_speed_lmt())
        return False

    def zhicai(self, x, y, z, pid, spd):
        targets = game_utils.getTarget(f"@a[x={x},y={y},z={z},c=1]")
        if targets == []:
            targets = ["???"]
        for cmd in self.exec_cmds:
            self.game_ctrl.sendwocmd(
                utils.simple_fmt(
                    {
                        "[x]": x,
                        "[y]": y,
                        "[z]": z,
                        "[最近玩家]": targets[0],
                        "[限速值]": spd,
                    },
                    cmd,
                )
            )
        del self.piston_lmt[pid]


entry = plugin_entry(PistonLmt)

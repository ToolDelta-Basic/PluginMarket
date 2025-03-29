import time
import math

from tooldelta import Frame, Plugin, utils, TYPE_CHECKING, plugin_entry
from tooldelta.constants import PacketIDS
from tooldelta.game_utils import getTarget, is_op
from tooldelta.utils.tooldelta_thread import ThreadExit


class WorldEdit(Plugin):
    author = "SuperScript"
    version = (0, 0, 10)
    name = "简易建造"
    description = "以更方便的方法在租赁服进行创作"

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.ListenPreload(self.on_def)
        self.ListenPacket(PacketIDS.IDBlockActorData, self.we_pkt56)
        self.x = -99999999999
        self.y = -99999999999
        self.z = -99999999999

    def on_def(self):
        self.getX = None
        self.getY = None
        self.getZ = None
        self.endX = None
        self.endY = None
        self.endZ = None
        self.intr = self.GetPluginAPI("前置-世界交互")
        if TYPE_CHECKING:
            from 前置_世界交互 import GameInteractive

            self.intr = self.get_typecheck_plugin_api(GameInteractive)

    def we_pkt56(self, jsonPkt: dict):
        return self._we_pkt56(jsonPkt)

    def request_position(self, x: float, y: float, z: float):
        if math.hypot(x - self.x, y - self.y, z - self.z) >= 32:
            self.game_ctrl.sendcmd(f"tp {x} {y} {z}")
            time.sleep(0.05)
            self.x = x
            self.y = y
            self.z = z

    @utils.thread_func("简易建造-事件执行")
    def _we_pkt56(self, jsonPkt: dict):
        if "NBTData" in jsonPkt and "id" in jsonPkt["NBTData"]:
            if not (jsonPkt["NBTData"]["id"] == "Sign"):
                return False
            signText = jsonPkt["NBTData"]["FrontText"]["Text"]
            placeX, placeY, placeZ = (
                jsonPkt["NBTData"]["x"],
                jsonPkt["NBTData"]["y"],
                jsonPkt["NBTData"]["z"],
            )
            nearestPlayer = getTarget(f"@a[x={placeX},y={placeY},z={placeZ},c=1,r=5]")
            if nearestPlayer == []:
                return False
            nearestPlayer = nearestPlayer[0]
            if not is_op(nearestPlayer):
                self.game_ctrl.say_to(nearestPlayer, "§c非OP无法使用此功能")
                return False
            dont_deleted = self.handler(placeX, placeY, placeZ, nearestPlayer, signText)
            if not dont_deleted:
                self.game_ctrl.sendwocmd(f"setblock {placeX} {placeY} {placeZ} air")
        return False

    def handler(self, x: int, y: int, z: int, op: str, opStr: str):
        opStrs = opStr.split()
        utils.fill_list_index(opStrs, ["", ""])
        if opStrs == []:
            return True
        match opStrs[0]:
            case "qd" | "起点":
                self.getX, self.getY, self.getZ = x, y, z
                self.showto(op, f"起点已设置: {x}, {y}, {z}")
                return False
            case "zd" | "终点":
                self.endX, self.endY, self.endZ = x, y, z
                self.showto(op, f"终点已设置: {x}, {y}, {z}")
                return False
            case "lf" | "立方":
                sx, sy, sz, ex, ey, ez = self.assert_se(op)
                self.cube_fill(x, y - 1, z, sx, sy, sz, ex, ey, ez, op)
                return False
            case "fz" | "复制":
                sx, sy, sz, ex, ey, ez = self.assert_se(op)
                self.game_ctrl.sendwocmd(
                    f"clone {sx} {sy} {sz} {ex} {ey} {ez} {x} {y} {z}"
                )
                self.showto(op, "已复制结构")
                return False
            case "zx" | "直线" | "xd" | "线段":
                sx, sy, sz, ex, ey, ez = self.assert_se(op)
                self.showto(op, "画线命令已执行")
                self.lineTo(sx, sy, sz, ex, ey, ez, x, y - 1, z)
                return False
            case "hy" | "画圆":
                sx, sy, sz, ex, ey, ez = self.assert_se(op)
                if ey != sy:
                    self.showto(op, "§6需要起始点和终止点在同一水平面")
                    return False
                r = round(math.hypot(ex - sx, ez - sz))
                self.showto(op, "画圆命令已执行")
                if opStrs[1] == "sx":
                    self.horizon_round(x, y - 1, z, sx, sy, sz, r)
                else:
                    self.hollow_horizon_round(x, y - 1, z, sx, sy, sz, r)
                return False
            case "yz" | "圆柱":
                sx, sy, sz, ex, ey, ez = self.assert_se(op)
                self.column(
                    x,
                    y - 1,
                    z,
                    sx,
                    sy,
                    sz,
                    round(math.hypot(ex - sx, ez - sz)),
                    ey - sy,
                )
            case "yz1" | "圆锥":
                sx, sy, sz, ex, ey, ez = self.assert_se(op)
                self.awl(
                    x,
                    y - 1,
                    z,
                    sx,
                    sy,
                    sz,
                    round(math.hypot(ex - sx, ez - sz)),
                    ey - sy,
                )
            case "qt" | "球体":
                sx, sy, sz, ex, ey, ez = self.assert_se(op)
                self.ball(
                    x,
                    y - 1,
                    z,
                    sx,
                    sy,
                    sz,
                    round(math.hypot(ex - sx, ey - sy, ez - sz)),
                )
            case "tc" | "填充":
                self.showto(op, "填充命令正在执行")
                self.fill_horizon(x, y - 1, z)
                self.showto(op, "填充命令执行完毕")
        return True

    @utils.thread_func("简易建造-填充")
    def cube_fill(self, bx, by, bz, sx, sy, sz, dx, dy, dz, op):
        def p2n(n):
            return 1 if n >= 0 else -1

        fx = p2n(dx - sx)
        fy = p2n(dy - sy)
        fz = p2n(dz - sz)
        self.showto(op, "开始填充方块..")
        for x in range(sx, dx + fx, fx):
            for y in range(sy, dy + fy, fy):
                for z in range(sz, dz + fz, fz):
                    self.game_ctrl.sendwocmd(
                        f"/clone {bx} {by} {bz} {bx} {by} {bz} {x} {y} {z}"
                    )
                    time.sleep(0.005)
        self.showto(op, "填充完成")

    @utils.thread_func("简易建造-画线")
    def lineTo(
        self,
        sx: int,
        sy: int,
        sz: int,
        ex: int,
        ey: int,
        ez: int,
        x: int,
        y: int,
        z: int,
    ):
        blocks_num = self.get_blocks_num(sx, sy, sz, ex, ey, ez)
        for i in range(blocks_num + 1):
            prog = i / blocks_num
            xb = self.get_midval(sx, ex, prog)
            yb = self.get_midval(sy, ey, prog)
            zb = self.get_midval(sz, ez, prog)
            self.request_position(xb, yb, zb)
            self.game_ctrl.sendwocmd(f"clone {x} {y} {z} {x} {y} {z} {xb} {yb} {zb}")
            time.sleep(0.05)

    def hollow_horizon_round(
        self, bx: int, by: int, bz: int, cx: int, cy: int, cz: int, r: int, delay=0.005
    ):
        self.game_ctrl.sendwocmd(f"clone {bx} {by} {bz} {bx} {by} {bz} {cx} {cy} {cz}")
        processor = round
        for dx in range(-2 * r, 2 * r + 1):
            dx1 = dx / 2
            dz = processor(math.cos(math.asin(dx1 / r)) * r)
            dx = dx // 2
            self.request_position(cx + dx, cy, cz + dz)
            self.game_ctrl.sendwocmd(
                f"clone {bx} {by} {bz} {bx} {by} {bz} {cx + dx} {cy} {cz + dz}"
            )
        for dx in range(-2 * r, 2 * r + 1):
            dx1 = dx / 2
            dz = processor(math.cos(math.asin(dx1 / r)) * r)
            dx = dx // 2
            self.request_position(cx + dx, cy, cz - dz)
            self.game_ctrl.sendwocmd(
                f"clone {bx} {by} {bz} {bx} {by} {bz} {cx + dx} {cy} {cz - dz}"
            )
            time.sleep(delay)
        for dz in range(-2 * r, 2 * r + 1):
            dz1 = dz / 2
            dx = processor(math.cos(math.asin(dz1 / r)) * r)
            dz = dz // 2
            self.request_position(cx + dx, cy, cz + dz)
            self.game_ctrl.sendwocmd(
                f"clone {bx} {by} {bz} {bx} {by} {bz} {cx + dx} {cy} {cz + dz}"
            )
        for dz in range(-2 * r, 2 * r + 1):
            dz1 = dz / 2
            dx = processor(math.cos(math.asin(dz1 / r)) * r)
            dz = dz // 2
            self.request_position(cx + dx, cy, cz - dz)
            self.game_ctrl.sendwocmd(
                f"clone {bx} {by} {bz} {bx} {by} {bz} {cx - dx} {cy} {cz + dz}"
            )
            time.sleep(delay)

    def horizon_round(
        self, bx: int, by: int, bz: int, cx: int, cy: int, cz: int, r: int, delay=0.005
    ):
        for x in range(cx - r, cx + r + 1):
            for z in range(cz - r, cz + r + 1):
                if math.hypot(x - cx, z - cz) <= r:
                    self.request_position(x, cy, z)
                    self.game_ctrl.sendwocmd(
                        f"clone {self.make_clone_pos(bx, by, bz, x, cy, z)}"
                    )
                    time.sleep(delay)

    def ball(self, bx: int, by: int, bz: int, cx: int, cy: int, cz: int, r: int):
        for x in range(cx - r, cx + r + 1):
            for y in range(cy - r, cy + r + 1):
                for z in range(cz - r, cz + r + 1):
                    if math.hypot(x - cx, y - cy, z - cz) <= r:
                        self.request_position(x, y, z)
                        self.game_ctrl.sendwocmd(
                            f"clone {self.make_clone_pos(bx, by, bz, x, y, z)}"
                        )

    def showto(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7WorldEdit§f>> §e{msg}")

    def assert_se(self, op: str):
        gx, gy, gz, ex, ey, ez = (
            self.getX,
            self.getY,
            self.getZ,
            self.endX,
            self.endY,
            self.endZ,
        )
        if (
            gx is None
            or gy is None
            or gz is None
            or ex is None
            or ey is None
            or ez is None
        ):
            self.showto(op, "§6还未设置起点或终点...")
            raise ThreadExit
        return gx, gy, gz, ex, ey, ez

    def column(
        self, bx: int, by: int, bz: int, cx: int, cy: int, cz: int, r: int, h: int
    ):
        for hi in range(h + 1):
            self.horizon_round(bx, by, bz, cx, cy + hi, cz, r, 0.003)

    def awl(self, bx: int, by: int, bz: int, cx: int, cy: int, cz: int, r: int, h: int):
        for hi in range(h + 1):
            dyna_r = self.get_midval(r, 0, hi / h)
            self.horizon_round(bx, by, bz, cx, cy + hi, cz, dyna_r, 0.003)

    def fill_horizon(self, bx: int, by: int, bz: int):
        BLOCK_AIR = 0
        BLOCK_BORDER = 1
        BLOCK_FILL = 2
        area = self.intr.get_structure((bx - 32, by, bz - 32), (64, 1, 64))
        mapping: list[list[int]] = []
        for x in range(64):
            mapping.append([])
            for z in range(64):
                b = area.get_block((x, 0, z))
                mapping[x].append(
                    BLOCK_AIR
                    if (b.name.endswith("air") or b.name.endswith("light_block"))
                    else BLOCK_BORDER
                )
        mapping[32][32] = BLOCK_FILL
        has_air = True
        while has_air:
            has_air = False
            for x, zs_map in enumerate(mapping.copy()):
                for z, x_block in enumerate(zs_map.copy()):
                    if x_block == BLOCK_FILL:
                        empty_blocks = self.is_in_fill(mapping, x, z)
                        if empty_blocks != []:
                            has_air = True
                        for x1, z1 in empty_blocks:
                            mapping[x1][z1] = BLOCK_FILL
                            destx = bx + x1 - 32
                            destz = bz + z1 - 32
                            self.send_clone_pos(bx, by, bz, destx, by, destz)
                            time.sleep(0.002)

    @staticmethod
    def make_clone_pos(bx: int, by: int, bz: int, destx: int, desty: int, destz: int):
        return f"{bx} {by} {bz} {bx} {by} {bz} {destx} {desty} {destz}"

    def send_clone_pos(
        self, bx: int, by: int, bz: int, destx: int, desty: int, destz: int
    ):
        self.game_ctrl.sendwocmd(
            f'execute as @a[name="{self.game_ctrl.bot_name}"] at @s run clone {bx} {by} {bz} {bx} {by} {bz} {destx} {desty} {destz}'
        )

    @staticmethod
    def get_blocks_num(sx: int, sy: int, sz: int, ex: int, ey: int, ez: int):
        return round(math.hypot(ex - sx, ey - sy, ez - sz))

    @staticmethod
    def get_midval(start: int, end: int, prog: float):
        return int(start + (end - start) * prog)

    @staticmethod
    def is_in_fill(mapping: list[list[int]], x: int, z: int):
        result: list[tuple[int, int]] = []
        for posx, posz in (x - 1, z), (x + 1, z), (x, z - 1), (x, z + 1):
            if 0 <= posx < 64 and 0 <= posz < 64:
                if mapping[posx][posz] == 0:
                    result.append((posx, posz))
        return result


entry = plugin_entry(WorldEdit)

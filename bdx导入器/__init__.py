from tooldelta import Plugin, Print, Utils, plugins, TYPE_CHECKING, game_utils
import os
import time
import json
from .BDXConverter.Converter.Converter import BDX
from .BDXConverter.General import Operation


@plugins.add_plugin
class BDX_BDump(Plugin):
    name = "BDX-BDump导入器"
    author = "xingchen/SuperScript"
    version = (0, 0, 5)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()

    def on_def(self):
        self.interact = plugins.get_plugin_api("前置-世界交互")
        if TYPE_CHECKING:
            from 前置_世界交互 import GameInteractive

            self.interact = plugins.instant_plugin_api(GameInteractive)
        Print.print_inf(
            '§bBDX加载器 使用了来自 "github.com/TriM-Organization/BDXConverter" 的开源库'
        )
        Print.print_inf(
            "§b其第一作者为 Eternal Crystal (Happy2018New) (其他协作者请在项目内查看)"
        )

    def on_inject(self):
        self.get_x: float | None = None
        self.get_y: float | None = None
        self.get_z: float | None = None
        self.frame.add_console_cmd_trigger(
            ["bdump"], None, "导入bdx文件", self.dump_bdx_menu
        )
        self.frame.add_console_cmd_trigger(
            ["bdxget"], None, "获取bdx文件导入坐标", self.get_bdx_pos_menu
        )

    def dump_bdx_menu(self, _):
        src_path = self.data_path
        if not self.get_x or not self.get_y or not self.get_z:
            Print.print_err("未设置导入坐标 (控制台输入 bdx-get 以设置)")
            return
        Print.print_inf(f"文件搜索路径: {src_path}")
        fs = list(filter(lambda x: x.endswith(".bdx"), os.listdir(src_path)))
        if fs == []:
            Print.print_war("该文件夹内没有任何 bdx 文件, 无法导入")
            return
        Print.print_inf("请选择导入的 bdx 文件:")
        for i, j in enumerate(fs):
            Print.print_inf(f" {i+1} - {j}")
        resp = Utils.try_int(input(Print.fmt_info(f"请选择 (1~{len(fs)}): ")))
        if not resp or resp not in range(1, len(fs) + 1):
            Print.print_err("输入错, 已退出")
            return
        bdx_file = fs[resp - 1]
        try:
            bdx_content = self.read_bdx(os.path.join(src_path, bdx_file))
        except Exception as err:
            Print.print_err(f"读取 {bdx_file} 出现问题: {err}")
            return
        bdx_name = bdx_file[:-4]
        Print.print_inf(f"{bdx_name} 的导入已经开始 (进度条显示于游戏内)")
        Utils.createThread(
            self.dump_bdx_at,
            (bdx_name, bdx_content, int(self.get_x), int(self.get_y), int(self.get_z)),
        )

    def get_bdx_pos_menu(self, _):
        avali_players = self.game_ctrl.allplayers
        if self.game_ctrl.bot_name in avali_players:
            avali_players.remove(self.game_ctrl.bot_name)
        if (
            len(
                gplayer := [
                    i
                    for i in self.game_ctrl.all_players_data
                    if i.op and i.name != self.game_ctrl.bot_name
                ]
            )
            == 1
        ):
            player_get = gplayer[0].name
        else:
            Print.print_inf("请选择玩家以获取其坐标:")
            for i, j in enumerate(avali_players):
                Print.print_inf(f" {i+1} - {j}")
            resp = Utils.try_int(
                input(Print.fmt_info(f"请选择 (1~{len(avali_players)}): "))
            )
            if not resp or resp not in range(1, len(avali_players) + 1):
                Print.print_err("输入错, 已退出")
                return
            player_get = avali_players[resp - 1]
        self.get_x, self.get_y, self.get_z = game_utils.getPosXYZ(player_get)
        Print.print_inf(f"成功获取 {player_get} 的坐标.")

    def read_bdx(self, path: str):
        with open(path, "rb") as f:
            return f.read()

    def dump_bdx_at(self, name: str, content: bytes, x: int, y: int, z: int):
        BDumpOP(self, content, name).dump_bdx(x, y, z, 0)
        Print.print_suc("bdx 导入完成")

    def progress_bar(self, name: str, curr, tota, sped):
        if tota == 0:
            Print.print_war("总进度为0")
            return
        n = round(curr / tota * 30)
        p = "§b" + "|" * n + "§f" + "|" * (30 - n)
        self.game_ctrl.player_actionbar(
            "@a", f"导入 {name} 进度: §l{curr} §7/ {tota} 速度： {sped}方块每秒 §r\n{p}"
        )


class BDumpOP:
    def __init__(self, f: BDX_BDump, content: bytes, name: str):
        self.f = f
        self.gc = f.frame.get_game_control()
        self.scmd = self.gc.sendwocmd
        self._content = content
        self.name = name

    def dump_bdx(self, base_x: int, base_y: int, base_z: int, delay: float = 0.003):
        x = base_x
        y = base_y
        z = base_z
        bot_x = base_x
        bot_y = base_y
        bot_z = base_z
        total_len = self.get_bdx_length_2_show(self._content)
        now_len = 0
        now_t = 0
        block_p = 0
        self.scmd(f"/execute as {self.f.game_ctrl.bot_name} at @s run tp {x} {y} {z}")
        cache_string_pool: list[str] = []

        # wo/execute SkyblueSuper ~~~ fill ~~~~40~15~40 air
        for i in BDX.Parse(self._content):
            time.sleep(delay)
            if isinstance(i, Operation.CreateConstantString):
                # CreateConstantString
                # print(i.constantString)
                cache_string_pool.append(i.constantString)
            # case 5 | 7 | 13:
            elif isinstance(
                i,
                Operation.PlaceBlock
                | Operation.PlaceBlockWithBlockStates
                | Operation.PlaceBlockWithBlockStatesDeprecated,
            ):
                now_len += 1
                if isinstance(i, Operation.PlaceBlockWithBlockStates):
                    if i.blockStatesConstantStringID >= len(cache_string_pool):
                        print(
                            f"state pass {i.blockStatesConstantStringID}>{len(cache_string_pool)}"
                        )
                        continue
                    self.scmd(
                        f"/execute as {self.f.game_ctrl.bot_name} at @s run setblock {x} {y} {z} {cache_string_pool[i.blockConstantStringID]} {cache_string_pool[i.blockStatesConstantStringID]}"
                    )
                elif isinstance(i, Operation.PlaceBlockWithBlockStatesDeprecated):
                    self.scmd(
                        f"/execute as {self.f.game_ctrl.bot_name} at @s run setblock {x} {y} {z} {cache_string_pool[i.blockConstantStringID]} {i.blockStatesString}"
                    )
                else:
                    self.scmd(
                        f"/execute as {self.f.game_ctrl.bot_name} at @s run setblock {x} {y} {z} {cache_string_pool[i.blockConstantStringID]} {i.blockData}"
                    )
            elif isinstance(i, Operation.AddXValue):
                x += 1
            elif isinstance(i, Operation.SubtractXValue):
                x -= 1
            elif isinstance(i, Operation.AddYValue):
                y += 1
            elif isinstance(i, Operation.SubtractYValue):
                y -= 1
            elif isinstance(i, Operation.AddZValue):
                z += 1
            elif isinstance(i, Operation.SubtractZValue):
                z -= 1
            elif isinstance(
                i,
                Operation.AddInt8XValue
                | Operation.AddInt16XValue
                | Operation.AddInt32XValue,
            ):
                x += i.value
            elif isinstance(
                i,
                Operation.AddInt8YValue
                | Operation.AddInt16YValue
                | Operation.AddInt32YValue,
            ):
                y += i.value
            elif isinstance(
                i,
                Operation.AddInt8ZValue
                | Operation.AddInt16ZValue
                | Operation.AddInt32ZValue,
            ):
                z += i.value
            elif isinstance(
                i,
                Operation.PlaceBlockWithCommandBlockData
                | Operation.SetCommandBlockData
                | Operation.PlaceCommandBlockWithCommandBlockData
                | Operation.PlaceRuntimeBlockWithCommandBlockData
                | Operation.PlaceRuntimeBlockWithCommandBlockDataAndUint32RuntimeID,
            ):
                # SetCommandBlockData
                pck = self.f.interact.make_packet_command_block_update(
                    (x, y, z),
                    i.command,
                    i.mode,
                    i.needsRedstone,
                    i.tickDelay,
                    i.conditional,
                    i.customName,
                    i.trackOutput,
                    i.executeOnFirstTick,
                )
                t = 0.1
                if isinstance(i, Operation.SetCommandBlockData):
                    self.gc.sendPacket(78, pck)
                else:
                    now_len += 1
                    if i.mode not in range(0, 3):
                        Print.print_err(
                            json.dumps(i.Dumps(), indent=2, ensure_ascii=False)
                        )
                        raise ValueError(
                            f"Range ERROR: {i.mode} (op:{i.operationNumber})"
                        )
                    if isinstance(i, Operation.PlaceBlockWithCommandBlockData):
                        data = i.blockData
                    elif isinstance(i, Operation.PlaceCommandBlockWithCommandBlockData):
                        data = i.data
                    else:
                        Print.print_err(
                            f"Unknown commandblock op: {i.operationNumber}, pass"
                        )
                    self.f.interact.place_command_block(pck, data, t)
                time.sleep(0.2)
            elif isinstance(i, Operation.PlaceBlockWithNBTData):
                nbtdata = i.blockNBT.unpack()
                # nbt data
                blockID = cache_string_pool[i.blockConstantStringID]
                blockStates = cache_string_pool[i.blockStatesConstantStringID]
                if blockID.endswith("command_block"):
                    pck = self.f.interact.make_packet_command_block_update(
                        (x, y, z),
                        nbtdata["Command"],
                        nbtdata["LPCommandMode"],
                        bool(nbtdata["LPRedstoneMode"]),
                        nbtdata["TickDelay"],
                        bool(nbtdata["LPCondionalMode"]),
                        nbtdata["CustomName"],
                        bool(nbtdata["TrackOutput"]),
                        bool(nbtdata["ExecuteOnFirstTick"]),
                    )
                    self.scmd(f"tp {x} {y} {z}")
                    self.f.game_ctrl.sendcmd_with_resp(
                        f"/execute as {self.f.game_ctrl.bot_name} at @s run setblock {x} {y} {z} {blockID} {blockStates}"
                    )
                    self.f.game_ctrl.sendPacket(78, pck)
                print(nbtdata["Command"])
            else:
                Print.print_war(f"Ignoring OP: {i.operationNumber}")
                Print.print_war(json.dumps(i.Dumps(), indent=4, ensure_ascii=False))

            if abs(x - bot_x) + abs(y - bot_y) + abs(z - bot_z) > 5:
                self.scmd(f"tp @a[name={self.gc.bot_name}] {x} {y} {z}")
                self.scmd(f"clear {self.gc.bot_name}")
                bot_x = x
                bot_y = y
                bot_z = z
                time.sleep(0.005)

            if time.time() - now_t > 1:
                now_t = time.time()
                bspeed = now_len - block_p
                block_p = now_len
                self.f.progress_bar(self.name, now_len, total_len, bspeed)
        # ok
        self.f.game_ctrl.player_actionbar("@a", f"§fBDX文件 {self.name} 导入完成.")

    def get_bdx_length_2_show(self, content: bytes):
        # not archieved
        count = 0
        t = time.time()
        for i in BDX.Parse(content):
            # is setting block op
            if isinstance(
                i,
                Operation.PlaceBlock
                | Operation.PlaceBlockWithBlockStates
                | Operation.PlaceBlockWithCommandBlockData
                | Operation.PlaceBlockWithBlockStatesDeprecated
                | Operation.PlaceCommandBlockWithCommandBlockData
                | Operation.PlaceRuntimeBlockWithCommandBlockData
                | Operation.PlaceRuntimeBlockWithCommandBlockDataAndUint32RuntimeID,
            ):
                count += 1
            del i
            if time.time() - t > 0.5:
                self.gc.player_actionbar(
                    "@a", f"§f正在计算 {self.name} 的方块总数 ({count})"
                )
                t = time.time()
        return count

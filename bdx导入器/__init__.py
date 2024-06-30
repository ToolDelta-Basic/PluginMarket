from tooldelta import Plugin, Print, Utils, plugins, TYPE_CHECKING, game_utils
import os, time
from .BDXConverter.Converter.Converter import BDX_2
from .BDXConverter import ReadBDXFile

import re

@plugins.add_plugin
class BDX_BDump(Plugin):
    name = "BDX-BDump导入器"
    author = "xingchen/SuperScript"
    version = (0, 0, 3)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()

    def on_def(self):
        self.interact = plugins.get_plugin_api("前置-世界交互")
        if TYPE_CHECKING:
            from 前置_世界交互 import GameInteractive
            self.interact = plugins.instant_plugin_api(GameInteractive)
        Print.print_inf("§bBDX加载器 使用了来自 \"github.com/TriM-Organization/BDXConverter\" 的开源库")
        Print.print_inf("§b其第一作者为 Eternal Crystal (Happy2018New) (其他协作者请在项目内查看)")

    def on_inject(self):
        self.get_x: float | None = None
        self.get_y: float | None = None
        self.get_z: float | None = None
        self.frame.add_console_cmd_trigger(["bdump", "导入bdx"], None, "导入bdx文件", self.dump_bdx_menu)
        self.frame.add_console_cmd_trigger(["bdx-get", "坐标bdx"], None, "获取bdx文件导入坐标", self.get_bdx_pos_menu)

    def dump_bdx_menu(self, _):
        src_path = self.data_path
        if not all((self.get_x, self.get_y, self.get_z)):
            Print.print_err("未设置导入坐标 (控制台输入 bdx-get 以设置)")
            return
        Print.print_inf(f"文件搜索路径: {src_path}")
        fs = list(filter(lambda x:x.endswith(".bdx"), os.listdir(src_path)))
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
            bdx_inf = self.read_bdx(os.path.join(self.data_path, bdx_file))
        except Exception as err:
            Print.print_err(f"读取 {bdx_file} 出现问题: {err}")
            return
        bdx_name = bdx_file[:-4]
        Print.print_inf(f"{bdx_name} 的导入已经开始 (进度条显示于游戏内)")
        Utils.createThread(self.dump_bdx_at, (bdx_name, bdx_inf, int(self.get_x), int(self.get_y), int(self.get_z))) # type: ignore

    def get_bdx_pos_menu(self, _):
        avali_players = self.game_ctrl.allplayers
        Print.print_inf("请选择玩家以获取其坐标:")
        for i, j in enumerate(avali_players):
            Print.print_inf(f" {i+1} - {j}")
        resp = Utils.try_int(input(Print.fmt_info(f"请选择 (1~{len(avali_players)}): ")))
        if not resp or resp not in range(1, len(avali_players) + 1):
            Print.print_err("输入错, 已退出")
            return
        player_get = avali_players[resp - 1]
        self.get_x, self.get_y, self.get_z = game_utils.getPosXYZ(player_get)
        Print.print_inf(f"成功获取 {player_get} 的坐标.")

    def read_bdx(self, path: str):
        return ReadBDXFile(path, BDX_2)

    def dump_bdx_at(self, name: str, bdx: BDX_2, x: int, y: int, z: int):
        BDumpOP(self, bdx, name).dump_bdx(x, y, z, 0)
        Print.print_suc("bdx 导入完成")

    def progress_bar(self, name: str, curr, tota, sped):
        if tota == 0:
            Print.print_war("总进度为0")
            return
        n = round(curr / tota * 30)
        p = "§b" + "|" * n + "§f" + "|" * (30 - n)
        self.game_ctrl.player_actionbar("@a", f"导入 {name} 进度: §l{curr} §7/ {tota} 速度： {sped}方块每秒 §r\n{p}")

class BDumpOP:
    def __init__(self, f: BDX_BDump, bdx: BDX_2, name: str):
        self.f = f
        self.gc = f.frame.get_game_control()
        self.scmd = self.gc.sendwocmd
        self.cache_string_pool: list[str] = []
        self._bdx = bdx
        self.name = name

    def dump_bdx(self, base_x: int, base_y: int, base_z: int, delay: float = 0):
        x = base_x
        y = base_y
        z = base_z
        bot_x = base_x
        bot_y = base_y
        bot_z = base_z
        total_len = self.get_bdx_length_2_show()
        now_len = 0
        now_t = 0
        block_p = 0
        self.scmd(f"/tp {self.f.game_ctrl.bot_name} {x} {y} {z}")

        # wo/execute SkyblueSuper ~~~ fill ~~~~40~15~40 air
        get_data_only = True
        use_scoreboards = set()
        use_tag = set()
        syn = re.compile(r"scoreboard (?:objectives|players) (?:add|remove|reset|set|test) (?:[^ ]*) ([^ ]*) [0-9]")
        syn2 = re.compile(r"scores={([^ {}=]*)=[0-9]*}")

        for i in self._bdx.BDXContents:
            time.sleep(delay)
            match i.operationNumber:
                case 1:
                    # CreateConstantString
                    self.cache_string_pool.append(i.constantString)
                case 5 | 7 | 13:
                    # 13 not achieved
                    now_len += 1
                    if not get_data_only:
                        self.scmd(f"setblock {x} {y} {z} {self.cache_string_pool[i.blockConstantStringID]} {i.blockData}")
                case 14:
                    x += 1
                case 15:
                    x -= 1
                case 16:
                    y += 1
                case 17:
                    y -= 1
                case 18:
                    z += 1
                case 19:
                    z -= 1
                case 20 | 21 | 28:
                    x += i.value
                case 22 | 23 | 29:
                    y += i.value
                case 24 | 25 | 30:
                    z += i.value
                case 26 | 36 | 27:
                    # SetCommandBlockData
                    now_len += 1
                    pck = self.f.interact.make_packet_command_block_update(
                        (x, y, z),
                        i.command,
                        i.mode,
                        i.needsRedstone,
                        i.tickDelay,
                        i.conditional,
                        i.customName,
                        i.trackOutput,
                        i.executeOnFirstTick
                    )
                    t = 0.2
                    if get_data_only:
                        cmd = i.command
                        if "score" in cmd:
                            for i in syn.findall(cmd) + syn2.findall(cmd):
                                use_scoreboards.add(i)
                    elif hasattr(i, "blockData"):
                        self.f.interact.place_command_block(pck, i.blockData, t)
                    else:
                        self.f.interact.place_command_block(pck, i.data, t)
                case 41:
                    nbt_data = i.blockNBT
                    Print.print_war(f"BDX导入器: 忽略NBT {nbt_data}")

            if abs(x - bot_x) + abs(y - bot_y) + abs(z - bot_z) > 5:
                self.scmd(f"/tp @a[name={self.gc.bot_name}] {x} {y} {z}")
                bot_x = x
                bot_y = y
                bot_z = z

            if time.time() - now_t > 1:
                now_t = time.time()
                bspeed = now_len - block_p
                block_p = now_len
                self.f.progress_bar(self.name, now_len, total_len, bspeed)
        # ok
        self.f.game_ctrl.player_actionbar("@a", f"§fBDX文件 {self.name} 导入完成.")
        Print.clean_print("§a使用计分板:")
        for i in use_scoreboards:
            Print.clean_print(f"§b - {i}")

    def get_bdx_length_2_show(self):
        # not archieved
        count = 0
        t = time.time()
        for i in self._bdx.BDXContents:
            if i.operationNumber in (5, 7, 13, 26, 36, 27):
                count += 1
            del i
            if time.time() - t > 0.5:
                self.gc.player_actionbar("@a", f"§f正在计算 {self.name} 的方块总数 ({count})")
                t = time.time()
        return count
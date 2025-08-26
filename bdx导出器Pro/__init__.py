from tooldelta import Plugin, game_utils, utils, fmts, TYPE_CHECKING, plugin_entry
from tooldelta.constants import PacketIDS
from . import lib
from .scanner import export_to_structures

POS = tuple[int, int, int]

def get_input_pos():
    resp = input(fmts.fmt_info("请输入坐标(如 0 0 0): "))
    try:
        x, y, z = map(int, resp.split())
        return x, y, z
    except ValueError:
        fmts.print_err("输入错误")
        return None


def get_op_pos(allplayers: list[str]):
    fmts.print_inf("选择一个玩家以获取他的坐标: ")
    for i, player in enumerate(allplayers):
        fmts.print_inf(f"{i + 1}. {player}")
    resp = input(fmts.fmt_info("请输入序号, 若想输入坐标值请直接按回车键: "))
    if resp == "":
        return get_input_pos()
    else:
        try:
            x, y, z = map(int, game_utils.getPosXYZ(allplayers[int(resp) - 1]))
            return x, y, z
        except (ValueError, TypeError):
            fmts.print_err("输入错误")
            return None


class BDXExporter(Plugin):
    name = "bdx导出器Pro"
    author = "SuperScript"
    version = (0, 0, 4)

    def __init__(self, frame):
        super().__init__(frame)
        self.start: POS | None = None
        self.end: POS | None = None
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPacket(PacketIDS.Text, self.ignore_text_10)

    def on_def(self):
        self.intr = self.GetPluginAPI("前置-世界交互", (1, 0, 0))
        if TYPE_CHECKING:
            global Structure, Block
            from 前置_世界交互 import GameInteractive, Structure, Block

            self.intr: GameInteractive

    def ignore_text_10(self, pk):
        if pk["TextType"] == 10:
            return True
        return False

    def on_inject(self):
        self.frame.add_console_cmd_trigger(["export"], None, "导出 bdx", self.on_export)

    def on_export(self, args: list[str]):
        # export set 388 28 102
        # export setend 626 283 -27
        # export test1.bdx

        # export set 1 -5 1
        # export setend 40 283 40
        # export test1.bdx

        if args:
            if args[0] == "set":
                if len(args) == 4:
                    try:
                        x, y, z = tuple(int(i) for i in args[1:])
                        self.start = (x, y, z)
                        fmts.print_suc(f"已获取起点 x={x} y={y} z={z}")
                        return
                    except Exception:
                        pass
                pos_get = get_op_pos(self.game_ctrl.allplayers)
                if pos_get is None:
                    return
                self.start = pos_get
                fmts.print_suc(f"已获取起点: {pos_get}")
            elif args[0] == "setend":
                if len(args) == 4:
                    try:
                        x, y, z = tuple(int(i) for i in args[1:])
                        self.end = (x, y, z)
                        fmts.print_suc(f"已获取终点 x={x} y={y} z={z}")
                        return
                    except Exception:
                        pass
                pos_get = get_op_pos(self.game_ctrl.allplayers)
                if pos_get is None:
                    return
                self.end = pos_get
                fmts.print_suc(f"已获取终点: {pos_get}")
            elif args[0].endswith(".bdx"):
                if self.start is None or self.end is None:
                    fmts.print_err("请先设置起点和终点")
                    return
                self.export(self.start, self.end, args[0])
            else:
                fmts.print_inf("§eBDX 导出器帮助:")
                fmts.print_inf(" - export set §7设置起点")
                fmts.print_inf(" - export setend §7设置终点")
                fmts.print_inf(" - export §7导出为 bdx")
        else:
            if self.start is None or self.end is None:
                fmts.print_err("请先设置起点和终点")
                return
            name = (
                input(fmts.fmt_info("请输入导出的文件名: ")).removesuffix(".bdx")
                + ".bdx"
            )
            self.export(self.start, self.end, name)

    @utils.thread_func("bdx导出线程")
    def export(self, start: POS, end: POS, fname: str):
        try:
            open(self.format_data_path(fname), "wb").close()
        except Exception:
            fmts.print_err("文件名错误")
            return
        with lib.LockGetterAndReleaser() as can_lock:
            if not can_lock:
                fmts.print_err("无法同时运行多个导出任务")
                return
            export_to_structures(self, *start, *end)
            fmts.print_inf("")
            fmts.print_inf("正在解析为 bdx ..")
            lib.StructuresToBDX()
            fmts.print_inf(f"正在导出到文件 {fname} .. ")
            with open(self.format_data_path(fname), "wb") as fp:
                lib.DumpBDX(fp.name)
            fmts.print_suc(f"导出成功: {self.format_data_path(fname)}")
            lib.ReleaseLock()


entry = plugin_entry(BDXExporter)

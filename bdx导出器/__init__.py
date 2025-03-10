from .BDXConverter import ReadBDXFile, VisualStructs
from .BDXConverter.Converter.FileOperation import DumpStructs
from .scanner import POS, export_to_structures, structures_to_bdx
from tooldelta import Plugin, game_utils, Print, TYPE_CHECKING, plugin_entry


def get_input_pos():
    resp = input(Print.fmt_info("请输入坐标(如 0 0 0): "))
    try:
        x, y, z = map(int, resp.split())
        return x, y, z
    except ValueError:
        Print.print_err("输入错误")
        return None


def get_op_pos(allplayers: list[str]):
    Print.print_inf("选择一个玩家以获取他的坐标: ")
    for i, player in enumerate(allplayers):
        Print.print_inf(f"{i + 1}. {player}")
    resp = input(Print.fmt_info("请输入序号, 若想输入坐标值请直接按回车键: "))
    if resp == "":
        return get_input_pos()
    else:
        try:
            x, y, z = map(int, game_utils.getPosXYZ(allplayers[int(resp) - 1]))
            return x, y, z
        except (ValueError, TypeError):
            Print.print_err("输入错误")
            return None


class BDXExporter(Plugin):
    name = "bdx导出器"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.start: POS | None = None
        self.end: POS | None = None
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        self.intr = self.GetPluginAPI("前置-世界交互")
        if TYPE_CHECKING:
            global Structure, Block
            from 前置_世界交互 import GameInteractive, Structure, Block

            self.intr = self.get_typecheck_plugin_api(GameInteractive)

    def on_inject(self):
        self.frame.add_console_cmd_trigger(["export"], None, "导出 bdx", self.on_export)
        self.frame.add_console_cmd_trigger(
            ["visual"], None, "转换 bdx 为可视化 json", self.on_visual
        )

    # def on_player_message(self, player: str, msg: str):
    #     if player != "SkyblueSuper":
    #         return
    #     if msg == "e1":
    #         x, y, z = map(int, game_utils.getPosXYZ("SkyblueSuper"))
    #         self.start = (x, y, z)
    #         self.game_ctrl.say_to(player, "OK")
    #     elif msg == "e2":
    #         x, y, z = map(int, game_utils.getPosXYZ("SkyblueSuper"))
    #         self.end = (x, y, z)
    #         self.game_ctrl.say_to(player, "OK")
    def on_visual(self, args: list[str]):
        if len(args) != 1:
            Print.print_err("参数错误")
            return
        fname = args[0] + ".bdx"
        try:
            fp = self.format_data_path(fname)
            bdx = ReadBDXFile(fp)
        except FileNotFoundError:
            Print.print_err("文件不存在")
            return
        fp = self.format_data_path(fname.replace(".bdx", ".json"))
        VisualStructs(bdx, fp)
        Print.print_suc(f"已导出可视化 json: {fp}")

    def on_export(self, args: list[str]):
        if args:
            if args[0] == "set":
                pos_get = get_op_pos(self.game_ctrl.allplayers)
                if pos_get is None:
                    return
                self.start = pos_get
                Print.print_suc(f"已获取起点: {pos_get}")
            elif args[0] == "setend":
                pos_get = get_op_pos(self.game_ctrl.allplayers)
                if pos_get is None:
                    return
                self.end = pos_get
                Print.print_suc(f"已获取终点: {pos_get}")
            elif args[0].endswith(".bdx"):
                if self.start is None or self.end is None:
                    Print.print_err("请先设置起点和终点")
                    return
                self.export(self.start, self.end, args[0])
            else:
                Print.print_inf("§eBDX 导出器帮助:")
                Print.print_inf(" - export set §7设置起点")
                Print.print_inf(" - export setend §7设置终点")
                Print.print_inf(" - export §7导出为 bdx")
        else:
            if self.start is None or self.end is None:
                Print.print_err("请先设置起点和终点")
                return
            name = (
                input(Print.fmt_info("请输入导出的文件名: ")).removesuffix(".bdx")
                + ".bdx"
            )
            self.export(self.start, self.end, name)

    def export(self, start: POS, end: POS, fname: str):
        try:
            open(self.format_data_path(fname), "wb").close()
        except Exception:
            Print.print_err("文件名错误")
            return
        structures = export_to_structures(self, *start, *end)
        bdx = structures_to_bdx(structures)
        Print.print_inf("")
        Print.print_inf(f"正在导出到文件 {fname} .. ")
        DumpStructs(bdx, self.format_data_path(fname))
        Print.print_suc(f"导出成功: {self.format_data_path(fname)}")


entry = plugin_entry(BDXExporter)

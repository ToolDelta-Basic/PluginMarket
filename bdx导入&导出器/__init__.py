from .bdx_utils.construct_file import write_bdx_file
from .scanner import POS, export_to_structures, structures_to_bdx
from .importer import import_bdx_file
from tooldelta import Plugin, game_utils, utils, fmts, TYPE_CHECKING, plugin_entry
from tooldelta.constants import PacketIDS


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
    name = "bdx导出器"
    author = "SuperScript/帥気的男主角"
    version = (0, 0, 2)

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
        # 如果export命令正常工作，那么两个命令都应该使用add_console_cmd_trigger
        self.frame.add_console_cmd_trigger(["export"], None, "导出 bdx", self.on_export)
        self.frame.add_console_cmd_trigger(["import"], None, "导入 bdx", self.on_import)
    def on_export(self, args: list[str]):
        # export set 388 28 102
        # export setend 626 283 -27
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
                fmts.print_inf(" - export 文件名.bdx §7导出为 bdx")
                fmts.print_inf(" - import 文件名.bdx §7导入 bdx 文件")
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
        structures = export_to_structures(self, *start, *end)
        bdx_content = structures_to_bdx(structures)
        fmts.print_inf("")
        fmts.print_inf(f"正在导出到文件 {fname} .. ")
        with open(self.format_data_path(fname), "wb") as fp:
            write_bdx_file(fp, "ToolDelta BDX Exporter", bdx_content)
        fmts.print_suc(f"导出成功: {self.format_data_path(fname)}")

    def on_import(self, args: list[str]):
        # import file.bdx
        # import file.bdx 100 64 100
        if args:
            if args[0].endswith(".bdx"):
                # 指定位置导入
                if len(args) == 4:
                    try:
                        import_x, import_y, import_z = tuple(int(i) for i in args[1:])
                        self.import_bdx(args[0], (import_x, import_y, import_z))
                        return
                    except Exception:
                        fmts.print_err("输入坐标格式错误")
                        pass
                
                # 让用户选择位置
                pos_get = get_op_pos(self.game_ctrl.allplayers)
                if pos_get is None:
                    return
                self.import_bdx(args[0], pos_get)
            else:
                self.show_import_help()
        else:
            self.show_import_help()
    
    def show_import_help(self):
        fmts.print_inf("§eBDX 导入器帮助:")
        fmts.print_inf(" - import 文件名.bdx §7导入指定的bdx文件，将询问导入位置")
        fmts.print_inf(" - import 文件名.bdx x y z §7导入指定的bdx文件到指定坐标位置")
    
    @utils.thread_func("bdx导入线程")
    def import_bdx(self, filename: str, position: POS):
        """导入BDX文件到指定位置"""
        filepath = self.format_data_path(filename)
        import_bdx_file(self, filepath, position)


entry = plugin_entry(BDXExporter)

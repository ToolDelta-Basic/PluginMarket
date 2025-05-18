import os
from tooldelta import Plugin, fmts, utils, TYPE_CHECKING, plugin_entry
from . import lib, bdx_operation
from .thisutils import render_bar


class BDX_BDump(Plugin):
    name = "bdx导入器Pro"
    author = "SuperScript"
    version = (0, 1, 0)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        lib.Init()
        self.interact = self.GetPluginAPI("前置-世界交互")
        if TYPE_CHECKING:
            from 前置_世界交互 import GameInteractive

            self.interact = self.get_typecheck_plugin_api(GameInteractive)

    def on_inject(self):
        self.get_x: float | None = None
        self.get_y: float | None = None
        self.get_z: float | None = None
        self.frame.add_console_cmd_trigger(
            ["bdump", "导入bdx"], None, "导入bdx文件", self.dump_bdx_menu
        )
        self.frame.add_console_cmd_trigger(
            ["bdxget", "坐标bdx"], None, "获取bdx文件导入坐标", self.get_bdx_pos_menu
        )

    def dump_bdx_menu(self, _):
        src_path = self.data_path
        if not self.get_x or not self.get_y or not self.get_z:
            fmts.print_err("未设置导入坐标 (控制台输入 bdx-get 以设置)")
            return
        fmts.print_inf(f"文件搜索路径: {src_path}")
        fs = list(filter(lambda x: x.endswith(".bdx"), os.listdir(src_path)))
        if fs == []:
            fmts.print_war("该文件夹内没有任何 bdx 文件, 无法导入")
            return
        fmts.print_inf("请选择导入的 bdx 文件:")
        for i, j in enumerate(fs):
            fmts.print_inf(f" {i + 1} - {j}")
        resp = utils.try_int(input(fmts.fmt_info(f"请选择 (1~{len(fs)}): ")))
        if not resp or resp not in range(1, len(fs) + 1):
            fmts.print_err("输入错, 已退出")
            return
        bdx_file = fs[resp - 1]
        path = str(self.data_path / bdx_file)
        self.dump_bdx_at(path, int(self.get_x), int(self.get_y), int(self.get_z))

    def get_bdx_pos_menu(self, _):
        avali_players = list(self.game_ctrl.players)
        # OP
        if len(avali_players) == 1:
            player_get = avali_players[0]
        else:
            fmts.print_inf("请选择玩家以获取其坐标:")
            for i, j in enumerate(avali_players):
                fmts.print_inf(f" {i + 1} - {j.name}")
            resp = utils.try_int(
                input(fmts.fmt_info(f"请选择 (1~{len(avali_players)}): "))
            )
            if not resp or resp not in range(1, len(avali_players) + 1):
                fmts.print_err("输入错, 已退出")
                return
            player_get = avali_players[resp - 1]
        _, self.get_x, self.get_y, self.get_z = player_get.getPos()
        fmts.print_inf(
            f"成功获取 {player_get.name} 的坐标: {self.get_x, self.get_y, self.get_z}"
        )

    @utils.thread_func("dump_bdx_at")
    def dump_bdx_at(self, path: str, x: int, y: int, z: int):
        self.print("正在解析 bdx 文件..")
        try:
            lib.LoadBDX(path)
        except RuntimeError as err:
            fmts.print_err(f"加载 BDX 出错: {err}")
            return
        self.print("解析 bdx 文件完成")
        filename = os.path.basename(path).removesuffix(".bdx")
        total_blocks = lib.BDXBlocks()
        last_progress = 0

        def progress_bar(progress: int):
            nonlocal last_progress
            if total_blocks == 0:
                fmts.print_war("总进度为0")
                return
            # n = round(progress / total_blocks * 60)
            # p = "§b" + "|" * n + "§f" + "|" * (60 - n)
            # self.game_ctrl.player_actionbar(
            #     "@a",
            #     f"导入 {filename} 进度: §l{progress} §7/ {total_blocks} 速度： {progress - last_progress} 方块每秒 §r\n{p}",
            # )
            bar = render_bar(progress, total_blocks, "§b", "§7")
            self.game_ctrl.player_actionbar(
                "@a",
                f"导入 {filename} 进度: §l{progress} §7/ {total_blocks} 速度： {progress - last_progress} 方块每秒 §r\n{bar}",
            )
            last_progress = progress

        bdx_operation.do_operations(self, (x, y, z), progress_bar, 1.00)
        self.game_ctrl.player_actionbar("@a", f"导入 {filename} 完成")
        fmts.print_suc("bdx 导入完成")


entry = plugin_entry(BDX_BDump)

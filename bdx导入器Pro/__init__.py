import os
import time
from tooldelta import Plugin, cfg, fmts, utils, TYPE_CHECKING, plugin_entry
from . import bdx_operation
from .thisutils import render_bar


class BDX_BDump(Plugin):
    name = "bdx导入器Pro"
    author = "SuperScript"
    version = (0, 1, 1)

    def __init__(self, frame):
        super().__init__(frame)
        CFG_DEFAULT = {
            "最大导入速度(方块/秒)": 1000.0,
            "自定义导入actionbar提示": "§7导入 §b[文件名] §7进度： §d[当前进度]/§7[总进度] §a[速度]方块/秒 §7预计完成时间：§e[预计完成时间]§r\n[进度条]",
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, self.version
        )
        self.make_data_path()
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        global lib
        self.interact = self.GetPluginAPI("前置-世界交互")
        pip = self.GetPluginAPI("pip")
        if TYPE_CHECKING:
            from 前置_世界交互 import GameInteractive
            from pip模块支持 import PipSupport

            self.interact: GameInteractive
            pip: PipSupport
        pip.require("msgpack")
        from . import lib
        lib.Init()

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
        predict_time_rest = 0
        start_time = time.time()
        actionbar_format = self.cfg["自定义导入actionbar提示"]

        def progress_bar(progress: int):
            nonlocal last_progress, predict_time_rest, start_time
            if progress > last_progress:
                averange_speed = progress / (time.time() - start_time)
                predict_time_rest = (total_blocks - progress) / averange_speed
            if total_blocks == 0:
                fmts.print_war("总进度为0")
                return
            speed_delta = progress - last_progress
            bar = render_bar(progress, total_blocks, "§b", "§7", 180)
            self.game_ctrl.player_actionbar(
                "@a",
                utils.simple_fmt(
                    {
                        "[文件名]": filename,
                        "[当前进度]": progress,
                        "[总进度]": total_blocks,
                        "[进度条]": bar,
                        "[速度]": speed_delta,
                        "[预计完成时间]": self.format_time(int(predict_time_rest)),
                    },
                    actionbar_format,
                ),
            )
            last_progress = progress

        bdx_operation.do_operations(self, (x, y, z), progress_bar, 1.00)
        self.game_ctrl.player_actionbar("@a", f"导入 {filename} 完成")
        fmts.print_suc("bdx 导入完成")

    @staticmethod
    def format_time(seconds: int):
        day = seconds // 86400
        hour = seconds % 86400 // 3600
        minute = seconds % 3600 // 60
        second = seconds % 60
        output = ""
        if day > 0:
            output += f"{day}天 "
        if hour > 0:
            output += f"{hour}小时 "
        if minute > 0:
            output += f"{minute}分钟 "
        output += f"{second}秒"
        return output


entry = plugin_entry(BDX_BDump)

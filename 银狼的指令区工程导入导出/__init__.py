import os
from tooldelta import Plugin, TYPE_CHECKING, fmts, utils, game_utils, plugin_entry

from . import file, dumper, loader


class SilverwolfLoadAndExport(Plugin):
    name = "[SilverWolf] 指令区工程导出"
    author = "SuperScript"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        self.print("§bSilverWolf Command Loader And Exporter")
        self.print("§bSilverWolf CommandArea Loader And Exporter")
        self.print("§b指令区工程导入 / 导出程序 @ SuperScript")
        self.print("§b控制台输入 cbdump / cbload 进行指令区工程导入导出")
        self.intr = self.GetPluginAPI("前置-世界交互")
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        if TYPE_CHECKING:
            global Structure, Block
            from 前置_世界交互 import GameInteractive, Structure, Block
            from 前置_聊天栏菜单 import ChatbarMenu

            self.intr = self.get_typecheck_plugin_api(GameInteractive)
            self.chatbar = self.get_typecheck_plugin_api(ChatbarMenu)

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["cbdump"], None, "导出指令区为工程文件夹", self.on_dump
        )
        self.frame.add_console_cmd_trigger(
            ["cbload"], None, "导入指令区为工程文件夹", self.on_load
        )

    def visual_chains_to(
        self,
        chains: dict[tuple[int, int, int], list[file.CommandBlock]],
        player: str,
    ):
        for start_point, chain in chains.items():
            self.game_ctrl.say_to(player, f"§eStart point: {start_point}")
            for i, cb in enumerate(chain):
                if cb.command == "tool:cutoff":
                    self.game_ctrl.say_to(player, f"  §c{i}: 断链")
                else:
                    color = ("§6", "§d", "§a")[cb.type]
                    self.game_ctrl.say_to(player, f"  {color}{i}: {cb.command}")

    def on_test(self, player: str, _):
        x, y, z = (int(i) for i in game_utils.getPosXYZ(player))
        stu = self.intr.get_structure((x, y, z), (20, 20, 20))
        matrix = dumper.to_matrix(stu)
        try:
            res = dumper.scan_all(stu, matrix)
            self.visual_chains_to(res, player)
        except Exception as err:
            self.game_ctrl.say_to(player, "§c" + str(err))
            print(err)

    def on_dump(self, _):
        try:
            resp = input(fmts.fmt_info("请输入起点坐标(如 149 1 143): ")).split() or (
                149,
                1,
                143,
            )
            startx, starty, startz = (int(i) for i in resp)
        except Exception:
            fmts.print_err("无效输入..")
            return
        try:
            resp = input(fmts.fmt_info("请输入终点坐标(如 100 81 128): ")).split() or (
                111,
                81,
                128,
            )
            endx, endy, endz = (int(i) for i in resp)
        except Exception:
            fmts.print_err("无效输入..")
            return
        x, endx = min(startx, endx), max(startx, endx)
        y, endy = min(starty, endy), max(starty, endy)
        z, endz = min(startz, endz), max(startz, endz)
        sizex = endx - x + 1
        sizey = endy - y + 1
        sizez = endz - z + 1
        if sizex > 64 or sizez > 64:
            fmts.print_err("xz范围最多只能为 64 x 64")
            return
        fmts.print_inf("正在扫描区域..")
        try:
            structure = self.intr.get_structure((x, y, z), (sizex, sizey, sizez))
        except Exception as err:
            fmts.print_err(f"获取世界结构出错, 请检查坐标合法性: {err}")
            return
        fmts.print_inf("正在解析..")
        matrix = dumper.to_matrix(structure)
        try:
            res = dumper.scan_all(structure, matrix)
        except dumper.ScanError as err:
            scanx, scany, scanz = err.pos
            actua_x, actua_y, actua_z = x + scanx, y + scany, z + scanz
            fmts.print_err(f"扫描 {actua_x}, {actua_y}, {actua_z} 时出错: {err.exc}")
            return
        except Exception as err:
            fmts.print_err(f"出现严重错误: {err}")
            import traceback

            self.print(traceback.format_exc())
            return
        os.makedirs(self.format_data_path(f"指令区 {x}, {y}, {z}"), exist_ok=True)
        if res == {}:
            fmts.print_err("未发现任何命令方块")
            return
        for start_point, chain in res.items():
            x1, y1, z1 = start_point
            fmts.print_inf(f"正在写入起始点位于 {x}, {y}, {z} 的命令链..", end="\r")
            with open(
                self.format_data_path(
                    f"指令区 {x}, {y}, {z}", f"{x1}, {y1}, {z1}.mcfunction"
                ),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(file.MCFProjectFile(chain).dump())
        fmts.print_suc("指令区工程写入完成")
        fmts.print_suc(f"工程文件夹在 {self.format_data_path(f'指令区 {x}, {y}, {z}')}")

    def on_load(self, _):
        project_dirs = [i for i in self.data_path.iterdir() if i.is_dir()]
        if not project_dirs:
            fmts.print_err(f"在 {self.data_path} 没有找到任何工程文件夹..")
            return
        fmts.print_inf("请选择一个工程文件夹进行导入:")
        for i, fdir in enumerate(project_dirs):
            fmts.print_inf(f"  {i + 1}. {fdir.name}")
        resp = input(fmts.fmt_info("请输入序号: "))
        if (section := utils.try_int(resp)) is None or section not in range(
            1, len(project_dirs) + 1
        ):
            fmts.print_err("无效输入..")
            return
        selected_dir = project_dirs[section - 1]
        try:
            resp = input(fmts.fmt_info("请输入导入起点坐标(如 200 0 100): ")).split() or (
                200,
                0,
                100,
            )
            startx, starty, startz = (int(i) for i in resp)
        except Exception:
            fmts.print_err("无效输入..")
            return
        for mcf_file in selected_dir.iterdir():
            if mcf_file.is_file() and mcf_file.suffix == ".mcfunction":
                try:
                    rx, ry, rz = (int(i) for i in mcf_file.stem.split(","))
                except Exception:
                    fmts.print_err(f"文件 {mcf_file.name} 的坐标无效..")
                    return
                try:
                    f = file.MCFProjectFile.load(mcf_file.read_text("utf-8"))
                except Exception as err:
                    fmts.print_err(f"文件 {mcf_file.name} 解析出现问题: {err}")
                    return
            self.print(f"正在导入链 {mcf_file.name}")
            loader.load_from_file(self, f, startx + rx, starty + ry, startz + rz)
        self.print("工程导入完成")


# {
#   "Command": "demo",
#   "CustomName": "",
#   "ExecuteOnFirstTick": 0,
#   "LPCommandMode": 0,
#   "LPCondionalMode": 0,
#   "LPRedstoneMode": 0,
#   "LastExecution": 0,
#   "LastOutput": "commands.generic.syntax",
#   "LastOutputParams": [
#     "",
#     "demo",
#     ""
#   ],
#   "SuccessCount": 0,
#   "TickDelay": 0,
#   "TrackOutput": 1,
#   "Version": 36,
#   "auto": 0,
#   "conditionMet": 0,
#   "conditionalMode": 1,
#   "id": "CommandBlock",
#   "isMovable": 1,
#   "powered": 0,
#   "x": 189,
#   "y": -60,
#   "z": -15
# }
entry = plugin_entry(SilverwolfLoadAndExport)

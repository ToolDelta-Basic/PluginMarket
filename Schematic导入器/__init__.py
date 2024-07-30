import time, os
from tooldelta import Plugin, plugins, Print, Utils, game_utils
from nbtschematic import SchematicFile
from .schematic_id import schema_id


@plugins.add_plugin
class SchematicImport(Plugin):
    name = "Schematic导入器"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()

    def on_inject(self):
        self.get_x: float | None = None
        self.get_y: float | None = None
        self.get_z: float | None = None
        self.frame.add_console_cmd_trigger(
            ["schematic"], None, "导入schematic文件", self.dump_schema_menu
        )
        self.frame.add_console_cmd_trigger(
            ["schem-get"], None, "设置schematic导入坐标", self.get_schema_pos_menu
        )

    def dump_schema_menu(self, _):
        src_path = self.data_path
        if not self.get_x or not self.get_y or not self.get_z:
            Print.print_err("未设置导入坐标 (控制台输入 schem-get 以设置)")
            return
        Print.print_inf(f"文件搜索路径: {src_path}")
        fs = list(filter(lambda x: x.endswith(".schematic"), os.listdir(src_path)))
        if fs == []:
            Print.print_war("该文件夹内没有任何 schematic 文件, 无法导入")
            return
        Print.print_inf("请选择导入的 schema 文件:")
        for i, j in enumerate(fs):
            Print.print_inf(f" {i+1} - {j}")
        resp = Utils.try_int(input(Print.fmt_info(f"请选择 (1~{len(fs)}): ")))
        if not resp or resp not in range(1, len(fs) + 1):
            Print.print_err("输入错, 已退出")
            return
        schema_file = fs[resp - 1]
        try:
            schema_inf = SchematicFile.load(os.path.join(self.data_path, schema_file))
            if schema_inf.root.get("Blocks") is None:
                raise ValueError("无法正常读取文件, 请确保这是Schematic文件而不是一个Schem文件")
        except Exception as err:
            Print.print_err(f"读取 {schema_file} 出现问题: {err}")
            return
        schema_name = schema_file[:-10]
        Print.print_inf(f"{schema_name} 的导入已经开始 (进度条显示于游戏内)")
        Utils.createThread(
            self.import_at,
            (schema_name, schema_inf, int(self.get_x), int(self.get_y), int(self.get_z))
        )

    def get_schema_pos_menu(self, _):
        avali_players = self.game_ctrl.allplayers
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

    def import_at(self, name: str, schema: SchematicFile, x: int, y: int, z: int):
        # schem-get
        # schematic
        size_x, size_y, size_z = schema.shape
        blocks       = schema.blocks
        block_datas  = schema.data
        size_total   = size_x * size_y * size_z
        timer        = 0
        prog_now     = 0
        prog_last    = 0
        for xp, yp, zp in self.snake_folding(int(size_x), int(size_y), int(size_z)):
            prog_now += 1
            block_id = int(blocks[xp, yp, zp])
            block_data = int(block_datas[xp, yp, zp])
            if block_id != 0:
                block_id = schema_id[block_id]
                self.game_ctrl.sendwocmd(f"setblock {x + yp} {y + xp} {z + zp} {block_id} {block_data}")
                time.sleep(0.001)
            if (new_timer := time.time()) - timer >= 1:
                self.progress_bar(name, prog_now, size_total, prog_now - prog_last)
                timer = new_timer
                prog_last = prog_now
                self.game_ctrl.sendwocmd(f"tp @a[name={self.game_ctrl.bot_name}] {x + yp} {y + xp} {z + zp}")
        self.progress_bar(name, prog_now, size_total, prog_now - prog_last)
        Print.print_suc("导入成功")

    @staticmethod
    def snake_folding(size_x: int, size_y: int, size_z: int):
        x = 0
        y = 0
        z = 0
        ax = 1
        ay = 1
        az = 1
        end_x = size_x - 1
        end_y = size_y - 1
        end_z = size_z - 1
        yield 0, 0, 0
        while (x, y, z) != (end_x, end_y, end_z):
            x += ax
            if x > end_x:
                x = end_x
                y += ay
                ax = -1
            elif x < 0:
                x = 0
                y += ay
                ax = 1
            if y > end_y:
                y = end_y
                z += az
                ay = -1
            elif y < 0:
                y = 0
                z += az
                ay = 1
            yield x, y, z

    def progress_bar(self, name: str, curr, tota, sped):
        if tota == 0:
            return
        n = round(curr / tota * 30)
        p = "§b" + "|" * n + "§f" + "|" * (30 - n)
        self.game_ctrl.player_actionbar(
            "@a", f"导入 {name} 进度: §l{curr} §7/ {tota} 速度： {sped}方块每秒 §r\n{p}"
        )
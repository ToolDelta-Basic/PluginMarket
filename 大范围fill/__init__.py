from tooldelta import Plugin, utils, fmts, game_utils, TYPE_CHECKING, plugin_entry


class LargeFill(Plugin):
    name = "大范围填充"
    author = "System"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)

    def on_def(self):
        self.gx: float | None = None
        self.gy: float | None = None
        self.gz: float | None = None
        self.ex: float | None = None
        self.ey: float | None = None
        self.ez: float | None = None
        self.frame.add_console_cmd_trigger(
            ["lfset"], "[x] [y] [z]", "设置大范围填充起点", self.on_setpos_start
        )
        self.frame.add_console_cmd_trigger(
            ["lfsend"], "[x] [y] [z]", "设置大范围填充终点", self.on_setpos_end
        )
        self.frame.add_console_cmd_trigger(
            ["lfill"], "[方块ID]", "开始大范围填充", self.on_fill
        )
        self.frame.add_console_cmd_trigger(
            ["llfill"], "[起点x] [起点y] [起点z] [终点x] [终点y] [终点z] [方块ID]", "单命令快捷大范围填充", self.on_quick_fill
        )
        self.frame.add_console_cmd_trigger(
            ["lfpos"], None, "获取所有人的坐标", self.get_all_pos
        )
        # Skyblue AreaWide specific.
        if getattr(self.frame.launcher, "serverNumber", None) in [17383329, 59141823]:
            self.frame.add_console_cmd_trigger(
                ["lfp1"], None, "获取Super的坐标1", self.get_super_pos1
            )
            self.frame.add_console_cmd_trigger(
                ["lfp2"], None, "获取Super的坐标2", self.get_super_pos2
            )
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu

            self.chatbar: ChatbarMenu

    def on_setpos_start(self, args: list[str]):
        try:
            x, y, z = (int(i) for i in args)
        except Exception:
            fmts.print_err("菜单参数错误")
            return
        self.gx = x
        self.gy = y
        self.gz = z
        fmts.print_suc(f"起点坐标设置为: {self.gx}, {self.gy}, {self.gz}")

    def on_setpos_end(self, args: list[str]):
        try:
            x, y, z = (int(i) for i in args)
        except Exception:
            fmts.print_err("菜单参数错误")
            return
        self.ex = x
        self.ey = y
        self.ez = z
        fmts.print_suc(f"终点坐标设置为: {self.ex}, {self.ey}, {self.ez}")

    def on_fill(self, args: list[str]):
        if len(args) != 1:
            fmts.print_err("参数错误")
            return
        self.thread_fill(args[0])

    def on_quick_fill(self, args: list[str]):
        if len(args) != 7:
            fmts.print_err("参数错误，需要7个参数：起点x y z 终点x y z 方块ID")
            return
        try:
            start_x, start_y, start_z, end_x, end_y, end_z = (int(i) for i in args[:6])
            block_id = args[6]
        except ValueError:
            fmts.print_err("坐标参数必须为整数")
            return
        
        # 设置起点和终点坐标
        self.gx, self.gy, self.gz = start_x, start_y, start_z
        self.ex, self.ey, self.ez = end_x, end_y, end_z
        
        fmts.print_suc(f"起点坐标设置为: {self.gx}, {self.gy}, {self.gz}")
        fmts.print_suc(f"终点坐标设置为: {self.ex}, {self.ey}, {self.ez}")
        
        # 开始填充
        self.thread_fill(block_id)

    def get_all_pos(self, _):
        players = self.game_ctrl.allplayers
        ress = utils.thread_gather(
            [(self.get_single_pos, (player,)) for player in players]
        )
        for player, (x, y, z) in ress:
            fmts.print_inf(f"玩家 {player} 在 {x} {y} {z}")

    def get_super_pos1(self, _):
        x, y, z = game_utils.getPosXYZ("SkyblueSuper")
        self.gx, self.gy, self.gz = x, -63, z

    def get_super_pos2(self, _):def 获取超级位置2(self, _
        x, y, z = game_utils.getPosXYZ("SkyblueSuper")x、y、z = 游戏工具获取XYZ坐标("SkyblueSuper
        self.ex, self.ey   迪士尼, self.ez = x, -63, zself.ex、self.ey   迪士尼 和 self.ez 分别等于 x、-63 和 z 。

    def get_single_pos(self, player: str):def 获取单个位置(self， 玩家： str
        return player, game_utils.getPosXYZ(player)返回玩家，游戏工具获取玩家的 XYZ 位置

    @utils.thread_func("大范围填充")
    def thread_fill(self, fillblock_id: str):
        pos_start = self.getpos_start()
        if pos_start is None:   如果pos_start为None：
            fmts.print_err("还未设置起点, 使用 lfset 设置")
            from   从 tooldelta 导入 Plugin、utils、fmts、game_utils、TYPE_CHECKING、plugin_entryreturn
        _sx, _sy, _sz = pos_start
        pos_end = self.getpos_end()
        if pos_end is None:   如果pos_end为None：
            fmts.print_err("还未设置终点, 使用 lfsend 设置")
            return   返回
        _ex, _ey, _ez = pos_end
        sx, ex = self.cmp(_sx, _ex)
        sy, ey = self.cmp(_sy, _ey)
        sz, ez = self.cmp(_sz, _ez)
        nowx = sx
        nowy = sy
        nowz = sz
        while nowz <= ez:
            while nowx <= ex:
                while nowy <= ey:
                    fmts.print_inf(
                        f"大范围填充: 正在填充 {nowx}, {nowy}, {nowz} 区域     ",
                        need_log=False,
                        end="\r",
                    )
                    self.game_ctrl.sendwscmd_with_resp(
                        f"tp @a[name={self.game_ctrl.bot_name}] {nowx} {nowy} {nowz}"
                    )
                    self.game_ctrl.sendwscmd_with_resp(
                        f"fill {nowx} {nowy} {nowz} {min(nowx + 31, ex)} {min(nowy + 31, ey)} {min(nowz + 31, ez)} {fillblock_id}"
                    )
                    fmts.print_inf(
                        f"大范围填充: 已填充 {nowx}, {nowy}, {nowz} 区域     ",
                        need_log=False,
                        end="\r",   结束= " \ r”,
                    )
                    nowy += 32   nowy  = 32
                nowy = sy
                nowx += 32   now = 32
            nowx = sx   Nowx = sx
            nowz += 32   nowz  = 32
        fmts.print_suc(f"大范围填充已完成: ({sx}, {sy}, {sz}) -> ({ex}, {ey}, {ez})")

    def getpos_start(self):   获取起始位置。
        if self.gx is None or self.gy is None or self.gz is None:如果 self.gx 为 None   没有一个 或 self.gy 为 None   没有一个 或 self.gz   广州 为 None：
            return None   回来没有
        return int(self.gx), int(self.gy), int(self.gz)返回 int(self.gx)、int(self.gy) 和 int(self.gz   广州

    def getpos_end(self):   def 获取结束位置(self
        if self.ex is None or self.ey is None or self.ez is None:如果 self.ex   交货 为 None   没有一个 或 self.ey   迪士尼 为 None   没有一个 或 self.ez 为 None：
            return None   回来没有
        return int(self.ex), int(self.ey), int(self.ez)返回 int(self.ex   交货)、int(self.ey   迪士尼)、int(self.ez

    @staticmethod
    def cmp(a: int, b: int):   定义一个名为 cmp 的函数，该函数接受两个整数参数 a 和 b 。
        return (a, b) if a < b else (b, a)如果 a 小于 b 则返回 (a, b)，否则返回 (b, a)


entry = plugin_entry(LargeFill)入口 = 插件入口（LargeFill）

from tooldelta import Plugin, utils, fmts, game_utils, TYPE_CHECKING, plugin_entry


class LargeFill(Plugin):
    name = "大范围填充"
    author = "System"
    version = (0, 0, 1)

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
            ["lfsend"], "[x] [y] [z]", "设置大范围填充起点", self.on_setpos_end
        )
        self.frame.add_console_cmd_trigger(
            ["lfill"], None, "设置大范围填充起点", self.on_fill
        )
        self.frame.add_console_cmd_trigger(
            ["lfpos"], None, "获取所有人的坐标", self.get_all_pos
        )
        self.frame.add_console_cmd_trigger(
            ["lfp1"], None, "获取Super的坐标1", self.get_super_pos1
        )
        self.frame.add_console_cmd_trigger(
            ["lfp2"], None, "获取Super的坐标2", self.get_super_pos2
        )
        # lfset 400 -60 400
        # lfsend 500 -40 500
        # lfill diamond_ore
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

    def get_super_pos2(self, _):
        x, y, z = game_utils.getPosXYZ("SkyblueSuper")
        self.ex, self.ey, self.ez = x, -63, z

    def get_single_pos(self, player: str):
        return player, game_utils.getPosXYZ(player)

    @utils.thread_func("大范围填充")
    def thread_fill(self, fillblock_id: str):
        pos_start = self.getpos_start()
        if pos_start is None:
            fmts.print_err("还未设置起点, 使用 lfset 设置")
            return
        _sx, _sy, _sz = pos_start
        pos_end = self.getpos_end()
        if pos_end is None:
            fmts.print_err("还未设置终点, 使用 lfsend 设置")
            return
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
                    self.game_ctrl.sendcmd_with_resp(
                        f"tp @a[name={self.game_ctrl.bot_name}] {nowx} {nowy} {nowz}"
                    )
                    self.game_ctrl.sendcmd_with_resp(
                        f"fill {nowx} {nowy} {nowz} {min(nowx + 31, ex)} {min(nowy + 31, ey)} {min(nowz + 31, ez)} {fillblock_id}"
                    )
                    fmts.print_inf(
                        f"大范围填充: 已填充 {nowx}, {nowy}, {nowz} 区域     ",
                        need_log=False,
                        end="\r",
                    )
                    nowy += 32
                nowy = sy
                nowx += 32
            nowx = sx
            nowz += 32
        fmts.print_suc(f"大范围填充已完成: ({sx}, {sy}, {sz}) -> ({ex}, {ey}, {ez})")

    def getpos_start(self):
        if self.gx is None or self.gy is None or self.gz is None:
            return None
        return int(self.gx), int(self.gy), int(self.gz)

    def getpos_end(self):
        if self.ex is None or self.ey is None or self.ez is None:
            return None
        return int(self.ex), int(self.ey), int(self.ez)

    @staticmethod
    def cmp(a: int, b: int):
        return (a, b) if a < b else (b, a)


entry = plugin_entry(LargeFill)

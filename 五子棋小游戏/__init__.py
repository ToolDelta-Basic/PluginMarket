import time
from typing import ClassVar
from tooldelta import ToolDelta, Plugin, Player, Chat, utils, plugin_entry

class GobangBasic:
    """
    SuperGobang v SuperScript|SuperAFK
    TM AND LICENSED BY DOYEN STUDIO(1991-2023).Inc.
    """

    rooms: ClassVar[dict[str, "Room"]] = {}
    waitingCache: ClassVar[dict] = {}
    cacheUID = 0

    class Room:
        def __init__(self, _1P: str, _2P: str):
            self.playerA = _1P
            self.playerB = _2P
            self.turns = 1
            self.timeleft = 120
            self.startTime = time.time()
            self.stage = SuperGobangStage()
            self.maxTimeout = 0
            self.status = ""

        def turn(self):
            self.turns = [0, 2, 1][self.turns]

        def isTurn(self, player: str):
            return (player == self.playerA and self.turns == 1) or (
                player == self.playerB and self.turns == 2
            )

        def resetTimer(self):
            self.startTime = time.time()
            self.timeleft = 120

        def fmtTimeLeft(self):
            time_min, time_sec = divmod(self.timeleft, 60)
            return f"{time_min:02d} ： {time_sec:02d}"

        def PID(self, player: str):
            return (
                1 if player == self.playerA else (2 if player == self.playerB else None)
            )

        def anotherPlayer(self, player: str):
            "请不要在未确认玩家为该局玩家的时候使用该方法"
            return self.playerA if player == self.playerB else self.playerB

        def setStatus(self, status: str):
            self.status = status

    def createRoom(self, roomdata: Room):
        roomUID = hex(GobangRoom.cacheUID)
        GobangRoom.cacheUID += 1
        self.rooms[roomUID] = roomdata
        return roomUID

    def removeRoom(self, roomUID: str):
        del self.rooms[roomUID]

    def getRoom(self, player: str):
        for _k in self.rooms:
            if self.rooms[_k].playerA == player or self.rooms[_k].playerB == player:
                return _k
        return None

    @staticmethod
    def GameStart(_1P: str, _2P: str):
        entry.game_ctrl.say_to(
            _1P,
            "§l§7> §a五子棋游戏已开始， 退出聊天栏查看棋盘，§f输入 xz <纵坐标> <横坐标>以下子.",
        )
        entry.game_ctrl.say_to(
            _2P,
            "§l§7> §a五子棋游戏已开始， 退出聊天栏查看棋盘，§f输入 xz <纵坐标> <横坐标>以下子.",
        )
        entry.game_ctrl.player_title(_1P, "§e游戏开始")
        entry.game_ctrl.player_title(_2P, "§e游戏开始")
        entry.game_ctrl.player_subtitle(
            _1P, "§a聊天栏输入 下子 <纵坐标> <横坐标> 即可落子"
        )
        entry.game_ctrl.player_subtitle(
            _2P, "§a聊天栏输入 下子 <纵坐标> <横坐标> 即可落子"
        )
        linked_room_uid = GobangRoom.createRoom(GobangBasic.Room(_1P, _2P))
        this_room: GobangBasic.Room = GobangRoom.rooms[linked_room_uid]
        while 1:
            time.sleep(1)
            nowPlayer = _1P if this_room.isTurn(_1P) else _2P
            actbarText = f"§e§l五子棋 {this_room.fmtTimeLeft()} %s\n{this_room.stage.strfChess()}§9SuperGobang\n§a"
            entry.game_ctrl.player_actionbar(
                _1P,
                actbarText % ("§a我方下子" if this_room.isTurn(_1P) else "§6对方下子"),
            )
            entry.game_ctrl.player_actionbar(
                _2P,
                actbarText % ("§a我方下子" if this_room.isTurn(_2P) else "§6对方下子"),
            )
            if this_room.status == "done":
                break
            if this_room.timeleft < 20:
                entry.game_ctrl.player_title(nowPlayer, "§c还剩 20 秒")
                entry.game_ctrl.player_subtitle(
                    nowPlayer, "§6若仍然没有下子， 将会跳过你的回合"
                )
            if this_room.timeleft <= 0:
                entry.game_ctrl.player_title(nowPlayer, "§c已跳过你的回合")
                entry.game_ctrl.player_title(
                    _1P if _1P != nowPlayer else _2P, "§6对方超时， 现在轮到你落子"
                )
                this_room.resetTimer()
                this_room.maxTimeout += 1
                this_room.turn()
                if this_room.maxTimeout > 1:
                    entry.game_ctrl.player_title(_1P, "§c游戏超时， 本局已结束")
                    entry.game_ctrl.player_title(_2P, "§c游戏超时， 本局已结束")
                    break
            this_room.timeleft -= 1
        GobangRoom.removeRoom(linked_room_uid)

    @utils.thread_func("五子棋匹配线程")
    def GameWait(self, _1P: str, _2P: str):
        entry.frame.game_ctrl.say_to(_1P, "§7§l> §r§6正在等待对方同意请求..")
        entry.game_ctrl.say_to(_2P, f"§7§l> §r§e{_1P}§f向你发送了五子棋对弈邀请 ！")
        entry.game_ctrl.say_to(_2P, "§7§l> §r§a输入wzq y同意， §c输入wzq n拒绝")
        waitStartTime = time.time()
        self.waitingCache[_2P] = None
        while 1:
            time.sleep(0.5)
            if time.time() - waitStartTime > 30:
                entry.game_ctrl.say_to(_1P, f"§7§l> §c等待{_2P}的请求超时， 已取消.")
                break
            if self.waitingCache.get(_2P, "none") == "none":
                break
            elif self.waitingCache[_2P]:
                if self.waitingCache[_2P] == 1:
                    GobangBasic.GameStart(_1P, _2P)
                    break
                else:
                    entry.game_ctrl.say_to(_1P, f"§7§l> §c{_2P}拒绝了您的邀请..")
        del self.waitingCache[_2P]


class SuperGobangStage:
    def __init__(self):
        self.basic()

    def basic(self):
        self.SIZE = 12
        self.field = [[0 for _ in range(self.SIZE)] for _v in range(self.SIZE)]
        self.winner = None
        self.BLACK = 1
        self.WHITE = 2
        self.PosSignLeft = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫"]

    def centers(self, rowIndex, w):
        if (
            (rowIndex < 3 or rowIndex > self.SIZE - 2) and (w < 3 or w > self.SIZE - 2)
        ) or not self.getField(rowIndex, w):
            return False
        return any(
            [
                (
                    self.getField(rowIndex, w)
                    == self.getField(rowIndex - 1, w)
                    == self.getField(rowIndex - 2, w)
                    == self.getField(rowIndex + 1, w)
                    == self.getField(rowIndex + 2, w)
                ),
                (
                    self.getField(rowIndex, w)
                    == self.getField(rowIndex, w - 1)
                    == self.getField(rowIndex, w - 2)
                    == self.getField(rowIndex, w + 1)
                    == self.getField(rowIndex, w + 2)
                ),
                (
                    self.getField(rowIndex, w)
                    == self.getField(rowIndex - 1, w - 1)
                    == self.getField(rowIndex - 2, w - 2)
                    == self.getField(rowIndex + 1, w + 1)
                    == self.getField(rowIndex + 2, w + 2)
                    != 0
                ),
                (
                    self.getField(rowIndex, w)
                    == self.getField(rowIndex - 1, w + 1)
                    == self.getField(rowIndex - 2, w + 2)
                    == self.getField(rowIndex + 1, w - 1)
                    == self.getField(rowIndex + 2, w - 2)
                    != 0
                ),
            ]
        )

    def getField(self, row: int, w: int):
        if row not in range(1, self.SIZE + 1) or w not in range(1, self.SIZE + 1):
            return None
        return self.field[row - 1][w - 1]

    def setField(self, rowIndex, w, chesType):
        if rowIndex not in range(1, self.SIZE + 1) or w not in range(1, self.SIZE + 1):
            return False
        self.field[rowIndex - 1][w - 1] = chesType
        return True

    def get_win(self):
        for cl in range(1, self.SIZE + 1):
            for cw in range(1, self.SIZE + 1):
                if self.centers(cl, cw):
                    return self.getField(cl, cw)
        return None

    def onchess(self, row: int, w: int, player):
        assert not self.getField(row, w), "§c此处不可以再下子哦"
        if row not in range(1, self.SIZE + 1) or w not in range(1, self.SIZE + 1):
            return False
        self.setField(row, w, player)
        return True

    def toSignLeft(self, num: int):
        return self.PosSignLeft[num - 1]

    def strfChess(self):
        fmt: str = "§e   1 2 3 4 5 6 7 8 9 10 1112§r"
        for cl in self.field:
            fmt += "\n{}"
            for cw in cl:
                if cw == 0:
                    fmt += "§7§l▒§r"
                elif cw == 1:
                    fmt += "§0§l▒§r"
                elif cw == 2:
                    fmt += "§f§l▒§r"
        return fmt.format(*[self.toSignLeft(i) for i in range(1, self.SIZE + 1)])


GobangRoom = GobangBasic()


class SuperGobang(Plugin):
    name = "五子棋小游戏"
    author = "SuperScript"
    version = (0, 0, 6)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)
        self.ListenChat(self.on_chess_cmd)

    def on_preload(self):
        chatbar = self.GetPluginAPI("聊天栏菜单")
        chatbar.add_trigger(
            ["五子棋", "wzq"],
            "[对手名]",
            "开一局五子棋游戏",
            self.on_menu_invoked,
            lambda x: x == 1,
        )

    def on_menu_invoked(self, player: str, args: list[str]):
        _2P = args[0]
        if len(_2P) < 2:
            self.game_ctrl.say_to(player, "§c模糊搜索玩家名， 输入的名字长度必须大于1")
            return
        allplayers = list(self.game_ctrl.allplayers)
        allplayers.remove(player)
        new2P = None
        for single_player in allplayers:
            if _2P in single_player:
                new2P = single_player
                break
        if not new2P:
            self.game_ctrl.say_to(player, f'§c未找到名字里含有"{_2P}"的玩家.')
            return
        if new2P in GobangRoom.waitingCache.keys():
            self.game_ctrl.say_to(player, "§c申请已经发出了")
        if not GobangRoom.getRoom(player):
            GobangRoom.GameWait(player, new2P)
        else:
            self.game_ctrl.say_to(player, "§c你还没有退出当前游戏房间")

    def on_chess_cmd(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg
        if (
            msg.startswith("下子")
            or msg.lower().startswith("xz")
            or msg.startswith("XZ")
        ):
            if GobangRoom.rooms:
                in_room = GobangRoom.getRoom(player)
                if in_room:
                    inRoom: GobangBasic.Room = GobangRoom.rooms[in_room]
                    if inRoom.isTurn(player):
                        try:
                            try:
                                _, posl, posw = msg.split()
                            except Exception:
                                raise AssertionError(
                                    "§c落子格式不正确； 下子/xiazi/xz <纵坐标> <横坐标>"
                                )
                            assert inRoom.stage.onchess(
                                int(posl), int(posw), inRoom.PID(player)
                            )
                            self.game_ctrl.say_to(player, "§l§7> §r§a成功下子.")
                            inRoom.resetTimer()
                            is_win = inRoom.stage.get_win()
                            if is_win:
                                self.game_ctrl.player_title(player, "§a§l恭喜！")
                                self.game_ctrl.player_subtitle(
                                    player, "§e本局五子棋您获得了胜利！"
                                )
                                self.game_ctrl.say_to(
                                    player,
                                    "§7§l> §r§e恭喜！ §a本局五子棋您取得了胜利！",
                                )
                                self.game_ctrl.sendwocmd(
                                    f"/execute {player} ~~~ playsound random.levelup @s"
                                )
                                self.game_ctrl.player_title(
                                    inRoom.anotherPlayer(player), "§7§l遗憾惜败"
                                )
                                self.game_ctrl.player_subtitle(
                                    inRoom.anotherPlayer(player), "§6下局再接再厉哦！"
                                )
                                self.game_ctrl.sendwocmd(
                                    f"/execute {inRoom.anotherPlayer(player)} ~~~ playsound note.pling @s ~~~ 1 0.5"
                                )
                                inRoom.setStatus("done")
                                return
                            else:
                                self.game_ctrl.say_to(
                                    inRoom.anotherPlayer(player), "§l§7> §r§a到你啦！"
                                )
                                inRoom.turn()
                        except AssertionError as err:
                            self.game_ctrl.say_to(player, str(err))
                    else:
                        self.game_ctrl.say_to(player, "§c还没有轮到你落子哦")
                else:
                    self.game_ctrl.say_to(player, "§c需要开启一场五子棋游戏才可以落子")
            else:
                self.game_ctrl.say_to(player, "§c需要开启一场五子棋游戏才可以落子")
        elif msg.lower() == "wzq y":
            if player in GobangRoom.waitingCache.keys():
                GobangRoom.waitingCache[player] = 1
        elif msg.lower() == "wzq n":
            if player in GobangRoom.waitingCache.keys():
                GobangRoom.waitingCache[player] = 2

    def player_exit(self, p: Player):
        player = p.name
        if GobangRoom.rooms:
            in_room = GobangRoom.getRoom(player)
            if in_room:
                inRoom: GobangBasic.Room = GobangRoom.rooms[in_room]
                self.game_ctrl.player_title(
                    inRoom.anotherPlayer(player), "§c对方已退出游戏，游戏结束"
                )
                inRoom.setStatus("done")


entry = plugin_entry(SuperGobang)

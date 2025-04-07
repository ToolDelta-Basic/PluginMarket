from tooldelta import Player, Plugin, Chat, ToolDelta, utils, plugin_entry


class JZQStage:
    def __init__(self):
        self.Stage = [
            "basic_0",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
        ]

        self.turn = 0

        self.luozi_type = ["§f▒§f", "§0▒§f"]

        self.panding = [
            (1, 2, 3),
            (4, 5, 6),
            (7, 8, 9),
            (1, 4, 7),
            (2, 5, 8),
            (3, 6, 9),
            (1, 5, 9),
            (3, 5, 7),
        ]

        self.__time = 180

    def 轮流(self, turn=False):
        if turn:
            if self.turn == 0:
                self.turn = 1
            else:
                self.turn = 0
        return self.turn

    def 落子(self, xpos: int, ypos: int, typePlayer: int):
        pos = self.Stage[(xpos - 1) * 3 + ypos]
        if pos == "§7▒§f":
            self.Stage[(xpos - 1) * 3 + ypos] = self.luozi_type[typePlayer]
            return True
        return False

    def 判定(self):
        for i in self.panding:
            pos1, pos2, pos3 = i
            if (
                self.Stage[pos1] == self.Stage[pos2] == self.Stage[pos3]
                and self.Stage[pos1] != "§7▒§f"
            ):
                return True
        return False

    def 判死(self):
        return "§7▒§f" not in self.Stage

    def 重置(self, done=False):
        self.__time = 180
        self.Stage = [
            "basic_0",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
            "§7▒§f",
        ]
        if done:
            self.turn = 0

    def Timer(self, time=None):
        if time:
            self.__time += time
        return self.__time

    def display(self):
        basic, ps1, ps2, ps3, ps4, ps5, ps6, ps7, ps8, ps9 = self.Stage
        return ps1 + ps2 + ps3 + "\n" + ps4 + ps5 + ps6 + "\n" + ps7 + ps8 + ps9

    def stage_display(self, index: tuple[Player, Player], player: Player, end=False):
        entry.game_ctrl.sendwscmd(
            f"/title {player.name} actionbar §e§l井字棋\n§b时间: §c{'**' if end else self.Timer() // 60}§f:§c{'**' if end else self.Timer() % 60}§r §6落子:{'§a✔' if Game_JZQ.轮流() == index.index(player.name) else '§c✘'}\n§l{Game_JZQ.display()}{'' if self.Timer() != 0 else '§c时间到!'}"
        )


Game_JZQ = JZQStage()
JZQ_Rooms: list[tuple[Player, Player]] = []


class JZQPlugin(Plugin):
    name = "井字棋小游戏"
    author = "SuperScript"
    version = (0, 0, 7)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenChat(self.on_chat)
        self.ListenActive(self.on_repeat)

    def on_chat(self, chat: Chat):
        player = chat.player
        playername = chat.player.name
        msg = chat.msg
        if msg.startswith(".井字棋 ") or msg.startswith(".jzq "):
            if not JZQ_Rooms:
                try:
                    to_who = msg.split()[1]
                except Exception:
                    to_who = ""
                to_who = self.frame.get_players().getPlayerByName(to_who)
                if to_who:
                    JZQ_Rooms.append((player, to_who))
                    player.show("§a井字棋§f>> §a成功开启游戏.")
                else:
                    player.show("§a井字棋§f>> §c玩家未找到!.")
            else:
                player.show("§a井字棋§f>> §c房间里正在游戏中!")

        elif msg.startswith("下子 "):
            for i in JZQ_Rooms:
                if player in i:
                    typePlayer = i.index(playername)
                    try:
                        x_xpos = int(msg.split()[1])
                        y_ypos = int(msg.split()[2])
                    except Exception:
                        player.show("§a井字棋§f>> §c下子格式有误")
                        return
                    if x_xpos < 1 or x_xpos > 3 or y_ypos < 1 or y_ypos > 3:
                        player.show("§a井字棋§f>> §c下子位置有误")
                    elif Game_JZQ.轮流() != typePlayer:
                        player.show("§a井字棋§f>> §c没有轮到你落子.")
                    else:
                        result = Game_JZQ.落子(x_xpos, y_ypos, typePlayer)
                        if result:
                            player.show("§a井字棋§f>> §a成功下子.")
                            Game_JZQ.轮流(True)
                            i[Game_JZQ.轮流()].show(
                                f"§a井字棋§f>> §6对方已落子: §e({x_xpos}, {y_ypos})§6 到你啦!",
                            )
                            if Game_JZQ.判定():
                                Game_JZQ.stage_display(i, player)
                                player.setTitle("§e井字棋", "§a祝贺!你赢了!")
                                nexPlayer = i[Game_JZQ.轮流()]
                                Game_JZQ.stage_display(i, nexPlayer)
                                nexPlayer.setTitle("§e井字棋", "§7惜败..")
                                JZQ_Rooms.remove(i)
                                Game_JZQ.重置(True)
                                continue
                            if Game_JZQ.判死():
                                Game_JZQ.重置()
                        else:
                            player.show("§a井字棋§f>> §c这个地方不能下子")

    @utils.timer_event(1, "井字棋游戏计时器")
    def on_repeat(self):
        if JZQ_Rooms:
            for i in JZQ_Rooms:
                for player in i:
                    for player in i:
                        Game_JZQ.stage_display(i, player)
                if Game_JZQ.Timer() == 0:
                    player.show("§a井字棋§f>> §c时间到!游戏结束")
                    for player in i:
                        Game_JZQ.stage_display(i, player, True)
                    JZQ_Rooms.remove(i)
                    Game_JZQ.重置(True)
                    continue
                Game_JZQ.Timer(-1)


entry = plugin_entry(JZQPlugin)

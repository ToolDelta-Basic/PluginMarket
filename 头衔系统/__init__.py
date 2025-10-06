import time
from tooldelta import (
    Plugin,
    cfg,
    TYPE_CHECKING,
    utils,
    Player,
    plugin_entry,
)


class Nametitle(Plugin):
    name = "头衔系统"
    author = "SuperScript"
    version = (0, 0, 4)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        CFG = {
            "说明": "因为头衔系统会干扰玩家列表上的计分板，所以请设置常显计分板的名字，为空则不设置",
            "常显计分板名字": "money_show",
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(CFG), CFG, self.version
        )
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.funclib = self.GetPluginAPI("基本插件功能库")
        self.intr = self.GetPluginAPI("前置-世界交互")
        cb2bot = self.GetPluginAPI("Cb2Bot通信")
        if TYPE_CHECKING:
            from 前置_基本插件功能库 import BasicFunctionLib
            from 前置_聊天栏菜单 import ChatbarMenu
            from 前置_世界交互 import GameInteractive
            from 前置_Cb2Bot通信 import TellrawCb2Bot
            self.funclib: BasicFunctionLib
            self.chatbar: ChatbarMenu
            self.intr: GameInteractive
            cb2bot: TellrawCb2Bot
        cb2bot.regist_message_cb(
            "nametitle.set", lambda x: self.on_set_titles(x[0], [x[1]])
        )
        cb2bot.regist_message_cb(
            "nametag.set", lambda x: self.on_set_titles(x[0], [x[1]])
        )

    def on_player_join(self, playerf: Player):
        self.flush_nametitles()

    def on_inject(self):
        self.chatbar.add_new_trigger(
            ["titles", "称号"],
            [("称号名", str, "")],
            "打开称号设置页",
            lambda player, args: self.on_set_titles(player.name, args),
        )
        if getattr(self.frame.launcher, "serverNumber", None) == 59141823:
            # SkyblueRPG specific.
            self.chatbar.add_new_trigger(
                ["title-set", "设置称号"],
                [("称号名", str, "")],
                "打开管理称号设置页",
                lambda player, args: self.on_operate_nametitle(player, args),
                True,
            )
        else:
            self.chatbar.add_new_trigger(
                ["title-set", "设置称号"],
                [],
                "打开管理称号设置页",
                lambda player, args: self.on_operate_nametitle(player, args),
                True,
            )
        self.nmtitle_cds: dict[Player, int] = {}
        self.nmtitle_cd()

    @utils.thread_func("玩家设置称号")
    def on_set_titles(self, playername: str, ls):
        player = self.game_ctrl.players.getPlayerByName(playername)
        if player is None:
            return
        if player in self.nmtitle_cds.keys() and not player.is_op():
            self.playsound(player, "bass", 0.707)
            self.show_err(player, "每次设置称号后有 60s 冷却时长")
            return
        titles = self.get_titles()
        mytitles = self.get_player_titles(player)
        if mytitles == []:
            self.playsound(player, "bass", 0.707)
            self.show_err(player, "暂无可切换称号")
            return
        nowtitle, *mytitles = mytitles
        if ls == []:
            player.show( "§7[§fi§7] §b选择一个称号：")
            for i, k in enumerate(mytitles):
                player.show(
                    f" {i + 1}. {k}： {titles.get(k, '<称号失效>')}"
                )
            resp = utils.try_int(player.input("§7[§fi§7] §b输入以进行更换："))
            if resp is None or resp - 1 not in range(len(mytitles)):
                self.playsound(player, "bass", 0.707)
                player.show( "§c无效选项")
                return
            section = mytitles[resp - 1]
        else:
            section = ls[0]
            if section not in mytitles:
                self.show_err(player, "你没有获得这个称号， 无法使用")
                self.playsound(player, "bass", 0.707)
                return
        self.game_ctrl.sendwocmd(
            f"scoreboard players reset {player.getSelector()} {nowtitle}"
        )
        if titles.get(section) is None:
            self.show_err(player, "该称号已失效， 无法使用")
            self.playsound(player, "bass", 0.707)
            return
        old = self.get_player_titles(player)
        old[0] = section
        self.set_player_titles(player, old[0], old[1:])
        self.show_war(player, f"正在更新称号到 {titles[section]} §6..")
        time.sleep(0.5)
        self.nmtitle_cds[player] = int(time.time())
        self.flush_nametitles()
        self.show_suc(player, "称号更新完成！")
        self.playsound(player, "bit", 1.414)
        time.sleep(0.14)
        self.playsound(player, "bit", 2.828)

    @utils.thread_func("管理设置称号")
    def on_operate_nametitle(self, player: Player, ls):
        if ls:
            # 蔚蓝空域专属
            x, y, z = [int(i) for i in player.getPos()][1:]
            self.intr.place_command_block(
                self.intr.make_packet_command_block_update(
                    (x, y, z),
                    r'tellraw @a[title=sr.rpg_bot] {"rawtext":[{"text":"nametitle.set"},{"selector":"@p"},{"text":"'
                    f"{ls[0]}"
                    r'"}]}',
                    need_redstone=True,
                )
            )
            self.game_ctrl.sendcmd("tp ~~20~")
            player.show( "§a放置完成")
            self.playsound(player, "pling", 0.707)
            return
        titles = self.get_titles()
        titles_kvs = []
        if titles == {}:
            player.show( "§6当前没有任何称号， 输入§f+§6添加：")
        else:
            titles_kvs = list(titles.items())
            player.show( "§6选择一个§f称号§6并进行设置：")
            for i, (k, v) in enumerate(titles_kvs):
                player.show( f" {i + 1}. {k}： {v}")
            player.show( "§6输入§f序号§6进行设置， §f+§6添加称号：")
        resp = player.input()
        if resp is None:
            player.show( "§c选项超时， 已退出")
            self.playsound(player, "bass", 0.707)
            return
        resp = resp.strip()
        if resp == "+":
            while True:
                resp = player.input("§6输入§f称号ID§6：")
                if resp is None:
                    player.show( "§c选项超时， 已退出")
                    self.playsound(player, "bass", 0.707)
                    return
                try:
                    self.game_ctrl.sendwocmd(f"scoreboard objectives remove {resp}")
                    if self.game_ctrl.sendwscmd_with_resp(
                        f"scoreboard objectives add {resp} dummy", 5
                    ).SuccessCount > 0:
                        self.game_ctrl.sendwocmd(f"scoreboard objectives remove {resp}")
                        break
                    else:
                        player.show( "§c似乎不是合法ID..")
                        self.playsound(player, "bass", 0.707)
                except TimeoutError:
                    player.show( "§c似乎含有敏感词..")
                    self.playsound(player, "bass", 0.707)
            title_id = resp
            while 1:
                resp = player.input("§6输入§f称号显示名§6：")
                if resp is None:
                    player.show( "§c选项超时， 已退出")
                    self.playsound(player, "bass", 0.707)
                    return
                try:
                    if self.game_ctrl.sendwscmd_with_resp(
                        f"scoreboard objectives add {title_id} dummy {resp}", 5
                    ).SuccessCount > 0:
                        break
                    else:
                        player.show( "§c似乎不是合法显示名..")
                        self.playsound(player, "bass", 0.707)
                except TimeoutError:
                    player.show( "§c似乎含有敏感词..")
                    self.playsound(player, "bass", 0.707)
            title_showname = resp
            old = self.get_titles()
            old[title_id] = title_showname
            self.set_titles(old)
            player.show( "§a设置完成")
            self.playsound(player, "pling", 0.707)
        elif resp.isdigit():
            resp = int(resp) - 1
            if resp not in range(len(titles_kvs)):
                player.show( "§c无效选项")
                return
            resp1 = player.input("§6选择以下设置：\n §f1. 删除该头衔\n 2. 给予头衔\n 3. 收回头衔")
            if resp1 is None:
                player.show( "§c选项超时， 已退出")
                return
            if resp1 not in ("1", "2", "3"):
                player.show( "§c选项不正确， 已退出")
                return
            title_id, title_showname = titles_kvs[resp]
            if resp1 == "1":
                self.game_ctrl.sendwocmd(f"scoreboard objectives remove {title_id}")
                old = self.get_titles()
                del old[title_id]
                self.set_titles(old)
                player.show( "§a删除成功")
            elif resp1 == "2":
                section = self.funclib.list_select(
                    player, self.game_ctrl.allplayers, "§6选择一个在线玩家："
                )
                if section is None or (target := self.game_ctrl.players.getPlayerByName(section)) is None:
                    return
                titles = self.get_player_titles(target)
                if len(titles) == 0:
                    titles.append(title_id)
                if title_id not in titles[1:]:
                    titles.append(title_id)
                    player.show(
                        f"§a已成功将称号 {title_showname}§r§a 给予 {section}"
                    )
                else:
                    player.show(
                        f"§6{section} 已有称号 {title_showname}"
                    )
                self.set_player_titles(target, titles[0], titles[1:])
            elif resp1 == "3":
                section = self.funclib.list_select(
                    player, self.game_ctrl.allplayers, "§6选择一个在线玩家："
                )
                if section is None or (target := self.game_ctrl.players.getPlayerByName(section)) is None:
                    return
                titles = self.get_player_titles(target)
                if titles[0] == title_id:
                    titles[0] = ""
                if title_id not in titles[1:]:
                    player.show(
                        f"§6{section} 没有头衔 §f{title_showname}"
                    )
                else:
                    player.show(
                        f"§a已收回 {section} 的称号 {title_showname}"
                    )
                    titles.remove(title_id)
                    self.set_player_titles(target, titles[0], titles[1:])
                    self.flush_nametitles()
        else:
            player.show( "§c无效选项")
            return

    def flush_nametitles(self):
        nts: set[str] = set()
        use_title: dict[Player, str] = {}
        for player in self.game_ctrl.players:
            titles = self.get_player_titles(player)
            if titles == []:
                continue
            t = titles[0]
            if t == "":
                continue
            nts.add(t)
            use_title[player] = t
            self.game_ctrl.sendwocmd(
                f"scoreboard players set {player.getSelector()} {t} 1"
            )
        for t in nts:
            self.game_ctrl.sendwocmd(f"scoreboard objectives setdisplay belowname {t}")
            self.game_ctrl.sendwocmd(f"scoreboard objectives setdisplay list {t}")
        time.sleep(0.3)
        scb_name = self.cfg["常显计分板名字"].strip()
        if scb_name:
            self.game_ctrl.sendwocmd(
                f"scoreboard objectives setdisplay list {scb_name}"
            )
        else:
            self.game_ctrl.sendwocmd("scoreboard objectives add tmp dummy")
            self.game_ctrl.sendwocmd("scoreboard objectives setdisplay list tmp")
            self.game_ctrl.sendwocmd("scoreboard objectives remove tmp")

    def get_titles(self) -> dict[str, str]:
        return utils.tempjson.load_and_read(
            self.format_data_path("titles.json"), need_file_exists=False, default={}
        )

    def get_current_nametitle(self, player: Player):
        curr = self.get_player_titles(player)
        if not curr:
            return None
        else:
            return curr[0]

    def set_titles(self, titles: dict[str, str]):
        return utils.tempjson.load_and_write(
            self.format_data_path("titles.json"), titles, need_file_exists=False
        )

    def get_player_titles(self, player: Player) -> list[str]:
        return utils.tempjson.load_and_read(
            self.format_data_path("player_titles.json"),
            need_file_exists=False,
            default={},
        ).get(player.xuid, [])

    def set_player_titles(self, player: Player, curr_title: str, titles: list[str]):
        old = utils.tempjson.load_and_read(
            self.format_data_path("player_titles.json"),
            need_file_exists=False,
            default={},
        )
        old[player.xuid] = [curr_title, *titles]
        utils.tempjson.load_and_write(
            self.format_data_path("player_titles.json"), old, need_file_exists=False
        )

    @utils.timer_event(20, "称号设置冷却")
    def nmtitle_cd(self):
        ntime = time.time()
        for k, v in self.nmtitle_cds.copy().items():
            if ntime - v >= 60:
                del self.nmtitle_cds[k]

    def show_suc(self, player: Player, msg: str):
        player.show( f"§7[§a√§7] §a{msg}")

    def show_war(self, player: Player, msg: str):
        player.show( f"§7[§6§l！§r§7] §6{msg}")

    def show_err(self, player: Player, msg: str):
        player.show( f"§7[§cx§7] §c{msg}")

    def playsound(self, target: Player, sound: str, pitch: float):
        self.game_ctrl.sendwocmd(
            f"execute as {target.safe_name} at @s"
            f" run playsound note.{sound} @s ~~~ 1 {pitch}"
        )


entry = plugin_entry(Nametitle, "头衔系统")

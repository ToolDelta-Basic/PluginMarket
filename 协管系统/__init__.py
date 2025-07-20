from tooldelta import Plugin, plugin_entry, Player, Chat, FrameExit, cfg, game_utils, utils, fmts, TYPE_CHECKING
class Auxiliary(Plugin):
    name = "协管系统"
    author = "果_k"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.players: "PlayerInfoMaintainer" = self.game_ctrl.players
        self.ListenPreload(self.on_def)
        CONFIG_DEFAULT = {
            "协管名单": [
                "player1",
                "player2"
        ],
            "命令转发": "命令转发 *转发协管输入命令内容",
            "命令转发禁用关键词":[
                "kick",
                "clear",
                "op",
                "deop",
                "give",
                "fog",
                "gamemode",
                "replaceitem",
                "setblock",
                "fill",
                "setworldspawn",
                "spawnpoint",
                "structure",
                "execute",
                "tag",
                "tickingarea",
                "clone",
                "difficulty",
                "event",
                "gamerule",
                "scoreboard"
            ]
        }
        CONFIG_STD = {
            "协管名单": cfg.JsonList((int,str)),
            "命令转发": str,
            "命令转发禁用关键词": cfg.JsonList(str)
        }
        config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
            )
        self.GMlist = config["协管名单"]
        self.CMDsend = config["命令转发"]
        self.NO_CMDsend = config["命令转发禁用关键词"]

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.chatbar.add_trigger(["协管系统"], None, "协管系统", self.GMmenu)
        self.chatbar.add_trigger(["命令转发","转发"], None, "命令转发", self.CMDpost)
        self.chatbar.add_trigger(["协管名单"], None, "查看所有协管名称", self.GMuser)
    def GMmenu(self, playername:str,*args):
        player = self.players.getPlayerByName(playername)
        print(playername)
        print(self.GMlist)
        if playername in self.GMlist:
            player.show("§b§l当前协管功能包含")
            player.show("§a§l" + self.CMDsend)
            player.show("§a§l您已是协管")
        else:
            player.show("您当前不是协管")

    @utils.thread_func("CMD")
    def CMDpost(self, playername: str, *args):
        player = self.players.getPlayerByName(playername)
        if playername not in self.GMlist:
            player.show("§c§l您不是协管")
            return
    
        if not args:
            player.show("§c§l没有参数")
            return

        try:
            if isinstance(args[0], list): #拼接参数
                cmd = ' '.join(args[0])
            else:
                cmd = ' '.join(args)

            for keyword in self.NO_CMDsend: #筛选指令内容
                if keyword in cmd:
                    player.show(f"§c§l命令包含禁止关键词:§e§l {keyword}§c§l，无法执行。")
                    return

            full_cmd = f"/execute as {playername} at {playername} run {cmd}"
            resp = self.game_ctrl.sendwocmd(full_cmd)
            fmts.print_inf(f"协管:{playername} 执行了指令: {cmd}")
            player.show(resp)

        except IndexError as e:
            player.show(f"§c§l参数索引错误: {str(e)}")
        except Exception as e:
            player.show(f"§c§l发生未知错误: {str(e)}")
    def GMuser(self, playername:str,*args):
        player = self.players.getPlayerByName(playername)
        if not self.GMlist:
            player.show("§c§l当前没有协管玩家。")
            return

        player.show("§e§l当前协管名单如下：")
        for idx, gm in enumerate(self.GMlist, 1):
            player.show(f"§f§l{idx}. {gm}")
            pass

entry = plugin_entry(Auxiliary)

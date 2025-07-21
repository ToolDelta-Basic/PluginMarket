from tooldelta import Plugin, plugin_entry, Player, Chat, FrameExit, cfg, game_utils, utils, fmts, TYPE_CHECKING
class Auxiliary(Plugin):
    name = "协管系统"
    author = "果_k"
    version = (0, 0, 2)

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
            ],
            "快捷功能": {
                "视角投射":True,
                "玩家查询":True,
                "清理掉落物":True,
                "查询背包物品":True,
                "权限设置":True

            },
            "在线时间计分板":"zxsj",

        }
        CONFIG_STD = {
            "协管名单": cfg.JsonList((int,str)),
            "命令转发": str,
            "命令转发禁用关键词": cfg.JsonList(str),
            "快捷功能": {
                "视角投射":bool,
                "玩家查询":bool,
                "清理掉落物":bool,
                "查询背包物品":bool,
                "权限设置":bool
            },
            "在线时间计分板":str,
        }
        config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
            )
        self.GMlist = config["协管名单"]
        self.CMDsend = config["命令转发"]
        self.NO_CMDsend = config["命令转发禁用关键词"]
        self.Focus = config["快捷功能"]
        self.online_time_scoreboard = config["在线时间计分板"]

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.chatbar.add_new_trigger(["协管系统"], [], "协管系统", self.GMmenu)
        self.chatbar.add_new_trigger(["命令转发","转发"], ..., "命令转发", self.CMDpost)
        self.chatbar.add_new_trigger(["快捷功能"], [], "协管的快捷功能", self.GM_focus)
        self.chatbar.add_new_trigger(["协管名单"], [], "查看所有协管名称", self.GMuser)
    def GMmenu(self, player: Player, args: tuple):
        playername = player.name
        if playername in self.GMlist:
            player.show("§b§l当前协管功能包含")
            player.show("§a§l" + self.CMDsend)
            player.show("§a§l您已是协管")
        else:
            player.show("您当前不是协管")

    @utils.thread_func("CMD")
    def CMDpost(self, player: Player, args: tuple):
        playername = player.name
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
    def GM_focus(self, player: Player, args: tuple):
        playername = player.name
        if playername not in self.GMlist:
            player.show("§c§l您不是协管")
            return
        enabled_features = [key for key, value in self.Focus.items() if value is True]
        if not enabled_features:
            player.show("§c§l当前没有可用的快捷功能。")
            return
        player.show("§b§l请选择一个功能：")
        for idx, feature in enumerate(enabled_features, 1):
            player.show(f"§f§l{idx}. {feature}")
        feature_handlers = {
            "视角投射": self.PosProjection,
            "玩家查询": self.PlayerQuery,
            "清理掉落物": self.ClearDropItems,
            "查询背包物品": self.QueryInventory,
            "权限设置": self.AbilitiesSet,
            # 此处进行函数映射
        }
        try:
            choice_str = player.input("请输入功能序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(enabled_features):
                selected_feature = enabled_features[choice]
                handler = feature_handlers.get(selected_feature)
                if handler:
                    handler(player, playername)  # 调用对应的功能处理函数
                else:
                    player.show("§c§l该功能尚未实现。")
            else:
                player.show("§c§l无效的序号。")
        except ValueError:
            player.show("§c§l请输入一个有效的数字。")

    def GMuser(self, player: Player, args: tuple):
        if not self.GMlist:
            player.show("§c§l当前没有协管玩家。")
            return

        player.show("§e§l当前协管名单如下: ")
        for idx, gm in enumerate(self.GMlist, 1):
            player.show(f"§f§l{idx}. {gm}")
            pass

    def PosProjection(self, player, playername: str):
        online_players = self.players.getAllPlayers()
        player.show("§e§l请选择一个玩家: ")
        for idx, p in enumerate(online_players, 1):
            player.show(f"§f§l{idx}. {p.name}")
        try:
            choice_str = player.input("请输入玩家序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(online_players):
                selected_player = online_players[choice]
                player.show(f"§a§l您选择了: {selected_player.name}")
                _,x1,y1,z1 = player.getPos()
                dim,x,y,z = selected_player.getPos()
                fmts.print_inf(f"协管:{playername} 使用了视角投射对: {selected_player.name} 至 {x} {y} {z}")
                self.game_ctrl.sendwocmd(f"/gamemode spectator {playername}")
                self.game_ctrl.sendwocmd(f"/execute as {playername} at {selected_player.name} run tp {x} {y} {z}")
                player.show(f"§a§l已传送至: {selected_player.name} 维度 {dim}")
                player.input("§a§l输入任意返回至原位置" ,-1 )
                self.game_ctrl.sendwocmd(f"/gamemode survival {playername}")
                self.game_ctrl.sendwocmd(f"/execute as {playername} at {playername} run tp {x1} {y1} {z1}")

            else:
                player.show("§c§l无效的序号。")
        except ValueError:
            player.show("§c§l请输入一个有效的数字。")

    def PlayerQuery(self, player, playername: str):
        online_players = self.players.getAllPlayers()
        player.show("§e§l请选择一个玩家：")
        for idx, p in enumerate(online_players, 1):
            player.show(f"§f§l{idx}. {p.name}")
        try:
            choice_str = player.input("请输入玩家序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(online_players):
                selected_player = online_players[choice]
                fmts.print_inf(f"协管:{playername} 使用了玩家查询: {selected_player.name}")
                dim, x, y, z = selected_player.getPos()
                onlinetinme = selected_player.getScore(self.online_time_scoreboard)
                player.show(f"§a§l您选择了: {selected_player.name}")
                player.show(f"§b§l游戏时长: {onlinetinme}")
                player.show(f"§b§lUUID: {selected_player.uuid}")
                player.show(f"§b§lUnique_id: {selected_player.unique_id}")
                player.show(f"§b§l游戏平台: {selected_player.build_platform}")
                player.show(f"§b§l玩家当前维度与坐标: {dim} {x} {y} {z}")
            else:
                player.show("§c§l无效的序号。")
        except ValueError:
            player.show("§c§l请输入一个有效的数字。")
    def ClearDropItems(self, player, playername: str):
        self.game_ctrl.sendwocmd(f"/kill @e[type=item]")
        fmts.print_inf(f"协管:{playername} 使用了清理掉落物")
        player.show("§a§l已清理掉落物")
    def QueryInventory(self, player, playername: str):
        online_players = self.players.getAllPlayers()
        player.show("§e§l请选择一个玩家：")
        for idx, p in enumerate(online_players, 1):
            player.show(f"§f§l{idx}. {p.name}")
        try:
            choice_str = player.input("请输入玩家序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(online_players):
                dim, x, y, z = player.getPos()
                self.game_ctrl.sendwocmd(f"/setblock {x} {y} {z} shulker_box") #创建容器
                selected_player = online_players[choice]
                inventory = selected_player.queryInventory()
                for i in range(27):  # 0 到 26
                    slot = inventory.slots[i] if i < len(inventory.slots) else None
                    if slot is not None:
                        item_id = getattr(slot, 'id', '未知ID')
                        stack_size = getattr(slot, 'stackSize', 0)
                        player.show(f"§f§l槽位 {i}: ID={item_id}, 数量={stack_size}")
                        self.game_ctrl.sendwocmd(
                            f"/replaceitem block {x} {y} {z} slot.container {i} {item_id} {stack_size}"
                        )
                    else:
                        player.show(f"§f§l槽位 {i}: 空")
                self.game_ctrl.sendwocmd(f"/setblock {x} {y + 1} {z} shulker_box")  # 在上方放置第二个箱子

                for i in range(27, 36):  # 27 到 35
                    slot = inventory.slots[i] if i < len(inventory.slots) else None
                    if slot is not None:
                        item_id = getattr(slot, 'id', '未知ID')
                        stack_size = getattr(slot, 'stackSize', 0)
                        player.show(f"§f§l槽位 {i}: ID={item_id}, 数量={stack_size}")
                        self.game_ctrl.sendwocmd(
                            f"/replaceitem block {x} {y + 1} {z} slot.container {i - 27} {item_id} {stack_size}"
                        )
                    else:
                        player.show(f"§f§l槽位 {i}: 空")
                self.game_ctrl.sendwocmd(f"/setblock {x} {y} {z} air 0 destroy")
                self.game_ctrl.sendwocmd(f"/setblock {x} {y + 1} {z} air 0 destroy")
                fmts.print_inf(f"协管:{playername} 使用了查询玩家背包: {selected_player.name}")
            else:
                player.show("§c§l无效的序号。")
        except ValueError:
            player.show("§c§l请输入一个有效的数字。")
    def AbilitiesSet(self, player, playername: str):
        online_players = self.players.getAllPlayers()
        player.show("§e§l请选择一个玩家：")
        for idx, p in enumerate(online_players, 1):
            player.show(f"§f§l{idx}. {p.name}")
        try:
            choice_str = player.input("请输入玩家序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(online_players):
                selected_player = online_players[choice]
                abilities = selected_player.abilities
                
                player.show("§b§l当前能力设置:") #显示当前能力设置
                player.show(f"§f§l1. 破坏方块: {'§a开启' if abilities.mine else '§c关闭'}")
                player.show(f"§f§l2. 攻击玩家: {'§a开启' if abilities.attack_players else '§c关闭'}")
                player.show(f"§f§l3. 攻击生物: {'§a开启' if abilities.attack_mobs else '§c关闭'}")
                
                choice_str = player.input("请输入要修改的能力序号(1-3): ")
                choice = int(choice_str) - 1
                
                if 0 <= choice < 3:
                    ability_names = ["mine", "attack_players", "attack_mobs"]
                    ability_name = ability_names[choice]
                    current_value = getattr(abilities, ability_name)
                    
                    setattr(abilities, ability_name, not current_value)
                    selected_player.setAbilities(abilities) #更新能力
                    fmts.print_inf(f"协管:{playername} 修改了玩家能力: {selected_player.name} {['破坏方块', '攻击玩家', '攻击生物'][choice]}为: {'§a开启' if not current_value else '§c关闭'}")
                    player.show(f"§a§l{['破坏方块', '攻击玩家', '攻击生物'][choice]}已{'§a开启' if not current_value else '§c关闭'}")
                else:
                    player.show("§c§l无效的序号。")
                    
            else:
                player.show("§c§l无效的序号。")
                
        except Exception as e:
            player.show(f"§c§l发生错误: {str(e)}")

entry = plugin_entry(Auxiliary)
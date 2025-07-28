from tooldelta import Player, fmts
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from . import Auxiliary

class Core:
    def __init__(self, plugin: "Auxiliary"):
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl
        self.players = plugin.players
        
    def GMmenu(self, player: Player, args: tuple):
        playername = player.name
        if playername in self.plugin.GMlist:
            player.show("§b§l当前协管功能包含")
            player.show(f"§a§l + {self.plugin.Info['命令转发']}")
            player.show("§a§l您已是协管")
        else:
            player.show(self.plugin.Info['若不是协管'])

    def CMDpost(self, player: Player, args: tuple):
        playername = player.name
        if playername not in self.plugin.GMlist:
            player.show(self.plugin.Info['若不是协管'])
            return True
    
        if not args:
            player.show("§c§l没有参数")
            return True

        try:
            if isinstance(args[0], list):  # 拼接参数
                cmd = ' '.join(args[0])
            else:
                cmd = ' '.join(args)

            for keyword in self.plugin.NO_CMDsend:  # 筛选指令内容
                if keyword in cmd:
                    player.show(f"§c§l命令包含禁止关键词:§e§l {keyword}§c§l，无法执行。")
                    return True

            full_cmd = f"/execute as {playername} at {playername} run {cmd}"
            self.game_ctrl.sendwocmd(full_cmd)
            fmts.print_inf(f"协管:{playername} 执行了指令: {cmd}")

        except IndexError as e:
            player.show(f"§c§l参数索引错误: {str(e)}")
        except Exception as e:
            player.show(f"§c§l发生未知错误: {str(e)}")
        return True
        
    def GM_focus(self, player: Player, args: tuple):
        playername = player.name
        if playername not in self.plugin.GMlist:
            player.show(self.plugin.Info['若不是协管'])
            return True
            
        enabled_features = [key for key, value in self.plugin.Focus.items() if value is True]  # 获取可用功能列表
        if not enabled_features:
            player.show("§c§l当前没有可用的快捷功能。")
            return True

        feature_handlers = {
            "视角投射": self.PosProjection,
            "玩家查询": self.PlayerQuery,
            "清理掉落物": self.ClearDropItems,
            "查询背包物品": self.QueryInventory,
            "权限设置": self.AbilitiesSet,
        }

        if args:  # 支持参数快速选中功能
            try:
                choice_str = args[0] if isinstance(args[0], str) else str(args[0])
                choice = int(choice_str) - 1

                if 0 <= choice < len(enabled_features):
                    selected_feature = enabled_features[choice]
                    handler = feature_handlers.get(selected_feature)  # 获取映射的函数
                    if handler:
                        handler(player, playername)  # 调用对应的功能处理函数
                    else:
                        player.show("§c§l该功能尚未实现。")
                else:
                    player.show("§c§l无效的序号。")
            except ValueError:
                player.show("§c§l请输入一个有效的数字。")
        else:
            player.show("§b§l请选择一个功能：")
            for idx, feature in enumerate(enabled_features, 1):
                player.show(f"§f§l{idx}. {feature}")
            try:
                choice_str = player.input("请输入功能序号: ")
                choice = int(choice_str) - 1

                if 0 <= choice < len(enabled_features):
                    selected_feature = enabled_features[choice]
                    handler = feature_handlers.get(selected_feature)
                    if handler:
                        handler(player, playername)
                    else:
                        player.show("§c§l该功能尚未实现。")
                else:
                    player.show("§c§l无效的序号。")
            except ValueError:
                player.show("§c§l请输入一个有效的数字。")
        return True
                
    def GMuser(self, player: Player, args: tuple):
        if not self.plugin.GMlist:
            player.show("§c§l当前没有协管玩家。")
            return True

        player.show("§e§l当前协管名单如下: ")
        for idx, gm in enumerate(self.plugin.GMlist, 1):
            player.show(f"§f§l{idx}. {gm}")
        return True

    def PosProjection(self, player, playername: str):
        online_players = self.players.getAllPlayers()
        player.show(self.plugin.Info['选择玩家列表'])
        for idx, p in enumerate(online_players, 1):
            player.show(f"§f§l{idx}. {p.name}")
        try:
            choice_str = player.input("请输入玩家序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(online_players):
                selected_player = online_players[choice]
                player.show(f"§a§l您选择了: {selected_player.name}")
                _, x1, y1, z1 = player.getPos()
                dim, x, y, z = selected_player.getPos()
                fmts.print_inf(f"协管:{playername} 使用了视角投射对: {selected_player.name} 至 {x} {y} {z}")
                self.game_ctrl.sendwocmd(f"/gamemode spectator {playername}")
                self.game_ctrl.sendwocmd(f"/execute as {playername} at {selected_player.name} run tp {x} {y} {z}")
                player.show(f"§a§l已传送至: {selected_player.name} 维度 {dim}")
                player.input("§a§l输入任意返回至原位置", -1)
                self.game_ctrl.sendwocmd(f"/gamemode survival {playername}")
                self.game_ctrl.sendwocmd(f"/execute as {playername} at {playername} run tp {x1} {y1} {z1}")

            else:
                player.show("§c§l无效的序号。")
        except ValueError:
            player.show("§c§l请输入一个有效的数字。")

    def PlayerQuery(self, player, playername: str):
        online_players = self.players.getAllPlayers()
        player.show(self.plugin.Info['选择玩家列表'])
        for idx, p in enumerate(online_players, 1):
            player.show(f"§f§l{idx}. {p.name}")
        try:
            choice_str = player.input("请输入玩家序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(online_players):
                selected_player = online_players[choice]
                fmts.print_inf(f"协管:{playername} 使用了玩家查询: {selected_player.name}")
                dim, x, y, z = selected_player.getPos()
                onlinetinme = selected_player.getScore(self.plugin.online_time_scoreboard)
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
        self.game_ctrl.sendwocmd("/kill @e[type=item]")
        fmts.print_inf(f"协管:{playername} 使用了清理掉落物")
        player.show("§a§l已清理掉落物")
        
    def QueryInventory(self, player, playername: str):
        online_players = self.players.getAllPlayers()
        player.show(self.plugin.Info['选择玩家列表'])
        for idx, p in enumerate(online_players, 1):
            player.show(f"§f§l{idx}. {p.name}")
        try:
            choice_str = player.input("请输入玩家序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(online_players):
                _, x, y, z = player.getPos()
                self.game_ctrl.sendwocmd(f"/setblock {x} {y} {z} shulker_box")  # 创建容器
                selected_player = online_players[choice]
                inventory = selected_player.queryInventory()
                for i in range(27):  # 0 到 26的物品
                    slot = inventory.slots[i] if i < len(inventory.slots) else None
                    if slot is not None:
                        item_id = getattr(slot, 'id', '未知ID')
                        stack_size = getattr(slot, 'stackSize', 0)
                        player.show(f"§f§l槽位 {i}: ID={item_id}, 数量={stack_size}")
                        self.game_ctrl.sendwocmd(f"/replaceitem block {x} {y} {z} slot.container {i} {item_id} {stack_size}")
                    else:
                        player.show(f"§f§l槽位 {i}: 空")
                self.game_ctrl.sendwocmd(f"/setblock {x} {y + 1} {z} shulker_box")  # 在上方放置第二个容器

                for i in range(27, 36):  # 将27 到 35 格位的物品放到另一个容器
                    slot = inventory.slots[i] if i < len(inventory.slots) else None
                    if slot is not None:
                        item_id = getattr(slot, 'id', '未知ID')
                        stack_size = getattr(slot, 'stackSize', 0)
                        player.show(f"§f§l槽位 {i}: ID={item_id}, 数量={stack_size}")
                        self.game_ctrl.sendwocmd(f"/replaceitem block {x} {y + 1} {z} slot.container {i - 27} {item_id} {stack_size}")
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
        filtered_players = [p for p in online_players if p.name not in self.plugin.GMlist]
        player.show(self.plugin.Info['选择玩家列表'])
        for idx, p in enumerate(filtered_players, 1):
            player.show(f"§f§l{idx}. {p.name}")
        try:
            choice_str = player.input("请输入玩家序号: ")
            choice = int(choice_str) - 1

            if 0 <= choice < len(filtered_players):
                selected_player = filtered_players[choice]
                abilities = selected_player.abilities
                
                player.show("§b§l当前能力设置:") 
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
                    selected_player.setAbilities(abilities)  # 更新能力
                    fmts.print_inf(f"协管:{playername} 修改了玩家能力: {selected_player.name} {['破坏方块', '攻击玩家', '攻击生物'][choice]}为: {'§a开启' if not current_value else '§c关闭'}")
                    player.show(f"§a§l{['破坏方块', '攻击玩家', '攻击生物'][choice]}已{'§a开启' if not current_value else '§c关闭'}")
                else:
                    player.show("§c§l无效的序号。")
                    
            else:
                player.show("§c§l无效的序号。")
                
        except Exception as e:
            player.show(f"§c§l发生错误: {str(e)}")
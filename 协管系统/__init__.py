from tooldelta import Plugin, plugin_entry, Player, cfg, utils, fmts
import requests
class Auxiliary(Plugin):
    name = "协管系统"
    author = "果_k"
    version = (0, 0, 4)

    def __init__(self, frame):
        super().__init__(frame)
        self.players: "PlayerInfoMaintainer" = self.game_ctrl.players
        self.ListenPreload(self.on_def)
        CONFIG_DEFAULT = {
            "协管名单": [
                "player1",
                "player2",
                "bot_name"
        ],
            "Info": {
                "若不是协管":"§c§l您当前不是协管",
                "选择玩家列表":"§e§l请选择一个玩家:",
                "命令转发": "命令转发 *转发协管输入命令内容",
                "DeepSeek": "DeepSeek *DeepSeek",

            },
            "SetDeepSeek":{
                "APIkey": "此处换成你的DeepSeekAPIkey",
                "DeepSeek提示词":"你现在要为我的世界基岩版服务器玩家提供服务,当玩家询问你指令相关问题,请你做出对应指令并仅仅只返回不带/前缀的指令信息,你需要依据玩家名做出对应的选择器替代,除此之外不要返回任何除命令以外信息,这是绝对的,尽量将玩家的请求转化为命令可实现形式,当有玩家询问了无法理解的内容请返回:非指令问题 不予处理",
                "max_history_length": 15,
                "DeepSeekModel":"deepseek-chat"

            
            },
            "命令转发禁用关键词":[
                "clear",
                "op",
                "deop",
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
            "命令转发是否启用":True,
            "DeepSeek是否启用":False,
            "协管名单是否启用":False,
            "在线时间计分板":"zxsj",

        }
        CONFIG_STD = {
            "协管名单": cfg.JsonList((int,str)),
            "Info": dict,
            "SetDeepSeek": dict,
            "命令转发禁用关键词": cfg.JsonList(str),
            "快捷功能": {
                "视角投射":bool,
                "玩家查询":bool,
                "清理掉落物":bool,
                "查询背包物品":bool,
                "权限设置":bool
            },
            "命令转发是否启用":bool,
            "DeepSeek是否启用":bool,
            "协管名单是否启用":bool,
            "在线时间计分板":str,
        }
        config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
            )
        self.config = config
        self.GMlist = config["协管名单"]
        self.Info = config["Info"]
        self.NO_CMDsend = config["命令转发禁用关键词"]
        self.Focus = config["快捷功能"]
        self.online_time_scoreboard = config["在线时间计分板"]
        self.SetDeepSeek = config["SetDeepSeek"]
        self.conversations = {}

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.conversations.clear() #清除所有的历史对话
        #固定注册
        always_registered = [
            (["协管系统"], [], "协管系统", self.GMmenu),
            (["快捷功能"], ..., "触发词后加对应功能数字可快速选择", self.GM_focus),
        ]
        #按条件配置注册
        conditional_registered = [
            #格式为 "开关配置名 [触发词] 参数 描述 处理函数"
            ("命令转发是否启用", ["命令转发", "转发"], ..., "命令转发", self.CMDpost),
            ("DeepSeek是否启用", ["DeepSeek", "ds"], ..., "DeepSeek", self.DeepSeek),
            ("协管名单是否启用",["协管名单"], [], "查看所有协管名称", self.GMuser),
        ]
        for trigger in always_registered:
            self.chatbar.add_new_trigger(*trigger)

        for config_key, *trigger_info in conditional_registered:
            if self.config[config_key]:
                self.chatbar.add_new_trigger(*trigger_info)
    def GMmenu(self, player: Player, args: tuple):
        playername = player.name
        if playername in self.GMlist:
            player.show("§b§l当前协管功能包含")
            player.show(f"§a§l + {self.Info['命令转发']}")
            player.show("§a§l您已是协管")
        else:
            player.show(self.Info['若不是协管'])

    @utils.thread_func("CMD")
    def CMDpost(self, player: Player, args: tuple):    #命令转发
        playername = player.name
        if playername not in self.GMlist:
            player.show(self.Info['若不是协管'])
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
    def GM_focus(self, player: Player, args: tuple):   #快捷功能
        playername = player.name
        if playername not in self.GMlist:
            player.show(self.Info['若不是协管'])
            return
        enabled_features = [key for key, value in self.Focus.items() if value is True] #获取可用功能列表
        if not enabled_features:
            player.show("§c§l当前没有可用的快捷功能。")
            return

        feature_handlers = {
            "视角投射": self.PosProjection,
            "玩家查询": self.PlayerQuery,
            "清理掉落物": self.ClearDropItems,
            "查询背包物品": self.QueryInventory,
            "权限设置": self.AbilitiesSet,

            #此处进行函数映射
        }

        if args:  #支持参数快速选中功能
            try:
                choice_str = args[0] if isinstance(args[0], str) else str(args[0])
                choice = int(choice_str) - 1

                if 0 <= choice < len(enabled_features):
                    selected_feature = enabled_features[choice]
                    handler = feature_handlers.get(selected_feature) #获取映射的函数
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
    def GMuser(self, player: Player, args: tuple):
        if not self.GMlist:
            player.show("§c§l当前没有协管玩家。")
            return

        player.show("§e§l当前协管名单如下: ")
        for idx, gm in enumerate(self.GMlist, 1):
            player.show(f"§f§l{idx}. {gm}")
            pass

    def PosProjection(self, player, playername: str):  #视角投射
        online_players = self.players.getAllPlayers()
        player.show(self.Info['选择玩家列表'])
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

    def PlayerQuery(self, player, playername: str):   #玩家查询
        online_players = self.players.getAllPlayers()
        player.show(self.Info['选择玩家列表'])
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
    def ClearDropItems(self, player, playername: str):   #清理掉落物
        self.game_ctrl.sendwocmd(f"/kill @e[type=item]")
        fmts.print_inf(f"协管:{playername} 使用了清理掉落物")
        player.show("§a§l已清理掉落物")
    def QueryInventory(self, player, playername: str):   #查询玩家背包
        online_players = self.players.getAllPlayers()
        player.show(self.Info['选择玩家列表'])
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
    def AbilitiesSet(self, player, playername: str):   #权限设置
        online_players = self.players.getAllPlayers()
        filtered_players = [p for p in online_players if p.name not in self.GMlist]
        player.show(self.Info['选择玩家列表'])
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
                    selected_player.setAbilities(abilities) #更新能力
                    fmts.print_inf(f"协管:{playername} 修改了玩家能力: {selected_player.name} {['破坏方块', '攻击玩家', '攻击生物'][choice]}为: {'§a开启' if not current_value else '§c关闭'}")
                    player.show(f"§a§l{['破坏方块', '攻击玩家', '攻击生物'][choice]}已{'§a开启' if not current_value else '§c关闭'}")
                else:
                    player.show("§c§l无效的序号。")
                    
            else:
                player.show("§c§l无效的序号。")
                
        except Exception as e:
            player.show(f"§c§l发生错误: {str(e)}")
    @utils.thread_func("DeepSeek")
    def DeepSeek(self, player: Player, args: tuple):   #DeepSeek
        playername = player.name
        if playername not in self.GMlist:
            player.show(self.Info['若不是协管'])
            return
            
        # 支持参数快速选中功能
        if args:  
            try:
                param = ' '.join(args) if isinstance(args, (list, tuple)) else str(args)
                player.show(f"§a§l内容: {param}，正在转发")
                DS_result = self.reDeepSeek(param,player.name)
                for keyword in self.NO_CMDsend:
                    if keyword in DS_result['choices'][0]['message']['content']:
                        player.show(f"§c§l命令包含禁止关键词:§e§l {keyword}§c§l，无法执行。")
                        return
                player.show(f"§f§l原始指令内容为:§u{DS_result['choices'][0]['message']['content']} §f本次消耗Token: {DS_result['usage']['total_tokens']} §a共花费{self.calculate_output_cost(DS_result['usage']['total_tokens'])}元")
                self.game_ctrl.sendwocmd(f"/{DS_result['choices'][0]['message']['content']}")
                fmts.print(f"§f§l玩家:§e§l {player.name}§f§l 请求了§e§l {param}")
                fmts.print(f"§f§l实际执行结果为§e§l {DS_result['choices'][0]['message']['content']} §f本次消耗Token: {DS_result['usage']['total_tokens']} §a共花费{self.calculate_output_cost(DS_result['usage']['total_tokens'])}元")
            except ValueError:
                player.show("§c§l参数格式错误")
        else: 
            try:
                user_input = player.input("§a§l请输入要问的指令: ")
                player.show(f"§a§l内容: {user_input}，正在转发")
                DS_result = self.reDeepSeek(user_input,player.name)
                for keyword in self.NO_CMDsend:
                    if keyword in DS_result['choices'][0]['message']['content']:
                        player.show(f"§c§l命令包含禁止关键词:§e§l {keyword}§c§l，无法执行。")
                        return
                player.show(f"§f§l原始指令内容为:§u{DS_result['choices'][0]['message']['content']} §f本次消耗Token: {DS_result['usage']['total_tokens']} §a共花费{self.calculate_output_cost(DS_result['usage']['total_tokens'])}元")
                self.game_ctrl.sendwocmd(f"/{DS_result['choices'][0]['message']['content']}")
                fmts.print(f"§f§l玩家:§e§l {player.name}§f§l 请求了§e§l {user_input}")
                fmts.print(f"§f§l实际执行结果为§e§l {DS_result['choices'][0]['message']['content']} §f本次消耗Token: {DS_result['usage']['total_tokens']} §a共花费{self.calculate_output_cost(DS_result['usage']['total_tokens'])}元")
            except Exception as e:
                print(f"§c§l输入无效{str(e)}")
    def calculate_output_cost(self,total_output_tokens):
        cost_per_million = 16  #计算价格 这里需要根据对应不同模型实际token价格进行修改
        return (total_output_tokens / 1_000_000) * cost_per_million


    def reDeepSeek(self, Message: str,playername: str):
        base_url = "https://api.deepseek.com"
        api_key = self.SetDeepSeek['APIkey']
        if not api_key:
            return "错误：插件管理者未提供 DeepSeek API 密钥。"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
            }
        if playername not in self.conversations:
            self.conversations[playername] = []
        messages = self.conversations[playername]
       
        if not messages or messages[0]["role"] != "system":
            messages.insert(0, {
                "role": "system",
                "content": self.SetDeepSeek['DeepSeek提示词']
            })
        messages.append({
            "role": "user",
            "content": f"{playername}: {Message}",
            "name": playername
        })
        payload = {
            "model": self.SetDeepSeek['DeepSeekModel'],  
            "messages": messages,
            "stream": False
        }
        try:
            response = requests.post(
                f"{base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            )
            if response.status_code != 200:
                return f"请求失败，状态码：{response.status_code}，响应内容：{response.text}"
            result = response.json()
            assistant_response = result['choices'][0]['message']['content']
            messages.append({
                "role": "assistant",
                "content": assistant_response
            })
            if len(messages) > self.SetDeepSeek['max_history_length'] * 2:
                self.conversations[playername] = messages[-self.SetDeepSeek['max_history_length'] * 2:]
            return result
        except requests.exceptions.RequestException as e:
            return f"网络请求异常：{str(e)}"
        except UnicodeError as e:
            return f"编码异常：{str(e)}"

entry = plugin_entry(Auxiliary)
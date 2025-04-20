from tooldelta import Plugin, Player, cfg, plugin_entry
import random
import data_operation as data


class CatFishing(Plugin):
    name = "更好的钓鱼"
    author = "猫猫"
    version = (0, 0, 3)
    description = "让你的每一次收杆充满惊喜"

    def __init__(self, frame):
        super().__init__(frame)
        DEFAULT_CFG = {
            "奖池配置": "猫猫钓鱼奖池.json",
            "鱼竿配置": {
                "是否限制次数": False,
                "是否启用冷却": True,
            },
            "爆率设置": {
                "基础爆率": 500,
                "空钩概率": 100,
                "§r§f普通": 70,
                "§r§b稀有": 30,
            },
            "初始属性": {
                "鱼竿_钓鱼冷却": 20,
                "鱼竿_钓鱼爆率": 0,
                "鱼竿_物品爆率": 0,
                "鱼竿_生物爆率": 0,
                "鱼竿_结构爆率": 0,
                "鱼竿_连钓次数": 0,
                "鱼竿_空钩概率": 0,
                "玩家_钓鱼次数": 10,
                "玩家_钓鱼冷却": 0,
                "玩家_钓鱼爆率": 0,
                "玩家_物品爆率": 0,
                "玩家_生物爆率": 0,
                "玩家_结构爆率": 0,
                "玩家_连钓次数": 1,
                "玩家_空钩概率": 0,
                "玩家_冷却计时": 0,
                "玩家_鱼饵属性": 0,
            },
            "鱼饵属性": {
                "100": {
                    "钓鱼冷却": 0,
                    "钓鱼爆率": 0,
                    "物品爆率": 0,
                    "生物爆率": 0,
                    "结构爆率": 0,
                    "连钓次数": 0,
                    "空钩概率": 0,
                }
            },
            "品质设置": [
                "§r§f普通",
                "§r§b稀有",
            ],
            "对接命令方块": {
                "物品": True,
                "生物": False,
                "结构": False,
            },
        }
        STD_CFG_TYPE = {
            "奖池配置": str,
            "鱼竿配置": {
                "是否限制次数": bool,
                "是否启用冷却": bool,
            },
            "爆率设置": cfg.AnyKeyValue(int),
            "初始属性": {
                "鱼竿_钓鱼冷却": int,
                "鱼竿_钓鱼爆率": int,
                "鱼竿_物品爆率": int,
                "鱼竿_生物爆率": int,
                "鱼竿_结构爆率": int,
                "鱼竿_连钓次数": int,
                "鱼竿_空钩概率": int,
                "玩家_钓鱼次数": int,
                "玩家_钓鱼冷却": int,
                "玩家_钓鱼爆率": int,
                "玩家_物品爆率": int,
                "玩家_生物爆率": int,
                "玩家_结构爆率": int,
                "玩家_连钓次数": int,
                "玩家_空钩概率": int,
                "玩家_冷却计时": int,
                "玩家_鱼饵属性": int,
            },
            "鱼饵属性": cfg.AnyKeyValue(dict),
            "品质设置": cfg.JsonList(str),
            "对接命令方块": {
                "物品": bool,
                "生物": bool,
                "结构": bool,
            },
        }
        FISHING_CFG = {
            "§r§f普通": {
                "物品": [
                    {
                        "名字": "苹果",
                        "英文ID": "apple",
                        "特殊值": 0,
                        "数量": 1,
                    },
                ],
                "生物": [
                    {
                        "名字": "一只猫猫",
                        "英文ID": "cat",
                        "实体事件": "如果没有就随便填,但也不能啥也不填qwq 不然实体名称会失效的",
                        "实体名称": "猫猫",
                        "数量": 1,
                    },
                ],
                "结构": [
                    {
                        "名字": "更多猫猫",
                        "结构名称": "两只猫猫",
                        "坐标偏移": [0, 0, 0],
                        "数量": 1,
                    },
                ],
            },
            "§r§b稀有": {
                "物品": [
                    {
                        "名字": "苹果",
                        "英文ID": "apple",
                        "特殊值": 0,
                        "数量": 1,
                    },
                    {
                        "名字": "喵喵喵",
                        "命令方块对接": True,
                        "标签": "Cat.Fishing.普通",
                    },
                ],
                "生物": [
                    {
                        "名字": "一只猫猫",
                        "英文ID": "cat",
                        "实体事件": "如果没有就随便填,但也不能啥也不填qwq 不然实体名称会失效的",
                        "实体名称": "猫猫",
                        "数量": 1,
                    },
                ],
                "结构": [
                    {
                        "名字": "更多猫猫",
                        "结构名称": "两只猫猫",
                        "坐标偏移": [0, 0, 0],
                        "数量": 1,
                    },
                ],
            },
        }

        self.cfg, ver = cfg.get_plugin_config_and_version(
            self.name, STD_CFG_TYPE, DEFAULT_CFG, self.version
        )

        self.fishing_pool = data.load_data(self.format_data_path(self.cfg["奖池配置"]))
        if not self.fishing_pool:
            data.save_data(self.format_data_path(self.cfg["奖池配置"]), FISHING_CFG)
        self.fishing_Attribute = data.load_data(self.format_data_path("钓鱼属性.json"))
        self.fishing_rod = self.cfg["鱼竿配置"]
        self.droprate = self.cfg["爆率设置"]
        self.scoreboard = self.cfg["初始属性"]
        self.quality = self.cfg["品质设置"]
        self.cmdapi = self.cfg["对接命令方块"]
        self.bait = self.cfg["鱼饵属性"]
        self.player = self.frame.get_players()
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)

    def on_inject(self):
        for sn in self.scoreboard:
            self.game_ctrl.sendwocmd(f"/scoreboard objectives add {sn} dummy")

    def on_def(self):
        self.cb2bot = self.GetPluginAPI("Cb2Bot通信")
        self.cb2bot.regist_message_cb("Cat.Fishing", self.on_player_message)
        self.cb2bot.regist_message_cb("Cat.upScore", self.on_player_update)

    def show_inf(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§f!§7] §f{msg}")

    def show_suc(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§a√§7] §a{msg}")

    def show_war(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§6!§7] §6{msg}")

    def show_err(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§cx§7] §c{msg}")

    def fishing(self, player: Player):
        name = player.name

        fishing_airHook = self.fishing_Attribute[name]["鱼竿_空钩概率"]
        player_airHook = self.fishing_Attribute[name]["玩家_空钩概率"]
        f_fishingDrop = self.fishing_Attribute[name]["鱼竿_钓鱼爆率"]
        p_fishingDrop = self.fishing_Attribute[name]["玩家_钓鱼爆率"]
        fishing_itemDrop = self.fishing_Attribute[name]["鱼竿_物品爆率"]
        fishing_entityDrop = self.fishing_Attribute[name]["鱼竿_生物爆率"]
        fishing_structDrop = self.fishing_Attribute[name]["鱼竿_结构爆率"]
        player_itemDrop = self.fishing_Attribute[name]["玩家_物品爆率"]
        player_entityDrop = self.fishing_Attribute[name]["玩家_生物爆率"]
        player_structDrop = self.fishing_Attribute[name]["玩家_结构爆率"]

        bait = self.bait[str(self.fishing_Attribute[name]["玩家_鱼饵属性"])]
        bait_airHook = bait["空钩概率"]
        bait_Drop = bait["钓鱼爆率"]
        bait_IDrop = bait["物品爆率"]
        bait_EDrop = bait["生物爆率"]
        bait_SDrop = bait["结构爆率"]

        airHook = random.randint(0, self.droprate["空钩概率"])
        total_airHook = airHook - fishing_airHook - player_airHook - bait_airHook
        if total_airHook > 0:
            return self.show_err(
                name,
                f"啧啧啧, 杂鱼~ 连钓到{self.quality[0]}品质的垃圾都做不到吗? 笨蛋杂鱼~",
            )
        itemDrop = random.randint(0, self.droprate["基础爆率"])
        total_itemDrop = itemDrop - f_fishingDrop - p_fishingDrop - bait_Drop
        for i in range(len(self.quality) - 1, -1, -1):
            quality = self.quality[i]
            total_itemDrop -= self.droprate[quality]
            if total_itemDrop > 0 and i:
                continue
            is_item = self.fishing_pool[quality].get("物品")
            is_entity = self.fishing_pool[quality].get("生物")
            is_struct = self.fishing_pool[quality].get("结构")
            if is_item is None and is_entity is None and is_struct is None:
                self.show_err(name, "杂鱼服主~ 连奖池配置都调不好 真是杂鱼~")
                self.game_ctrl.sendwocmd(
                    f"/scoreboard players set {name} 玩家_冷却计时 0"
                )
                if self.fishing_rod["是否限制次数"]:
                    self.game_ctrl.sendwocmd(
                        f"/scoreboard players add {name} 玩家_钓鱼次数 1"
                    )
                return
            aiidr = fishing_itemDrop + player_itemDrop + bait_IDrop
            aeidr = fishing_entityDrop + player_entityDrop + bait_EDrop
            asidr = fishing_structDrop + player_structDrop + bait_SDrop
            population = []
            weights = []
            if is_item:
                population.append("物品")
                weights.append(aiidr)
            if is_entity:
                population.append("生物")
                weights.append(aeidr)
            if is_struct:
                population.append("结构")
                weights.append(asidr)
            if all(w == 0 for w in weights):
                weights = [1] * len(population)
            index = random.choices(population, weights=weights, k=1)[0]
            rn = random.randint(0, len(self.fishing_pool[quality][index]) - 1)
            item = self.fishing_pool[quality][index][rn]
            if item.get("名字"):
                self.show_suc(
                    name,
                    f"噗噗~只钓到了 {quality} §r§f的 {item['名字']} §r真是笨蛋杂鱼呢~",
                )
            if self.cmdapi[index] and item["命令方块对接"]:
                self.game_ctrl.sendwocmd(f"/tag {name} add {item['标签']}")
                return
            if index == "物品":
                self.game_ctrl.sendwocmd(
                    f"/give {name} {item['英文ID']} {item['数量']} {item['特殊值']}"
                )
            elif index == "生物":
                for _ in range(item["数量"]):
                    self.game_ctrl.sendwocmd(
                        f"/execute as {name} at @s run summon {item['英文ID']} ~ ~ ~ ~ ~ {item['实体事件']} {item['实体名称']}"
                    )
            elif index == "结构":
                for _ in range(item["数量"]):
                    self.game_ctrl.sendwocmd(
                        f"/execute as {name} at @s run structure load {item['结构名称']} ~{item['坐标偏移'][0]} ~{item['坐标偏移'][1]} ~{item['坐标偏移'][2]}"
                    )

    def on_player_update(self, args: list[str]):
        sn = [
            "玩家_冷却计时",
            "玩家_钓鱼次数",
            "玩家_钓鱼冷却",
            "玩家_钓鱼爆率",
            "玩家_物品爆率",
            "玩家_生物爆率",
            "玩家_结构爆率",
            "玩家_空钩概率",
            "玩家_连钓次数",
            "鱼竿_钓鱼冷却",
            "鱼竿_钓鱼爆率",
            "鱼竿_物品爆率",
            "鱼竿_生物爆率",
            "鱼竿_结构爆率",
            "鱼竿_空钩概率",
            "鱼竿_连钓次数",
            "玩家_鱼饵属性",
        ]
        for index, (name, score) in enumerate(zip(args[::2], args[1::2])):
            name = name.split(",")
            score = score.split(",")
            for i, n in enumerate(name):
                if self.fishing_Attribute.get(n) is None:
                    self.fishing_Attribute[n] = {}
                self.fishing_Attribute[n][sn[index]] = int(score[i])

    def on_player_message(self, args: list[str]):
        name, name_ = args
        if name != name_:
            return
        player = self.player.getPlayerByName(name)
        fishing_num_ = self.fishing_Attribute[name]["玩家_钓鱼次数"]
        fishing_cd = self.fishing_Attribute[name]["鱼竿_钓鱼冷却"]
        player_cr = self.fishing_Attribute[name]["玩家_钓鱼冷却"]
        fishing_num = self.fishing_Attribute[name]["鱼竿_连钓次数"]
        player_num = self.fishing_Attribute[name]["玩家_连钓次数"]
        cd_time = self.fishing_Attribute[name]["玩家_冷却计时"]

        bait = self.bait[str(self.fishing_Attribute[name]["玩家_鱼饵属性"])]
        bait_cd = bait["钓鱼冷却"]
        bait_num = bait["连钓次数"]

        if self.fishing_rod["是否启用冷却"]:
            if cd_time:
                self.show_err(
                    name, f"还在冷却呢! 笨蛋杂鱼~ 冷却还剩§f{cd_time}§c秒 真是杂鱼呢~"
                )
                return
        if self.fishing_rod["是否限制次数"]:
            if not fishing_num_:
                self.show_err(name, "剩余次数用完了! 真是杂鱼呢~ 杂鱼~")
                return
            self.game_ctrl.sendwocmd(
                f"/scoreboard players remove {name} 玩家_钓鱼次数 1"
            )
            self.fishing_Attribute[name]["玩家_钓鱼次数"] = fishing_num_
        if self.fishing_rod["是否启用冷却"]:
            acd = int(max(0, int(fishing_cd * max(0, 1 - player_cr / 100)) + bait_cd))
            self.game_ctrl.sendwocmd(
                f"/scoreboard players set {name} 玩家_冷却计时 {acd}"
            )
            self.fishing_Attribute[name]["玩家_冷却计时"] = acd
        total_num = fishing_num + player_num + bait_num
        for _ in range(total_num):
            self.fishing(player)
        data.save_data(self.format_data_path("钓鱼属性.json"), self.fishing_Attribute)

    def on_player_join(self, player: Player):
        if self.fishing_Attribute.get(player.name) is None:
            self.fishing_Attribute[player.name] = {}
            for sn in self.scoreboard:
                self.fishing_Attribute[player.name][sn] = self.scoreboard[sn]
                self.game_ctrl.sendwocmd(
                    f"/scoreboard players set {player.name} {sn} {self.scoreboard[sn]}"
                )
        data.save_data(self.format_data_path("钓鱼属性.json"), self.fishing_Attribute)


entry = plugin_entry(CatFishing)

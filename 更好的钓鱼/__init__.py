from tooldelta import Plugin, Player, Chat, cfg, utils, plugin_entry
from tooldelta.utils import tempjson
import random


class CatFishing(Plugin):
    name = "更好的钓鱼"
    author = "猫猫"
    version = (0, 0, 2)
    description = "让你的每一次收杆充满惊喜"

    def __init__(self, frame):
        super().__init__(frame)
        DEFAULT_CFG = {
            "奖池配置": "猫猫钓鱼奖池.json",
            "鱼竿配置": {
                "是否限制次数": False,
                "是否启用冷却": True,
                "钓鱼失败执行": [
                    "/playsound note.bass [name] ~ ~ ~",
                ],
                "钓鱼成功执行": [
                    "/playsound note.pling [name] ~ ~ ~",
                ],
            },
            "爆率设置": {
                "基础爆率": 500,
                "空钩概率": 100,
                "§r§f普通": 70,
                "§r§b稀有": 30,
            },
            "初始属性": {
                "鱼竿_钓鱼冷却": 0,
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
            },
            "品质设置": [
                "§r§f普通",
                "§r§b稀有",
            ],
        }
        STD_CFG_TYPE = {
            "奖池配置": str,
            "鱼竿配置": {
                "是否限制次数": bool,
                "是否启用冷却": bool,
                "钓鱼失败执行": cfg.JsonList(str),
                "钓鱼成功执行": cfg.JsonList(str),
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
            },
            "品质设置": cfg.JsonList(str),
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

        self.fishing_pool = tempjson.load_and_read(
            self.format_data_path(self.cfg["奖池配置"]),
            need_file_exists=False,
            default=FISHING_CFG,
        )
        self.fishing_rod = self.cfg["鱼竿配置"]
        self.droprate = self.cfg["爆率设置"]
        self.scoreboard = self.cfg["初始属性"]
        self.quality = self.cfg["品质设置"]
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenChat(self.on_player_message)

    def on_inject(self):
        self.on_second_event()
        for sn in self.scoreboard:
            self.game_ctrl.sendwocmd(f"/scoreboard objectives add {sn} dummy")

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
        (
            fishing_airHook,
            player_airHook,
            fishing_itemDrop,
            player_itemDrop,
            fiidr,
            feidr,
            fsidr,
            piidr,
            peidr,
            psidr,
        ) = utils.thread_gather(
            [
                player.getScore,
                ("鱼竿_空钩概率",),
                player.getScore,
                ("玩家_空钩概率",),
                player.getScore,
                ("鱼竿_钓鱼爆率",),
                player.getScore,
                ("玩家_钓鱼爆率",),
                player.getScore,
                ("鱼竿_物品爆率",),
                player.getScore,
                ("鱼竿_生物爆率",),
                player.getScore,
                ("鱼竿_结构爆率",),
                player.getScore,
                ("玩家_物品爆率",),
                player.getScore,
                ("玩家_生物爆率",),
                player.getScore,
                ("玩家_结构爆率",),
            ]
        )
        airHook = random.randint(0, self.droprate["空钩概率"])
        total_airHook = airHook - fishing_airHook - player_airHook
        if total_airHook > 0:
            for cmd in self.fishing_rod["钓鱼失败执行"]:
                self.game_ctrl.sendcmd_with_resp(
                    utils.simple_fmt(
                        {
                            "[name]": name,
                        },
                        cmd,
                    )
                )
            return self.show_err(
                name,
                f"啧啧啧, 杂鱼~ 连钓到{self.quality[0]}品质的垃圾都做不到吗? 笨蛋杂鱼~",
            )
        for cmd in self.fishing_rod["钓鱼成功执行"]:
            self.game_ctrl.sendcmd_with_resp(
                utils.simple_fmt(
                    {
                        "[name]": name,
                    },
                    cmd,
                )
            )
        itemDrop = random.randint(0, self.droprate["基础爆率"])
        total_itemDrop = itemDrop - fishing_itemDrop - player_itemDrop
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
            aiidr = fiidr + piidr
            aeidr = feidr + peidr
            asidr = fsidr + psidr
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
            self.show_suc(
                name,
                f"噗噗~只钓到了 {quality} §r§f的 {item['名字']} §r真是笨蛋杂鱼呢~",
            )
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

    @utils.timer_event(1, "每秒事件")
    def on_second_event(self):
        self.game_ctrl.sendwocmd(
            "/scoreboard players remove @a[scores={玩家_冷却计时=1..}] 玩家_冷却计时 1"
        )

    @utils.thread_func("钓鱼检测")
    def on_player_message(self, chat: Chat):
        player = chat.player
        name = player.name
        msg = chat.msg
        if msg != "Cat.Fishing":
            return
        isFishing = bool(
            self.game_ctrl.sendcmd_with_resp(
                f"/tag {name} remove Cat.Fishing"
            ).SuccessCount
        )
        if not isFishing:
            return self.show_war(
                name, "笨蛋杂鱼~ 以为这样就能作弊吗? 真是差劲呐~ 垃圾杂鱼~"
            )
        dim, x, y, z = player.getPos()
        if dim:
            return self.show_err(
                name, "真是杂鱼, 连只有在主世界才能钓鱼都不知道吗? 杂鱼~笨蛋杂鱼~"
            )
        (cd_time, fishing_num, fishing_cd, player_cr, fishing_num, player_num) = (
            utils.thread_gather(
                [
                    player.getScore,
                    ("玩家_冷却计时",),
                    player.getScore,
                    ("玩家_钓鱼次数",),
                    player.getScore,
                    ("鱼竿_钓鱼冷却",),
                    player.getScore,
                    ("玩家_钓鱼冷却",),
                    player.getScore,
                    ("鱼竿_连钓次数",),
                    player.getScore,
                    ("玩家_连钓次数",),
                ]
            )
        )
        if self.fishing_rod["是否启用冷却"]:
            if cd_time:
                for cmd in self.fishing_rod["钓鱼失败执行"]:
                    self.game_ctrl.sendwocmd(
                        utils.simple_fmt(
                            {
                                "[name]": name,
                            },
                            cmd,
                        )
                    )
                self.show_err(
                    name, f"还在冷却呢! 笨蛋杂鱼~ 冷却还剩§f{cd_time}§c秒 真是杂鱼呢~"
                )
                return
        if self.fishing_rod["是否限制次数"]:
            if not fishing_num:
                for cmd in self.fishing_rod["钓鱼失败执行"]:
                    self.game_ctrl.sendwocmd(
                        utils.simple_fmt(
                            {
                                "[name]": name,
                            },
                            cmd,
                        )
                    )
                self.show_err(name, "剩余次数用完了! 真是杂鱼呢~ 杂鱼~")
                return
            self.game_ctrl.sendwocmd(
                f"/scoreboard players remove {name} 玩家_钓鱼次数 1"
            )
        if self.fishing_rod["是否启用冷却"]:
            acd = fishing_cd * max(0, 1 - player_cr / 100)
            self.game_ctrl.sendwocmd(
                f"/scoreboard players set {name} 玩家_冷却计时 {acd}"
            )
        total_num = fishing_num + player_num
        for _ in range(total_num):
            self.fishing(player)

    def on_player_join(self, player: Player):
        isNewPlayer = bool(
            self.game_ctrl.sendcmd_with_resp(
                f"/tag {player.name} add Cat.initFishing"
            ).SuccessCount
        )
        if isNewPlayer:
            for sn in self.scoreboard:
                self.game_ctrl.sendwocmd(
                    f"/scoreboard players set {player.name} {sn} {self.scoreboard[sn]}"
                )


entry = plugin_entry(CatFishing)

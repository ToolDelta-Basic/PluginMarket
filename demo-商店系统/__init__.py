from tooldelta import Plugin, Config, game_utils, utils, plugin_entry


class Shop(Plugin):
    name = "demo-商店系统"
    author = "作者名"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        CONFIG_DEFAULT = {
            "货币计分板名": "money",
            "出售": {
                "钻石": {"ID": "diamond", "价格": 200},
                "绿宝石": {"ID": "emerald", "价格": 100},
            },
            "收购": {
                "铁锭": {
                    "ID": "iron_ingot",
                    "价格": 10,
                },
                "金锭": {"ID": "gold_ingot", "价格": 20},
            },
        }
        CONFIG_STD = {
            "货币计分板名": str,
            "出售": Config.AnyKeyValue(
                {
                    "ID": str,
                    "价格": Config.NNInt,
                }
            ),
            "收购": Config.AnyKeyValue(
                {
                    "ID": str,
                    "价格": Config.NNInt,
                }
            ),
        }
        # 读取配置, 没有配置就写入默认配置
        # cfg_version 我们不需要用到, 这个是插件配置版本号
        # 在这步如果配置文件出现异常, 不需要处理
        # ToolDelta 会自动处理并以优雅的方式显示问题
        cfg, cfg_version = Config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.money_scb_name = cfg["货币计分板名"]
        self.sells = cfg["出售"]
        self.buys = cfg["收购"]
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        # 导入前置插件只能在 on_def() 方法内使用
        # 这样, 当前置插件不存在的时候
        # ToolDelta 会显示前置插件不存在的报错
        self.chatbar = self.GetPluginAPI("聊天栏菜单")

    def on_inject(self):
        # 将玩家购买商品的触发词方法注册进聊天栏菜单
        # 输入 ".buy" 或者 "。购买" 或者 ".购买"
        # 就会执行 when_player_buy 回调 (传参: 玩家名, [])
        self.chatbar.add_trigger(
            ["购买", "buy"], None, "打开商店物品购买页面", self.when_player_buy
        )
        self.chatbar.add_trigger(
            ["收购", "sell"], None, "打开商店物品收购页面", self.when_player_sell
        )

    def when_player_buy(self, playername: str, _):
        # playername 传入玩家名
        # 由于触发词不需要参数, 因此可以舍弃这个参数 _
        # 先把所有出售的物品名整理成一个有序列表
        sells_list = list(self.sells.keys())
        if sells_list == []:
            self.game_ctrl.say_to(playername, "§c没有可购买的物品， 已退出")
            return
        # 然后向玩家展示
        self.game_ctrl.say_to(playername, "§6你想购买哪件商品？")
        for i, good_name in enumerate(sells_list):
            self.game_ctrl.say_to(playername, f"{i + 1}. {good_name}")
        self.game_ctrl.say_to(playername, "§6请输入选项序号以选择商品：")
        # 询问， 获取答复
        resp = game_utils.waitMsg(playername)
        # 如果超时了或者玩家在中途退出游戏
        if resp is None:
            self.game_ctrl.say_to(playername, "§c太久没有回应， 已退出")
            return
        # 回应太长
        elif len(resp) > 10:
            self.game_ctrl.say_to(playername, "§c输入过长， 已退出")
            return
        # 如果选项不合法
        # 回应不是数字; 或者不在范围内
        resp = utils.try_int(resp)
        if resp is None or resp not in range(1, len(sells_list) + 1):
            self.game_ctrl.say_to(playername, "§c选项不合法， 已退出")
            return
        good_to_buy = sells_list[resp - 1]
        good_id = self.sells[good_to_buy]["ID"]
        good_price = self.sells[good_to_buy]["价格"]
        # 询问需要购买多少个商品
        self.game_ctrl.say_to(playername, f"§6你需要购买多少个{good_to_buy}？")
        buy_count = utils.try_int(game_utils.waitMsg(playername))
        if buy_count is None:
            self.game_ctrl.say_to(playername, "§c输入有误， 已退出")
            return
        elif buy_count < 1:
            self.game_ctrl.say_to(playername, "§c商品数量不能小于1， 已退出")
            return
        # 计算总金额并进行处理
        price_total = good_price * buy_count
        # 使用 game_utils 提供的 getScore 获取玩家分数
        have_money = game_utils.getScore(self.money_scb_name, playername)
        if have_money < price_total:
            self.game_ctrl.say_to(
                playername,
                f"§c需要 §e{price_total}金币 §c才可以购买， 你只有 §e{have_money} 金币",
            )
        else:
            self.game_ctrl.sendwocmd(f'give "{playername}" {good_id} {buy_count}')
            self.game_ctrl.sendwocmd(
                f'scoreboard players remove "{playername}" {self.money_scb_name} {price_total}'
            )
            self.game_ctrl.say_to(
                playername, f"§a你成功购买了 {buy_count} 个 {good_to_buy}"
            )

    def when_player_sell(self, playername: str, _):
        buys_list = list(self.buys.keys())
        if buys_list == []:
            self.game_ctrl.say_to(playername, "§c没有可出售的物品， 已退出")
            return
        self.game_ctrl.say_to(playername, "§6你想出售哪件物品？")
        for i, good_name in enumerate(buys_list):
            self.game_ctrl.say_to(playername, f"{i + 1}. {good_name}")
        self.game_ctrl.say_to(playername, "§6请输入选项序号以选择：")
        resp = game_utils.waitMsg(playername)
        if resp is None:
            self.game_ctrl.say_to(playername, "§c太久没有回应， 已退出")
            return
        elif len(resp) > 10:
            self.game_ctrl.say_to(playername, "§c输入过长， 已退出")
            return
        resp = utils.try_int(resp)
        if resp is None or resp not in range(1, len(buys_list) + 1):
            self.game_ctrl.say_to(playername, "§c输入不合法， 已退出")
            return
        good_to_buy = buys_list[resp - 1]
        good_id = self.buys[good_to_buy]["ID"]
        good_price = self.buys[good_to_buy]["价格"]
        # 询问需要出售多少个物品
        self.game_ctrl.say_to(playername, f"§6你需要出售多少个{good_to_buy}？")
        sell_count = utils.try_int(game_utils.waitMsg(playername))
        if sell_count is None:
            self.game_ctrl.say_to(playername, "§c输入有误， 已退出")
            return
        elif sell_count < 1:
            self.game_ctrl.say_to(playername, "§c商品数量不能小于1， 已退出")
            return
        # 获取玩家物品数量
        have_good = game_utils.getItem(playername, good_id)
        if have_good < sell_count:
            self.game_ctrl.say_to(
                playername, f"§c你只有 {have_good} 个 {good_to_buy}， 无法出售， 已退出"
            )
        else:
            self.game_ctrl.sendwocmd(f'clear "{playername}" {good_id} 0 {sell_count}')
            self.game_ctrl.say_to(
                playername,
                f"§a你出售了 {sell_count} 个 {good_to_buy}， 获得 §e{good_price * sell_count} 金币",
            )
            self.game_ctrl.sendwocmd(
                f'scoreboard players add "{playername}" {self.money_scb_name} {good_price * sell_count}'
            )


entry = plugin_entry(Shop)

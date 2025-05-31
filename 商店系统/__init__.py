from tooldelta import Plugin, Config, utils, plugin_entry, TYPE_CHECKING


class Shop(Plugin):
    name = "demo-商店系统"
    author = "猫猫"
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

        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu

            self.chatbar = self.get_typecheck_plugin_api(ChatbarMenu)

    def on_inject(self):
        # 将玩家购买商品的触发词方法注册进聊天栏菜单
        # 输入 ".buy" 或者 "。购买" 或者 ".购买"
        # 就会执行 when_player_buy 回调 (传参: 玩家名, [])
        self.chatbar.add_trigger(
            ["购买", "buy"],
            "[商品名] [数量]",
            "打开商店物品购买页面",
            self.when_player_buy,
        )
        self.chatbar.add_trigger(
            ["出售", "sell"],
            "[商品名] [数量]",
            "打开商店物品出售页面",
            self.when_player_sell,
        )
        self.chatbar.add_trigger(
            ["搜索", "search"],
            "[商品名]",
            "打开商店物品搜索页面",
            self.when_player_search,
            lambda x: x == 1,
        )

    def show_inf(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§f!§7] §f{msg}")

    def show_suc(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§a√§7] §a{msg}")

    def show_war(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§6!§7] §6{msg}")

    def show_err(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§cx§7] §c{msg}")

    def show_page(self, player: str, items: list, page: int, price_dict=None):
        items_per_page = 10
        total_pages = (len(items) + items_per_page - 1) // items_per_page
        start_index = (page - 1) * items_per_page
        end_index = min(start_index + items_per_page, len(items))

        for i in range(start_index, end_index):
            good_name = items[i]
            if price_dict is None:
                good_price = ""
            else:
                good_price = price_dict[good_name]["价格"]
            self.game_ctrl.say_to(
                player,
                f"{i + 1}. {good_name} §a{str(good_price) + '¥' if price_dict is not None else ''}",
            )

        if total_pages > 1:
            self.game_ctrl.say_to(
                player,
                f"          §a{page}§7/§f{total_pages}\n§6输入 + 下一页，- 上一页",
            )
        self.game_ctrl.say_to(player, "§6请输入选项序号选择商品：")

    def when_player_buy(self, name: str, args: list):
        players = self.frame.get_players()
        player = players.getPlayerByName(name)
        sells_list = list(self.sells.keys())
        if sells_list == []:
            self.show_err(name, "§c没有可购买的物品， 已退出")
            return

        if args:
            good_name = args[0]
            if good_name in sells_list:
                good_to_buy = good_name
                good_id = self.sells[good_to_buy]["ID"]
                good_price = self.sells[good_to_buy]["价格"]
            else:
                self.show_err(name, f"§c商品'{good_name}'不存在")
                return
        else:
            current_page = 1
            while True:
                self.show_page(name, sells_list, current_page, self.sells)

                resp = player.input()

                if resp == "+":
                    total_pages = (len(sells_list) + 9) // 10
                    if current_page < total_pages:
                        current_page += 1
                    continue
                elif resp == "-":
                    if current_page > 1:
                        current_page -= 1
                    continue

                if resp is None:
                    self.show_err(name, "§c太久没有回应，已退出")
                    return
                if len(resp) > 10:
                    self.show_err(name, "§c输入过长，已退出")
                    return

                resp = utils.try_int(resp)
                if resp is None or resp not in range(1, len(sells_list) + 1):
                    self.show_err(name, "§c选项不合法，已退出")
                    return

                good_to_buy = sells_list[resp - 1]
                good_id = self.sells[good_to_buy]["ID"]
                good_price = self.sells[good_to_buy]["价格"]
                break

        if len(args) > 1:
            buy_count = utils.try_int(args[1])
            if buy_count is None:
                self.show_err(name, "§c数量参数无效， 已退出")
                return
        else:
            buy_count = utils.try_int(
                player.input(f"§6你需要购买多少个{good_to_buy}？")
            )
            if buy_count is None:
                self.show_err(name, "§c输入有误， 已退出")
                return

        if buy_count < 1:
            self.show_err(name, "§c商品数量不能小于1， 已退出")
            return

        price_total = good_price * buy_count
        have_money = player.getScore(self.money_scb_name)
        if have_money < price_total:
            self.show_err(
                name,
                f"§c需要 §e{price_total}猫猫币 §c才可以购买， 你只有 §e{have_money} 猫猫币",
            )
        else:
            if good_id.startswith("cmd:"):
                for _ in range(utils.try_int(buy_count)):
                    self.game_ctrl.sendwocmd(
                        utils.simple_fmt(
                            {
                                "[玩家名]": name,
                            },
                            good_id[4:],
                        )
                    )
            elif good_id.startswith("struct:"):
                for _ in range(utils.try_int(buy_count)):
                    self.game_ctrl.sendwocmd(
                        f"execute as {name} at @s run structure load {good_id[7:]} ~ ~ ~"
                    )
            else:
                self.game_ctrl.sendwocmd(f'give "{name}" {good_id} {buy_count}')
            self.game_ctrl.sendwocmd(
                f'scoreboard players remove "{name}" {self.money_scb_name} {price_total}'
            )
            self.show_suc(name, f"§a你成功购买了 {buy_count} 个 {good_to_buy}")

    def when_player_sell(self, name: str, args: list):
        players = self.frame.get_players()
        player = players.getPlayerByName(name)
        buys_list = list(self.buys.keys())
        if buys_list == []:
            self.show_err(name, "§c没有可出售的物品， 已退出")
            return

        if args:
            good_name = args[0]
            if good_name in buys_list:
                good_to_buy = good_name
                good_id = self.buys[good_to_buy]["ID"]
                good_price = self.buys[good_to_buy]["价格"]
            else:
                self.show_err(name, f"§c商品'{good_name}'不可出售")
                return
        else:
            current_page = 1
            while True:
                self.show_page(name, buys_list, current_page, self.buys)

                resp = player.input()

                if resp == "+":
                    total_pages = (len(buys_list) + 9) // 10
                    if current_page < total_pages:
                        current_page += 1
                    continue
                elif resp == "-":
                    if current_page > 1:
                        current_page -= 1
                    continue

                if resp is None:
                    self.show_err(name, "§c太久没有回应， 已退出")
                    return
                if len(resp) > 10:
                    self.show_err(name, "§c输入过长， 已退出")
                    return

                resp = utils.try_int(resp)
                if resp is None or resp not in range(1, len(buys_list) + 1):
                    self.show_err(name, "§c输入不合法， 已退出")
                    return

                good_to_buy = buys_list[resp - 1]
                good_id = self.buys[good_to_buy]["ID"]
                good_price = self.buys[good_to_buy]["价格"]
                break

        if len(args) > 1:
            sell_count = utils.try_int(args[1])
            if sell_count is None:
                self.show_err(name, "§c数量参数无效， 已退出")
                return
        else:
            sell_count = utils.try_int(
                player.input(f"§6你需要出售多少个{good_to_buy}？")
            )
            if sell_count is None:
                self.show_err(name, "§c输入有误， 已退出")
                return

        if sell_count < 1:
            self.show_err(name, "§c商品数量不能小于1， 已退出")
            return

        have_good = player.getItemCount(good_id)
        if have_good < sell_count:
            self.show_err(
                name, f"§c你只有 {have_good} 个 {good_to_buy}， 无法出售， 已退出"
            )
        else:
            self.game_ctrl.sendwocmd(f'clear "{name}" {good_id} 0 {sell_count}')
            self.show_suc(
                name,
                f"§a你出售了 {sell_count} 个 {good_to_buy}， 获得 §e{good_price * sell_count} 猫猫币",
            )
            self.game_ctrl.sendwocmd(
                f'scoreboard players add "{name}" {self.money_scb_name} {good_price * sell_count}'
            )

    def when_player_search(self, name: str, args: list):
        players = self.frame.get_players()
        player = players.getPlayerByName(name)
        if not player:
            self.show_err(name, "§c玩家不在线")
            return
        if not args or not args[0].strip():
            self.show_err(name, "§c请输入搜索关键词")
            return
        search_term = args[0].lower()
        sells_list = list(self.sells.keys())
        buys_list = list(self.buys.keys())
        all_items = list(set(sells_list + buys_list))
        matches = [item for item in all_items if search_term in item.lower()]
        if not matches:
            self.show_err(name, f"§c没有找到包含 '{args[0]}' 的商品")
            return

        current_page = 1
        while True:
            self.show_page(name, matches, current_page)
            resp = player.input()
            if resp == "+":
                total_pages = (len(matches) + 9) // 10
                if current_page < total_pages:
                    current_page += 1
                continue
            elif resp == "-":
                if current_page > 1:
                    current_page -= 1
                continue
            if resp is None:
                self.show_err(name, "§c太久没有回应，已退出")
                return
            if len(resp) > 10:
                self.show_err(name, "§c输入过长，已退出")
                return
            resp_num = utils.try_int(resp)
            if resp_num is None:
                self.show_err(name, "§c请输入有效数字")
                continue

            if resp_num < 1 or resp_num > len(matches):
                self.show_err(name, f"§c请输入1-{len(matches)}之间的数字")
                continue
            selected_item = matches[resp_num - 1]
            resp_action = player.input(
                f"§6请选择操作: §a1.购买 [{selected_item}] §f| §a2.出售 [{selected_item}] §f| §c其他.取消"
            )

            if resp_action == "1":
                if selected_item in self.sells:
                    self.when_player_buy(name, [selected_item])
                else:
                    self.show_err(name, f"§c商品 '{selected_item}' 不可购买")
            elif resp_action == "2":
                if selected_item in self.buys:
                    self.when_player_sell(name, [selected_item])
                else:
                    self.show_err(name, f"§c商品 '{selected_item}' 不可出售")
            else:
                self.show_inf(name, "§a已取消操作")
            break


entry = plugin_entry(Shop)

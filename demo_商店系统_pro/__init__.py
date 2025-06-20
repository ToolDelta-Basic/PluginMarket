from tooldelta import Plugin, Config, game_utils, utils, Player, plugin_entry, TYPE_CHECKING
import json
import os
from datetime import datetime


class Shop(Plugin):
    name = "demo_商店系统_pro"
    author = "帥気的男主角"
    version = (0, 2, 0)

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
        
        # 初始化交易记录数据文件
        self.data_dir = os.path.join(os.path.dirname(__file__), "shop_data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.trade_records_file = os.path.join(self.data_dir, "trade_records.json")
        
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        # 导入前置插件只能在 on_def() 方法内使用
        # 这样, 当前置插件不存在的时候
        # ToolDelta 会显示前置插件不存在的报错
        self.chatbar = self.GetPluginAPI("聊天栏菜单")

        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu
            self.chatbar: ChatbarMenu

    def on_inject(self):
        # 将玩家购买商品的触发词方法注册进聊天栏菜单
        # 输入 ".buy" 或者 "。购买" 或者 ".购买"
        # 就会执行 when_player_buy 回调 (传参: 玩家名, [])
        self.chatbar.add_trigger(  # Updated method name
            ["购买", "buy", "买东西", "购物"], [], "打开商店物品购买页面", self.when_player_buy
        )
        self.chatbar.add_trigger(  # Updated method name
            ["收购", "sell", "回收", "卖东西"], [], "打开商店物品收购页面", self.when_player_sell
        )
        # 添加带参数的搜索功能
        self.chatbar.add_trigger(
            ["查询购买"], ["物品关键词"], "搜索并购买指定物品", self.search_and_buy
        )
        self.chatbar.add_trigger(
            ["查询回收"], ["物品关键词"], "搜索并回收指定物品", self.search_and_sell
        )
        # 添加查看交易历史的功能
        self.chatbar.add_trigger(
            ["交易记录", "交易历史", "history", "记录"], [], "查看你的交易历史记录", self.show_trade_history
        )

    def when_player_buy(self, player, _):
        # 确保 player 是 Player 对象
        if isinstance(player, str):
            player = self.game_ctrl.players.getPlayerByName(player)
            if player is None:
                return  # 玩家不存在，直接返回

        # 获取可购买的商品列表
        sells_list = list(self.sells.keys())
        if not sells_list:
            player.show("§c没有可购买的物品， 已退出")
            return

        # 提示用户可以使用搜索功能
        player.show("§b▂▂▂ 商店购买系统 ▂▂▂")
        player.show("§7提示：你也可以使用 §6'查询购买 <物品关键词>' §7来快速搜索物品")
        player.show("§7例如：§6查询购买 钻石、查询购买 绿宝石 §7等")
        player.show("§b▂▂▂▂▂▂▂▂▂▂▂▂▂")

        page = 0  # 当前页码
        items_per_page = 8  # 每页显示8个物品
        
        while True:
            # 计算当前页的商品
            start_idx = page * items_per_page
            end_idx = min(start_idx + items_per_page, len(sells_list))
            current_page_items = sells_list[start_idx:end_idx]
            
            if not current_page_items:
                page = max(0, page - 1)  # 如果当前页没有物品，回到上一页
                continue
            
            # 显示商品列表
            player.show(f"§6你想购买哪件商品？ §u(第{page + 1}页/共{(len(sells_list) + items_per_page - 1) // items_per_page}页)\n§7▂▂▂▂▂▂▂▂▂▂▂▂▂")
            for i, good_name in enumerate(current_page_items):
                price = self.sells[good_name]["价格"]
                player.show(f"{i + 1}. {good_name} (§e$§l{price}§r§g星梦币§b/个)")
            
            # 显示翻页选项
            page_options = []
            if page > 0:
                page_options.append("0. 上一页")
            if end_idx < len(sells_list):
                page_options.append("9. 下一页")
            
            for option in page_options:
                player.show(f"§a{option}")
            
            player.show("§7▂▂▂▂▂▂▂▂▂▂▂▂▂\n§6请输入选项序号以选择商品（输入\"取消\"退出）：")

            # 等待玩家输入
            try:
                resp_str = player.input(timeout=30)
                if resp_str is None:
                    player.show("§c太久没有回应， 已退出")
                    return
                elif len(resp_str) > 10:
                    player.show("§c输入过长， 已退出")
                    return
                # 检查是否输入取消
                if resp_str.strip() in ["取消", "cancel", "退出", "exit"]:
                    player.show("§a已取消购买操作")
                    return
                resp = utils.try_int(resp_str)
                if resp is None:
                    player.show("§c输入不合法， 请重新选择")
                    continue
                
                # 处理翻页
                if resp == 0 and page > 0:
                    page -= 1
                    continue
                elif resp == 9 and end_idx < len(sells_list):
                    page += 1
                    continue
                elif resp in range(1, len(current_page_items) + 1):
                    # 选择了有效的商品
                    break
                else:
                    player.show("§c选项不合法， 请重新选择")
                    continue
                    
            except TimeoutError:
                player.show("§c输入超时， 已退出")
                return

        # 获取玩家选择的商品
        good_to_buy = current_page_items[resp - 1]  # 使用当前页的商品列表
        good_id = self.sells[good_to_buy]["ID"]
        good_price = self.sells[good_to_buy]["价格"]

        # 询问购买数量
        try:
            count_str = player.input(f"§6你需要购买多少个{good_to_buy}？（如需购买一组则输入65，输入\"取消\"退出）")
            if count_str is None:
                player.show("§c输入超时， 已退出")
                return
            # 检查是否输入取消
            if count_str.strip() in ["取消", "cancel", "退出", "exit"]:
                player.show("§a已取消购买操作")
                return
            buy_count = utils.try_int(count_str)
            if buy_count is None or buy_count < 1:
                player.show("§c商品数量无效， 已退出")
                return
            if buy_count > 64:
                buy_count = 64

        except TimeoutError:
            player.show("§c输入超时， 已退出")
            return

        # 检查玩家金币是否足够
        price_total = good_price * buy_count
        try:
            have_money = player.getScore(self.money_scb_name)
            if have_money < price_total:
                player.show(f"§c需要 §e{price_total}金币 §c才可以购买， 你只有 §e{have_money} 金币")
                return
        except ValueError:
            player.show("§c无法获取你的金币信息， 已退出")
            return


        # 执行购买操作
        self.game_ctrl.sendwocmd(f'give "{player.name}" {good_id} {buy_count}')
        self.game_ctrl.sendwocmd(
            f'scoreboard players remove "{player.name}" {self.money_scb_name} {price_total}'
        )
        player.show(f"§a你成功购买了 {buy_count} 个 {good_to_buy}")
        
        # 保存交易记录
        self.save_trade_record(
            player.name, "purchase", good_to_buy, good_id, 
            buy_count, good_price, price_total
        )


    def when_player_sell(self, player, _):
        # 确保 player 是 Player 对象
        if isinstance(player, str):
            player = self.game_ctrl.players.getPlayerByName(player)
            if player is None:
                return  # 玩家不存在，直接返回

        # 获取可出售的物品列表
        buys_list = list(self.buys.keys())
        if not buys_list:
            player.show("§c没有可出售的物品， 已退出")
            return

        # 提示用户可以使用搜索功能
        player.show("§b▂▂▂ 商店回收系统 ▂▂▂")
        player.show("§7提示：你也可以使用 §6'查询回收 <物品关键词>' §7来快速搜索物品")
        player.show("§7例如：§6查询回收 铁锭、查询回收 钻石 §7等")
        player.show("§b▂▂▂▂▂▂▂▂▂▂▂▂▂")

        page = 0  # 当前页码
        items_per_page = 8  # 每页显示8个物品
        
        while True:
            # 计算当前页的物品
            start_idx = page * items_per_page
            end_idx = min(start_idx + items_per_page, len(buys_list))
            current_page_items = buys_list[start_idx:end_idx]
            
            if not current_page_items:
                page = max(0, page - 1)  # 如果当前页没有物品，回到上一页
                continue
            
            # 显示可出售的物品列表
            player.show(f"§6你想出售哪件物品？ (第{page + 1}页/共{(len(buys_list) + items_per_page - 1) // items_per_page}页)\n§7▂▂▂▂▂▂▂▂▂▂▂▂▂")
            for i, good_name in enumerate(current_page_items):
                price = self.buys[good_name]["价格"]
                player.show(f"{i + 1}. {good_name} (§e$§l{price}§r§g星梦币§b/个)")
            
            # 显示翻页选项
            page_options = []
            if page > 0:
                page_options.append("0. 上一页")
            if end_idx < len(buys_list):
                page_options.append("9. 下一页")
            
            for option in page_options:
                player.show(f"§a{option}")
            
            player.show("§7▂▂▂▂▂▂▂▂▂▂▂▂▂\n§6请输入选项序号以选择（输入\"取消\"退出）：")

            # 等待玩家输入
            try:
                resp_str = player.input(timeout=30)
                if resp_str is None:
                    player.show("§c太久没有回应， 已退出")
                    return
                elif len(resp_str) > 10:
                    player.show("§c输入过长， 已退出")
                    return
                # 检查是否输入取消
                if resp_str.strip() in ["取消", "cancel", "退出", "exit"]:
                    player.show("§a已取消出售操作")
                    return
                resp = utils.try_int(resp_str)
                if resp is None:
                    player.show("§c输入不合法， 请重新选择")
                    continue
                
                # 处理翻页
                if resp == 0 and page > 0:
                    page -= 1
                    continue
                elif resp == 9 and end_idx < len(buys_list):
                    page += 1
                    continue
                elif resp in range(1, len(current_page_items) + 1):
                    # 选择了有效的物品
                    break
                else:
                    player.show("§c输入不合法， 请重新选择")
                    continue

            except TimeoutError:
                player.show("§c输入超时， 已退出")
                return

        # 获取玩家选择的物品
        good_to_sell = current_page_items[resp - 1]  # 使用当前页的物品列表
        good_id = self.buys[good_to_sell]["ID"]
        good_price = self.buys[good_to_sell]["价格"]

        # 询问出售数量
        try:
            count_str = player.input(f"§6你需要出售多少个{good_to_sell}？（如需出售一组则输入65，输入\"取消\"退出）")
            if count_str is None:
                player.show("§c输入超时， 已退出")
                return
            # 检查是否输入取消
            if count_str.strip() in ["取消", "cancel", "退出", "exit"]:
                player.show("§a已取消出售操作")
                return
            sell_count = utils.try_int(count_str)
            if sell_count is None or sell_count < 1:
                player.show("§c商品数量无效， 已退出")
                return
            if sell_count > 64:
                sell_count = 64
                player.show("§c出售数量超过64， 已自动调整为64")

        except TimeoutError:
            player.show("§c输入超时， 已退出")
            return

        # 检查玩家是否有足够的物品
        try:
            have_good = player.getItemCount(good_id)
            if have_good < sell_count:
                player.show(f"§c你只有 {have_good} 个 {good_to_sell}， 无法出售， 已退出")
                return
        except ValueError:
            player.show("§c无法获取你的物品信息， 已退出")
            return

        # 执行出售操作
        sell_total = good_price * sell_count
        self.game_ctrl.sendwocmd(f'clear "{player.name}" {good_id} 0 {sell_count}')
        self.game_ctrl.sendwocmd(
            f'scoreboard players add "{player.name}" {self.money_scb_name} {sell_total}'
        )
        player.show(f"§a你出售了 {sell_count} 个 {good_to_sell}， 获得 §e{sell_total} 金币")
        
        # 保存交易记录
        self.save_trade_record(
            player.name, "sell", good_to_sell, good_id, 
            sell_count, good_price, sell_total
        )
        
        # 检查玩家是否还有该物品，如果有则询问是否继续回收
        self.check_and_continue_selling(player, good_to_sell, good_id, good_price)

    def search_items(self, keyword, item_dict):
        """根据关键词搜索物品"""
        matching_items = []
        keyword_lower = keyword.lower()
        
        for item_name, item_info in item_dict.items():
            # 检查物品名称和ID是否包含关键词
            if (keyword_lower in item_name.lower() or 
                keyword_lower in item_info["ID"].lower()):
                matching_items.append(item_name)
        
        return matching_items

    def search_and_buy(self, player, args):
        """搜索并购买物品"""
        # 确保 player 是 Player 对象
        if isinstance(player, str):
            player = self.game_ctrl.players.getPlayerByName(player)
            if player is None:
                return  # 玩家不存在，直接返回

        if not args or len(args) == 0:
            player.show("§c请输入要搜索的物品关键词，例如：查询购买 钻石")
            return

        keyword = args[0]
        matching_items = self.search_items(keyword, self.sells)
        
        if not matching_items:
            player.show(f"§c没有找到包含关键词 '{keyword}' 的可购买物品")
            player.show("§7提示：你可以使用 '购买' 命令查看所有可购买的物品")
            return
        
        if len(matching_items) == 1:
            # 只有一个匹配项，直接购买
            self.buy_specific_item(player, matching_items[0])
        else:
            # 多个匹配项，让玩家选择
            self.select_from_matches(player, matching_items, "购买", self.buy_specific_item)

    def search_and_sell(self, player, args):
        """搜索并回收物品"""
        # 确保 player 是 Player 对象
        if isinstance(player, str):
            player = self.game_ctrl.players.getPlayerByName(player)
            if player is None:
                return  # 玩家不存在，直接返回

        if not args or len(args) == 0:
            player.show("§c请输入要搜索的物品关键词，例如：查询回收 铁锭")
            return

        keyword = args[0]
        matching_items = self.search_items(keyword, self.buys)
        
        if not matching_items:
            player.show(f"§c没有找到包含关键词 '{keyword}' 的可回收物品")
            player.show("§7提示：你可以使用 '回收' 命令查看所有可回收的物品")
            return
        
        if len(matching_items) == 1:
            # 只有一个匹配项，直接回收
            self.sell_specific_item(player, matching_items[0])
        else:
            # 多个匹配项，让玩家选择
            self.select_from_matches(player, matching_items, "回收", self.sell_specific_item)

    def select_from_matches(self, player, matching_items, action_type, callback):
        """从匹配的物品中选择一个"""
        player.show(f"§6找到多个包含该关键词的{action_type}物品：")
        player.show("§7▂▂▂▂▂▂▂▂▂▂▂▂▂")
        
        for i, item_name in enumerate(matching_items):
            if action_type == "购买":
                price = self.sells[item_name]["价格"]
            else:
                price = self.buys[item_name]["价格"]
            player.show(f"{i + 1}. {item_name} (§e$§l{price}§r§g星梦币§b/个)")
        
        player.show("§7▂▂▂▂▂▂▂▂▂▂▂▂▂")
        player.show(f"§6请输入选项序号选择要{action_type}的物品（输入\"取消\"退出）：")

        try:
            resp_str = player.input(timeout=30)
            if resp_str is None:
                player.show("§c太久没有回应，已退出")
                return
            elif len(resp_str) > 10:
                player.show("§c输入过长，已退出")
                return
            
            if resp_str.strip() in ["取消", "cancel", "退出", "exit"]:
                player.show(f"§a已取消{action_type}操作")
                return
                
            resp = utils.try_int(resp_str)
            if resp is None or resp < 1 or resp > len(matching_items):
                player.show("§c选项不合法，已退出")
                return
            
            selected_item = matching_items[resp - 1]
            callback(player, selected_item)
            
        except TimeoutError:
            player.show("§c输入超时，已退出")
            return

    def buy_specific_item(self, player, good_name):
        """购买指定物品"""
        good_id = self.sells[good_name]["ID"]
        good_price = self.sells[good_name]["价格"]

        # 询问购买数量
        try:
            count_str = player.input(f"§6你需要购买多少个{good_name}？（如需购买一组则输入65，输入\"取消\"退出）")
            if count_str is None:
                player.show("§c输入超时，已退出")
                return
            # 检查是否输入取消
            if count_str.strip() in ["取消", "cancel", "退出", "exit"]:
                player.show("§a已取消购买操作")
                return
            buy_count = utils.try_int(count_str)
            if buy_count is None or buy_count < 1:
                player.show("§c商品数量无效，已退出")
                return
            if buy_count > 64:
                buy_count = 64

        except TimeoutError:
            player.show("§c输入超时，已退出")
            return

        # 检查玩家金币是否足够
        price_total = good_price * buy_count
        try:
            have_money = player.getScore(self.money_scb_name)
            if have_money < price_total:
                player.show(f"§c需要 §e{price_total}金币 §c才可以购买，你只有 §e{have_money} 金币")
                return
        except ValueError:
            player.show("§c无法获取你的金币信息，已退出")
            return

        # 执行购买操作
        self.game_ctrl.sendwocmd(f'give "{player.name}" {good_id} {buy_count}')
        self.game_ctrl.sendwocmd(
            f'scoreboard players remove "{player.name}" {self.money_scb_name} {price_total}'
        )
        player.show(f"§a你成功购买了 {buy_count} 个 {good_name}")
        
        # 保存交易记录
        self.save_trade_record(
            player.name, "purchase", good_name, good_id, 
            buy_count, good_price, price_total
        )

    def sell_specific_item(self, player, good_name):
        """回收指定物品"""
        good_id = self.buys[good_name]["ID"]
        good_price = self.buys[good_name]["价格"]

        # 询问出售数量
        try:
            count_str = player.input(f"§6你需要出售多少个{good_name}？（如需出售一组则输入65，输入\"取消\"退出）")
            if count_str is None:
                player.show("§c输入超时，已退出")
                return
            # 检查是否输入取消
            if count_str.strip() in ["取消", "cancel", "退出", "exit"]:
                player.show("§a已取消出售操作")
                return
            sell_count = utils.try_int(count_str)
            if sell_count is None or sell_count < 1:
                player.show("§c商品数量无效，已退出")
                return
            if sell_count > 64:
                sell_count = 64
                player.show("§c出售数量超过64，已自动调整为64")

        except TimeoutError:
            player.show("§c输入超时，已退出")
            return

        # 检查玩家是否有足够的物品
        try:
            have_good = player.getItemCount(good_id)
            if have_good < sell_count:
                player.show(f"§c你只有 {have_good} 个 {good_name}，无法出售，已退出")
                return
        except ValueError:
            player.show("§c无法获取你的物品信息，已退出")
            return

        # 执行出售操作
        sell_total = good_price * sell_count
        self.game_ctrl.sendwocmd(f'clear "{player.name}" {good_id} 0 {sell_count}')
        self.game_ctrl.sendwocmd(
            f'scoreboard players add "{player.name}" {self.money_scb_name} {sell_total}'
        )
        player.show(f"§a你出售了 {sell_count} 个 {good_name}，获得 §e{sell_total} 金币")
        
        # 保存交易记录
        self.save_trade_record(
            player.name, "sell", good_name, good_id, 
            sell_count, good_price, sell_total
        )
        
        # 检查玩家是否还有该物品，如果有则询问是否继续回收
        self.check_and_continue_selling(player, good_name, good_id, good_price)

    def check_and_continue_selling(self, player, good_name, good_id, good_price):
        """检查玩家是否还有该物品，如果有则询问是否继续回收"""
        try:
            # 检查玩家是否还有该物品
            remaining_count = player.getItemCount(good_id)
            if remaining_count > 0:
                player.show(f"§6检测到你还有 {remaining_count} 个 {good_name}")
                player.show("§6是否继续回收该物品？")
                player.show("§a输入 'y' 或 '是' 继续回收")
                player.show("§c输入 'n' 或 '否' 取消回收")
                
                try:
                    # 设置20秒超时，给玩家足够时间思考
                    response = player.input("§6请选择 (y/n)：", timeout=20)
                    if response is None:
                        player.show("§c长时间未回答，已取消继续回收")
                        return
                    
                    response = response.strip().lower()
                    if response in ['y', 'yes', '是', '继续', '1']:
                        # 玩家选择继续回收，调用单个物品回收方法
                        self.sell_specific_item(player, good_name)
                    elif response in ['n', 'no', '否', '取消', '0']:
                        player.show("§a已取消继续回收操作")
                    else:
                        player.show("§c输入无效，已取消继续回收操作")
                        
                except TimeoutError:
                    player.show("§c输入超时，已取消继续回收操作")
                    
        except ValueError:
            # 如果无法获取物品信息，静默处理，不影响正常流程
            pass

    def save_trade_record(self, player_name, action, item_name, item_id, quantity, unit_price, total_amount):
        """保存交易记录到数据文件"""
        try:
            # 读取现有记录
            trade_records = self.load_trade_records()
            
            # 创建新的交易记录
            trade_record = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "player": player_name,
                "action": action,  # "purchase" 或 "sell"
                "item_name": item_name,
                "item_id": item_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_amount": total_amount
            }
            
            # 如果玩家记录不存在，创建新的
            if player_name not in trade_records:
                trade_records[player_name] = []
            
            # 添加交易记录
            trade_records[player_name].append(trade_record)
            
            # 保存到文件
            with open(self.trade_records_file, 'w', encoding='utf-8') as f:
                json.dump(trade_records, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            # 如果保存失败，至少在控制台记录错误
            self.print(f"保存交易记录失败: {e}")

    def load_trade_records(self):
        """从数据文件读取交易记录"""
        try:
            if os.path.exists(self.trade_records_file):
                with open(self.trade_records_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {}
        except Exception as e:
            self.print(f"保存交易记录失败: {e}")
            return {}

    def get_player_trade_history(self, player_name, limit=10):
        """
        function: 获取玩家的交易历史记录
        detail: 把玩家的交易历史记录从文件中读取并返回
        """
        trade_records = self.load_trade_records()
        player_records = trade_records.get(player_name, [])
        
        # 按时间戳倒序排列，返回最近的记录
        player_records.sort(key=lambda x: x["timestamp"], reverse=True)
        return player_records[:limit]

    def show_trade_history(self, player):
        """
        function: 显示玩家的交易历史
        detail: 把玩家的交易历史保存在文件里面，管理员可以查看
        """
        # 确保 player 是 Player 对象
        if isinstance(player, str):
            player = self.game_ctrl.players.getPlayerByName(player)
            if player is None:
                return

        history = self.get_player_trade_history(player.name, 15)
        
        if not history:
            player.show("§c你还没有任何交易记录")
            return

        player.show("§b▂▂ 你的交易历史记录 ▂▂")
        player.show("§7(显示最近15条记录)")
        player.show("§7▂▂▂▂▂▂▂▂▂▂▂▂▂")

        for record in history:
            action_text = "§a购买" if record["action"] == "purchase" else "§e出售"
            timestamp = record["timestamp"]
            item_name = record["item_name"]
            quantity = record["quantity"]
            unit_price = record["unit_price"]
            total_amount = record["total_amount"]
            
            player.show(f"§7[{timestamp}]")
            player.show(f"{action_text}§r {item_name} x{quantity}")
            player.show(f"§7单价: §e{unit_price}金币 §7总计: §e{total_amount}金币")
            player.show("§7▂▂▂▂▂▂▂▂▂▂▂▂")
        
        player.show("§b▂▂▂▂▂▂▂▂▂▂▂▂▂")


entry = plugin_entry(Shop)

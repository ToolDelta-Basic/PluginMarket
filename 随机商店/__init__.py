

from tooldelta import Plugin, plugin_entry, cfg, game_utils, utils, fmts, Player, Chat
from tooldelta.utils import tempjson
import os
import json
import threading
import time
import random
import math

class Random_Shop(Plugin):
    name = "随机商店"
    author = "伊嘉" #反馈请加3302988965 
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.data_file_path = self.format_data_path("商品清单.json")
        self.runtime_config_path = self.format_data_path("运行数据.json")
        self._file_lock = threading.Lock()
        self.init_product_data()
        self.init_runtime_config()

        # 聊天监听触发商店/强制刷新
        self.ListenChat(self.on_chat_trigger)

        # 启动计时器线程
        self.counter_running = True
        self.ListenFrameExit(lambda _: self.stop_counter())
        self.start_counter()

    def init_product_data(self):
        default_data = [
            {
                "商品显示名称": "泥土",
                "权重": 1,
                "货币显示名称": "通用货币",
                "货币实际名称": "§k§emoney",
                "单价随机下限": 1,
                "单价随机上限": 10,
                "个人限购": 10,
                "全服限购": 10,
                "单次购买数量下限": 1,
                "单次购买数量上限": 10,
                "限购实际数量": True,
                "是否自定义购买后的执行命令": False,
                "商品实际名称": "dirt",
                "商品数据值": 0,
                "自定义命令": "/give [player] dirt [amount]",
                "是否启用多次执行": False
            },
            {
                "商品显示名称": "泥土",
                "权重": 2,
                "货币显示名称": "通用货币",
                "货币实际名称": "§k§emoney",
                "单价随机下限": 11,
                "单价随机上限": 101,
                "个人限购": 1011,
                "全服限购": 1011,
                "单次购买数量下限": 11,
                "单次购买数量上限": 101,
                "限购实际数量": True,
                "是否自定义购买后的执行命令": True,
                "商品实际名称": "dirt",
                "商品数据值": 0,
                "自定义命令": "/give [player] dirt [amount]",
                "是否启用多次执行": False
            }
        ]
        if not os.path.exists(self.data_file_path):
            with open(self.data_file_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, ensure_ascii=False, indent=4)
            fmts.print_inf(f"商品清单文件已创建：{self.data_file_path}")
        else:
            with open(self.data_file_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    if not data:
                        with open(self.data_file_path, "w", encoding="utf-8") as f2:
                            json.dump(default_data, f2, ensure_ascii=False, indent=4)
                        fmts.print_inf(f"商品清单文件为空，已重置：{self.data_file_path}")
                except json.JSONDecodeError:
                    with open(self.data_file_path, "w", encoding="utf-8") as f2:
                        json.dump(default_data, f2, ensure_ascii=False, indent=4)
                    fmts.print_war(f"商品清单文件格式错误，已重置：{self.data_file_path}")

    def stop_counter(self):
        """安全停止商店刷新计时器线程"""
        try:
            self.counter_running = False
            fmts.print_inf("商店刷新计时器线程已标记停止")
        except Exception as e:
            fmts.print_err(f"停止计时器线程时出错: {e}")


    def init_runtime_config(self):
        with open(self.data_file_path, "r", encoding="utf-8") as f:
            product_list = json.load(f)
            product_count = len(product_list)
        default_config = {
            "单次随机商品数量": 1,
            "随机周期": 60,
            "刷新提示": "随机商店已刷新",
            "计数器": 0,
            "当前商品清单": [],
            "限购记录": {
                "全服限购": [0] * product_count,
                "个人限购": {}
            }
        }
        if not os.path.exists(self.runtime_config_path):
            with open(self.runtime_config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            fmts.print_inf(f"运行数据文件已创建：{self.runtime_config_path}")
        else:
            with open(self.runtime_config_path, "r", encoding="utf-8") as f:
                try:
                    config = json.load(f)
                    if not isinstance(config, dict):
                        raise ValueError()
                    fmts.print_inf(f"运行数据文件加载成功：{self.runtime_config_path}")
                except (json.JSONDecodeError, ValueError):
                    with open(self.runtime_config_path, "w", encoding="utf-8") as f2:
                        json.dump(default_config, f2, ensure_ascii=False, indent=4)
                    fmts.print_war(f"运行数据文件格式错误或字段缺失，已重置：{self.runtime_config_path}")

    def atomic_modify_runtime_config(self, modifier_func):
        with self._file_lock:
            with open(self.runtime_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            new_config = modifier_func(config)
            with open(self.runtime_config_path, "w", encoding="utf-8") as f:
                json.dump(new_config, f, ensure_ascii=False, indent=4)
            return new_config

    def load_runtime_config(self):
        with self._file_lock:
            with open(self.runtime_config_path, "r", encoding="utf-8") as f:
                return json.load(f)

    def refresh_shop(self):
        with open(self.data_file_path, "r", encoding="utf-8") as f:
            product_list = json.load(f)
        config = self.load_runtime_config()
        product_count = len(product_list)
        weights = [p.get("权重", 1) for p in product_list]
        k = min(config["单次随机商品数量"], product_count)

        # 基于索引去重 + 权重概率选择
        available_indices = list(range(product_count))
        chosen_indices = []
        for _ in range(k):
            chosen = random.choices(
                available_indices,
                weights=[weights[i] for i in available_indices],
                k=1
            )[0]
            chosen_indices.append(chosen)
            available_indices.remove(chosen)

        current_shop = []
        for idx in chosen_indices:
            product = product_list[idx].copy()
            # 随机价格
            low_price = product.get("单价随机下限", 1)
            high_price = product.get("单价随机上限", low_price)
            if high_price < low_price:
                high_price = low_price
            product["单价"] = random.randint(low_price, high_price)
            # 随机打包数量
            min_qty = max(1, product.get("单次购买数量下限", 1))
            max_qty = max(min_qty, product.get("单次购买数量上限", min_qty))
            if max_qty < min_qty:
                max_qty = min_qty
            product["打包数量"] = random.randint(min_qty, max_qty)
            current_shop.append(product)

        def update_cfg(cfg):
            cfg["当前商品清单"] = current_shop
            cfg["限购记录"]["全服限购"] = [0] * product_count
            cfg["限购记录"]["个人限购"] = {}  # 清空个人限购
            return cfg

        self.atomic_modify_runtime_config(update_cfg)
        self.game_ctrl.say_to("@a", config.get("刷新提示", "随机商店已刷新"))


    @utils.thread_func("商店刷新计时器线程")
    def start_counter(self):
        """使用 ToolDelta 装饰器创建循环计时器线程"""
        fmts.print_inf("一个商店计时器线程已启动")
        while self.counter_running:
            time.sleep(3)
            if not self.counter_running: break
            try:
                new_config = self.atomic_modify_runtime_config(lambda cfg: self._modify_counter(cfg))
                if new_config["计数器"] >= new_config["随机周期"]:
                    fmts.print_inf("开始刷新商店...")
                    self.refresh_shop()
                    self.atomic_modify_runtime_config(lambda cfg: self._reset_counter(cfg))
            except Exception as e:
                fmts.print_err(f"计数器处理出错: {e}")
            time.sleep(3)

    def _modify_counter(self, config):
        config["计数器"] += 1
        return config

    def _reset_counter(self, config):
        config["计数器"] = 0
        return config

    def on_chat_trigger(self, chat: Chat):
        msg = chat.msg.strip()
        player_name = chat.player.name
        if msg in ["Bshop", "黑市", "随机商店"]:
            self.shop_interaction(chat.player)
        elif msg == "强制刷新" and player_name == "TURU伊嘉":
            fmts.print_inf(f"玩家 {player_name} 发起强制刷新")
            self.refresh_shop()
            self.atomic_modify_runtime_config(lambda cfg: self._reset_counter(cfg))
            chat.player.show("§a商店已强制刷新完成")


    def shop_interaction(self, player: Player):
        shop_config = self.load_runtime_config()
        products = shop_config["当前商品清单"]
        product_count = len(products)
        if product_count == 0:
            player.show("§c当前商店没有商品")
            return

        player_name = player.name
        personal_limits = shop_config["限购记录"]["个人限购"].get(player_name)
        if personal_limits is None:
            personal_limits = [0] * product_count
            shop_config["限购记录"]["个人限购"][player_name] = personal_limits
            self.atomic_modify_runtime_config(lambda cfg: cfg)

        page_size = 10
        total_pages = math.ceil(product_count / page_size)
        current_page = 0

        def format_limit(used, total):
            if isinstance(total, int) and total > 0:
                return f"{used}/{total}"
            else:
                return "无限"

        def show_page(page_idx):
            player.show("§e============== 随机商店 ==============")
            start_idx = page_idx * page_size
            end_idx = min(start_idx + page_size, product_count)
            for i in range(start_idx, end_idx):
                p = products[i]
                g_used = shop_config["限购记录"]["全服限购"][i]
                g_total = p.get("全服限购", -1)
                p_used = personal_limits[i]
                p_total = p.get("个人限购", -1)
                pkg_qty = p.get("打包数量", 1)

                # 限购信息
                limit_str = f"个人:{format_limit(p_used, p_total)} 全服:{format_limit(g_used, g_total)}"

                # 判断价格和批量提示
                if pkg_qty == 1:
                    # 不打包，按单个计价
                    price_info = f"{p['单价']}/个"
                    extra_note = ""
                else:
                    # 打包，显示包价 + 批量提示
                    price_info = f"{p['单价'] * pkg_qty}元/{pkg_qty}个/包"
                    extra_note = " §c(必须整包购买)"

                # 输出商品信息
                player.show(
                    f"§6{i+1}. §f{p['商品显示名称']} - §e{price_info} {p['货币显示名称']} "
                    f"§7[限购 {limit_str}]{extra_note}"
                )

            player.show(f"§e页码: {page_idx+1}/{total_pages}  输入+下一页 -上一页 输入序号购买 其他退出")


        while True:
            show_page(current_page)
            resp = player.input("", timeout=60)
            if resp is None:
                player.show("§c操作超时，已退出商店")
                return
            resp = resp.strip()
            if resp == "+":
                if current_page + 1 < total_pages:
                    current_page += 1
                else:
                    player.show("§c已经是最后一页")
            elif resp == "-":
                if current_page > 0:
                    current_page -= 1
                else:
                    player.show("§c已经是第一页")
            elif resp.isdigit():
                idx = int(resp) - 1
                if 0 <= idx < product_count:
                    self.buy_product(player, idx)
                    return
                else:
                    player.show("§c没有该序号的商品")
            else:
                player.show("§e已退出商店")
                return

    def buy_product(self, player, product_index):
        shop_config = self.load_runtime_config()
        products = shop_config["当前商品清单"]
        product_count = len(products)
        if product_index < 0 or product_index >= product_count:
            player.show("§c商品不存在")
            return

        product = products[product_index]
        player_name = player.name
        personal_limits = shop_config["限购记录"]["个人限购"].get(player_name)
        if personal_limits is None:
            personal_limits = [0] * product_count
            shop_config["限购记录"]["个人限购"][player_name] = personal_limits

        global_limits = shop_config["限购记录"]["全服限购"]

      
        # 获取打包数量
        package_qty = product.get("打包数量", 1)

        if package_qty > 1:
            # 打包购买提示
            player.show(f"本商品为打包购买，每包 {package_qty} 个")
            pkg_resp = player.input(f"请输入购买包数(1包={package_qty}个)：", timeout=30)
        else:
            # 单个购买提示
            pkg_resp = player.input("请输入购买数量(至少 1 个)：", timeout=30)

        if pkg_resp is None:
            player.show("§c超时未输入，已取消购买")
            return

        try:
            package_count = int(pkg_resp)
        except ValueError:
            player.show("§c输入无效，已取消购买")
            return

        if package_count <= 0:
            player.show("§c购买数量必须大于0")
            return

        buy_qty = package_qty * package_count


        # 限购判断
        if product.get("限购实际数量", True):
            # 按实际数量判断
            if isinstance(product.get("全服限购"), int) and product["全服限购"] > 0:
                if global_limits[product_index] + buy_qty > product["全服限购"]:
                    player.show("§c购买数量超过全服限购剩余数量")
                    return
            if isinstance(product.get("个人限购"), int) and product["个人限购"] > 0:
                if personal_limits[product_index] + buy_qty > product["个人限购"]:
                    player.show("§c购买数量超过个人限购剩余数量")
                    return
        else:
            # 按购买次数判断
            if isinstance(product.get("全服限购"), int) and product["全服限购"] > 0:
                if global_limits[product_index] + package_count > product["全服限购"]:
                    player.show("§c购买次数超过全服限购剩余次数")
                    return
            if isinstance(product.get("个人限购"), int) and product["个人限购"] > 0:
                if personal_limits[product_index] + package_count > product["个人限购"]:
                    player.show("§c购买次数超过个人限购剩余次数")
                    return

        # 检查余额
        try:
            money = game_utils.getScore(product["货币实际名称"], player_name)
        except Exception:
            player.show(f"§c无法获取你的 {product['货币显示名称']} 余额")
            return

        total_price = product["单价"] * buy_qty
        if money < total_price:
            player.show(f"§c你的{product['货币显示名称']}不足，需要 {total_price}，你只有 {money}")
            return

        # 扣钱
        self.game_ctrl.sendwocmd(f'scoreboard players remove "{player_name}" {product["货币实际名称"]} {total_price}')

        # 发货
        if not product.get("是否自定义购买后的执行命令", False):
            self.game_ctrl.sendwocmd(f'give "{player_name}" {product["商品实际名称"]} {buy_qty} {product["商品数据值"]}')
        else:
            cmd = product["自定义命令"].replace("[player]", player_name).replace("[amount]", str(buy_qty))
            if product.get("是否启用多次执行", False):
                for _ in range(buy_qty):
                    self.game_ctrl.sendwocmd(cmd)
            else:
                self.game_ctrl.sendwocmd(cmd)

        # 更新限购记录（区分数量模式和次数模式）
        if product.get("限购实际数量", True):
            global_limits[product_index] += buy_qty
            personal_limits[product_index] += buy_qty
        else:
            global_limits[product_index] += package_count
            personal_limits[product_index] += package_count

        shop_config["限购记录"]["个人限购"][player_name] = personal_limits
        self.atomic_modify_runtime_config(lambda cfg: shop_config)

        player.show(f"§a购买成功！获得 {buy_qty} 个 {product['商品显示名称']}，花费 {total_price} {product['货币显示名称']}")


entry = plugin_entry(Random_Shop)

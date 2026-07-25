#
#  ██████╗██╗   ██╗ █████╗ ███╗   ██╗    ███████╗████████╗ ██████╗ ██████╗ ██╗  ██╗
# ██╔════╝╚██╗ ██╔╝██╔══██╗████╗  ██║    ██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██║ ██╔╝
# ██║      ╚████╔╝ ███████║██╔██╗ ██║    ███████╗   ██║   ██║   ██║██████╔╝█████╔╝
# ██║       ╚██╔╝  ██╔══██║██║╚██╗██║    ╚════██║   ██║   ██║   ██║██╔══██╗██╔═██╗
# ╚██████╗   ██║   ██║  ██║██║ ╚████║    ███████║   ██║   ╚██████╔╝██║  ██║██║  ██╗
#  ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝    ╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
#
# 券商股票系统 （CyanStock） – 作者：CyanForest
#
# 本插件的玩法灵感源于一位群友的构想。
# CyanForest 基于此构想，从 1 开始独立完成了全部代码的编写与系统设计，并添加四大核心玩法。
#
# 本插件已通过 ToolDelta 标准配置框架实现全参数可视化编辑。
# 可直接在面板中调整券商、VIP、事件等所有核心设置。
#
# 问题反馈与建议：QQ 1841804129
# 使用前请根据实际部署环境修改配置文件（面板可视化编辑）
#
import copy
import json
import os
import random
import threading
import time
from tooldelta import (
    plugin_entry,
    Plugin,
    ToolDelta,
    Player,
    Chat,
    FrameExit,
    game_utils,
)
from tooldelta.utils.cfg import NNInt, PInt, IntRange


class StockBrokerPlugin(Plugin):
    name = "CyanStock(券商股票系统)"
    author = "CyanForest"
    version = (0, 1, 3)
    description = "五家券商|计分板货币交易|市场情绪指数|随机利好利空事件|VIP分级折扣|定时补货|持仓上限自动平仓|全菜单式交互|支持面板可视化配置"

    # ---------- 扁平化配置 ----------
    CONFIG_SCHEMA = {
        "计分板名称": str,
        "注册赠送货币数": NNInt,
        "初始库存股数": NNInt,
        "单家持仓上限": NNInt,
        "会话超时秒数": NNInt,
        "单笔购入上限": PInt,
        "补货间隔分钟": PInt,
        "事件触发间隔分钟": PInt,
        "事件持续时间分钟": PInt,
        "初始市场情绪": IntRange(0, 100),
        "全局事件情绪影响": NNInt,
        "单券商事件情绪影响": NNInt,
        "事件触发概率": IntRange(0, 100),
        "券商配置": dict,
        "会员等级": list,
        "市场事件": list,
    }

    CONFIG_DEFAULT = {
        "计分板名称": "kp",
        "注册赠送货币数": 12000,
        "初始库存股数": 500,
        "单家持仓上限": 999,
        "会话超时秒数": 300,
        "单笔购入上限": 9999,
        "补货间隔分钟": 10,
        "事件触发间隔分钟": 10,
        "事件持续时间分钟": 8,
        "初始市场情绪": 30,
        "全局事件情绪影响": 5,
        "单券商事件情绪影响": 2,
        "事件触发概率": 70,
        "券商配置": {
            "平安证券": {"购买成本": 1500, "风险等级": "低", "最低卖出": 800, "最高卖出": 2500},
            "国泰证券": {"购买成本": 3500, "风险等级": "中", "最低卖出": 1500, "最高卖出": 6500},
            "华泰证券": {"购买成本": 7000, "风险等级": "中高", "最低卖出": 3000, "最高卖出": 14000},
            "中信证券": {"购买成本": 15000, "风险等级": "高", "最低卖出": 6000, "最高卖出": 30000},
            "海通证券": {"购买成本": 35000, "风险等级": "极高", "最低卖出": 12000, "最高卖出": 70000},
        },
        "会员等级": [
            {"等级名称": "普通", "累计交易额": 0, "购买折扣": 0.00, "卖出加成": 0.00, "显示颜色": "§7"},
            {"等级名称": "铜牌", "累计交易额": 50000, "购买折扣": 0.03, "卖出加成": 0.02, "显示颜色": "§6"},
            {"等级名称": "银牌", "累计交易额": 200000, "购买折扣": 0.05, "卖出加成": 0.03, "显示颜色": "§f"},
            {"等级名称": "金牌", "累计交易额": 800000, "购买折扣": 0.08, "卖出加成": 0.05, "显示颜色": "§e"},
            {"等级名称": "钻石", "累计交易额": 2500000, "购买折扣": 0.12, "卖出加成": 0.08, "显示颜色": "§b"},
        ],
        "市场事件": [
            {"事件类型": "利好", "影响范围": "全局",
             "事件描述": "央行降息，市场流动性增加",
             "持续时间分钟": 8, "价格修正": 1.10},
            {"事件类型": "利好", "影响范围": "全局",
             "事件描述": "政策利好：资本市场改革方案",
             "持续时间分钟": 8, "价格修正": 1.10},
            {"事件类型": "利空", "影响范围": "全局",
             "事件描述": "外部市场大跌，A股承压",
             "持续时间分钟": 8, "价格修正": 0.90},
            {"事件类型": "利空", "影响范围": "全局",
             "事件描述": "监管层加强风险管控",
             "持续时间分钟": 8, "价格修正": 0.90},
            {"事件类型": "利好", "影响范围": "单券商",
             "事件描述": "财报超预期，业绩亮眼",
             "持续时间分钟": 8, "价格修正": 1.15},
            {"事件类型": "利空", "影响范围": "单券商",
             "事件描述": "遭遇监管调查",
             "持续时间分钟": 8, "价格修正": 0.85},
            {"事件类型": "利好", "影响范围": "单券商",
             "事件描述": "获得重大订单",
             "持续时间分钟": 8, "价格修正": 1.15},
            {"事件类型": "利空", "影响范围": "单券商",
             "事件描述": "高管离职引发担忧",
             "持续时间分钟": 8, "价格修正": 0.85},
        ],
    }
    STATE_BUY_SELECT_BROKER = 1
    STATE_BUY_INPUT_QUANTITY = 2
    STATE_SELL_SELECT_BROKER = 3
    STATE_SELL_INPUT_QUANTITY = 4
    STATE_SELLALL_SELECT_BROKER = 5
    STATE_SELLALL_CONFIRM = 8
    STATE_DETAIL_SELECT_BROKER = 6
    STATE_INFO_VIEW = 7
    STATE_MAIN_MENU = 10

    # UI 常量
    H1 = "§6§l══════════ §e§l{0} §6§l══════════§r"
    H2 = "§6§l════ §e§l{0} §6§l════§r"
    TIP = "§7» §f{0}§r"
    CMD = "§b§l{0}§r"
    DESC = "§7{0}§r"
    NUM = "§e§l{0}§r"
    GREEN = "§a{0}§r"
    RED = "§c{0}§r"
    GOLD = "§e{0}§r"

    # 主菜单分页
    MENU_ITEMS = [
        ("注册", 1), ("余额", 2), ("买入", 3), ("卖出", 4), ("清仓", 5),
        ("持仓", 6), ("走势", 7), ("券商", 8), ("情绪", 9), ("等级", 10),
        ("帮助", 11),
    ]
    PAGE_SIZE = 5

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)  # CyanForest watermark

        self.data_file = self.data_path / "stock_data.json"

        # 加载扁平化配置文件
        raw_cfg, cfg_vers = self.get_config_and_version(
            self.CONFIG_SCHEMA, self.CONFIG_DEFAULT
        )
        self.print_suc(f"§a配置文件加载成功，版本 §e{'.'.join(str(x) for x in cfg_vers)}")

        self.scoreboard_name = raw_cfg["计分板名称"]
        self.register_bonus = raw_cfg["注册赠送货币数"]
        self.initial_stock = raw_cfg["初始库存股数"]
        self.max_holdings = raw_cfg["单家持仓上限"]
        self.session_timeout = raw_cfg["会话超时秒数"]
        self.max_purchase = raw_cfg["单笔购入上限"]
        self.refill_interval = raw_cfg["补货间隔分钟"]
        self.event_interval = raw_cfg["事件触发间隔分钟"]
        self.event_duration = raw_cfg["事件持续时间分钟"]
        self.sentiment_initial = raw_cfg["初始市场情绪"]
        self.sentiment_delta_global = raw_cfg["全局事件情绪影响"]
        self.sentiment_delta_single = raw_cfg["单券商事件情绪影响"]
        self.event_chance_base = raw_cfg["事件触发概率"]

        # 将面板的中文字段映射为内部英文字段
        self.brokers = {
            name: {
                "cost": info["购买成本"],
                "risk": info["风险等级"],
                "sell_min": info["最低卖出"],
                "sell_max": info["最高卖出"],
            }
            for name, info in raw_cfg["券商配置"].items()
        }
        self.broker_names = list(self.brokers.keys())
        self.vip_tiers = [
            {
                "name": t["等级名称"],
                "min_volume": t["累计交易额"],
                "buy_discount": t["购买折扣"],
                "sell_bonus": t["卖出加成"],
                "color": t["显示颜色"],
            }
            for t in raw_cfg["会员等级"]
        ]
        scope_map = {"全局": "all", "单券商": "single"}
        self.market_events = [
            {
                "type": e["事件类型"],
                "desc": e["事件描述"],
                "scope": scope_map.get(e["影响范围"], e["影响范围"]),
                "duration": e["持续时间分钟"],
                "modifier": e["价格修正"],
            }
            for e in raw_cfg["市场事件"]
        ]

        self.config = raw_cfg
        self.players = {}
        self.broker_stocks = {}
        self.market_sentiment = self.sentiment_initial
        self.active_events = []
        self._event_chance = self.event_chance_base / 100
        self._event_running = False
        self._event_thread = None
        self._timer_running = False
        self._timer_thread = None
        self._autosave_running = False
        self._autosave_thread = None
        self._data_dirty = False
        self._data_lock = threading.Lock()
        self._save_lock = threading.Lock()
        self._sessions_lock = threading.RLock()
        self.sessions = {}
        self._liquidation_warned: set = set()
        self.chatbar = None

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenChat(self.on_chat)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenFrameExit(self.on_frame_exit)

    # ---------- 数据 ----------
    def load_data(self):
        if self.data_file.exists():
            try:
                data = json.loads(self.data_file.read_text(encoding="utf-8"))
                self.players = data.get("players", {})
                self.broker_stocks = data.get("broker_stocks", {})
                self.market_sentiment = data.get(
                    "market_sentiment", self.sentiment_initial
                )
                self.active_events = data.get("active_events", [])
                for broker in self.broker_names:
                    if broker not in self.broker_stocks:
                        self.broker_stocks[broker] = self.initial_stock
                self.print_suc(f"§a数据加载成功，玩家数: §e{len(self.players)}")
            except Exception as e:
                self.print_err(f"§c数据加载失败: {e}")
                self.reset_data()
        else:
            self.reset_data()
            self.print_inf("§e未找到历史数据，初始化新数据")
        self.save_data()

    def reset_data(self):
        self.players = {}
        self.broker_stocks = {
            broker: self.initial_stock for broker in self.broker_names
        }

    def save_data(self):
        """标记数据为脏，由自动存档线程异步写入"""
        self._data_dirty = True

    def _flush_save(self):
        """实际写入磁盘（线程安全 + 原子写入）"""
        with self._save_lock:
            self._data_dirty = False
            with self._data_lock:
                data = {
                    "players": copy.deepcopy(self.players),
                    "broker_stocks": copy.deepcopy(self.broker_stocks),
                    "market_sentiment": self.market_sentiment,
                    "active_events": copy.deepcopy(self.active_events),
                }
            tmp_file = self.data_file.with_suffix(".tmp")
            try:
                tmp_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=4),
                    encoding="utf-8"
                )
                os.replace(tmp_file, self.data_file)
            except Exception as e:
                self.print_err(f"§c保存数据失败: {e}")
                self._data_dirty = True
                if tmp_file.exists():
                    tmp_file.unlink()

    # ---------- {self.scoreboard_name} 计分板辅助 ----------
    def get_kp(self, player_name: str) -> int:
        score = game_utils.getScore(self.scoreboard_name, player_name)
        if score is None:
            return 0
        return score

    def add_kp(self, player_name: str, amount: int):
        if amount <= 0:
            return
        self.game_ctrl.sendcmd(
            f"/scoreboard players add {player_name}"
            f" {self.scoreboard_name} {amount}"
        )

    def remove_kp(self, player_name: str, amount: int):
        if amount <= 0:
            return
        self.game_ctrl.sendcmd(
            f"/scoreboard players remove {player_name}"
            f" {self.scoreboard_name} {amount}"
        )

    # ---------- 生命周期 ----------
    def on_preload(self):
        self.load_data()
        try:
            self.chatbar = self.GetPluginAPI("聊天栏菜单")
            self.print_suc("§a已接入聊天栏菜单 API")
        except Exception as e:
            self.chatbar = None
            self.print_war(f"§e未找到聊天栏菜单插件，.help 中不会显示菜单入口: {e}")

    def on_active(self):
        try:
            self.game_ctrl.sendwocmd(
                f"/scoreboard objectives add {self.scoreboard_name} dummy"
            )
        except Exception:
            pass
        self.print_suc("§aCyanStock(券商股票系统) §ev0.1.3 CyanForest特供 §a已激活")
        if self.chatbar is not None:
            self.chatbar.add_new_trigger(
                ["券商股票", "stock"],
                [],
                "打开CyanStock(券商股票系统)主菜单",
                self.open_stock_menu
            )
            self.print_suc("§a已注册 .券商股票 到聊天栏菜单")
        self.start_refill_loop()
        self.start_autosave_loop()
        self.start_event_loop()

    def start_autosave_loop(self):
        self._autosave_running = True
        self._autosave_thread = threading.Thread(
            target=self._autosave_loop, daemon=True
        )
        self._autosave_thread.start()

    def _autosave_loop(self):
        while self._autosave_running:
            time.sleep(30)
            if self._data_dirty:
                self._flush_save()
            self._cleanup_sessions()

    def start_refill_loop(self):
        self._timer_running = True
        self._timer_thread = threading.Thread(target=self._refill_loop, daemon=True)
        self._timer_thread.start()

    def _refill_loop(self):
        interval = self.refill_interval * 60
        while self._timer_running:
            time.sleep(interval)
            if not self._timer_running:
                break
            self.refill_all_brokers()

    def refill_all_brokers(self):
        with self._data_lock:
            for broker in self.broker_names:
                self.broker_stocks[broker] = self.initial_stock
        self._update_sentiment()
        self._cleanup_expired_events()
        self.save_data()
        label, color = self._get_sentiment_label()
        broadcast = (
            self.H2.format("§a系统公告") + "\n"
            + f"§e所有券商§f已补货至 §e{self.initial_stock} §f股！\n"
            + f"§f市场情绪：{color}§l{self.market_sentiment}§r §f({color}{label}§r)\n"
        )
        if self.active_events:
            now = time.time()
            active = [e for e in self.active_events if e["expiry"] > now]
            if active:
                broadcast += "§6§l活跃事件：§r\n"
                for ev in active:
                    remaining = int((ev["expiry"] - now) / 60)
                    t_color = "§a" if ev["type"] == "利好" else "§c"
                    scope = ev.get("broker", "全市场") or "全市场"
                    broadcast += (
                        f"  {t_color}[{ev['type']}] §f{ev['desc']}"
                        f" §7({scope}, §e{remaining}分钟§7)\n"
                    )
        self.game_ctrl.say_to("@a", broadcast)
        self.print_inf("§e所有券商补货完成")

    # ---------- 玩家辅助 ----------
    def get_player_data(self, uuid: str):
        if uuid not in self.players:
            self.players[uuid] = {
                "registered": False,
                "holdings": {},
                "trade_volume": 0,
            }
        pdata = self.players[uuid]
        if "trade_volume" not in pdata:
            pdata["trade_volume"] = 0
        return pdata

    def get_player_view(self, uuid: str) -> dict:
        """返回玩家数据的只读副本（防止外部误修改内部状态）"""
        pdata = self.get_player_data(uuid)
        return copy.deepcopy(pdata)

    def _nav_tip(self) -> str:
        return self.TIP.format("r 返回主菜单，q 退出")

    def say_lines(self, name: str, text: str):
        """自动分段发送多行文本，避免 MC 消息截断"""
        MAX_LEN = 400
        if len(text) <= MAX_LEN:
            self.game_ctrl.say_to(name, text)
            return
        lines = text.split("\n")
        buf = ""
        for line in lines:
            if len(buf) + len(line) + 1 > MAX_LEN and buf:
                self.game_ctrl.say_to(name, buf)
                buf = line
            else:
                buf = buf + "\n" + line if buf else line
        if buf:
            self.game_ctrl.say_to(name, buf)

    def get_holdings(self, uuid: str, broker: str) -> int:
        return self.get_player_data(uuid)["holdings"].get(broker, 0)

    def set_holdings(self, uuid: str, broker: str, amount: int):
        pdata = self.get_player_data(uuid)
        if amount <= 0:
            pdata["holdings"].pop(broker, None)
        else:
            pdata["holdings"][broker] = amount
        self.save_data()

    def add_holdings(self, uuid: str, broker: str, delta: int):
        current = self.get_holdings(uuid, broker)
        new = current + delta
        if new < 0:
            new = 0
        self.set_holdings(uuid, broker, new)
        return new

    def require_registered(self, uuid: str) -> str:
        pdata = self.get_player_data(uuid)
        if pdata["registered"]:
            return None
        return "§c请先注册：输入 " + self.CMD.format(".注册")

    # ---------- 市场事件 ----------
    def _trigger_market_event(self):
        event = random.choice(self.market_events)
        expiry = time.time() + event.get("duration", self.event_duration) * 60
        ev = {
            "desc": event["desc"],
            "type": event["type"],
            "scope": event["scope"],
            "modifier": event["modifier"],
            "expiry": expiry,
        }
        if event["scope"] == "single":
            ev["broker"] = random.choice(self.broker_names)
            broker_name = ev["broker"]
        else:
            ev["broker"] = None
            broker_name = "全市场"
        with self._data_lock:
            self.active_events.append(ev)
            # 事件本身也影响市场信心（全局事件影响更大，单券商事件影响较小）
            delta = (
                self.sentiment_delta_global
                if event["scope"] == "all"
                else self.sentiment_delta_single
            )
            if event["type"] == "利好":
                self.market_sentiment = min(100, self.market_sentiment + delta)
            else:
                self.market_sentiment = max(0, self.market_sentiment - delta)
        self.save_data()
        type_color = "§a" if event["type"] == "利好" else "§c"
        self.game_ctrl.say_to(
            "@a",
            self.H2.format("§6市场快讯") + "\n"
            + f"{type_color}§l[{event['type']}] §f{event['desc']}\n"
            + f"§7影响范围：§f{broker_name}  §7持续：§e{event['duration']}§f分钟\n"
            + f"§7价格修正：§e{event['modifier']:.0%}"
        )
        self.print_inf(f"§e市场事件触发：{event['desc']}")

    def _cleanup_expired_events(self):
        now = time.time()
        with self._data_lock:
            before = len(self.active_events)
            self.active_events = [e for e in self.active_events if e["expiry"] > now]
            if len(self.active_events) < before:
                self.save_data()

    def _get_price_modifier(self, broker: str) -> float:
        """获取某券商的最终价格修正系数（事件 × 情绪）"""
        modifier = 1.0
        with self._data_lock:
            events_snapshot = list(self.active_events)
            sentiment_snapshot = self.market_sentiment
        for ev in events_snapshot:
            if ev["expiry"] <= time.time():
                continue
            if ev["scope"] == "all" or ev.get("broker") == broker:
                modifier *= ev["modifier"]
        # 情绪影响：每偏离50点，修正1%
        sentiment_factor = 1.0 + (sentiment_snapshot - 50) / 100
        modifier *= sentiment_factor
        return max(0.3, min(modifier, 3.0))

    def _get_effective_sell_range(self, broker: str):
        """返回修正后的 (sell_min, sell_max)"""
        info = self.brokers[broker]
        mod = self._get_price_modifier(broker)
        s_min = max(1, int(info["sell_min"] * mod))
        s_max = max(s_min, int(info["sell_max"] * mod))
        return s_min, s_max

    # ---------- 市场情绪 ----------
    def _update_sentiment(self, buyer_count: int = 0):
        """补货时更新情绪指数"""
        with self._data_lock:
            # 库存越少 = 需求越旺 = 情绪越高
            total_stock = sum(self.broker_stocks.values())
            max_stock = self.initial_stock * len(self.broker_names)
            stock_ratio = total_stock / max_stock if max_stock > 0 else 1.0
            # 库存低 → 情绪高
            target = int(50 + (1 - stock_ratio) * 40 + random.randint(-5, 5))
            target = max(0, min(100, target))
            # 平滑过渡
            self.market_sentiment = int(self.market_sentiment * 0.6 + target * 0.4)
        self.save_data()

    def _get_sentiment_label(self) -> tuple:
        s = self.market_sentiment
        if s < 20:
            return "极度恐慌", "§4"
        elif s < 35:
            return "恐慌", "§c"
        elif s < 45:
            return "谨慎", "§6"
        elif s <= 55:
            return "中性", "§e"
        elif s <= 70:
            return "乐观", "§a"
        elif s <= 85:
            return "狂热", "§2"
        else:
            return "极度狂热", "§d"

    def show_market_sentiment(self, player: Player, show_nav: bool = True) -> str:
        label, color = self._get_sentiment_label()
        s = self.market_sentiment
        # 进度条
        bar_len = 20
        filled = s * bar_len // 100
        bar = "§a" + "■" * filled + "§7" + "□" * (bar_len - filled)
        lines = [
            self.H2.format("§e市场情绪指数"),
            f"§f当前指数：{color}§l{s}§r §f/ §e100",
            f"§f市场状态：{color}§l{label}§r",
            f"§f{bar}",
            "",
        ]
        if self.active_events:
            lines.append("§6§l活跃事件：§r")
            now = time.time()
            with self._data_lock:
                events_snapshot = list(self.active_events)
            for ev in events_snapshot:
                if ev["expiry"] <= now:
                    continue
                remaining = int((ev["expiry"] - now) / 60)
                t_color = "§a" if ev["type"] == "利好" else "§c"
                scope = ev.get("broker", "全市场") or "全市场"
                lines.append(
                    f"  {t_color}[{ev['type']}] §f{ev['desc']}\n"
                    + f"  §7范围：§f{scope}  §7剩余：§e{remaining}§f分钟"
                    + f"  §7修正：§e{ev['modifier']:.0%}"
                )
        else:
            lines.append("§7当前无活跃市场事件")
        lines.append("")
        lines.append(self.TIP.format("情绪指数影响卖出收益，利好事件提升价格"))
        if show_nav:
            lines.append(self._nav_tip())
        return "\n".join(lines)

    # ---------- VIP 系统 ----------
    def _get_vip_tier(self, uuid: str) -> dict:
        pdata = self.get_player_data(uuid)
        volume = pdata.get("trade_volume", 0)
        tier = self.vip_tiers[0]
        for t in self.vip_tiers:
            if volume >= t["min_volume"]:
                tier = t
        return tier

    def _add_trade_volume(self, uuid: str, amount: int, player_name: str = ""):
        pdata = self.get_player_data(uuid)
        old_tier = self._get_vip_tier(uuid)
        pdata["trade_volume"] += amount
        new_tier = self._get_vip_tier(uuid)
        self.save_data()
        if old_tier != new_tier and new_tier["min_volume"] > 0 and player_name:
            self.game_ctrl.say_to(
                player_name,
                self.H2.format("§e等级提升！") + "\n"
                + f"§f恭喜晋升至 {new_tier['color']}§l{new_tier['name']}§r §f等级\n"
                + f"§f买入折扣：§a{new_tier['buy_discount']:.0%}"
                + f"  §f卖出加成：§a{new_tier['sell_bonus']:.0%}"
            )

    def show_vip_status(self, player: Player, show_nav: bool = True) -> str:
        uuid = player.uuid
        err = self.require_registered(uuid)
        if err:
            return err
        tier = self._get_vip_tier(uuid)
        pdata = self.get_player_data(uuid)
        volume = pdata.get("trade_volume", 0)
        # 找下一个等级
        next_tier = None
        for t in self.vip_tiers:
            if t["min_volume"] > volume:
                next_tier = t
                break
        lines = [
            self.H2.format("§e等级权益"),
            f"§f当前：{tier['color']}§l{tier['name']}§r"
            f" §7(累计 §e{volume}§7 {self.scoreboard_name})",
            "",
        ]
        # 直接列出每个等级的加成
        for t in self.vip_tiers:
            marker = "§e» " if t["name"] == tier["name"] else "§7  "
            if t["buy_discount"] > 0 or t["sell_bonus"] > 0:
                lines.append(
                    f"{marker}§f{t['color']}{t['name']}§r"
                    f" §7入§a-{t['buy_discount']:.0%}"
                    f" §7出§a+{t['sell_bonus']:.0%}"
                )
            else:
                lines.append(f"{marker}§f{t['color']}{t['name']}§r §7无加成")
        lines.append("")
        if next_tier:
            need = next_tier["min_volume"] - volume
            lines.append(
                f"§7再交易 §e{need}§7 {self.scoreboard_name}"
                f" 升至 {next_tier['color']}{next_tier['name']}§r"
            )
        else:
            lines.append("§7已满级")
        if show_nav:
            lines.append(self._nav_tip())
        return "\n".join(lines)

    # ---------- 事件循环 ----------
    def start_event_loop(self):
        self._event_running = True
        self._event_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._event_thread.start()

    def _event_loop(self):
        interval = self.event_interval * 60
        while self._event_running:
            time.sleep(interval)
            if not self._event_running:
                break
            self._cleanup_expired_events()
            if random.random() < self._event_chance:
                self._trigger_market_event()
                self._event_chance = self.event_chance_base / 100
            else:
                self.game_ctrl.say_to(
                    "@a", self.H2.format("§6市场播报")
                    + "\n§f当前市场平稳，无重大事件"
                )
                self._event_chance = min(0.95, self._event_chance + 0.1)
            self._update_sentiment()

    # ---------- 注册 ----------
    def register_player(self, player: Player) -> str:
        uuid = player.uuid
        pdata = self.get_player_data(uuid)
        if pdata["registered"]:
            return "§c你已经注册过了，无需重复注册"
        pdata["registered"] = True
        self.save_data()
        self.add_kp(player.name, self.register_bonus)
        return (
            self.H2.format("§a注册成功") + "\n"
            + f"§f注册成功，赠送 §e{self.register_bonus} {self.scoreboard_name}\n"
            + self.TIP.format(f"所有交易直接使用 {self.scoreboard_name} 计分板，无需额外充值")
        )

    # ---------- 查询 {self.scoreboard_name} ----------
    def show_kp_balance(self, player: Player, show_nav: bool = True) -> str:
        uuid = player.uuid
        err = self.require_registered(uuid)
        if err:
            return err
        kp = self.get_kp(player.name)
        text = (
            self.H2.format(f"§e我的 {self.scoreboard_name}") + "\n"
            + f"§f当前 {self.scoreboard_name}：§e{kp}\n"
            + self.TIP.format(
                f"买入股票时自动扣除 {self.scoreboard_name}，"
                f"卖出股票时自动获得 {self.scoreboard_name}"
            )
        )
        if show_nav:
            text += "\n" + self._nav_tip()
        return text

    # ---------- 购买 ----------
    def buy_stock(self, player: Player, broker: str, quantity: int) -> str:
        if quantity <= 0:
            return "§c买入数量必须为正整数"
        uuid = player.uuid
        err = self.require_registered(uuid)
        if err:
            return err
        if broker not in self.broker_names:
            return f"§c券商不存在，可选：§e{', '.join(self.broker_names)}"
        with self._data_lock:
            if self.broker_stocks.get(broker, 0) < quantity:
                return (
                    f"§c{broker} §f库存不足\n"
                    f"§f当前仅剩：§e{self.broker_stocks.get(broker, 0)} §f股"
                )
            tier = self._get_vip_tier(uuid)
            base_cost = self.brokers[broker]["cost"] * quantity
            cost = int(base_cost * (1 - tier["buy_discount"]))
            kp = self.get_kp(player.name)
            if kp < cost:
                return (
                    f"§c{self.scoreboard_name} 不足\n"
                    f"§f需要：§e{cost} {self.scoreboard_name}"
                    f"  §f当前：§e{kp} {self.scoreboard_name}"
                )
            current_hold = self.get_holdings(uuid, broker)
            if current_hold + quantity > self.max_holdings:
                return (
                    f"§c该券商持仓将超过上限 §e{self.max_holdings} §f股\n"
                    f"§f当前：§e{current_hold} §f股"
                )
            self.remove_kp(player.name, cost)
            self.add_holdings(uuid, broker, quantity)
            self.broker_stocks[broker] -= quantity
        self._add_trade_volume(uuid, cost, player.name)
        self.save_data()
        new_hold = self.get_holdings(uuid, broker)
        discount_text = (
            f" §7(等级{tier['name']} §a-{tier['buy_discount']:.0%}§7)"
            if tier["buy_discount"] > 0 else ""
        )
        eff_min, eff_max = self._get_effective_sell_range(broker)
        if new_hold >= self.max_holdings:
            if uuid in self._liquidation_warned:
                self._liquidation_warned.discard(uuid)
                total_income = self.sell_all_holdings(uuid, broker, player.name)
                return (
                    self.H2.format("§c强制平仓") + "\n"
                    + f"§c持仓已达上限 §e{self.max_holdings} §c股\n"
                    + f"§f已自动卖出所有 §e{broker} §f股票\n"
                    + f"§f获得 {self.scoreboard_name}：§e{total_income}\n"
                    + f"§f每股随机：§e{eff_min}~{eff_max}"
                )
            else:
                self._liquidation_warned.add(uuid)
                return (
                    self.H2.format("§e持仓预警") + "\n"
                    + f"§e持仓已达上限 §e{self.max_holdings} §e股\n"
                    + f"§f当前持仓：§e{new_hold} §f股\n"
                    + "§c§l注意：§r§c再次购买将触发强制平仓！"
                )
        return (
            self.H2.format("§a买入成功") + "\n"
            + f"§f券商：§e{broker}\n"
            + f"§f数量：§e{quantity} §f股\n"
            + f"§f花费：§e{cost} {self.scoreboard_name}{discount_text}\n"
            + f"§f当前持仓：§e{new_hold} §f股"
        )

    # ---------- 一键卖出 ----------
    def sell_all_holdings(self, uuid: str, broker: str, player_name: str = "") -> int:
        with self._data_lock:
            pdata = self.get_player_data(uuid)
            shares = pdata["holdings"].get(broker, 0)
            if shares <= 0:
                return 0
            sell_min, sell_max = self._get_effective_sell_range(broker)
            base_total = sum(random.randint(sell_min, sell_max) for _ in range(shares))
            tier = self._get_vip_tier(uuid)
            total = int(base_total * (1 + tier["sell_bonus"]))
            self.set_holdings(uuid, broker, 0)
        if player_name:
            self.add_kp(player_name, total)
        self._add_trade_volume(uuid, total, player_name)
        self.save_data()
        return total

    # ---------- 股势 ----------
    def get_trend(self, show_nav: bool = True) -> str:
        with self._data_lock:
            sentiment_snapshot = self.market_sentiment
            stocks_snapshot = dict(self.broker_stocks)
        label, color = self._get_sentiment_label()
        lines = [
            self.H1.format("§e券商股势一览"),
            f"§f市场情绪：{color}§l{sentiment_snapshot}§r §f({color}{label}§r)",
            f"§7图例：存=库存 价=成本 险=风险 售=出售价 ({self.scoreboard_name})",
            "",
        ]
        for broker in self.broker_names:
            info = self.brokers[broker]
            stock = stocks_snapshot.get(broker, 0)
            risk_color = self._effective_risk_color(broker)
            eff_min, eff_max = self._get_effective_sell_range(broker)
            base_min, base_max = info["sell_min"], info["sell_max"]
            price_tag = ""
            if eff_min != base_min or eff_max != base_max:
                if eff_max > base_max:
                    price_tag = " §a↑"
                else:
                    price_tag = " §c↓"
            lines.append(
                f"§e• §f{broker} §7存§f{stock} §7价§e{info['cost']}"
                f" §7险{risk_color} §7出§a{eff_min}-{eff_max}{price_tag}"
            )
        lines.append("")
        lines.append(self.TIP.format("输入 " + self.CMD.format(".券商详情") + " 查看单家详情"))
        lines.append(self.TIP.format("出售价受市场情绪和事件影响，↑↓=偏离基准"))
        if show_nav:
            lines.append(self._nav_tip())
        return "\n".join(lines)

    # 风险等级映射
    RISK_LEVELS = ["低", "中", "中高", "高", "极高"]

    def _risk_color(self, risk: str) -> str:
        colors = {"低": "§a", "中": "§e", "中高": "§6", "高": "§c", "极高": "§4"}
        display = {"低": "低", "中": "中等", "中高": "中高", "高": "高", "极高": "极高"}
        return colors.get(risk, "§f") + display.get(risk, risk) + "§r"

    def _get_effective_risk(self, broker: str) -> str:
        """市场恐慌风险↑，牛市风险↓"""
        info = self.brokers[broker]
        base = info["risk"]
        try:
            idx = self.RISK_LEVELS.index(base)
        except ValueError:
            return base
        if self.market_sentiment <= 30:
            idx = min(len(self.RISK_LEVELS) - 1, idx + 1)
        elif self.market_sentiment >= 70:
            idx = max(0, idx - 1)
        return self.RISK_LEVELS[idx]

    def _effective_risk_color(self, broker: str) -> str:
        return self._risk_color(self._get_effective_risk(broker))

    # ---------- 券商详情 ----------
    def get_broker_detail(self, uuid: str, broker: str) -> str:
        if broker not in self.broker_names:
            return f"§c券商不存在，可选：§e{', '.join(self.broker_names)}"
        err = self.require_registered(uuid)
        if err:
            return err
        info = self.brokers[broker]
        stock = self.broker_stocks.get(broker, 0)
        holdings = self.get_holdings(uuid, broker)
        tier = self._get_vip_tier(uuid)
        eff_min, eff_max = self._get_effective_sell_range(broker)
        lines = [
            self.H2.format(f"§e{broker} §f详情"),
            f"§f买入成本：§e{info['cost']} {self.scoreboard_name} §f/股",
            f"§f等级折扣：§a-{tier['buy_discount']:.0%}"
            f" §7(实付 §e{int(info['cost'] * (1 - tier['buy_discount']))}"
            f" {self.scoreboard_name}§7)",
            f"§f风险等级：{self._effective_risk_color(broker)}",
            f"§f基准收益：§7{info['sell_min']} ~ {info['sell_max']}"
            f" {self.scoreboard_name} §f/股",
            f"§f当前收益：§a{eff_min} ~ {eff_max} {self.scoreboard_name} §f/股 §7(含事件+情绪)",
            f"§f券商库存：§e{stock} §f股",
            f"§f你的持仓：§a{holdings} §f股",
            f"§f持仓上限：§c{self.max_holdings} §f股",
        ]
        # 显示影响该券商的事件
        now = time.time()
        broker_events = [
            e for e in self.active_events
            if e["expiry"] > now and (e["scope"] == "all" or e.get("broker") == broker)
        ]
        if broker_events:
            lines.append("§6§l活跃事件：§r")
            for ev in broker_events:
                remaining = int((ev["expiry"] - now) / 60)
                t_color = "§a" if ev["type"] == "利好" else "§c"
                lines.append(
                    f"  {t_color}[{ev['type']}] §f{ev['desc']}"
                    f" §7(§e{remaining}分钟§7, §e{ev['modifier']:.0%}§7)"
                )
        if holdings >= self.max_holdings:
            lines.append("§c§l注意：§r§c已触及持仓上限，将触发强制平仓！")
        lines.append("")
        lines.append(self._nav_tip())
        return "\n".join(lines)

    # ---------- 菜单交互 ----------
    def show_broker_list(self, player: Player, state: int, menu_page: int = 0):
        action_names = {
            self.STATE_BUY_SELECT_BROKER: "买入",
            self.STATE_SELL_SELECT_BROKER: "卖出",
            self.STATE_SELLALL_SELECT_BROKER: "一键卖出",
            self.STATE_DETAIL_SELECT_BROKER: "查看详情",
        }
        action_name = action_names.get(state, "操作")
        lines = [
            self.H2.format(f"请选择：{action_name}"),
            f"§7图例：价=成本 险=风险 卖=卖出价 ({self.scoreboard_name})",
            ""
        ]
        for idx, name in enumerate(self.broker_names, 1):
            info = self.brokers[name]
            risk_color = self._effective_risk_color(name)
            eff_min, eff_max = self._get_effective_sell_range(name)
            price_tag = ""
            if eff_max > info["sell_max"]:
                price_tag = " §a↑"
            elif eff_max < info["sell_max"]:
                price_tag = " §c↓"
            lines.append(
                f"§e{idx}. §f{name} §7价§e{info['cost']}"
                f" §7险{risk_color} §7卖{eff_min}-{eff_max}{price_tag}"
            )
        lines.append("")
        lines.append(self.TIP.format(f"输入数字 1-{len(self.broker_names)}，r 返回主菜单，q 退出"))
        self.game_ctrl.say_to(player.name, "\n".join(lines))
        self._set_session(player.uuid, state, menu_page=menu_page)

    def open_stock_menu(self, player: Player, args: tuple):
        self.show_main_menu(player, page=0)
        self._set_session(player.uuid, self.STATE_MAIN_MENU, page=0)

    def show_main_menu(self, player: Player, page: int = 0):
        kp = self.get_kp(player.name)
        pdata = self.get_player_view(player.uuid)
        reg_text = "§a已开通" if pdata["registered"] else "§c未开通"
        tier = self._get_vip_tier(player.uuid)
        label, color = self._get_sentiment_label()
        total_pages = (len(self.MENU_ITEMS) + self.PAGE_SIZE - 1) // self.PAGE_SIZE
        start = page * self.PAGE_SIZE
        end = min(start + self.PAGE_SIZE, len(self.MENU_ITEMS))
        # 构建当前页菜单项
        items = []
        for i in range(start, end):
            name, _ = self.MENU_ITEMS[i]
            display_idx = i - start + 1
            items.append(f"§e{display_idx} §f{name}")
        # 行列排布
        if len(items) <= 3:
            item_lines = ["§6请选择:§r " + "  ".join(items)]
        else:
            mid = (len(items) + 1) // 2
            item_lines = [
                "§6请选择:§r " + "  ".join(items[:mid]),
                "         " + "  ".join(items[mid:]),
            ]
        # 翻页导航
        nav_parts = []
        if page > 0:
            nav_parts.append("§e- §7上页")
        if page < total_pages - 1:
            nav_parts.append("§e+ §7下页")
        nav = "  ".join(nav_parts)
        lines = [
            self.H1.format("§eCyanStock(券商股票系统)"),
            f"§7版本 §fv0.1.3 CyanForest特供  §7状态 {reg_text}",
            f"§f{self.scoreboard_name}:§e{kp}  §f等级:{tier['color']}{tier['name']}§r"
            f"  §f情绪:{color}{self.market_sentiment}§r",
            "",
            *item_lines,
        ]
        if nav:
            lines.extend(["", self.TIP.format(
                f"第{page+1}/{total_pages}页  {nav}  输入0/q退出"
            )])
        else:
            lines.extend(["", self.TIP.format(f"第{page+1}/{total_pages}页  输入0/q退出")])
        self.say_lines(player.name, "\n".join(lines))
        # 更新 session 中的页码
        with self._sessions_lock:
            if player.uuid in self.sessions:
                self.sessions[player.uuid]["page"] = page

    def handle_main_menu(self, player: Player, choice):
        uuid = player.uuid
        session = self.sessions.get(uuid)
        page = session.get("page", 0) if session else 0
        start = page * self.PAGE_SIZE
        # 将页内选项号映射为实际菜单项 ID
        if isinstance(choice, int):
            mapped = start + choice
            if mapped < 1 or mapped > len(self.MENU_ITEMS):
                self.game_ctrl.say_to(player.name, "§c无效选择")
                return
            choice = mapped
        else:
            self.game_ctrl.say_to(player.name, "§c无效选择")
            return
        if choice == 1:
            result = self.register_player(player)
            self.game_ctrl.say_to(player.name, result)
            self.cancel_session(uuid)
        elif choice == 2:
            result = self.show_kp_balance(player)
            self.game_ctrl.say_to(player.name, result)
            self._set_session(uuid, self.STATE_INFO_VIEW, menu_page=page)
        elif choice == 3:
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(player.name, err)
                self.cancel_session(uuid)
                return
            self.show_broker_list(player, self.STATE_BUY_SELECT_BROKER, menu_page=page)
        elif choice == 4:
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(player.name, err)
                self.cancel_session(uuid)
                return
            pdata = self.get_player_view(uuid)
            has_stock = any(v > 0 for v in pdata["holdings"].values())
            if not has_stock:
                self.game_ctrl.say_to(player.name, "§c你没有任何股票可卖出")
                self.cancel_session(uuid)
                return
            self.show_broker_list(player, self.STATE_SELL_SELECT_BROKER, menu_page=page)
        elif choice == 5:
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(player.name, err)
                self.cancel_session(uuid)
                return
            pdata = self.get_player_view(uuid)
            has_stock = any(v > 0 for v in pdata["holdings"].values())
            if not has_stock:
                self.game_ctrl.say_to(player.name, "§c你没有任何股票可卖出")
                self.cancel_session(uuid)
                return
            self.show_broker_list(
                player, self.STATE_SELLALL_SELECT_BROKER, menu_page=page
            )
        elif choice == 6:
            result = self.show_holdings(uuid, player.name)
            self.game_ctrl.say_to(player.name, result)
            self._set_session(uuid, self.STATE_INFO_VIEW, menu_page=page)
        elif choice == 7:
            trend = self.get_trend()
            self.say_lines(player.name, trend)
            self._set_session(uuid, self.STATE_INFO_VIEW, menu_page=page)
        elif choice == 8:
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(player.name, err)
                self.cancel_session(uuid)
                return
            self.show_broker_list(
                player, self.STATE_DETAIL_SELECT_BROKER, menu_page=page
            )
        elif choice == 9:
            result = self.show_market_sentiment(player)
            self.game_ctrl.say_to(player.name, result)
            self._set_session(uuid, self.STATE_INFO_VIEW, menu_page=page)
        elif choice == 10:
            result = self.show_vip_status(player)
            self.game_ctrl.say_to(player.name, result)
            self._set_session(uuid, self.STATE_INFO_VIEW, menu_page=page)
        elif choice == 11:
            self.show_help(player.name)
            self._set_session(uuid, self.STATE_INFO_VIEW, menu_page=page)
        else:
            self.game_ctrl.say_to(
                player.name,
                f"§c无效选择，请输入 §e1-{len(self.MENU_ITEMS)} §c选择功能"
            )

    def cancel_session(self, uuid: str):
        with self._sessions_lock:
            if uuid in self.sessions:
                del self.sessions[uuid]

    def _set_session(self, uuid: str, state: int, broker=None, page=0, menu_page=None):
        with self._sessions_lock:
            sess = {"state": state, "broker": broker, "ts": time.time(), "page": page}
            if menu_page is not None:
                sess["menu_page"] = menu_page
            self.sessions[uuid] = sess

    def _touch_session(self, uuid: str):
        with self._sessions_lock:
            if uuid in self.sessions:
                self.sessions[uuid]["ts"] = time.time()

    def _cleanup_sessions(self):
        with self._sessions_lock:
            now = time.time()
            expired = [
                uid for uid, s in self.sessions.items()
                if now - s.get("ts", 0) > self.session_timeout
            ]
            for uid in expired:
                del self.sessions[uid]

    def handle_broker_selection(self, player: Player, choice: int):
        broker_count = len(self.broker_names)
        if choice < 1 or choice > broker_count:
            self.game_ctrl.say_to(player.name, f"§c无效选择，请输入 1-{broker_count} 之间的数字")
            return
        broker = self.broker_names[choice - 1]
        uuid = player.uuid
        session = self.sessions.get(uuid)
        if not session:
            return
        state = session.get("state")
        session["broker"] = broker

        if state == self.STATE_BUY_SELECT_BROKER:
            detail = self.get_broker_detail(uuid, broker)
            self.game_ctrl.say_to(player.name, detail)
            self.game_ctrl.say_to(
                player.name,
                self.H2.format("请输入买入数量") + "\n" + self._nav_tip()
            )
            session["state"] = self.STATE_BUY_INPUT_QUANTITY

        elif state == self.STATE_SELL_SELECT_BROKER:
            holdings = self.get_holdings(uuid, broker)
            if holdings <= 0:
                self.game_ctrl.say_to(
                    player.name,
                    self.RED.format(f"你在 {broker} 没有股票可卖出")
                )
                self.cancel_session(uuid)
                return
            self.game_ctrl.say_to(
                player.name,
                self.H2.format("请输入卖出数量") + "\n"
                + f"§f当前持有 §e{broker}：§a{holdings} §f股\n"
                + self._nav_tip()
            )
            session["state"] = self.STATE_SELL_INPUT_QUANTITY

        elif state == self.STATE_SELLALL_SELECT_BROKER:
            shares = self.get_holdings(uuid, broker)
            if shares <= 0:
                self.game_ctrl.say_to(
                    player.name,
                    self.RED.format(f"你在 {broker} 没有股票可卖出")
                )
                self.cancel_session(uuid)
                return
            eff_min, eff_max = self._get_effective_sell_range(broker)
            est_low = eff_min * shares
            est_high = eff_max * shares
            self.game_ctrl.say_to(
                player.name,
                self.H2.format("§e确认一键清仓") + "\n"
                + f"§f券商：§e{broker}\n"
                + f"§f将卖出全部：§c{shares} §f股\n"
                + f"§f预计获得：§a{est_low}~{est_high} {self.scoreboard_name}\n"
                + self.TIP.format("输入 y 确认，任意其他键取消")
            )
            session["state"] = self.STATE_SELLALL_CONFIRM
            self._touch_session(uuid)

        elif state == self.STATE_DETAIL_SELECT_BROKER:
            detail = self.get_broker_detail(uuid, broker)
            self.game_ctrl.say_to(player.name, detail)
            back_page = session.get("menu_page", 0)
            self._set_session(uuid, self.STATE_INFO_VIEW, menu_page=back_page)

        else:
            self.cancel_session(uuid)

    def handle_quantity_input(self, player: Player, quantity: int):
        uuid = player.uuid
        session = self.sessions.get(uuid)
        if not session:
            return
        broker = session.get("broker")
        state = session.get("state")

        if quantity <= 0:
            self.game_ctrl.say_to(player.name, "§c已取消操作")
            self.cancel_session(uuid)
            return
        if quantity > self.max_purchase:
            self.game_ctrl.say_to(player.name, f"§c单笔数量不能超过 {self.max_purchase}")
            return

        if state == self.STATE_BUY_INPUT_QUANTITY:
            result = self.buy_stock(player, broker, quantity)
            self.game_ctrl.say_to(player.name, result)
            self.cancel_session(uuid)

        elif state == self.STATE_SELL_INPUT_QUANTITY:
            holdings = self.get_holdings(uuid, broker)
            if quantity > holdings:
                self.game_ctrl.say_to(
                    player.name,
                    self.RED.format("卖出数量超过持有量") + "\n"
                    + f"§f当前持有 §e{broker}：§a{holdings} §f股"
                )
                return
            with self._data_lock:
                sell_min, sell_max = self._get_effective_sell_range(broker)
                base_total = sum(
                    random.randint(sell_min, sell_max)
                    for _ in range(quantity)
                )
                tier = self._get_vip_tier(uuid)
                total = int(base_total * (1 + tier["sell_bonus"]))
                self.add_kp(player.name, total)
                new_hold = self.add_holdings(uuid, broker, -quantity)
            self._add_trade_volume(uuid, total, player.name)
            self.save_data()
            bonus_text = (
                f" §7(等级{tier['name']} §a+{tier['sell_bonus']:.0%}§7)"
                if tier["sell_bonus"] > 0 else ""
            )
            self.game_ctrl.say_to(
                player.name,
                self.H2.format("§a卖出成功") + "\n"
                + f"§f券商：§e{broker}\n"
                + f"§f数量：§e{quantity} §f股\n"
                + f"§f获得：§e{total} {self.scoreboard_name}{bonus_text}\n"
                + f"§f剩余：§a{new_hold} §f股"
            )
            self.cancel_session(uuid)

        else:
            self.cancel_session(uuid)

    # ---------- 持仓 ----------
    def show_holdings(
        self, uuid: str, player_name: str = "", show_nav: bool = True
    ) -> str:
        err = self.require_registered(uuid)
        if err:
            return err
        kp = self.get_kp(player_name) if player_name else 0
        pdata = self.get_player_view(uuid)
        tier = self._get_vip_tier(uuid)
        volume = pdata.get("trade_volume", 0)
        lines = [
            self.H1.format("§e我的持仓"),
            f"§f当前 {self.scoreboard_name}：§e{kp}",
            f"§f当前等级：{tier['color']}§l{tier['name']}§r"
            f" §7(累计交易 §e{volume}§7 {self.scoreboard_name})",
            "",
            "§f持有股票："
        ]
        has_stock = False
        for broker in self.broker_names:
            shares = pdata["holdings"].get(broker, 0)
            if shares > 0:
                eff_min, eff_max = self._get_effective_sell_range(broker)
                lines.append(
                    f"§e• §f{broker}  §a{shares} §f股"
                    f"  §7收益 §a{eff_min}~{eff_max} {self.scoreboard_name}"
                )
                has_stock = True
        if not has_stock:
            lines.append("§7暂无股票")
        lines.append("")
        if show_nav:
            lines.append(self._nav_tip())
        return "\n".join(lines)

    # ---------- 帮助 ----------
    def show_help(self, player_name: str, show_nav: bool = True):
        help_text = (
            self.H2.format("§eCyanStock 菜单") + "\n"
            + "§7v0.1.3 CyanForest特供\n"
            + "\n"
            + self.CMD.format(".券商股票") + " §7» §f主菜单\n"
            + self.CMD.format(".查询") + f" §7» §f查询{self.scoreboard_name}\n"
            + self.CMD.format(".购入") + " §7» §f购入股票\n"
            + self.CMD.format(".出售") + " §7» §f出售股票\n"
            + self.CMD.format(".一键出售") + " §7» §f一键清仓\n"
            + self.CMD.format(".持仓") + " §7» §f持有股票\n"
            + self.CMD.format(".走势") + " §7» §f券商行情\n"
            + self.CMD.format(".券商详情") + " §7» §f单家详情\n"
            + self.CMD.format(".情绪") + " §7» §f市场情绪\n"
            + self.CMD.format(".等级") + " §7» §f等级加成\n"
            + self.CMD.format(".帮助") + " §7» §f本页\n"
        )
        if show_nav:
            help_text += "\n" + self._nav_tip()
        self.say_lines(player_name, help_text)

    # ---------- 聊天指令 ----------
    def on_chat(self, chat: Chat):
        pname = chat.player.name
        uuid = chat.player.uuid
        msg = chat.msg.strip()

        session = self.sessions.get(uuid)
        if session:
            self._touch_session(uuid)
            # 子面板兼容：输入任何 .xxx 命令静默关闭子面板，不留提示
            if msg.startswith("."):
                self.cancel_session(uuid)
                return
            if msg == "q" or msg == "0":
                self.game_ctrl.say_to(pname, "§c已退出交易系统")
                self.cancel_session(uuid)
                return
            state = session.get("state")
            # r 返回主菜单（仅在子面板生效，回到进入前的页码）
            if msg.lower() == "r" and state != self.STATE_MAIN_MENU:
                pdata = self.get_player_view(uuid)
                if pdata.get("registered", False):
                    back_page = session.get("menu_page", 0)
                    self.show_main_menu(chat.player, back_page)
                    self._set_session(uuid, self.STATE_MAIN_MENU, page=back_page)
                else:
                    self.cancel_session(uuid)
                    self.game_ctrl.say_to(pname, "§c请先注册")
                return
            # 主菜单翻页
            if state == self.STATE_MAIN_MENU:
                if msg in ("+", "＋"):
                    cur = session.get("page", 0)
                    total = (
                        len(self.MENU_ITEMS) + self.PAGE_SIZE - 1
                    ) // self.PAGE_SIZE
                    if cur < total - 1:
                        self.show_main_menu(chat.player, cur + 1)
                    return
                if msg in ("-", "－"):
                    cur = session.get("page", 0)
                    if cur > 0:
                        self.show_main_menu(chat.player, cur - 1)
                    return
            # 一键清仓确认
            if state == self.STATE_SELLALL_CONFIRM:
                if msg.lower() in ("y", "yes", "是"):
                    broker = session.get("broker")
                    shares = self.get_holdings(uuid, broker)
                    total = self.sell_all_holdings(uuid, broker, pname)
                    self.game_ctrl.say_to(
                        pname,
                        self.H2.format("§a一键卖出成功") + "\n"
                        + f"§f券商：§e{broker}\n"
                        + f"§f数量：§e{shares} §f股\n"
                        + f"§f获得：§e{total} {self.scoreboard_name}"
                    )
                else:
                    self.game_ctrl.say_to(pname, "§c已取消清仓")
                self.cancel_session(uuid)
                return
            try:
                num = int(msg)
                if state == self.STATE_MAIN_MENU:
                    self.handle_main_menu(chat.player, num)
                elif state in (
                    self.STATE_BUY_SELECT_BROKER,
                    self.STATE_SELL_SELECT_BROKER,
                    self.STATE_SELLALL_SELECT_BROKER,
                    self.STATE_DETAIL_SELECT_BROKER,
                ):
                    self.handle_broker_selection(chat.player, num)
                elif state in (
                    self.STATE_BUY_INPUT_QUANTITY,
                    self.STATE_SELL_INPUT_QUANTITY,
                ):
                    self.handle_quantity_input(chat.player, num)
                elif state == self.STATE_INFO_VIEW:
                    back_page = session.get("menu_page", 0)
                    self.show_main_menu(chat.player, back_page)
                    self._set_session(uuid, self.STATE_MAIN_MENU, page=back_page)
                else:
                    self.cancel_session(uuid)
                    self.game_ctrl.say_to(pname, "§c会话状态异常，请重新操作")
                return
            except ValueError:
                self.game_ctrl.say_to(pname, "§c请输入数字，" + self._nav_tip())
                return

        if msg == ".查询":
            result = self.show_kp_balance(chat.player, show_nav=False)
            self.game_ctrl.say_to(pname, result)
            return

        if msg == ".购入":
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(pname, err)
                return
            self.show_broker_list(chat.player, self.STATE_BUY_SELECT_BROKER)
            return

        if msg == ".出售":
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(pname, err)
                return
            pdata = self.get_player_view(uuid)
            has_stock = any(v > 0 for v in pdata["holdings"].values())
            if not has_stock:
                self.game_ctrl.say_to(pname, "§c你没有任何股票可出售")
                return
            self.show_broker_list(chat.player, self.STATE_SELL_SELECT_BROKER)
            return

        if msg == ".一键出售":
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(pname, err)
                return
            pdata = self.get_player_view(uuid)
            has_stock = any(v > 0 for v in pdata["holdings"].values())
            if not has_stock:
                self.game_ctrl.say_to(pname, "§c你没有任何股票可出售")
                return
            self.show_broker_list(chat.player, self.STATE_SELLALL_SELECT_BROKER)
            return

        if msg == ".券商详情":
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(pname, err)
                return
            self.show_broker_list(chat.player, self.STATE_DETAIL_SELECT_BROKER)
            return

        if msg == ".持仓":
            result = self.show_holdings(uuid, pname, show_nav=False)
            self.game_ctrl.say_to(pname, result)
            return

        if msg == ".走势":
            trend = self.get_trend(show_nav=False)
            self.say_lines(pname, trend)
            return

        if msg == ".情绪":
            result = self.show_market_sentiment(chat.player, show_nav=False)
            self.game_ctrl.say_to(pname, result)
            return

        if msg in (".等级", ".特权", ".会员"):
            result = self.show_vip_status(chat.player, show_nav=False)
            self.game_ctrl.say_to(pname, result)
            return

        if msg in (".帮助", ".列表", ".说明", ".指南"):
            self.show_help(pname, show_nav=False)
            return

        # 旧命令兼容（静默转发，不提示）
        if msg in (".买入", ".购买"):
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(pname, err)
                return
            self.show_broker_list(chat.player, self.STATE_BUY_SELECT_BROKER)
            return
        if msg == ".卖出":
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(pname, err)
                return
            pdata = self.get_player_view(uuid)
            has_stock = any(v > 0 for v in pdata["holdings"].values())
            if not has_stock:
                self.game_ctrl.say_to(pname, "§c你没有任何股票可出售")
                return
            self.show_broker_list(chat.player, self.STATE_SELL_SELECT_BROKER)
            return
        if msg == ".一键卖出":
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(pname, err)
                return
            pdata = self.get_player_view(uuid)
            has_stock = any(v > 0 for v in pdata["holdings"].values())
            if not has_stock:
                self.game_ctrl.say_to(pname, "§c你没有任何股票可出售")
                return
            self.show_broker_list(chat.player, self.STATE_SELLALL_SELECT_BROKER)
            return
        if msg in (".行情", ".股势"):
            trend = self.get_trend(show_nav=False)
            self.say_lines(pname, trend)
            return
        if msg in (".详情", ".公司详情"):
            err = self.require_registered(uuid)
            if err:
                self.game_ctrl.say_to(pname, err)
                return
            self.show_broker_list(chat.player, self.STATE_DETAIL_SELECT_BROKER)
            return

    # ---------- 玩家离开 ----------
    def on_player_leave(self, player: Player):
        with self._sessions_lock:
            self.sessions.pop(player.uuid, None)

    # ---------- 退出 ----------
    def on_frame_exit(self, evt: FrameExit):
        self._timer_running = False
        self._autosave_running = False
        self._event_running = False
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=1)
        if self._autosave_thread is not None:
            self._autosave_thread.join(timeout=2)
        if self._event_thread is not None:
            self._event_thread.join(timeout=1)
        self._flush_save()
        self.print_war("§e数据已保存")


entry = plugin_entry(StockBrokerPlugin)

import time
from collections.abc import Callable
from tooldelta import utils, cfg as config, Plugin, fmts, plugin_entry


class BetterAnnounce(Plugin):
    name = "更好的公告栏"
    author = "SuperScript"
    version = (0, 0, 10)

    def __init__(self, f):
        super().__init__(f)
        CFG = {
            "公告内容(公告内容:计分板数字)": {
                r"§7%m/%d/20%y 星期[星期]": 0,
                r"§a%H§f : §a%M": -1,
                r"§f在线人数: §a[在线人数]": -2,
                r"§6TPS: [TPS带颜色]§7/20": -3,
                r"§d欢迎大家游玩": -4,
            },
            "公告标题栏名(请注意长度)": "公告",
            "刷新频率(秒)": 20,
        }
        CFG_STD = {
            "公告内容(公告内容:计分板数字)": config.AnyKeyValue(int),
            "公告标题栏名(请注意长度)": str,
            "刷新频率(秒)": int,
        }
        cfg, _ = config.get_plugin_config_and_version(
            self.name, CFG_STD, CFG, self.version
        )
        self.anos = cfg["公告内容(公告内容:计分板数字)"]
        self.flush_secs = cfg["刷新频率(秒)"]
        self.ano_title = cfg["公告标题栏名(请注意长度)"]
        self.formatters: dict[str, Callable[[], str]] = {}
        if len(self.ano_title) >= 20:
            fmts.print_war(f"公告标题超出20字符长度: {self.ano_title}, 可能失效")
        if self.flush_secs < 2:
            fmts.print_err("公告刷新速率不能大于 1次/2秒")
            raise SystemExit
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        self.tpscalc = self.GetPluginAPI("tps计算器", (0, 0, 1), False)

    def on_inject(self):
        self.ftime = 100
        self.locked = False
        self.flush_gg()
        self.flush_announcement1()

    # ------ API ------
    def regist_formatter(self, formatter: str, formatter_func: Callable[[], str]):
        self.formatters[formatter] = formatter_func

    # -----------------

    @utils.thread_func("公告刷新")
    def flush_gg(self):
        self.game_ctrl.sendwocmd("/scoreboard objectives remove 公告")
        time.sleep(0.3)
        self.game_ctrl.sendwocmd(
            f'/scoreboard objectives add 公告 dummy "{self.ano_title}"'
        )
        self.game_ctrl.sendwocmd("/scoreboard objectives setdisplay sidebar 公告")

    def get_tps_str(self, color=False):
        if self.tpscalc is None:
            return "§c无前置tps计算器"
        elif color:
            return self.get_tps_color() + str(round(self.tpscalc.get_tps(), 1))
        else:
            return str(round(self.tpscalc.get_tps(), 1))

    def get_tps_color(self):
        tps = self.tpscalc.get_tps()
        if tps > 14:
            return "§a"
        elif tps > 10:
            return "§6"
        else:
            return "§c"

    @utils.timer_event(1, "计分板公告刷新")
    @utils.thread_func("计分板公告刷新")
    def flush_announcement1(self):
        if self.locked:
            return
        self.locked = True
        scmd = self.game_ctrl.sendwocmd
        self.ftime += 1
        if self.ftime > self.flush_secs:
            self.ftime = 0
            scmd("/scoreboard players reset * 公告")
            basic_args = {
                "[在线人数]": len(self.game_ctrl.allplayers),
                "[星期]": "一二三四五六日"[time.localtime().tm_wday],
                "[TPS]": self.get_tps_str(),
                "[TPS带颜色]": self.get_tps_str(True),
            }
            extra_args = {k: v() for k, v in self.formatters.items()}
            basic_args.update(extra_args)
            for text, scb_score in self.anos.items():
                text = time.strftime(
                    utils.simple_fmt(
                        basic_args,
                        text,
                    )
                )
                scmd(f'/scoreboard players set "{text}" 公告 {scb_score}')
        self.locked = False


entry = plugin_entry(BetterAnnounce, "更好的公告栏")

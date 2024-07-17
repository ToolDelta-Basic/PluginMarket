import random
import time

from tooldelta import Builtins, Config, Plugin, Print, plugins


@plugins.add_plugin
class BetterAnnounce(Plugin):
    name = "更好的公告栏"
    author = "SuperScript"
    version = (0, 0, 5)

    def on_def(self):
        self.funclib = plugins.get_plugin_api("基本插件功能库")
        CFG = {
            "公告内容(公告内容:计分板数字)": {
                r"§7%m/%d/20%y 星期[星期]": 0,
                r"§a%H§f : §a%M": -1,
                r"§f在线人数: §a[在线人数]": -2,
                r"§d欢迎大家游玩": -3,
            },
            "公告标题栏名(请注意长度)": "公告",
            "刷新频率(秒)": 20,
        }
        std = Config.auto_to_std(CFG)
        cfg, _ = Config.getPluginConfigAndVersion(self.name, std, CFG, self.version)  # type: ignore
        self.anos = cfg["公告内容(公告内容:计分板数字)"]
        self.flush_secs = cfg["刷新频率(秒)"]
        self.ano_title = cfg["公告标题栏名(请注意长度)"]
        if len(self.ano_title) >= 15:
            Print.print_err(f"公告标题超出15字符长度: {self.ano_title}")
            raise SystemExit
        elif self.flush_secs < 2:
            Print.print_err("公告刷新速率不能大于 1次/2秒")
            raise SystemExit

    def on_inject(self):
        self.flush_gg()
        self.flush_announcement1()

    @Builtins.thread_func
    def flush_gg(self):
        self.game_ctrl.sendwocmd("/scoreboard objectives remove 公告")
        time.sleep(0.3)
        self.game_ctrl.sendwocmd(
            f"/scoreboard objectives add 公告 dummy {self.ano_title}"
        )
        self.game_ctrl.sendwocmd("/scoreboard objectives setdisplay sidebar 公告")

    @Builtins.thread_func("计分板公告刷新")
    def flush_announcement1(self):
        scmd = self.game_ctrl.sendwocmd
        ftime = 100
        while 1:
            time.sleep(1)
            ftime += 1
            if ftime > self.flush_secs:
                ftime = 0
                scmd("/scoreboard players reset * 公告")
                for text, scb_score in self.anos.items():
                    text = time.strftime(
                        Builtins.SimpleFmt(
                            {
                                "[在线人数]": len(self.game_ctrl.allplayers),
                                "[随机]": random.randint(1, 5),
                                "[星期]": "一二三四五六日"[time.localtime().tm_wday],
                            },
                            text,
                        )
                    )
                    scmd(f'/scoreboard players set "{text}" 公告 {scb_score}')

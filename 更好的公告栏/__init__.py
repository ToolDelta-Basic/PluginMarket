import time, random

from tooldelta import Plugin, plugins, Config, Builtins, Print

@plugins.add_plugin
class BetterAnnounce(Plugin):
    name = "更好的公告栏"
    author = "SuperScript"
    version = (0, 0, 1)

    def on_def(self):
        self.funclib = plugins.get_plugin_api("基本插件功能库")
        CFG = {
            "公告内容(列表的每项代表一行公告)": [
                "§7%m/%d/%y",
                "§a%H§f : §a%M",
                "§f在线人数: §a[在线人数]",
                "§d欢迎大家游玩"
            ],
            "公告标题栏名(请注意长度)": "公告",
            "刷新频率(秒)": 20
        }
        std = Config.auto_to_std(CFG)
        cfg, _ = Config.getPluginConfigAndVersion(self.name, std, CFG, self.version)
        self.anos = cfg["公告内容(列表的每项代表一行公告)"]
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

    @Builtins.new_thread
    def flush_gg(self):
        self.game_ctrl.sendwocmd("/scoreboard objectives remove 公告")
        time.sleep(0.3)
        self.game_ctrl.sendwocmd(f"/scoreboard objectives add 公告 dummy {self.ano_title}")
        self.game_ctrl.sendwocmd("/scoreboard objectives setdisplay sidebar 公告")

    @Builtins.new_thread
    def flush_announcement1(self):
        scmd = self.game_ctrl.sendwocmd
        ftime = 100
        posix = len(self.anos)  // 2
        while 1:
            time.sleep(1)
            ftime += 1
            if ftime > self.flush_secs:
                ftime = 0
                scmd(f"/scoreboard players reset * 公告")
                new_posix = posix
                for i in self.anos:
                    text = time.strftime(Builtins.SimpleFmt(
                        {
                            "[在线人数]": len(self.game_ctrl.allplayers),
                            "[随机]": random.randint(1, 5)
                        }, i
                    ))
                    scmd(f'/scoreboard players set "{text}" 公告 {new_posix}')
                    new_posix -= 1

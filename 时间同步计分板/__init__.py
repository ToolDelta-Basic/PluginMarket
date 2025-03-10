import datetime
from tooldelta import Plugin, utils, Config, plugin_entry


class ScoreboardTime(Plugin):
    name = "时间同步计分板"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        CFG_DEFAULT = {
            "同步到哪个计分板上": "time",
            "同步间隔秒数": 20,
            "是否同步年月日": True,
            "是否同步星期": True,
        }
        cfg, _ = Config.get_plugin_config_and_version(
            self.name, Config.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, self.version
        )
        self.sync_gap = cfg["同步间隔秒数"]
        self.sync_scbname = cfg["同步到哪个计分板上"]
        self.sync_yms = cfg["是否同步年月日"]
        self.sync_wd = cfg["是否同步星期"]
        self.ListenActive(self.on_inject)

    def on_inject(self):
        utils.timer_event(self.sync_gap, "时间同步计分板")(self.sync_time)()

    def sync_time(self):
        now = datetime.datetime.now()
        swcmd = self.game_ctrl.sendwocmd
        scbname = self.sync_scbname
        if self.sync_yms:
            swcmd(f"scoreboard players set 年 {scbname} {now.year}")
            swcmd(f"scoreboard players set 月 {scbname} {now.month}")
            swcmd(f"scoreboard players set 日 {scbname} {now.day}")
        if self.sync_wd:
            swcmd(f"scoreboard players set 星期 {scbname} {now.weekday() + 1}")
        swcmd(f"scoreboard players set 时 {scbname} {now.hour}")
        swcmd(f"scoreboard players set 分 {scbname} {now.minute}")
        swcmd(f"scoreboard players set 秒 {scbname} {now.second}")


entry = plugin_entry(ScoreboardTime)

from tooldelta import Plugin, plugin_entry,cfg, game_utils, fmts

class SystemOnline(Plugin):
    name = "系统上线提示"
    author = "Mono"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        DEFAULT_CFG = {"启动时信息显示": [
			[
				"@a",
				"§6§l * §r§o§bToolDelta §r§aSystem Online"
			],
			[
				"@a[m=c]",
				"前往 插件配置文件/系统上线提示.json 配置"
			]
		]}
        STD_CFG_TYPE = {"启动时信息显示": cfg.JsonList(cfg.JsonList(str,2))}
        self.cfg, ver = cfg.get_plugin_config_and_version(
            self.name, STD_CFG_TYPE, DEFAULT_CFG, self.version
        )
        self.ListenActive(self.on_bot_working)
        
    def on_bot_working(self):
        for i in self.cfg["启动时信息显示"]:
            self.game_ctrl.say_to(i[0], i[1])

        

entry = plugin_entry(SystemOnline)
from tooldelta import Frame, Plugin, utils, Chat, plugin_entry, cfg


class reload(Plugin):
    version = (0, 0, 1)
    name = "重启"
    author = "大庆油田"
    description = "重启"

    def __init__(self, frame: Frame):
        super().__init__(frame)
        self.ListenChat(self.on_chat)
        CFG_DEFAULT = {"允许使用人": ""}
        cfg_std = cfg.auto_to_std(CFG_DEFAULT)
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg_std, CFG_DEFAULT, self.version
        )
        self.op = self.cfg["允许使用人"]

    @utils.thread_func("reload", thread_level=utils.ToolDeltaThread.SYSTEM)
    def on_chat(self, chat: Chat):
        if chat.msg == ".reload" and chat.player.name == self.op:
            self.frame.reload()


entry = plugin_entry(reload)

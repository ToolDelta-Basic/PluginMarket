import os

from tooldelta import Plugin, cfg, plugin_entry

from .config_mixin import QQLinkerConfigMixin
from .message_utils import QQMsgTrigger
from .orion_mixin import QQLinkerOrionMixin
from .qq_mixin import QQLinkerQQMixin
from .runtime_mixin import QQLinkerRuntimeMixin


class QQLinker(
    QQLinkerQQMixin,
    QQLinkerOrionMixin,
    QQLinkerRuntimeMixin,
    QQLinkerConfigMixin,
    Plugin,
):
    version = (0, 2, 15)
    name = "群服互通云链版Ultra版"
    author = "大庆油田 / 小六神"
    description = "提供多群独立管理的群服互通、QQ群管理员体系和 Orion 联动封禁功能"
    QQMsgTrigger = QQMsgTrigger

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        self.group_state_dir = self.format_data_path("群聊权限数据")
        os.makedirs(self.group_state_dir, exist_ok=True)

        self.ws = None
        self.reloaded = False
        self.available = False
        self.triggers: list[QQMsgTrigger] = []
        self.waitmsg_cbs = {}
        self.plugin = []
        self._manual_launch = False
        self._manual_launch_port = -1
        self.tps_calc = None
        self.orion = None
        self.whitelist_checker = None

        raw_cfg, _ = cfg.get_plugin_config_and_version(
            self.name,
            {},
            self.cfg_default(),
            self.version,
        )
        self.cfg = self.migrate_config(raw_cfg)
        cfg.check_auto(self.cfg_std(), self.cfg)
        cfg.upgrade_plugin_config(self.name, self.cfg, self.version)

        self.group_cfgs = {}
        self.group_order = []
        self.reload_group_configs()

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)

    def on_def(self):
        self.tps_calc = self.GetPluginAPI("tps计算器", (0, 0, 1), False)
        self.orion = self.GetPluginAPI("Orion_System", force=False)
        self.whitelist_checker = self.GetPluginAPI("白名单&管理员检测云链联动版", force=False)

    def on_inject(self):
        self.print("尝试连接到群服互通云链版Ultra版机器人..")
        if not self._manual_launch:
            self.connect_to_websocket()
        self.init_basic_triggers()

    def init_basic_triggers(self):
        self.frame.add_console_cmd_trigger(
            ["QQ", "发群"],
            "[群号可选] [消息]",
            "在群内发消息测试",
            self.on_sendmsg_test,
        )
        self.frame.add_console_cmd_trigger(
            ["OPQQ"],
            None,
            "进入QQ群管理员增删菜单",
            self.on_console_add_qq_op,
        )


entry = plugin_entry(QQLinker, "群服互通")

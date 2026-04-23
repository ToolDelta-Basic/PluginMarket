"""
群服互通云链版 Ultra 的入口模块。
这个文件故意保持得比较薄：
1. 统一声明插件元信息和生命周期入口。
2. 在构造阶段准备所有 mixin 共用的运行时状态。
3. 把真正的配置、QQ 菜单、Orion 联动、WebSocket 运行逻辑交给拆分后的模块。
"""

import os
import threading

from tooldelta import Plugin, cfg, fmts, plugin_entry

from .config_mixin import QQLinkerConfigMixin
from .message_utils import QQMsgTrigger
from .orion_mixin import QQLinkerOrionMixin
from .qq_mixin import QQLinkerQQMixin
from .runtime_mixin import QQLinkerRuntimeMixin


# 入口类只负责装配 mixin 和生命周期注册，具体业务逻辑拆在各模块里。
class QQLinker(
    QQLinkerQQMixin,
    QQLinkerOrionMixin,
    QQLinkerRuntimeMixin,
    QQLinkerConfigMixin,
    Plugin,
):
    version = (1, 0, 0)
    name = "群服互通云链版Ultra版"
    author = "大庆油田 / 小六神"
    description = "提供多群独立管理的群服互通、QQ群管理员体系和 Orion 联动封禁功能"
    QQMsgTrigger = QQMsgTrigger

    @staticmethod
    def console_menu_header(title: str) -> str:
        return (
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓"
            "§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧\n"
            f"§l§d❐§f 『§6群服互通云链版Ultra版§f』 §b{title}"
        )

    @staticmethod
    def console_menu_footer(page_label: str, body: str) -> str:
        return (
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓 "
            f"§r§7[ §b{page_label} §7] "
            "§l§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧\n"
            f"§r{body}"
        )

    def print_console_info(self, text: str):
        # 按统一 UI 风格输出控制台普通信息。
        fmts.print_inf(f"§a❀ §b{text}")

    def print_console_success(self, text: str):
        # 按统一 UI 风格输出控制台成功信息。
        fmts.print_suc(f"§a❀ §b{text}")

    def print_console_warn(self, text: str):
        # 按统一 UI 风格输出控制台警告信息。
        fmts.print_war(f"§6❀ §e{text}")

    def print_console_error(self, text: str):
        # 按统一 UI 风格输出控制台错误信息。
        fmts.print_err(f"§c❀ §e{text}")

    def print_console_card(
        self,
        title: str,
        page_label: str,
        body_lines: list[str],
        level: str = "info",
    ):
        card = (
            self.console_menu_header(title)
            + "\n"
            + self.console_menu_footer(
                page_label,
                "\n".join(
                    i if i.startswith("§") else f"§a❀ §b{i}" for i in body_lines
                ),
            )
        )
        {
            "info": fmts.print_inf,
            "success": fmts.print_suc,
            "warn": fmts.print_war,
            "error": fmts.print_err,
        }.get(level, fmts.print_inf)(card)

    def __init__(self, frame):
        """
        初始化插件的共享状态。
        这里不直接做网络连接或重逻辑初始化，只准备后续各 mixin 需要共享的状态容器。
        真正依赖外部插件 API 的动作，会留到 `on_def` / `on_inject` 再做。
        """
        super().__init__(frame)
        self.make_data_path()
        self.group_state_dir = self.format_data_path("群聊权限数据")
        os.makedirs(self.group_state_dir, exist_ok=True)

        # 运行时状态集中放在入口类上，方便多个 mixin 共享同一份上下文。
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
        self._ws_runner_lock = threading.Lock()
        self._ws_runner_active = False
        self._ws_session_id = 0
        self._ws_reconnect_delay = None

        # 配置只在启动时加载和归一化一次，后续 mixin 统一读 self.cfg。
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
        """
        在 preload 阶段拿前置插件 API。
        这些对象都可能被多个 mixin 使用，所以统一在入口层绑定一次，
        后面各模块直接读 `self.xxx`，不用重复向 ToolDelta 申请。
        """
        self.tps_calc = self.GetPluginAPI("tps计算器", (0, 0, 1), False)
        self.orion = self.GetPluginAPI("Orion_System", force=False)
        self.whitelist_checker = self.GetPluginAPI("白名单&管理员检测云链联动版", force=False)

    def on_inject(self):
        """
        在框架注入完成后启动主动能力。
        这一步才真正尝试连云链，因为这时前置 API、配置和游戏控制器都已经可用。
        """
        self.print_console_card(
            "群服互通 云链连接",
            "准备启动",
            ["正在准备云链连接"],
            level="info",
        )
        if not self._manual_launch:
            self.connect_to_websocket()
        self.init_basic_triggers()

    def init_basic_triggers(self):
        # 注册给控制台使用的少量入口命令。
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

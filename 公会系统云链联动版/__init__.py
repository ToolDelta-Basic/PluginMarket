"""Guild cloud interop ToolDelta plugin entrypoint."""

from threading import Event
from typing import Dict, TYPE_CHECKING as PY_TYPE_CHECKING

from tooldelta import (
    FrameExit,
    Player,
    Plugin,
    ToolDelta,
    TYPE_CHECKING,
    plugin_entry,
    utils,
)
from tooldelta.constants import PacketIDS
from tooldelta.utils import tempjson

from guild_cloud_interop.matchers import ItemNameMatcher
from guild_cloud_interop.handlers import handlers
from guild_cloud_interop.handlers_quick import handlers_quick
from guild_cloud_interop.logic import logic_functions
from guild_cloud_interop.api import guild_api_functions
from guild_cloud_interop.control import GuildManager
from guild_cloud_interop.config import Config, PLUGIN_ENABLED_KEY
from guild_cloud_interop.config_watcher import (
    config_reload_task,
    refresh_config_file_state,
)
from guild_cloud_interop.ui import wrap_player

if PY_TYPE_CHECKING:
    from 前置_聊天栏菜单 import ChatbarMenu
    from 前置_玩家XUID获取 import XUIDGetter


def _normalize_chatbar_trigger(trigger: object, fallback: str = "公会") -> str:
    """Return the trigger token expected by 聊天栏菜单.add_new_trigger."""
    if not isinstance(trigger, str):
        return fallback
    normalized = trigger.strip()
    while normalized.startswith("."):
        normalized = normalized[1:].strip()
    return normalized or fallback


# FIRE 公会插件主类 FIRE
class GuildPlugin(Plugin):
    """ToolDelta plugin entrypoint for guild cloud interop."""

    name = "公会系统云链联动版"
    author = "星林 & 夏至"
    version = (0, 1, 7)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)

        self.config = Config.load(self.name, self.version)
        self.guilds_file = self.format_data_path("公会数据文件.json")
        self.guild_manager = GuildManager(self.guilds_file)
        self.guild_chat_mode: Dict[str, bool] = {}
        self._stop_event = Event()
        self._effect_refresh_cache = {}
        self._guild_menu_callback = None
        self._guild_menu_chatbar_entry = None
        self._guild_runtime_events = {}
        self._config_file_state = None
        self.chatbar = None
        self.xuidm = None
        self.item_matcher = ItemNameMatcher()
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenFrameExit(self.on_frame_exit)
        self.exp_thread = utils.createThread(
            self.guild_exp_task, usage="公会经验增加任务")
        self.online_thread = utils.createThread(
            self.update_online_task, usage="在线状态更新任务")
        refresh_config_file_state(self)
        self.config_thread = utils.createThread(
            config_reload_task, args=(self,), usage="公会配置热更新任务")

    def _plugin_enabled(self) -> bool:
        """Implement the plugin enabled operation."""
        return bool(getattr(self, "config", {}).get(PLUGIN_ENABLED_KEY, False))

    def get_config_file_state(self):
        """Return the last observed runtime config file state."""
        return getattr(self, "_config_file_state", None)

    def set_config_file_state(self, state) -> None:
        """Store the last observed runtime config file state."""
        self._config_file_state = state

    def reset_effect_refresh_cache(self) -> None:
        """Clear cached guild effect refresh timestamps."""
        self._effect_refresh_cache = {}

    def should_stop_runtime_task(self) -> bool:
        """Return whether background runtime tasks should exit."""
        return self._stop_event.is_set()

    def wait_runtime_task_or_stopped(self, seconds: float) -> bool:
        """Wait for a background interval or until shutdown is requested."""
        return self._stop_event.wait(seconds)

    def on_def(self):
        """Implement the on def operation."""
        if not self._plugin_enabled():
            return

        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.xuidm = self.GetPluginAPI("XUID获取")

        if TYPE_CHECKING:
            self.chatbar = self.get_typecheck_plugin_api(ChatbarMenu)
            self.xuidm = self.get_typecheck_plugin_api(XUIDGetter)

    def ui_callback(self, callback):
        """Implement the ui callback operation."""
        if self is None:
            return callback

        def wrapped(player, args):
            """Implement the wrapped operation."""
            return callback(wrap_player(player), args)

        return wrapped

    def _guild_menu_commands(self) -> list[str]:
        """Implement the guild menu commands operation."""
        if self is None:
            return ["公会"]
        raw_triggers = getattr(Config, "GUILD_MENU_TRIGGER", ["公会"])
        if isinstance(raw_triggers, str):
            raw_triggers = [raw_triggers]
        if not isinstance(raw_triggers, list):
            raw_triggers = ["公会"]

        commands: list[str] = []
        for trigger in raw_triggers:
            command = _normalize_chatbar_trigger(trigger, "")
            if command and command not in commands:
                commands.append(command)
        return commands or ["公会"]

    def _find_guild_menu_chatbar_entry(self):
        """Implement the find guild menu chatbar entry operation."""
        chatbar_entry = getattr(self, "_guild_menu_chatbar_entry", None)
        if chatbar_entry is not None:
            return chatbar_entry

        chatbar = getattr(self, "chatbar", None)
        chatbar_triggers = getattr(chatbar, "chatbar_triggers", None)
        if not isinstance(chatbar_triggers, list):
            return None
        triggers = list(chatbar_triggers)

        callback = getattr(self, "_guild_menu_callback", None)
        for candidate in triggers:
            if getattr(candidate, "usage", None) != "公会系统指令":
                continue
            if callback is not None and getattr(
                    candidate, "func", None) is not callback:
                continue
            self._guild_menu_chatbar_entry = candidate
            return candidate
        return None

    def sync_runtime_config_bindings(self):
        """Apply hot-reloaded config values that are registered outside Config."""
        chatbar_entry = self._find_guild_menu_chatbar_entry()
        if chatbar_entry is None:
            return

        commands = self._guild_menu_commands()
        current_commands = list(getattr(chatbar_entry, "triggers", []))
        if current_commands == commands:
            return

        chatbar_entry.triggers = commands

    def on_inject(self):
        """Implement the on inject operation."""
        if not self._plugin_enabled():
            return

        self.game_ctrl.sendwocmd(
            f"/scoreboard objectives add {Config.GUILD_SCOREBOARD} dummy 积分")
        self.game_ctrl.sendwocmd(
            f"/scoreboard players add @a {Config.GUILD_SCOREBOARD} 0")
        guild_menu_commands = self._guild_menu_commands()
        self._guild_menu_callback = self.ui_callback(self.guild_menu_cb)
        self.chatbar.add_new_trigger(
            guild_menu_commands,
            [("", str, "")],
            "公会系统指令",
            self._guild_menu_callback,
        )
        chatbar_triggers = getattr(self.chatbar, "chatbar_triggers", None)
        if isinstance(chatbar_triggers, list) and chatbar_triggers:
            self._guild_menu_chatbar_entry = chatbar_triggers[-1]

        trigger_configs = [
            {"commands": ["gc", "公会聊天"],
             "args": [("message", str, "")],
             "description": "公会聊天频道", "callback": self.guild_chat_cb, },
            {"commands": ["仓库出售", "出售"],
             "args":
             [("item_id", str, ""),
              ("count", int, 1),
              ("price", int, 0)],
             "description": "快速出售物品到仓库", "callback": self.quick_vault_sell, },
            {"commands": ["自定义出售"],
             "args":
             [("item_id", str, ""),
              ("count", int, 1),
              ("price", int, 0)],
             "description": "自定义价格出售物品到仓库",
             "callback": self.custom_vault_sell, },
            {"commands": ["物品列表", "支持物品"],
             "args": [("", str, "")],
             "description": "查看支持的物品名称列表", "callback": self.show_item_list, },
            {"commands": ["清理公会数据"],
             "args": [("confirm", str, "")],
             "description": "清理所有公会数据 (管理员专用)",
             "callback": self.admin_clear_guild_data, },
            {"commands": ["调试公会菜单"],
             "args": [("", str, "")],
             "description": "调试公会菜单显示问题", "callback": self.debug_guild_menu, },
            {"commands": ["调试据点功能"],
             "args": [("", str, "")],
             "description": "调试据点功能问题",
             "callback": self.debug_base_function, },]

        # 注册数据更新菜单
        self.frame.add_console_cmd_trigger(
            ["更新公会数据"],
            "", "更新由于版本更新导致的数据丢失",
            self.guild_update_data
        )
        for trigger in trigger_configs:
            self.chatbar.add_new_trigger(
                trigger["commands"],
                trigger["args"],
                trigger["description"],
                self.ui_callback(trigger["callback"]),
            )

        self.ListenPacket(PacketIDS.IDText, self.on_chat_packet)
        self.ListenPacket(PacketIDS.IDPlayerAction, self.on_player_action)

    def on_player_join(self, player: Player):
        """Implement the on player join operation."""
        if not self._plugin_enabled():
            return

        player_name = getattr(player, "safe_name", player.name)
        self.game_ctrl.sendcmd(
            f"/scoreboard players add {player_name} {Config.GUILD_SCOREBOARD} 0")
        self._apply_guild_effects_to_player(
            player.name, force=True, command_delay=0)

    def on_frame_exit(self, _: FrameExit):
        """Implement the on frame exit operation."""
        self._stop_event.set()
        try:
            if not self.guild_manager.flush_dirty_guilds():
                self.print_err("保存公会数据失败")
        except Exception as err:
            self.print_err(f"保存公会数据失败: {err}")
        try:
            tempjson.flush(self.guilds_file)
        except Exception:
            pass
        for attr in ("exp_thread", "online_thread", "config_thread"):
            thread = getattr(self, attr, None)
            if thread is None:
                continue
            try:
                thread.stop()
            except Exception:
                pass


for name, func in {**handlers, **handlers_quick, **
                   logic_functions, **guild_api_functions}.items():
    setattr(GuildPlugin, name, func)


entry = plugin_entry(GuildPlugin, "guild-cloud-interop")

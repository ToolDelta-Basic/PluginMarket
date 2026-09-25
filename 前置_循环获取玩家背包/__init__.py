"""ToolDelta pre-plugin that polls online player inventories via WebSocket commands."""

from __future__ import annotations

import threading
from typing import Any

from tooldelta import (
    FrameExit,
    InternalBroadcast,
    Plugin,
    ToolDelta,
    plugin_entry,
    utils,
)

from .config import DEFAULT_CONFIG, STANDARD_CONFIG
from .core import (
    InventoryService,
    WebSocketCommandUnavailable,
    validate_cycle_seconds,
)


class GlobalGetPlayerInventory(Plugin):
    """循环查询在线玩家背包并通过内部广播提供给其他插件。"""

    name = "前置-循环获取玩家背包"
    author = "小六神"
    version = (0, 0, 1)
    description = "使用 WebSocket 指令循环查询在线玩家背包，并通过 API 广播对象和字典数据"

    def __init__(self, frame: ToolDelta):
        """初始化插件：加载配置、构建背包服务并注册事件监听。"""
        super().__init__(frame)
        self.cfg, _ = self.get_config_and_version(STANDARD_CONFIG, DEFAULT_CONFIG)
        self._stop_event = threading.Event()
        self._paused = False
        self._warned_websocket_unavailable = False
        self._service = InventoryService(
            self.game_ctrl,
            self._get_online_players,
            publish=self._publish_inventory,
        )
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_frame_exit)
        self.ListenInternalBroadcast("ggpi:force_update", self._on_force_update)
        self.ListenInternalBroadcast("ggpi:set_cycle", self._on_set_cycle)

    def _get_online_players(self) -> list[Any]:
        """Return all online players and include the ToolDelta bot."""
        players_api = getattr(self.game_ctrl, "players", None)
        if players_api is None:
            return []
        try:
            players = list(players_api.getAllPlayers() or [])
        except (AttributeError, TypeError, ValueError):
            players = []
        # During login/logout transitions ``getBotInfo`` can briefly be
        # unavailable.  A missing bot must not discard the regular players.
        try:
            bot = players_api.getBotInfo()
        except (AttributeError, TypeError, ValueError):
            bot = None
        if bot is not None and getattr(bot, "online", True):
            names = {getattr(player, "name", None) for player in players}
            if getattr(bot, "name", None) not in names:
                players.append(bot)
        return players

    def _websocket_available(self) -> bool:
        """Detect WebSocket command support without sending a probe command."""
        if not callable(getattr(self.game_ctrl, "sendwscmd", None)):
            return False
        launcher = getattr(self.game_ctrl, "launcher", None)
        if launcher is not None and not callable(getattr(launcher, "sendwscmd", None)):
            return False
        return True

    def _warn_websocket_unavailable(self):
        """Print the unsupported-launcher warning only once."""
        if self._warned_websocket_unavailable:
            return
        self._warned_websocket_unavailable = True
        self.print_war("当前接入点不支持 WebSocket 指令，已暂停循环获取玩家背包")

    def on_inject(self):
        """Start polling after ToolDelta and the game connection are ready."""
        if not self._websocket_available():
            self._paused = True
            self._warn_websocket_unavailable()
            return
        self._paused = False
        self._stop_event.clear()
        self._main_thread()

    def on_frame_exit(self, _: FrameExit):
        """Stop the polling loop when ToolDelta unloads the plugin."""
        self._stop_event.set()

    def _publish_inventory(self, snapshot: dict[str, Any]):
        """Broadcast the latest inventory snapshot to all plugins."""
        self.BroadcastEvent(
            InternalBroadcast("ggpi:publish_player_inventory", snapshot)
        )

    def _on_force_update(self, _: InternalBroadcast):
        """Handle a broadcast request for an immediate full scan."""
        if self._paused:
            return None
        return self.force_update()

    def _on_set_cycle(self, event: InternalBroadcast):
        """Update the polling interval from an internal broadcast."""
        data = event.data if isinstance(event.data, dict) else {}
        value = data.get("间隔", data.get("cycle"))
        if value is not None:
            self.set_cycle(value)
        return self.cfg["发送命令间隔时长(单位：秒)"]

    def set_cycle(self, seconds: float):
        """Set the in-memory delay between completed scans."""
        self.cfg["发送命令间隔时长(单位：秒)"] = validate_cycle_seconds(seconds)

    def force_update(self):
        """Immediately scan all online players and broadcast the snapshot."""
        if self._paused:
            return None
        try:
            return self._service.scan_and_publish(
                timeout=float(self.cfg["单次查询超时时间(秒)"])
            )
        except WebSocketCommandUnavailable:
            # Keep direct API callers consistent with the background loop:
            # unsupported launchers pause polling and emit one warning.
            self._paused = True
            self._warn_websocket_unavailable()
            return None

    def query_inventory(self, player_name: str, timeout: float | None = None):
        """Immediately query one online player and update its cache entry."""
        return self._service.query_inventory(
            player_name,
            timeout=float(
                self.cfg["单次查询超时时间(秒)"] if timeout is None else timeout
            ),
        )

    def queryInventory(self, player_name: str, timeout: float | None = None):
        """CamelCase alias matching ToolDelta ``Player.queryInventory()``."""
        return self.query_inventory(player_name, timeout)

    def get_cached_inventory(self, player_name: str):
        """Return a cloned cached inventory for one player."""
        return self._service.get_cached_inventory(player_name)

    def get_cached_inventories(self):
        """Return cloned cached inventory objects for all players."""
        return self._service.get_cached_inventories()

    def get_cached_inventories_dict(self):
        """Return all cached inventories as raw dictionaries."""
        return self._service.get_cached_inventories_dict()

    def get_last_failures(self):
        """Return failure metadata from the latest completed scan."""
        return self._service.get_last_failures()

    @utils.thread_func("循环获取玩家背包")
    def _main_thread(self):
        """Run scans until the plugin is unloaded."""
        while not self._stop_event.is_set():
            try:
                self.force_update()
            except WebSocketCommandUnavailable:
                self._paused = True
                self._warn_websocket_unavailable()
                return
            except Exception as exc:  # keep the next cycle alive on transient errors
                self.print_war(f"循环获取玩家背包本轮失败: {exc}")
            if self._paused:
                return
            self._stop_event.wait(float(self.cfg["发送命令间隔时长(单位：秒)"]))


entry = plugin_entry(GlobalGetPlayerInventory, "循环获取玩家背包", (0, 0, 1))

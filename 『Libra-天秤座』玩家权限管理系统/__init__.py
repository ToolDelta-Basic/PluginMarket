"""『Libra-天秤座』玩家权限管理系统的 ToolDelta 入口。"""
from __future__ import annotations

import threading
from typing import Any

try:
    from tooldelta import Plugin, ToolDelta, cfg, plugin_entry
except ImportError:  # pragma: no cover
    Plugin = object  # type: ignore
    ToolDelta = Any  # type: ignore
    cfg = None  # type: ignore

    def plugin_entry(cls, *args):  # type: ignore[misc]
        """ToolDelta 不可用时的占位实现，直接返回插件类。"""
        return cls

try:
    from .config import ConfigManager
    from .core import CONSOLE_ROOT_TRIGGER, format_flags, parse_flags, permission_descriptions
    from .abilities import permission_category
    from .identity import IdentityIndex
    from .menu import ConsoleMenuMixin
    from .service import PermissionService
    from .storage import StateStore
    from .realtime import RealtimeManager
except ImportError:  # pragma: no cover
    from config import ConfigManager  # type: ignore
    from core import CONSOLE_ROOT_TRIGGER, format_flags, parse_flags, permission_descriptions  # type: ignore
    from abilities import permission_category  # type: ignore
    from identity import IdentityIndex  # type: ignore
    from menu import ConsoleMenuMixin  # type: ignore
    from service import PermissionService  # type: ignore
    from storage import StateStore  # type: ignore
    from realtime import RealtimeManager  # type: ignore


class ServerPermissionManager(ConsoleMenuMixin, PermissionService, IdentityIndex, Plugin):
    name = "『Libra-天秤座』玩家权限管理系统"
    author = "小六神"
    version = (0, 2, 0)
    description = (
        "\n§d✦§f━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━§d✦\n"
        "§l§b『Libra-天秤座』§f玩家权限管理系统\n"
        "§l§b[ §e1§b ] §r§eOrion 风格控制台总菜单与数字选择交互\n"
        "§l§b[ §e2§b ] §r§e接入 XUID获取 API，支持在线/离线玩家搜索\n"
        "§l§b[ §e3§b ] §r§e管理员列表读取与 XUID 对应玩家名解析\n"
        "§l§b[ §e4§b ] §r§e8 位权限标志设置与在线/离线玩家搜索\n"
        "§l§b[ §e5§b ] §r§e快照新建、分页查找、预览、还原、删除与操作记录\n"
        "§l§b[ §e6§b ] §r§e为其他 ToolDelta 插件提供稳定权限管理 API\n"
        "§l§b[ §e7§b ] §r§e读取在线玩家八项能力并实时维护托管权限\n"
        "§l§b[ §e8§b ] §r§e进服检查、周期复核、未知管理员策略与修正记录\n"
        "§d✦§f━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━§d✦"
    )

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self._lock = threading.RLock()
        self._mutation_lock = threading.Lock()
        self.make_data_path()
        self.store = StateStore(self.format_data_path("状态.json"), self.format_data_path("审计日志.jsonl"))
        self.state_path = str(self.store.state_path)
        self.audit_path = str(self.store.audit_path)
        self.cfg = ConfigManager(cfg, self.name, self.version).load()
        self.state = self.store.load()
        self._menu = "closed"
        self._pending: dict[str, Any] | None = None
        self._identity_records: dict[str, str] = {}
        self.xuid_api = None
        self.realtime = RealtimeManager(self)
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenFrameExit(self.on_exit)

    def _save_state(self) -> None:
        self.store.save(self.state)

    def _audit(self, event: str, **details: Any) -> None:
        self.store.audit(event, **details)

    def _save_config(self) -> None:
        if cfg is not None and hasattr(cfg, "upgrade_plugin_config"):
            cfg.upgrade_plugin_config(self.name, self.cfg, self.version)

    # ------------------------------------------------------------------
    # 协作组件的公开接口。
    # RealtimeManager 等内部组件不应直接访问下划线前缀的成员，
    # 统一从这里进入，保持封装边界清晰。
    # ------------------------------------------------------------------
    def save_state(self) -> None:
        """持久化当前状态。"""
        self._save_state()

    def audit_event(self, event: str, **details: Any) -> None:
        """写入一条审计日志。"""
        self._audit(event, **details)

    def log_orion(self, tag: str, message: str) -> None:
        """按 Orion 风格输出一条控制台消息。"""
        self._orion(tag, message)

    def save_config(self) -> None:
        """把当前配置写回 ToolDelta 配置系统。"""
        self._save_config()

    def run_admin_list(self, show: bool = False) -> list[str]:
        """读取服务器管理员列表。"""
        return self._run_list(show=show)

    @property
    def state_lock(self) -> Any:
        """状态读写锁，供协作组件在同一把锁下操作。"""
        return self._lock

    def on_preload(self) -> None:
        try:
            self.xuid_api = self.GetPluginAPI("XUID获取", (0, 0, 7))
        except Exception as exc:
            self._orion("ALERT", f"XUID获取 API 不可用：{exc}")
        self._refresh_identity_index()
        self.frame.add_console_cmd_trigger(
            [CONSOLE_ROOT_TRIGGER], None, "打开 Libra 玩家权限管理菜单", self.on_console
        )

    def on_active(self) -> None:
        realtime_cfg = self.cfg.get("实时管理", {})
        realtime_enabled = isinstance(realtime_cfg, dict) and bool(realtime_cfg.get("是否启用", False))
        immediate_check = bool(realtime_cfg.get("启动后立即检查", True)) if isinstance(realtime_cfg, dict) else True
        if not realtime_enabled or immediate_check:
            threading.Thread(
                target=self._run_list,
                kwargs={"show": False},
                name="libra-startup-refresh",
                daemon=True,
            ).start()
        self.realtime.start()

    def on_player_join(self, player: Any) -> None:
        self.realtime.on_player_join(player)

    def on_player_leave(self, player: Any) -> None:
        self.realtime.on_player_leave(player)

    def on_exit(self, *_args: Any) -> None:
        self.realtime.stop()
        with self._lock:
            self._save_state()

    # Stable aliases for other ToolDelta plugins.
    parse_flags = staticmethod(parse_flags)
    format_flags = staticmethod(format_flags)
    describe_flags = staticmethod(permission_descriptions)
    classify_permission = staticmethod(permission_category)
    list_admins = PermissionService.list_permissions
    list_admin_details = PermissionService.list_admin_details
    set_permission_flags = PermissionService.set_permission
    revoke_admin = PermissionService.revoke_permission
    audit = PermissionService.audit_admins
    get_status = PermissionService.get_health
    save_snapshot = PermissionService.create_snapshot
    list_snapshots_api = PermissionService.list_snapshots
    preview_snapshot_api = PermissionService.preview_snapshot
    restore_snapshot_api = PermissionService.restore_snapshot
    delete_snapshot_api = PermissionService.delete_snapshot
    set_managed_rule = RealtimeManager.set_managed_rule
    get_managed_rule = RealtimeManager.get_managed_rule
    set_managed_enabled = RealtimeManager.set_managed_enabled
    pause_managed_rule = RealtimeManager.pause_managed_rule
    remove_managed_rule = RealtimeManager.remove_managed_rule
    list_online_permissions = RealtimeManager.list_online_permissions
    get_realtime_status = RealtimeManager.status
    set_realtime_enabled = RealtimeManager.set_enabled
    subscribe_permission_events = RealtimeManager.subscribe
    subscribe_unknown_admin_events = RealtimeManager.subscribe_unknown_admin
    unsubscribe_permission_events = RealtimeManager.unsubscribe

    def get_permission_fix_history(self, limit: int = 100) -> list[Any]:
        """返回最近的权限修正记录（对外稳定 API）。"""
        records = self.state.get("实时管理", {}).get("最近权限修正", [])
        if not isinstance(records, list):
            return []
        return list(records)[-max(0, int(limit)):]

    def get_player_permissions(self, xuid: str) -> dict[str, Any] | None:
        try:
            normalized = str(xuid).strip().lower()
        except Exception:
            return None
        return self.state.get("实时管理", {}).get("权限观测", {}).get(normalized)

    def request_permission_check(self, xuid: str | None = None) -> Any:
        if xuid is None:
            return self.realtime.inspect_players()
        normalized = str(xuid).strip().lower()
        players = getattr(getattr(self, "game_ctrl", None), "players", None)
        player = None
        if players is not None and hasattr(players, "getPlayerByXUID"):
            player = players.getPlayerByXUID(normalized)
        if player is None and players is not None and self.xuid_api is not None:
            try:
                name = self.xuid_api.get_name_by_xuid(normalized, allow_offline=True)
                player = players.getPlayerByName(name) if name and hasattr(players, "getPlayerByName") else None
            except Exception:
                player = None
        if player is None:
            return {"状态": "玩家不在线", "XUID": normalized}
        return self.realtime.inspect_player(player, trigger="API调用")


entry = plugin_entry(ServerPermissionManager, "『Libra-天秤座』玩家权限管理系统", (0, 2, 0))

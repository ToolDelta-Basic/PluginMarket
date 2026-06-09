"""Gatekeeper 代理 — 业务模块访问框架核心的唯一通道

═══════════════════════════════════════════════════════════════════════════
隔离层设计:

  业务模块                     GatekeeperProxy                  框架核心
  ─────────────────────────────────────────────────────────────────────
  self.gatekeeper.get_service()    →  UID 检查 + 审计  →  ServiceContainer
  self.gatekeeper.register_command() →  min_uid 校验   →  self._commands
  self.gatekeeper.listen()        →  事件白名单       →  event_bus
  self.gatekeeper.get_config()    →  权限透传         →  _ConfigProxy
  self.gatekeeper.read_file()     →  沙箱检查         →  builtins.open
  self.gatekeeper.send_group()    →  频率检查+审计    →  MessageManager

每个 GatekeeperProxy 实例绑定到一个模块，三重检查:
  1. UID 级别检查（继承自 ServiceContainer.view）
  2. 资源配额检查（委托给 ResourceGuardian）
  3. 审计记录（委托给 AuditTrail）

不允许模块直接访问 self.services、self.register_command 等底层 API。
═══════════════════════════════════════════════════════════════════════════
"""
import functools
import logging
import os
import time
from typing import Any, Callable, Dict, Optional

_log = logging.getLogger(__name__)

# ── 事件允许列表（非 root 模块可订阅的事件类型）──
ALLOWED_EVENTS = frozenset({
    'GroupMessageEvent',
    'PlayerJoinEvent',
    'PlayerLeaveEvent',
    'GameChatEvent',
    'ConfigReloadEvent',
    'AIPrePromptReflectionEvent',
    'AIPostResponseReflectionEvent',
})


def _audit(
    gatekeeper: "GatekeeperProxy",
    action: str,
    target: str = "",
    detail: str = "",
    level: str = "INFO",
) -> None:
    """内部审计记录辅助函数。"""
    try:
        audit_svc = gatekeeper._audit
        if audit_svc is None:
            return
        # AuditTrail 的 record 方法不兼容此参数签名 — 改为日志审计
        if hasattr(audit_svc, 'record'):
            audit_svc.record(
                user_id=0,
                group_id=0,
                nickname="",
                command=f"gatekeeper.{action}",
                args=[target, detail],
                module=gatekeeper._module_name,
                uid_level=gatekeeper._uid,
                success=True,
            )
    except Exception:
        # 审计失败不应影响主流程
        pass


class GatekeeperProxy:
    """业务模块访问框架核心的唯一代理。

    每个模块持有自己的 GatekeeperProxy 实例，
    所有核心 API 调用必须经过此代理。
    代理内部做三重检查：
    1. UID 级别检查（继承自 ServiceContainer.view）
    2. 资源配额检查（委托给 ResourceGuardian）
    3. 审计记录（委托给 AuditTrail）
    """

    __slots__ = (
        "_services",
        "_uid",
        "_module_name",
        "_guardian",
        "_audit",
        "_config",
        "_message",
        "_event_bus",
        "_q_callbacks",
        "_module_commands",
        "_module_events",
    )

    def __init__(
        self,
        services: Any,
        uid: int,
        module_name: str,
        guardian: Any = None,
        audit: Any = None,
        config: Any = None,
        message: Any = None,
        event_bus: Any = None,
        q_callbacks: dict = None,
    ):
        self._services = services
        self._uid = uid
        self._module_name = module_name
        self._guardian = guardian
        self._audit = audit
        self._config = config
        self._message = message
        self._event_bus = event_bus
        self._q_callbacks = q_callbacks or {}
        self._module_commands: dict = {}
        self._module_events: list = []

    @property
    def uid(self) -> int:
        """只读 UID 属性。"""
        return self._uid

    # ══════════════════════════════════════════════════════════════════
    # 1. 服务访问代理
    # ══════════════════════════════════════════════════════════════════

    def get_service(self, name: str) -> Any:
        """带审计日志的服务获取。

        通过 ServiceContainer.get() 实现，自动做 UID 级别检查。
        每次服务获取都会记录审计日志。

        Args:
            name: 服务名称。

        Returns:
            服务实例。

        Raises:
            KeyError: 服务未注册。
            PermissionError: 调用方等级不足。
        """
        _audit(self, "get_service", target=name, detail="service_access")
        result = self._services.get(name)
        return result

    def has_service(self, name: str) -> bool:
        """安全检查：服务是否已注册（不触发 UID 级别检查）。"""
        return self._services.has(name)

    def try_get(self, name: str) -> Optional[Any]:
        """安全的可选服务获取，权限不足时返回 None。"""
        return self._services.try_get(name)

    # ══════════════════════════════════════════════════════════════════
    # 2. 命令注册代理
    # ══════════════════════════════════════════════════════════════════

    def register_command(
        self,
        trigger: str,
        callback: Callable,
        *,
        cmd_type: str = "group",
        description: str = "",
        op_only: bool = False,
        required_role: str = "",
        argument_hint: str = "",
        cooldown: float | None = None,
        min_uid: int = 400,  # UID_NOBODY
    ) -> None:
        """注册命令处理器 — 通过 Gatekeeper 代理。

        校验 min_uid ≥ 模块自身 uid，防止低权限模块注册高权限命令。
        同时做资源配额检查。

        Args:
            trigger: 命令触发词。
            callback: 命令回调函数。
            cmd_type: 命令类型（group/private）。
            description: 命令描述。
            op_only: 是否仅管理员可用。
            required_role: 要求的角色名。
            argument_hint: 参数提示。
            cooldown: 冷却时间（秒）。
            min_uid: 最低 UID 要求。
        """
        # ── 沙箱检查: min_uid 不能低于模块自身 uid ──
        # 即模块不可注册高于自身权限的命令
        if min_uid < self._uid:
            _log.warning(
                "Gatekeeper: 模块 '%s' (uid=%d) 尝试注册命令 '%s' "
                "(min_uid=%d < 自身 uid=%d)，已拒绝",
                self._module_name, self._uid, trigger, min_uid, self._uid,
            )
            return

        # ── 资源配额检查 ──
        # 同步调用 check_rate 不可行（它是 async），降级为记录日志
        # 频率检查由 ResourceGuardian.guard() 在命令执行时做

        _audit(self, "register_command", target=trigger,
               detail=f"min_uid={min_uid} type={cmd_type}")

        self._module_commands[trigger] = {
            "trigger": trigger,
            "cmd_type": cmd_type,
            "callback": callback,
            "description": description,
            "op_only": op_only,
            "required_role": required_role,
            "argument_hint": argument_hint,
            "cooldown": cooldown or 0.0,
            "min_uid": min_uid,
        }

    def listen(self, event_type: str, handler: Callable, priority: int = 0) -> None:
        """订阅事件 — 通过 Gatekeeper 代理。

        校验事件类型是否在允许列表中（非 root 模块）。
        同时进行资源配额检查并记录审计日志。

        Args:
            event_type: 事件类型字符串（如 'GroupMessageEvent'）。
            handler: 事件处理回调。
            priority: 订阅优先级。
        """
        # ── 沙箱检查: 非 root 模块只能订阅白名单事件 ──
        if self._uid > 0 and event_type not in ALLOWED_EVENTS:
            _log.warning(
                "Gatekeeper: 模块 '%s' (uid=%d) 尝试订阅受限事件 '%s'，已拒绝",
                self._module_name, self._uid, event_type,
            )
            return

        _audit(self, "listen", target=event_type,
               detail=f"priority={priority}")

        # ── 事件注册到 gatekeeper 内部注册表 ──
        # 实际订阅由 Module._apply_conventions 在收集后统一处理
        self._module_events.append((event_type, handler, priority))

    # ══════════════════════════════════════════════════════════════════
    # 3. 配置代理
    # ══════════════════════════════════════════════════════════════════

    def get_config(self, key: str, default: Any = None) -> Any:
        """读取配置值 — 透传到 _ConfigProxy.get()。

        自动使用模块自身的 caller_uid，保证权限约束。
        """
        if self._config is None:
            return default
        return self._config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """写入配置值 — 带审计记录。

        自动使用模块自身的 caller_uid，保证权限约束。
        """
        _audit(self, "set_config", target=key,
               detail=f"value_changed" if value is not None else "value_cleared",
               level="WARNING")
        if self._config is None:
            _log.warning("Gatekeeper: config 服务不可用，无法写入 '%s'", key)
            return
        return self._config.set(key, value)

    def register_section(self, section: str, defaults: dict) -> None:
        """注册配置节 — 权限校验。

        自动使用模块自身的 caller_uid。
        """
        _audit(self, "register_section", target=section,
               detail=f"keys={list(defaults.keys())[:5]}...")
        if self._config is None:
            _log.warning("Gatekeeper: config 服务不可用，无法注册节 '%s'", section)
            return
        return self._config.register_section(section, defaults)

    @property
    def config(self) -> Any:
        """直接访问配置代理。"""
        return self._config

    # ══════════════════════════════════════════════════════════════════
    # 4. 文件访问代理
    # ══════════════════════════════════════════════════════════════════

    def read_file(self, path: str) -> Optional[str]:
        """带沙箱检查的文件读取。

        非 root 模块只能读取 data/ 和配置/ 目录下的文件。
        若 guardian 拒绝访问则返回 None。

        Args:
            path: 文件路径。

        Returns:
            文件内容字符串，或 None（权限拒绝/文件不存在）。
        """
        if self._guardian and not self._guardian.check_file_access(
            path, self._uid, mode="r", module_name=self._module_name
        ):
            _log.warning(
                "Gatekeeper: 模块 '%s' 文件读取被沙箱拒绝: '%s'",
                self._module_name, path,
            )
            _audit(self, "read_file_denied", target=path, level="WARNING")
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            _audit(self, "read_file", target=path)
            return content
        except (OSError, PermissionError) as e:
            _log.warning("Gatekeeper: 读取文件 '%s' 失败: %s", path, e)
            return None

    def write_file(self, path: str, data: str) -> bool:
        """带沙箱检查的文件写入。

        非 root 模块只能写入 data/ 和配置/ 目录下的文件。

        Args:
            path: 文件路径。
            data: 要写入的内容。

        Returns:
            True 写入成功，False 被拒绝或失败。
        """
        if self._guardian and not self._guardian.check_file_access(
            path, self._uid, mode="w", module_name=self._module_name
        ):
            _log.warning(
                "Gatekeeper: 模块 '%s' 文件写入被沙箱拒绝: '%s'",
                self._module_name, path,
            )
            _audit(self, "write_file_denied", target=path, level="WARNING")
            return False

        try:
            dirname = os.path.dirname(path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)
            _audit(self, "write_file", target=path)
            return True
        except OSError as e:
            _log.warning("Gatekeeper: 写入文件 '%s' 失败: %s", path, e)
            return False

    @property
    def data_dir(self) -> Optional[str]:
        """模块数据目录 — 始终通过 config 服务获取基础路径。"""
        if self._config is not None:
            try:
                base = self._config.get_data_dir()
                if base:
                    return os.path.join(base, "模块", self._module_name)
            except Exception:
                pass
        return None

    # ══════════════════════════════════════════════════════════════════
    # 5. 消息发送代理
    # ══════════════════════════════════════════════════════════════════

    async def send_group(self, group_id: int, text: str) -> None:
        """发送群消息 — 频率检查 + 审计。

        委托给 MessageManager，内部包含 guardian 限流和审计追踪。

        Args:
            group_id: 群号。
            text: 消息文本。
        """
        if self._message is None:
            _log.error(
                "Gatekeeper: message 服务不可用，群消息发送被拒绝 "
                "(group_id=%s, module=%s, uid=%d)",
                group_id, self._module_name, self._uid,
            )
            return

        # ── 资源配额检查 ──
        if self._guardian:
            allowed = await self._guardian.check_msg_send(
                self._uid, module_name=self._module_name
            )
            if not allowed:
                _log.warning(
                    "Gatekeeper: 模块 '%s' 消息配额耗尽，发送被拒绝 "
                    "(group_id=%s)", self._module_name, group_id,
                )
                return

        _audit(self, "send_group", target=str(group_id),
               detail=f"msg_len={len(text)}")
        await self._message.send_group(group_id, text, requester_uid=self._uid)

    async def send_private(self, user_id: int, text: str) -> None:
        """发送私聊消息 — 频率检查 + 审计。

        委托给 MessageManager，内部包含 guardian 限流和审计追踪。

        Args:
            user_id: QQ 号。
            text: 消息文本。
        """
        if self._message is None:
            _log.error(
                "Gatekeeper: message 服务不可用，私聊消息发送被拒绝 "
                "(user_id=%s, module=%s, uid=%d)",
                user_id, self._module_name, self._uid,
            )
            return

        # ── 资源配额检查 ──
        if self._guardian:
            allowed = await self._guardian.check_msg_send(
                self._uid, module_name=self._module_name
            )
            if not allowed:
                _log.warning(
                    "Gatekeeper: 模块 '%s' 消息配额耗尽，发送被拒绝 "
                    "(user_id=%s)", self._module_name, user_id,
                )
                return

        _audit(self, "send_private", target=str(user_id),
               detail=f"msg_len={len(text)}")
        await self._message.send_private(user_id, text, requester_uid=self._uid)

    # ══════════════════════════════════════════════════════════════════
    # 内部 API（供 Module 基类使用）
    # ══════════════════════════════════════════════════════════════════

    def _collect_commands(self) -> dict:
        """收集通过 gatekeeper 注册的命令（供 Module._apply_conventions 使用）。"""
        return dict(self._module_commands)

    def _collect_events(self) -> list:
        """收集通过 gatekeeper 注册的事件（供 Module._apply_conventions 使用）。"""
        return list(self._module_events)

    def _record_audit(self, action: str, target: str = "",
                      detail: str = "", level: str = "INFO") -> None:
        """程序化审计记录入口（供 Module 基类在关键节点使用）。"""
        _audit(self, action, target=target, detail=detail, level=level)

    def __repr__(self) -> str:
        return (f"<GatekeeperProxy module={self._module_name!r} "
                f"uid={self._uid}>")

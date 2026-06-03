"""能力安全桥梁 (Capability Security Bridge)

═══════════════════════════════════════════════════════════════════════════
核心职责:
  1. 安全隔离: 模块永远拿不到内核对象引用，只能通过 bridge 调用
  2. API 稳定: 内核方法名可自由重构，bridge 映射保持对外不变
  3. UID 门控: 不同 UID 的模块看到不同的白名单方法集

设计:
  - bridge 自身 uid=0（root 权限访问内核服务），但不注册到 ServiceContainer
  - 模块通过 Module._bridge 私有属性获取（opt-in，与现有 self.services 共存）
  - 所有调用: bridge.call("服务.方法", arg1, arg2, ...)
  - 白名单决定: 某种 UID 级别能看到哪些方法

═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

_log = logging.getLogger(__name__)


# ── UID 等级常量（引用 services 模块，避免循环导入运行时获取）────────────────
_TIER_KERNEL = 0
_TIER_DAEMON = 100
_TIER_APP = 300


def _uid_tier(uid: int) -> str:
    """将 uid/tier 映射到权限层名称。"""
    if uid <= 0:
        return "root"
    if uid <= 100:
        return "daemon"
    if uid <= 200:
        return "service"
    if uid <= 300:
        return "app"
    return "nobody"


# ═══════════════════════════════════════════════════════════════
# 方法定义 (MethodSpec) — 描述一个 bridge 方法的元数据
# ═══════════════════════════════════════════════════════════════

class MethodSpec:
    """描述一个可通过 bridge 调用的方法。"""

    __slots__ = (
        "name", "method", "min_tier",
        "readonly", "description",
    )

    def __init__(
        self,
        name: str,
        method: Callable,
        min_tier: str = "app",
        readonly: bool = False,
        description: str = "",
    ):
        self.name = name          # bridge 路径: "config.read"
        self.method = method       # 实际的 Python callable
        self.min_tier = min_tier   # 最低允许层级: root/daemon/app/nobody
        self.readonly = readonly
        self.description = description


# ═══════════════════════════════════════════════════════════════
# GatekeeperBridge
# ═══════════════════════════════════════════════════════════════

_TIER_RANK = {"root": 0, "daemon": 1, "service": 2, "app": 3, "nobody": 4}


class GatekeeperBridge:
    """能力安全桥梁 — 模块与内核之间的唯一受控通道。

    FrameworkHost 在 start() 中创建 bridge 并初始化方法注册表。
    bridge 不注册到 ServiceContainer — 模块通过 Module._bridge 私有属性使用。
    """

    def __init__(self, services: Any):
        """
        Args:
            services: root 级 ServiceContainer（FrameworkHost 持有）。
        """
        self._services = services  # root 级，用于 bridge 内部调用内核方法
        self._methods: Dict[str, MethodSpec] = {}
        self._lock = __import__('threading').Lock()

    # ── 注册 ──

    def register(
        self,
        name: str,
        method: Callable,
        min_tier: str = "app",
        readonly: bool = False,
        description: str = "",
    ) -> None:
        """注册一个 bridge 方法。

        Args:
            name: bridge 路径，如 "config.read"
            method: Python callable（可以是 lambda/闭包包装内核方法）
            min_tier: 最低允许调用层级
            readonly: 标记为只读
            description: 人类可读描述
        """
        with self._lock:
            self._methods[name] = MethodSpec(
                name=name, method=method,
                min_tier=min_tier, readonly=readonly,
                description=description,
            )

    # ── 调用 ──

    def call(self, path: str, caller_uid: int, *args, **kwargs) -> Any:
        """通过 bridge 调用方法，受 UID 门控。

        Args:
            path: bridge 方法路径，如 "config.read"
            caller_uid: 调用方模块的 uid
            *args, **kwargs: 传递给底层方法的参数

        Returns:
            底层方法的返回值。

        Raises:
            KeyError: 方法未注册。
            PermissionError: 调用方层级不足。
        """
        spec = self._methods.get(path)
        if spec is None:
            raise KeyError(
                f"bridge 方法 '{path}' 未注册。"
                f"可用方法: {self.list_methods(caller_uid)}"
            )

        caller_tier = _uid_tier(caller_uid)
        min_rank = _TIER_RANK.get(spec.min_tier, 99)
        caller_rank = _TIER_RANK.get(caller_tier, 99)
        if caller_rank > min_rank:
            raise PermissionError(
                f"{caller_tier}(uid={caller_uid}) 无权调用 "
                f"'{path}' (至少需要 {spec.min_tier})"
            )

        try:
            return spec.method(*args, **kwargs)
        except Exception as e:
            _log.debug("bridge 调用 '%s' 失败: %s", path, e)
            raise

    def call_async(self, path: str, caller_uid: int, *args, **kwargs) -> Any:
        """bridge 调用，返回协程（用于异步方法）。"""
        import asyncio
        result = self.call(path, caller_uid, *args, **kwargs)
        if asyncio.iscoroutine(result):
            return result
        # 同步方法包装为协程
        async def _wrapped():
            return result
        return _wrapped()

    # ── 内省 ──

    def list_methods(self, caller_uid: int) -> List[Dict[str, Any]]:
        """列出调用方可用的所有 bridge 方法。"""
        caller_tier = _uid_tier(caller_uid)
        caller_rank = _TIER_RANK.get(caller_tier, 99)
        result = []
        for spec in self._methods.values():
            spec_rank = _TIER_RANK.get(spec.min_tier, 99)
            accessible = caller_rank <= spec_rank
            result.append({
                "name": spec.name,
                "min_tier": spec.min_tier,
                "accessible": accessible,
                "readonly": spec.readonly,
                "description": spec.description,
            })
        result.sort(key=lambda x: x["name"])
        return result

    def list_accessible(self, caller_uid: int) -> List[str]:
        """列出调用方可访问的 bridge 方法名。"""
        return [
            m["name"] for m in self.list_methods(caller_uid)
            if m["accessible"]
        ]

    # ── 内核方法引用（内部使用）──

    def _get_service(self, name: str) -> Any:
        """bridge 内部获取内核服务（root 级权限）。"""
        return self._services.get(name)


# ═══════════════════════════════════════════════════════════════
# 预定义的默认方法注册（由 FrameworkHost 调用）
# ═══════════════════════════════════════════════════════════════

def register_default_capabilities(bridge: GatekeeperBridge) -> None:
    """注册默认的 bridge 方法集合。

    覆盖 config / adapter / message / tool 四个核心服务。
    映射规则:
      - config.write / config.reload → daemon 级以上
      - config.read → app 级以上
      - adapter.send → app 级以上
      - adapter.game_command → daemon 级以上
      - message.send → app 级以上
      - tool.* → app 级以上
    """

    # ── config ────────────────────────────────────────────────
    try:
        cfg = bridge._get_service("config")
    except Exception:
        cfg = None

    if cfg is not None:
        bridge.register(
            "config.read",
            lambda key, default=None: cfg.get(key, default),
            min_tier="app", readonly=True,
            description="读取配置项，传入点号分隔键和默认值",
        )
        bridge.register(
            "config.write",
            lambda key, value: (cfg.set(key, value), cfg.save()),
            min_tier="daemon", readonly=False,
            description="写入配置项并持久化（需要 daemon 权限）",
        )
        bridge.register(
            "config.reload",
            lambda: cfg.reload(),
            min_tier="daemon", readonly=False,
            description="从磁盘重新加载配置",
        )

    # ── adapter ───────────────────────────────────────────────
    try:
        adapter = bridge._get_service("adapter")
    except Exception:
        adapter = None

    if adapter is not None:
        bridge.register(
            "game.send_message",
            lambda target, msg: adapter.send_game_message(target, msg),
            min_tier="app", readonly=False,
            description="向游戏内玩家发送消息",
        )
        bridge.register(
            "game.run_command",
            lambda cmd: adapter.send_game_command(cmd),
            min_tier="daemon", readonly=False,
            description="执行游戏原生指令（需要 daemon 权限）",
        )

    # ── message ───────────────────────────────────────────────
    try:
        msg_svc = bridge._get_service("message")
    except Exception:
        msg_svc = None

    if msg_svc is not None:
        bridge.register(
            "qq.send_group",
            lambda gid, text: msg_svc.send_group_msg(gid, text),
            min_tier="app", readonly=False,
            description="向 QQ 群发送消息",
        )
        bridge.register(
            "qq.send_private",
            lambda uid, text: msg_svc.send_private_msg(uid, text),
            min_tier="app", readonly=False,
            description="向 QQ 用户发送私聊消息",
        )

    # ── tool ──────────────────────────────────────────────────
    try:
        tool = bridge._get_service("tool")
    except Exception:
        tool = None

    if tool is not None:
        bridge.register(
            "tool.execute",
            lambda name, args: tool.execute(name, args),
            min_tier="app", readonly=False,
            description="执行已注册的工具",
        )

    _log.info(
        "bridge 已注册 %d 个方法 (%d config + %d adapter + %d message + %d tool)",
        len(bridge._methods),
        sum(1 for m in bridge._methods if m.startswith("config.")),
        sum(1 for m in bridge._methods if m.startswith("game.")),
        sum(1 for m in bridge._methods if m.startswith("qq.")),
        sum(1 for m in bridge._methods if m.startswith("tool.")),
    )

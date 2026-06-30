from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..kernel.audit import audit_log, AuditLevel
from ..kernel.services import (
    TIER_KERNEL as _TIER_KERNEL,
    TIER_DAEMON as _TIER_DAEMON,
    TIER_APP as _TIER_APP,
    tier_label,
    TIER_LABELS,
)

_log = logging.getLogger(__name__)


def _bridge_module_call(host, module_name: str, method_name: str, args: list):
    """Gatekeeper 安全的模块间方法调用。

    仅允许调用标记了 @exec_exposed 的方法，防止任意代码执行。
    """
    try:
        from ..kernel.decorators import is_exec_exposed
    except ImportError:
        is_exec_exposed = lambda m: True
    mod = host.module_mgr._loaded_modules.get(module_name)
    if mod is None:
        raise ValueError(f"模块 '{module_name}' 未加载")
    method = getattr(mod, method_name, None)
    if method is None or not callable(method):
        raise ValueError(f"方法 '{method_name}' 不存在于模块 '{module_name}'")
    if not is_exec_exposed(method):
        raise PermissionError(f"方法 '{method_name}' 未标记 @exec_exposed")
    return method(*args) if args else method()


# ── UID 等级映射（从 services.py 导入统一常量）────────────────
def _uid_tier(uid: int) -> str:
    """将 uid/tier 映射到权限层名称（委托 services.tier_label）。"""
    if uid <= 0:
        return "root"
    # 按 tier 阈值从低到高匹配
    for threshold in sorted(TIER_LABELS.keys()):
        if uid <= threshold:
            return TIER_LABELS[threshold]
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

# 从 TIER_LABELS 派生 rank map，保证与 services.py 同步
_TIER_RANK = {label: rank for rank, label in sorted(TIER_LABELS.items())}
_TIER_RANK["root"] = _TIER_RANK.get("kernel", 0)  # "root" 别名


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
            # 自动注入 caller_uid 供 bridge 方法使用
            # 方法可声明 uid 参数来接收调用方 UID
            # 不影响未声明该参数的方法
            try:
                result = spec.method(*args, **kwargs, uid=caller_uid)
            except TypeError:
                # 方法不接受 uid 关键字，不注入
                result = spec.method(*args, **kwargs)
            # 审计日志：记录关键 bridge 调用
            if spec.min_tier in ("daemon", "root"):
                audit_log(
                    sender=f"uid:{caller_uid}",
                    action=f"bridge.{path}",
                    target=str(caller_tier),
                    detail=f"min_tier={spec.min_tier} readonly={spec.readonly}",
                    level=AuditLevel.INFO,
                )
            return result
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
            "配置.读",
            lambda key, default=None, uid=0: cfg.get(key, default, requester_uid=uid),
            min_tier="app", readonly=True,
            description="按模块 UID 权限读取配置（KEY路径, 默认值）",
        )
        bridge.register(
            "配置.写",
            lambda key, value, uid=0: cfg.set(key, value, requester_uid=uid),
            min_tier="daemon", readonly=False,
            description="按模块 UID 权限写入配置（KEY路径, 值）",
        )
        bridge.register(
            "配置.节权限",
            lambda section: cfg.get_section_permissions(section),
            min_tier="app", readonly=True,
            description="查询某配置节的读/写权限 uid",
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

    # ── AI 引擎桥梁 (v1.5) ──────────────────────────────────
    # 其他模块通过 bridge.call("ai.chat", ...) 调用 AI
    try:
        ai_engine = bridge._get_service("ai_engine")
    except Exception:
        ai_engine = None

    if ai_engine is not None:
        bridge.register(
            "ai.chat",
            lambda messages, tools=None, max_rounds=5,
                   tool_executor=None, caller_uid=400, uid=0:
                ai_engine.chat(
                    messages=messages, tools=tools,
                    max_rounds=max_rounds,
                    tool_executor=tool_executor,
                    caller_uid=caller_uid),
            min_tier="app", readonly=False,
            description="调用 AI 对话接口（支持工具调用循环）",
        )
        bridge.register(
            "ai.chat_with_tools",
            lambda messages, tools, max_rounds=5,
                   tool_executor=None, caller_uid=400, uid=0:
                ai_engine.chat(
                    messages=messages, tools=tools,
                    max_rounds=max_rounds,
                    tool_executor=tool_executor,
                    caller_uid=caller_uid),
            min_tier="app", readonly=False,
            description="调用 AI 对话接口（显式传入工具列表）",
        )
        bridge.register(
            "ai.chat_simple",
            lambda messages, uid=0:
                ai_engine.chat_simple(messages=messages),
            min_tier="app", readonly=False,
            description="调用 AI 简单对话（无工具调用）",
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

    # ── 网络连接管理器桥梁 (v1.5) ──────────────────────────
    try:
        network = bridge._get_service("network")
    except Exception:
        network = None

    if network is not None:
        bridge.register(
            "网络.GET",
            lambda url, headers=None, timeout=None, uid=0:
                network.http_get(url, headers=headers, timeout=timeout),
            min_tier="app", readonly=True,
            description="通过统一网络管理器发起 HTTP GET（含重试/熔断）",
        )
        bridge.register(
            "网络.POST",
            lambda url, data=None, json_body=None, headers=None, timeout=None, uid=0:
                network.http_post(url, data=data, json=json_body, headers=headers, timeout=timeout),
            min_tier="app", readonly=False,
            description="通过统一网络管理器发起 HTTP POST（含重试/熔断）",
        )
        bridge.register(
            "网络.健康检查",
            lambda url, timeout=5, uid=0:
                network.health_check(url, timeout=timeout),
            min_tier="app", readonly=True,
            description="检查远端服务是否可达",
        )

    # ── 管理工具桥梁 (v1.5) ────────────────────────────────
    try:
        admin_tool = bridge._get_service("admin_tool")
    except Exception:
        admin_tool = None

    if admin_tool is not None:
        bridge.register(
            "管理工具.列出工作流",
            lambda uid=0: admin_tool.list_workflows(),
            min_tier="app", readonly=True,
            description="列出所有已注册的管理工具工作流",
        )
        bridge.register(
            "管理工具.获取工作流",
            lambda name, uid=0: admin_tool.get_workflow(name),
            min_tier="app", readonly=True,
            description="获取指定工作流的详细信息",
        )
        bridge.register(
            "管理工具.执行工作流",
            lambda name, ctx_data, bypass_confirm=False, caller_uid=400, uid=0:
                admin_tool.execute_workflow(
                    name, ctx_data,
                    bypass_confirm=bypass_confirm,
                    caller_uid=caller_uid,
                ),
            min_tier="daemon", readonly=False,
            description="执行一个管理工具工作流（组合调用 @exec_exposed 方法）",
        )

    # ── 模块间通信 (v1.4.3) ──────────────────────────────────
    try:
        host = bridge._get_service("_host")
    except Exception:
        host = None

    if host is not None:
        bridge.register(
            "模块.已加载",
            lambda name: host.module_mgr._loaded_modules.get(name) is not None,
            min_tier="app", readonly=True,
            description="检查指定模块是否已加载（模块名 → bool）",
        )
        bridge.register(
            "模块.调用",
            lambda name, method, args=None: _bridge_module_call(host, name, method, args or []),
            min_tier="daemon", readonly=False,
            description="调用已加载模块的公开方法（模块名, 方法名, 参数）",
        )

    _log.info(
        "bridge 已注册 %d 个方法 (%d config + %d game + %d qq + %d tool + %d ai + %d network + %d admin)",
        len(bridge._methods),
        sum(1 for m in bridge._methods if m.startswith("config.")),
        sum(1 for m in bridge._methods if m.startswith("game.")),
        sum(1 for m in bridge._methods if m.startswith("qq.")),
        sum(1 for m in bridge._methods if m.startswith("tool.")),
        sum(1 for m in bridge._methods if m.startswith("ai.")),
        sum(1 for m in bridge._methods if m.startswith("网络.")),
        sum(1 for m in bridge._methods if m.startswith("管理工具.")),
    )

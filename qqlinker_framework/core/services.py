"""服务容器 (ServiceContainer) — 五层等级制权限体系

═══════════════════════════════════════════════════════════════════════════
等级体系（新版 — v2）：

  等级值  名称         说明                       模块示例
  ─────────────────────────────────────────────────────────────────────
  0       kernel       root 完全权限               FrameworkHost
  100     daemon       框架守护/核心引擎             ai_core, orion
  200     service      框架服务引擎                 WS, dedup, market
  300     app          用户业务模块                  forwarder, acg_image
  400     nobody       外部第三方模块                外部 .py 文件

访问规则:
  - 模块可以访问 ≤自身等级的服务（0 最低=权限最高）
  - 同级之间互访
  - 不可访问高于自身等级的服务

注册规则:
  - 服务声明自己的等级 (service_tier)
  - 模块等级由 validate_module_tier() 决定

═══════════════════════════════════════════════════════════════════════════
"""
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set

_log = logging.getLogger(__name__)

# ── 等级常量 ────────────────────────────────────────────────

TIER_KERNEL = 0
TIER_DAEMON = 100
TIER_SERVICE = 200
TIER_APP = 300
TIER_NOBODY = 400

TIER_LABELS: Dict[int, str] = {
    TIER_KERNEL: "kernel",
    TIER_DAEMON: "daemon",
    TIER_SERVICE: "service",
    TIER_APP: "app",
    TIER_NOBODY: "nobody",
}

# 兼容旧代码别名
UID_ROOT = TIER_KERNEL
UID_DAEMON_MIN = TIER_DAEMON
UID_DAEMON_MAX = TIER_DAEMON
UID_SERVICE_MIN = TIER_SERVICE
UID_SERVICE_MAX = TIER_SERVICE
UID_APP_MIN = TIER_APP
UID_APP_MAX = TIER_APP
UID_NOBODY = TIER_NOBODY

# ── 各层允许声明的等级 ─────────────────────────────────────
# 防提权：模块只能声明自己层级的等级值

TIER_ALLOWED: Dict[str, int] = {
    "kernel": TIER_KERNEL,
    "daemon": TIER_DAEMON,
    "service": TIER_SERVICE,
    "app": TIER_APP,
    "nobody": TIER_NOBODY,
}


def tier_label(tier: int) -> str:
    """返回等级的可读标签。"""
    return TIER_LABELS.get(tier, f"unknown({tier})")


# 兼容旧代码
uid_label = tier_label


def uid_layer(uid: int) -> str:
    """返回等级标签。"""
    return tier_label(uid)


def validate_module_tier(
    declared: int, module_name: str = "",
    layer: str = "app"
) -> int:
    """校验模块声明的等级是否合法。

    防提权：外部模块声明的等级被无条件忽略，返回其层级默认值。

    Returns:
        校验后的有效等级。非法声明时自动降级。
    """
    allowed = TIER_ALLOWED.get(layer, TIER_NOBODY)

    # ★ 硬限制：kernel 等级仅 kernel 层可用，其他层（含外部模块）一律降级
    if declared == TIER_KERNEL and layer != "kernel":
        _log.warning(
            "模块 '%s' 声明了 kernel 等级 (0)，这是严重的安全违规。"
            "已强制降级为 %s。",
            module_name, tier_label(allowed),
        )
        return allowed

    if declared == allowed:
        return declared

    # 非法声明 → 降级
    _log.warning(
        "模块 '%s' 声明了非法等级 %d (层级=%s, 允许=%d(%s))，"
        "已自动降级为 %d。",
        module_name, declared, layer,
        allowed, tier_label(allowed), allowed,
    )
    return allowed


# 兼容旧代码
validate_module_uid = validate_module_tier


# ── 白名单：可信的 daemon 级路径 ────────────────────────────

_DAEMON_TRUSTED_PATHS: Set[str] = {
    "qqlinker_framework.core",
    "qqlinker_framework.managers",
    "qqlinker_framework.modules.security.orion",
    "qqlinker_framework.modules.ai",
    "qqlinker_framework.modules.game.admin",
    "qqlinker_framework.modules.game.forwarder",
    "qqlinker_framework.modules.game.tracker",
    "qqlinker_framework.modules.logging",
    "qqlinker_framework.modules.system.auth",
}


def is_daemon_trusted(caller_module: str) -> bool:
    """检查调用方是否来自可信的内核/守护路径。"""
    for p in _DAEMON_TRUSTED_PATHS:
        if caller_module == p or (
            caller_module.startswith(p) and caller_module[len(p)] == '.'
        ):
            return True
    return False


class ServiceContainer:
    """服务的注册与获取容器，五层等级制权限体系。

    等级值越小权限越高。模块可访问 ≤自身等级的服务注册。
    root(0) 始终拥有一切权限。
    """

    def __init__(self, tier: int = TIER_KERNEL):
        self._tier = tier
        self._services: Dict[str, Any] = {}
        self._service_tiers: Dict[str, int] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._lock = threading.Lock()
        self._deps: Dict[str, Set[str]] = {}

    @property
    def tier(self) -> int:
        return self._tier

    @property
    def tier_name(self) -> str:
        return tier_label(self._tier)

    # 兼容旧代码
    @property
    def uid(self) -> int:
        return self._tier

    @uid.setter
    def uid(self, value: int):
        self._tier = value

    @property
    def uid_name(self) -> str:
        return tier_label(self._tier)

    def view(self, tier: int) -> "ServiceContainer":
        """创建一个等级受限的视图，共享底层服务注册表。

        每个模块得到独立的 ServiceContainer 视图 —— 共享 _services /
        _factories / _service_tiers，但 _tier 被限制为模块自身等级。
        防止低权限模块越权获取高级别服务。
        """
        view = ServiceContainer.__new__(ServiceContainer)
        view._tier = tier
        view._services = self._services
        view._factories = self._factories
        view._service_tiers = self._service_tiers
        view._deps = self._deps
        view._lock = self._lock
        return view

    def register(
        self, name: str, instance_or_factory: Any, *,
        uid: int = TIER_SERVICE,
        _caller: str = "",
    ):
        """注册服务实例或工厂函数。

        Args:
            name: 服务名称。
            instance_or_factory: 实例或可调用工厂。
            uid: 该服务的等级（数值越小权限越高）。
            _caller: 内部用，调用方的模块路径（用于防提权校验）。
        """
        if name in self._services or name in self._factories:
            _log.warning("服务 '%s' 已注册，将被覆盖", name)

        # 防提权: daemon 级服务只有可信路径能注册
        if uid <= TIER_DAEMON and not is_daemon_trusted(_caller):
            _log.error(
                "安全拒绝: '%s' 尝试注册 daemon 级服务 '%s' (tier=%d)。",
                _caller or "unknown", name, uid,
            )
            raise PermissionError(
                f"非可信路径 '{_caller}' 不能注册 daemon 级服务 '{name}'"
            )

        with self._lock:
            if callable(instance_or_factory):
                self._factories[name] = instance_or_factory
            else:
                self._services[name] = instance_or_factory
            self._service_tiers[name] = uid

    def get(self, name: str) -> Any:
        """获取服务实例，校验等级访问权限。

        规则：调用方等级 ≤ 服务等级 才允许（数值小=权限高）。

        Raises:
            KeyError: 服务未注册。
            PermissionError: 调用方等级不足。
        """
        req_tier = self._service_tiers.get(name)
        if req_tier is None:
            raise KeyError(f"服务 '{name}' 未注册")

        # kernel(0) 拥有一切权限
        if self._tier != TIER_KERNEL and self._tier > req_tier:
            raise PermissionError(
                f"{self.tier_name}(tier={self._tier}) "
                f"无权访问 '{name}' "
                f"(需要 {tier_label(req_tier)}/tier≤{req_tier})"
            )

        if name in self._services:
            return self._services[name]
        # 工厂延迟创建
        with self._lock:
            if name in self._services:
                return self._services[name]
            instance = self._factories[name]()
            self._services[name] = instance
            return instance

    def try_get(self, name: str) -> Optional[Any]:
        """尝试获取服务，权限不足时返回 None。"""
        try:
            return self.get(name)
        except (KeyError, PermissionError):
            return None

    def has(self, name: str) -> bool:
        """检查服务是否已注册（不校验等级）。"""
        return name in self._services or name in self._factories

    def get_service_uid(self, name: str) -> Optional[int]:
        """查询指定服务的等级。"""
        return self._service_tiers.get(name)

    def list_accessible(self) -> Dict[str, int]:
        """列出当前等级可访问的所有服务及等级。"""
        return {
            name: tier
            for name, tier in self._service_tiers.items()
            if self._tier == TIER_KERNEL or self._tier <= tier
        }

    # ── 依赖拓扑 ──

    def register_dependency(self, name: str, depends_on: str) -> None:
        """声明服务间依赖关系。"""
        with self._lock:
            self._deps.setdefault(name, set()).add(depends_on)

    def resolve_order(self) -> List[str]:
        """返回拓扑排序后的初始化顺序。"""
        all_names = set(self._service_tiers.keys()) | set(self._deps.keys())
        for deps in self._deps.values():
            all_names |= deps
        in_degree = {n: 0 for n in all_names}
        graph = {n: set() for n in all_names}
        for name, deps in self._deps.items():
            for dep in deps:
                if dep in all_names:
                    graph[dep].add(name)
                    in_degree[name] = in_degree.get(name, 0) + 1
        queue = [n for n in all_names if in_degree.get(n, 0) == 0]
        result = []
        while queue:
            n = queue.pop(0)
            result.append(n)
            for succ in graph.get(n, set()):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)
        return result

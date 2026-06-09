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
import inspect
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

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

# 仅保留 UID_NOBODY 别名（广泛使用），其余使用 TIER_*
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
    """返回等级的可读标签（精确匹配 v2 离散 tier 值）。"""
    return TIER_LABELS.get(tier, f"unknown({tier})")


def uid_label(uid: int) -> str:
    """返回等级的可读标签（精确 tier）。"""
    return TIER_LABELS.get(uid, f"unknown({uid})")

def uid_layer(uid: int) -> str:
    """返回等级标签。"""
    return uid_label(uid)


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

    # ★ 硬限制：非 kernel 层模块不可声明 kernel 等级
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




# ── 白名单：可信的 daemon 级路径 ────────────────────────────
# L1 修复: 改为 frozenset 显式匹配，不再使用字符串前缀匹配
# 避免 qqlinker_framework.modules.unknown_fake 伪造成 qqlinker_framework.modules
# 包含框架实际使用的所有 caller 字符串

_DAEMON_TRUSTED_MODULES: frozenset = frozenset({
    "qqlinker_framework.core.host",
    "qqlinker_framework.__init__",
    "qqlinker_framework.modules.security.orion",
})


def is_daemon_trusted(caller_module: str) -> bool:
    """检查调用方是否来自可信的内核/守护路径。

    L1 修复: 使用 frozenset 精确匹配，不再依赖字符串前缀匹配。
    前缀匹配可被 qqlinker_framework.modules.fake 等路径伪造绕过。
    """
    return caller_module in _DAEMON_TRUSTED_MODULES


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
        # ★ C1 修复: 视图锁定标记（root 容器本身不锁定 _tier 修改）
        self._view_locked = False

    @property
    def tier(self) -> int:
        return self._tier

    @property
    def tier_name(self) -> str:
        return tier_label(self._tier)

    @property
    def uid(self) -> int:
        return self._tier

    @uid.setter
    def uid(self, value: int):
        raise PermissionError(
            "ServiceContainer.uid 只读。视图的 tier 在创建时已锁定，"
            "不可提升权限。使用 view(tier) 创建新的低权限视图。"
        )

    @property
    def uid_name(self) -> str:
        return tier_label(self._tier)

    def __setattr__(self, name, value):
        """拦截 _tier 的直接赋值，防止越权提权。

        C1 修复: 恶意模块可执行 self.services._tier = 0 获得 root。
        视图创建后 _view_locked=True，任何 _tier 修改均被拒绝。
        view() 使用 object.__setattr__ 绕过锁定以在构造期设置值。
        """
        if name == '_tier' and getattr(self, '_view_locked', False):
            raise PermissionError(
                "ServiceContainer._tier 只读。视图的 tier 在创建时已锁定，"
                "不可提升权限。"
            )
        super().__setattr__(name, value)

    def view(self, tier: int) -> "ServiceContainer":
        """创建一个等级受限的视图，共享底层服务注册表。

        每个模块得到独立的 ServiceContainer 视图 —— 共享 _services /
        _factories / _service_tiers，但 _tier 被限制为模块自身等级。
        防止低权限模块越权获取高级别服务。
        """
        view = ServiceContainer.__new__(ServiceContainer)
        object.__setattr__(view, '_tier', tier)
        view._services = self._services
        view._factories = self._factories
        view._service_tiers = self._service_tiers
        view._deps = self._deps
        view._lock = self._lock
        # ★ C1 修复: 锁定视图，_tier 此后不可修改
        object.__setattr__(view, '_view_locked', True)
        return view

    def register(
        self, name: str, instance_or_factory: Any, *,
        uid: int = TIER_SERVICE,
        is_factory: Optional[bool] = None,
        _caller: str = "",
    ):
        """注册服务实例或工厂函数。

        Args:
            name: 服务名称。
            instance_or_factory: 实例或可调用工厂。
            uid: 该服务的等级（数值越小权限越高）。
            is_factory: None=自动检测, True=强制工厂, False=强制服务实例。
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
            if is_factory is True:
                self._factories[name] = instance_or_factory
            elif is_factory is False:
                self._services[name] = instance_or_factory
            elif callable(instance_or_factory) and not inspect.isclass(instance_or_factory):
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

    def register_dependency(self, service_name: str, dependent: str) -> None:
        """注册模块对服务的依赖关系（测试用 API）。

        在 v2 tier 体系中，依赖关系由服务注册时的 uid 值隐式表达。
        该方法保留作为兼容接口。
        """
        _log.debug("依赖注册（无操作）: '%s' -> '%s'", dependent, service_name)

    def resolve_order(self) -> list:
        """返回模块解析顺序（按 tier 从低到高排序）。

        v2 tier 体系: kernel(0) → daemon(100) → service(200) → app(300)
        无需复杂的图拓扑排序。
        """
        # 从服务注册表中提取模块名并排 tier
        modules = []
        for name in list(self._service_tiers.keys()):
            if not name.startswith('_') and name not in ('config', 'event_bus',
                    'command', 'tool', 'adapter', 'message', 'package',
                    'recovery', 'uid_lookup', 'group_config', 'group_filter',
                    'dedup', 'debug', 'market_server', 'market', 'ws_client'):
                modules.append((self._service_tiers.get(name, 400), name))
        modules.sort()
        return [name for _, name in modules]

    def list_accessible(self) -> Dict[str, int]:
        """列出当前等级可访问的所有服务及等级。"""
        return {
            name: tier
            for name, tier in self._service_tiers.items()
            if self._tier == TIER_KERNEL or self._tier <= tier
        }

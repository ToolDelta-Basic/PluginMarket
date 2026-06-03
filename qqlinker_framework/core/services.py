"""服务容器 (ServiceContainer) — Linux 风格 UID 权限体系

═══════════════════════════════════════════════════════════════════════════
UID 分级（参考 Linux 用户模型）：

  UID 范围       标签        权限                                    类比
  ─────────────────────────────────────────────────────────────────────
  uid=0          root        全部接口可用，框架开发者/终端持有者      root
  uid=1..999     daemon      系统守护进程，框架内部核心引擎           系统守护
  uid=1000..1999 service     框架服务引擎（WS/去重/调试/市场）        systemd 服务
  uid=2000..2999 app         业务模块、系统内置模块                   普通用户
  uid=3000..∞    nobody      第三方外部模块、未知来源插件             nobody

接口暴露规则:
  - 低级别模块不能获取高级别注册的服务
  - uid=0 (root) 始终拥有全部权限
  - 模块声明的 uid 必须在源包允许范围内（防提权伪造）

提权机制:
  - 终端持有者 ≡ root (uid=0)，通过控制台/CLI 交互
  - 用户模块需要高级别服务时，通过 .sudo 命令请求管理员授权
  - 管理员可以在终端用 grant 命令授予临时或永久权限

使用方式:
  svc = ServiceContainer(uid=2000)  # 运行在 app 等级
  svc.register("config", cfg_mgr, uid=1000)   # service 级服务
  svc.get("config")  # uid≥1000 才能获取，uid=2000 会被拒
═══════════════════════════════════════════════════════════════════════════
"""
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set

_log = logging.getLogger(__name__)

# ── UID 等级常量（Linux 风格）─────────────────────────────

UID_ROOT = 0            # root：全部权限
UID_DAEMON_MIN = 1      # 守护进程起始
UID_DAEMON_MAX = 999
UID_SERVICE_MIN = 1000   # 服务引擎起始
UID_SERVICE_MAX = 1999
UID_APP_MIN = 2000       # 业务模块起始
UID_APP_MAX = 2999
UID_NOBODY = 3000        # 第三方/未知模块起始

# ── 各层允许声明的 UID 范围 ─────────────────────────────────
# 用于防提权：模块只能在自己的层级范围内声明 uid
# 内核 core/ 不可声明 uid，由 FrameworkHost 硬编码分配
# daemon 由 FrameworkHost 在 register 时自动分配
# service 层 : 1000~1999
# app 层 : 2000~2999（用户模块默认 2000）
# nobody : 3000+

LAYER_ALLOWED_UID_RANGE: Dict[str, range] = {
    "kernel": range(UID_ROOT, UID_ROOT + 1),  # uid=0 仅内核可用
    "daemon": range(UID_DAEMON_MIN, UID_DAEMON_MAX + 1),
    "service": range(UID_SERVICE_MIN, UID_SERVICE_MAX + 1),
    "app": range(UID_APP_MIN, UID_APP_MAX + 1),
    "nobody": range(UID_NOBODY, UID_NOBODY + 10000),
}


def uid_label(uid: int) -> str:
    """返回 UID 的可读标签（Linux 风格）。"""
    if uid == UID_ROOT:
        return "root"
    if uid < UID_SERVICE_MIN:
        return "daemon"
    if uid < UID_APP_MIN:
        return "service"
    if uid < UID_NOBODY:
        return "app"
    return "nobody"


def uid_layer(uid: int) -> str:
    """返回 UID 所属层级名（复用 uid_label）。"""
    return uid_label(uid)


def _same_layer(uid_a: int, uid_b: int) -> bool:
    """检查两个 UID 是否属于同一权限层级。

    同一层级内的模块可以互访彼此注册的服务
    （例如 daemon 层 uid=100 访问 daemon 服务 uid=2）。
    """
    if uid_a == UID_ROOT or uid_b == UID_ROOT:
        return uid_a == uid_b  # root 是独一层
    # daemon: 1..999
    if UID_DAEMON_MIN <= uid_a <= UID_DAEMON_MAX:
        return UID_DAEMON_MIN <= uid_b <= UID_DAEMON_MAX
    # service: 1000..1999
    if UID_SERVICE_MIN <= uid_a <= UID_SERVICE_MAX:
        return UID_SERVICE_MIN <= uid_b <= UID_SERVICE_MAX
    # app: 2000..2999
    if UID_APP_MIN <= uid_a <= UID_APP_MAX:
        return UID_APP_MIN <= uid_b <= UID_APP_MAX
    # nobody: 3000+
    return uid_b >= UID_NOBODY


def validate_module_uid(
    declared_uid: int, module_name: str = "",
    layer: str = "app"
) -> int:
    """校验模块声明的 uid 是否合法，返回有效 uid。

    Args:
        declared_uid: 模块类声明的 uid。
        module_name: 模块名（用于日志）。
        layer: 模块所在层级（daemon/service/app/nobody）。

    Returns:
        校验后的有效 uid。非法声明时自动降级到该层默认值。

    防提权: 模块不能在代码里声明超出自己层级的 uid。
    """
    allowed = LAYER_ALLOWED_UID_RANGE.get(layer)
    if allowed and declared_uid in allowed:
        # ★ 安全：uid=0 仅在 kernel 层且来自可信源路径时放行
        # 可信源：core/ 和 modules/system/ 目录下的框架内置模块
        if declared_uid == UID_ROOT and layer == "kernel":
            # 外部模块在 _load_py_file 已强制降级（autodiscover.py）
            # 此处放行仅是给 kernel_auth 等内置 root 模块
            pass
        return declared_uid

    allowed = LAYER_ALLOWED_UID_RANGE.get(layer)
    if allowed and declared_uid in allowed:
        return declared_uid

    # 非法声明 → 降级
    default = allowed.start if allowed else UID_NOBODY
    if module_name:
        _log.warning(
            "模块 '%s' 声明了非法 uid=%d (层级=%s, 允许范围=%s)，"
            "已自动降级为 uid=%d。请修正模块代码中的 uid 声明。",
            module_name, declared_uid, layer,
            f"{allowed.start}~{allowed.stop - 1}" if allowed else "nobody",
            default,
        )
    return default


# ── 白名单：可信的 daemon 级路径 ──────────────────────────
# 只有这些路径下的代码可以在启动时注册 daemon 级服务。
# 每条路径都是终结路径：精确匹配或作为包前缀（后接 "."）。
_DAEMON_TRUSTED_PATHS: Set[str] = {
    "qqlinker_framework.core",      # core/ 下所有模块
    "qqlinker_framework.managers",   # managers/ 下所有模块
    # 框架内置 daemon 模块（uid≤999）— 精确匹配
    "qqlinker_framework.modules.security.orion",
    "qqlinker_framework.modules.ai",          # ai 包前缀
    "qqlinker_framework.modules.game.admin",
    "qqlinker_framework.modules.game.forwarder",
    "qqlinker_framework.modules.game.tracker",
    "qqlinker_framework.modules.logging",      # logging 包前缀
    "qqlinker_framework.modules.system.auth",
}


def is_daemon_trusted(caller_module: str) -> bool:  # noqa: PYL-W0074 (utility function, not a method — correct placement at module level for security checks)
    """检查调用方是否来自可信的内核/守护路径。

    匹配规则：caller_module 等于白名单路径，或以白名单路径后接 "." 开头。
    这防止了前缀伪造攻击，例如 "qqlinker_framework.modules.ai" 不会
    匹配到 "qqlinker_framework.modules.ai_malicious"。
    """
    for p in _DAEMON_TRUSTED_PATHS:
        if caller_module == p or (
            caller_module.startswith(p) and caller_module[len(p)] == '.'
        ):
            return True
    return False


class ServiceContainer:
    """服务的注册与获取容器，Linux 风格 UID 权限体系。

    每个服务和调用方都有 UID 等级。低级别调用方无法获取高级别服务。
    root(uid=0) 始终拥有一切权限。

    ── 依赖拓扑（新增）──
    支持 register_dependency() 声明服务间依赖关系，
    resolve_order() 返回拓扑排序后的初始化顺序。
    用于 ModuleManager.initialize_all() 确保服务按依赖顺序初始化。
    """

    def __init__(self, uid: int = UID_ROOT):
        self._uid = uid
        self._services: Dict[str, Any] = {}
        self._service_uids: Dict[str, int] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._lock = threading.Lock()
        # ── 依赖拓扑 ──
        # _deps[name] = set of service names that name depends on
        self._deps: Dict[str, Set[str]] = {}

    @property
    def uid(self) -> int:
        return self._uid

    @property
    def uid_name(self) -> str:
        return uid_label(self._uid)

    def register(
        self, name: str, instance_or_factory: Any, *,
        uid: int = UID_SERVICE_MIN,
        _caller: str = "",
    ):
        """注册服务实例或工厂函数。

        Args:
            name: 服务名称。
            instance_or_factory: 实例或可调用工厂。
            uid: 该服务所需的 UID 等级。调用方必须 ≥ 此值才能获取。
            _caller: 内部用，调用方的模块路径（用于防提权校验）。
        """
        if name in self._services or name in self._factories:
            _log.warning("服务 '%s' 已注册，将被覆盖", name)

        # ── 防提权: daemon 级服务只有可信路径能注册 ──
        if uid <= UID_DAEMON_MAX and not is_daemon_trusted(_caller):
            _log.error(
                "安全拒绝: '%s' 尝试注册 daemon 级服务 '%s' (uid=%d)。"
                "只有框架内核路径 (core/ + managers/) 可以注册 daemon 级服务。",
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
            self._service_uids[name] = uid

    def get(self, name: str) -> Any:
        """获取服务实例，校验 UID 访问权限。

        UID 体系：数值越小权限越高（0=root, 1..999=daemon, 1000+...）。
        按层级校验：调用方层级必须 ≤ 服务层级（同层互访，高层可访问低层）。

        Raises:
            KeyError: 服务未注册。
            PermissionError: 调用方层级不足。
        """
        req_uid = self._service_uids.get(name)
        if req_uid is None:
            raise KeyError(f"服务 '{name}' 未注册")

        # root 拥有一切权限
        if self._uid == UID_ROOT:
            pass
        elif self._uid > req_uid:
            # 调用方 uid 数值大于服务 uid = 调用方层级更低 → 拒绝
            # 例外：同一层级内互访允许（daemon 100 可以访问 daemon 1）
            if not _same_layer(self._uid, req_uid):
                raise PermissionError(
                    f"{self.uid_name}(uid={self._uid}) "
                    f"无权访问 '{name}' "
                    f"(需要 {uid_label(req_uid)}/uid≤{req_uid})"
                )
        # self._uid <= req_uid 或者同层 → 允许

        if name in self._services:
            return self._services[name]
        # 工厂延迟创建（加锁防并发重复实例化）
        with self._lock:
            # Double-check: 可能另一个线程已创建
            if name in self._services:
                return self._services[name]
            factory = self._factories[name]
            try:
                instance = factory()
            except Exception:
                # 工厂创建失败时移除条目，防止下次 get() 再次失败
                del self._factories[name]
                raise
            self._services[name] = instance
            return instance

    def try_get(self, name: str) -> Optional[Any]:
        """尝试获取服务，权限不足时返回 None 而非抛异常。"""
        try:
            return self.get(name)
        except (KeyError, PermissionError):
            return None

    def has(self, name: str) -> bool:
        """检查服务是否已注册（不校验 UID）。"""
        return name in self._services or name in self._factories

    def get_service_uid(self, name: str) -> Optional[int]:
        """查询指定服务的 UID 等级。"""
        return self._service_uids.get(name)

    # ── 依赖拓扑（供 ModuleManager 排序用）──

    def register_dependency(
        self, service_name: str, depends_on_name: str,
    ) -> None:
        """声明服务依赖：service_name 依赖于 depends_on_name。

        Args:
            service_name: 服务名（依赖方）。
            depends_on_name: 被依赖的服务名。
        """
        with self._lock:
            deps = self._deps.setdefault(service_name, set())
            deps.add(depends_on_name)
            # 确保被依赖方在图中也有节点
            self._deps.setdefault(depends_on_name, set())

    def resolve_order(self) -> List[str]:
        """返回拓扑排序后的服务初始化顺序。

        基于 register_dependency() 声明的依赖关系，
        使用 Kahn 算法进行拓扑排序。

        若存在循环依赖，静默降级：直接返回原注册顺序（不中断流程）。

        Returns:
            拓扑排序后的服务名列表。
        """
        with self._lock:
            # 构建 in-degree 和 adjacency
            all_nodes: Set[str] = set()
            in_degree: Dict[str, int] = {}
            adj: Dict[str, List[str]] = {}

            for node in self._deps:
                all_nodes.add(node)
            for node, deps in self._deps.items():
                all_nodes.update(deps)

            for node in all_nodes:
                in_degree[node] = 0
                adj[node] = []

            for node, deps in self._deps.items():
                for dep in deps:
                    if dep in all_nodes:
                        in_degree[dep] += 1
                        adj[node].append(dep)

            # Kahn算法
            queue = [n for n, d in in_degree.items() if d == 0]
            result: List[str] = []
            visited_count = 0

            while queue:
                node = queue.pop(0)
                result.append(node)
                visited_count += 1
                for neighbor in adj.get(node, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            if visited_count != len(in_degree):
                # 循环依赖 → 静默降级为原始注册顺序
                _log.warning(
                    "服务依赖拓扑排序检测到循环依赖，"
                    "降级为原始注册顺序。已访问 %d/%d 节点",
                    visited_count, len(in_degree),
                )
                return list(self._service_uids.keys())

            return result

    def list_accessible(self) -> Dict[str, int]:
        """列出当前 UID 可访问的所有服务及等级。"""
        return {
            name: uid
            for name, uid in self._service_uids.items()
            if self._uid == UID_ROOT or self._uid >= uid
        }

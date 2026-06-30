import inspect
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

_log = logging.getLogger(__name__)

# ── MID 常量 (v6: 重命名自 TIER_*) ─────────────────────────

MID_KERNEL = 0
MID_DAEMON = 100
MID_SERVICE = 200
MID_APP = 300
MID_NOBODY = 400

MID_LABELS: Dict[int, str] = {
    MID_KERNEL: "kernel",
    MID_DAEMON: "daemon",
    MID_SERVICE: "service",
    MID_APP: "app",
    MID_NOBODY: "nobody",
}

# ── 旧名别名 (v6: TIER_* → MID_* 兼容层) ───────────────────

TIER_KERNEL = MID_KERNEL
TIER_DAEMON = MID_DAEMON
TIER_SERVICE = MID_SERVICE
TIER_APP = MID_APP
TIER_NOBODY = MID_NOBODY
UID_NOBODY = MID_NOBODY

TIER_LABELS = MID_LABELS

# ── 各层允许声明的 mid ─────────────────────────────────────
# 防提权：模块只能声明自己层级的 mid 值

MID_ALLOWED: Dict[str, int] = {
    "kernel": MID_KERNEL,
    "daemon": MID_DAEMON,
    "service": MID_SERVICE,
    "app": MID_APP,
    "nobody": MID_NOBODY,
}

TIER_ALLOWED = MID_ALLOWED  # 旧名别名


# ── ModuleGroup 数据类 (v6) ─────────────────────────────────

@dataclass
class ModuleGroup:
    """模块编组定义：mid 范围 + 默认权限级别。"""
    name: str
    mid_min: int
    mid_max: int
    default_perm: str  # "owner"|"admin"|"writer"|"reader"|"none"
    members: frozenset = field(default_factory=frozenset)


FIXED_GROUPS: Dict[str, ModuleGroup] = {
    "kernel":  ModuleGroup("kernel",  0, 0,   "owner"),
    "daemon":  ModuleGroup("daemon",  100, 199, "admin"),
    "service": ModuleGroup("service", 200, 299, "writer"),
    "app":     ModuleGroup("app",     300, 399, "reader"),
    "nobody":  ModuleGroup("nobody",  400, 499, "none"),
}


# ── ModulePerm 数据类 (v6) ──────────────────────────────────

@dataclass
class ModulePerm:
    """模块间权限位：对目标模块可执行的操作。"""
    read_config: bool = False
    write_config: bool = False
    terminate: bool = False
    freeze: bool = False
    delegate: bool = False


# ── 权限级别 → ModulePerm 映射 ──────────────────────────────

_PERM_MAP: Dict[str, ModulePerm] = {
    "owner":  ModulePerm(read_config=True, write_config=True, terminate=True, freeze=True, delegate=True),
    "admin":  ModulePerm(read_config=True, write_config=True, terminate=True, freeze=True),
    "writer": ModulePerm(read_config=True, write_config=True),
    "reader": ModulePerm(read_config=True),
    "none":   ModulePerm(),
}


# ── 权限检查函数 (v6) ───────────────────────────────────────

def check_perm(actor_mid: int, target_mid: int, action: str,
               groups: Optional[Dict[str, ModuleGroup]] = None,
               delegations: Optional[Dict[str, Dict[str, Dict[str, bool]]]] = None) -> bool:
    """检查 actor 对 target 是否有 action 权限。

    action ∈ {"read_config","write_config","terminate","freeze"}

    权限规则:
      - kernel 组 (mid=0) 拥有全部权限
      - 同组内按 default_perm 判断 (owner→admin→writer→reader→none)
      - 跨组查 delegations 字典
    """
    # kernel 总是通过
    if actor_mid == MID_KERNEL:
        return True

    if groups is None:
        groups = FIXED_GROUPS

    # 确定 actor 和 target 的组
    actor_group = _find_group(actor_mid, groups)
    target_group = _find_group(target_mid, groups)

    if actor_group is None or target_group is None:
        return False

    # 同组: 按 default_perm 判断
    if actor_group.name == target_group.name:
        perm = _PERM_MAP.get(actor_group.default_perm, _PERM_MAP["none"])
        return getattr(perm, action, False)

    # 跨组: 查 delegations
    if delegations:
        target_delegs = delegations.get(target_group.name, {})
        actor_deleg = target_delegs.get(actor_group.name, {})
        return actor_deleg.get(action, False)

    return False


def _find_group(mid: int, groups: Dict[str, ModuleGroup]) -> Optional[ModuleGroup]:
    """根据 mid 值查找所属 ModuleGroup。"""
    for group in groups.values():
        if group.mid_min <= mid <= group.mid_max:
            return group
    return None


def mid_label(mid: int) -> str:
    """返回 mid 的可读标签（v6 新名）。"""
    return MID_LABELS.get(mid, f"unknown({mid})")


def tier_label(tier: int) -> str:
    """返回等级的可读标签（旧名别名，指向 mid_label）。"""
    return mid_label(tier)


def uid_label(uid: int) -> str:
    """返回等级的可读标签（旧名别名，指向 mid_label）。"""
    return mid_label(uid)


def uid_layer(uid: int) -> str:
    """返回等级标签。"""
    return mid_label(uid)


def validate_module_mid(
    declared: int, module_name: str = "",
    layer: str = "app"
) -> int:
    """校验模块声明的 mid 是否合法（v6 新名）。

    防提权：外部模块声明的 mid 被无条件忽略，返回其层级默认值。

    Returns:
        校验后的有效 mid。非法声明时自动降级。
    """
    allowed = MID_ALLOWED.get(layer, MID_NOBODY)

    # ★ 硬限制：非 kernel 层模块不可声明 kernel mid
    if declared == MID_KERNEL and layer != "kernel":
        _log.warning(
            "模块 '%s' 声明了 kernel mid (0)，这是严重的安全违规。"
            "已强制降级为 %s。",
            module_name, mid_label(allowed),
        )
        return allowed

    if declared == allowed:
        return declared

    # 非法声明 → 降级
    _log.warning(
        "模块 '%s' 声明了非法 mid %d (层级=%s, 允许=%d(%s))，"
        "已自动降级为 %d。",
        module_name, declared, layer,
        allowed, mid_label(allowed), allowed,
    )
    return allowed


# ── 旧名别名 (v6 兼容层) ────────────────────────────────────

validate_module_tier = validate_module_mid




# ── 白名单：可信的 daemon 级路径 ────────────────────────────
# L1 修复: 改为 frozenset 显式匹配，不再使用字符串前缀匹配
# 避免 qqlinker_framework.modules.unknown_fake 伪造成 qqlinker_framework.modules
# 包含框架实际使用的所有 caller 字符串

_DAEMON_TRUSTED_MODULES: frozenset = frozenset({
    "qqlinker_framework.core.host", "qqlinker_framework.libraries.channel_host",
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
    """服务的注册与获取容器，mid + role + group 权限模型 (v6)。

    mid 值越小权限越高。root(0) 始终拥有一切权限。
    """

    def __init__(self, mid: int = MID_KERNEL, tier: Optional[int] = None,
                 service_registry=None, group: str = ""):
        if tier is not None:
            mid = tier  # 旧名兼容
        self._mid = mid
        self._services: Dict[str, Any] = {}
        self._service_mids: Dict[str, int] = {}
        self._service_groups: Dict[str, str] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._lock = threading.Lock()
        self._deps: Dict[str, Set[str]] = {}
        self._required_services: Dict[str, List[str]] = {}
        # ── v5.2: 服务注册表（允则控制）──
        self._service_registry = service_registry
        # ★ C1 修复: 视图锁定标记
        self._view_locked = False
        # ── v1.5.1: 组内免检 ──
        self._group = group

    # ── v6 新名属性 ──

    @property
    def mid(self) -> int:
        """当前模块 ID。"""
        return self._mid

    @property
    def mid_name(self) -> str:
        """当前模块 ID 的可读名称。"""
        return mid_label(self._mid)

    # ── 旧名别名 (v6 兼容层) ──

    @property
    def tier(self) -> int:
        """旧名别名 → self.mid。"""
        return self._mid

    @property
    def tier_name(self) -> str:
        """旧名别名 → self.mid_name。"""
        return self.mid_name

    @property
    def uid(self) -> int:
        """旧名别名 → self.mid。"""
        return self._mid

    @uid.setter
    def uid(self, value: int):  # noqa: PYL-R0201
        """UID 只读 setter，禁止提权。"""
        raise PermissionError(
            "ServiceContainer.uid 只读。视图的 mid 在创建时已锁定，"
            "不可提升权限。使用 scope(mid) 创建新的低权限视图。"
        )

    @property
    def uid_name(self) -> str:
        """旧名别名 → self.mid_name。"""
        return self.mid_name

    def __setattr__(self, name, value):
        """拦截 _mid / _tier 的直接赋值，防止越权提权。

        C1 修复: 恶意模块可执行 self.services._mid = 0 获得 root。
        视图创建后 _view_locked=True，任何 _mid 修改均被拒绝。
        scope() 使用 object.__setattr__ 绕过锁定以在构造期设置值。
        """
        if name in ('_mid', '_tier') and getattr(self, '_view_locked', False):
            raise PermissionError(
                "ServiceContainer._mid 只读。视图的 mid 在创建时已锁定，"
                "不可提升权限。"
            )
        super().__setattr__(name, value)

    def scope(self, mid: int, group: str = "") -> "ServiceContainer":
        """创建一个 mid 受限的视图（v6 新名，原 view()），共享底层服务注册表。

        每个模块得到独立的 ServiceContainer 视图 —— 共享 _services /
        _factories / _service_mids，但 _mid 被限制为模块自身 mid。
        防止低权限模块越权获取高级别服务。

        v6: 不再按数值大小过滤服务，改为检查 required_services 声明。
        """
        scoped = ServiceContainer.__new__(ServiceContainer)
        object.__setattr__(scoped, '_mid', mid)
        # 同时设置 _tier 以兼容依赖 _tier 检查的旧代码
        object.__setattr__(scoped, '_tier', mid)
        scoped._services = self._services
        scoped._factories = self._factories
        scoped._service_mids = self._service_mids
        scoped._deps = self._deps
        scoped._lock = self._lock
        scoped._required_services = self._required_services
        # ── v5.2: 服务注册表引用 ──
        scoped._service_registry = self._service_registry
        scoped._service_groups = self._service_groups
        # ── v1.5.1: 组内免检 ──
        scoped._group = group
        # ★ C1 修复: 锁定视图，_mid 此后不可修改
        object.__setattr__(scoped, '_view_locked', True)
        return scoped

    # ── 旧名别名 ──

    def view(self, tier: int) -> "ServiceContainer":
        """旧名别名 → scope()。"""
        return self.scope(tier)

    def register(
        self, name: str, instance_or_factory: Any, *,
        uid: Optional[int] = None,
        mid: int = MID_SERVICE,
        is_factory: Optional[bool] = None,
        _caller: str = "",
        description: str = "",
        group: str = "",
    ):
        """注册服务实例或工厂函数。

        Args:
            name: 服务名称。
            instance_or_factory: 实例或可调用工厂。
            uid: (deprecated) 旧名，等同 mid。
            mid: 该服务的模块 ID（数值越小权限越高）。
            is_factory: None=自动检测, True=强制工厂, False=强制服务实例。
            _caller: 内部用，调用方的模块路径（用于防提权校验）。
            description: 服务描述（文档用途，不参与逻辑）。
        """
        if uid is not None:
            mid = uid  # 旧名兼容

        # ── v5.2: 服务注册表允则检查 ──
        if self._service_registry is not None:
            if not self._service_registry.is_allowed(name, mid):
                # 注册表为空 → 首次启动兜底：自动签署
                if not self._service_registry.get_all_entries():
                    self._service_registry.auto_sign(name)
                else:
                    _log.error(
                        "安全拒绝: 服务 '%s' 未在服务注册表中启用", name
                    )
                    raise PermissionError(
                        f"服务 '{name}' 未在服务注册表中启用。"
                        f"请将 '{name}' 添加到 数据/服务注册表.json"
                    )

        if name in self._services or name in self._factories:
            _log.warning("服务 '%s' 已注册，将被覆盖", name)

        # 防提权: daemon 级服务只有可信路径能注册
        if mid <= MID_DAEMON and not is_daemon_trusted(_caller):
            _log.error(
                "安全拒绝: '%s' 尝试注册 daemon 级服务 '%s' (mid=%d)。",
                _caller or "unknown", name, mid,
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
            self._service_mids[name] = mid
            # 兼容旧代码: _service_tiers 同步引用
            self._service_tiers = self._service_mids
            # ── v1.5.1: 记录服务所属组 ──
            self._service_groups[name] = group

    def get(self, name: str, *, mid: Optional[int] = None) -> Any:
        """获取服务实例，基于 declarative 权限检查 (v6)。

        v6 规则:
          1. kernel(mid=0) 始终通过
          2. daemon 组 (mid≤199) 允许旧式 mid 数值比较（兼容）
          3. 其他: 同mid或更低权限(mid较大)的服务允许；
             跨组访问更高权限(mid较小)的服务需要声明 required_services

        Raises:
            KeyError: 服务未注册。
            PermissionError: 调用方权限不足。
        """
        req_mid = self._service_mids.get(name)
        if req_mid is None:
            raise KeyError(f"服务 '{name}' 未注册")

        caller_mid = self._mid

        # kernel 始终通过
        if caller_mid == MID_KERNEL:
            pass
        # v1.5.1: 组内免检
        elif self._group and self._group == self._service_groups.get(name, ""):
            pass  # 同组，跳过 mid 检查
        elif caller_mid <= MID_DAEMON:
            # daemon 组: 仍允许旧式访问（兼容）
            if caller_mid > req_mid:
                raise PermissionError(
                    f"{self.mid_name}(mid={caller_mid}) "
                    f"无权访问 '{name}' "
                    f"(服务 mid={req_mid} > 调用方 mid={caller_mid})"
                )
        elif caller_mid <= req_mid:
            # 同 mid 或更低权限服务（mid 更大）: 始终允许
            pass
        else:
            # 跨组访问更高权限服务: 需要声明式依赖
            declared = self._required_services.get(caller_mid, [])
            if name not in declared:
                raise PermissionError(
                    f"{self.mid_name}(mid={caller_mid}) "
                    f"无权访问 '{name}' "
                    f"(服务 mid={req_mid} < 调用方 mid={caller_mid}，"
                    f"且未在 required_services 中声明)"
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

    def get_service_mid(self, name: str) -> Optional[int]:
        """查询指定服务的 mid (v6 新名)。"""
        return self._service_mids.get(name)

    def get_service_uid(self, name: str) -> Optional[int]:
        """旧名别名 → get_service_mid()。"""
        return self._service_mids.get(name)

    def register_dependency(self, service_name: str, dependent: str) -> None:  # noqa: PYL-R0201
        """注册模块对服务的依赖关系（测试用 API）。

        在 v2 tier 体系中，依赖关系由服务注册时的 uid 值隐式表达。
        该方法保留作为兼容接口。
        """
        _log.debug("依赖注册（无操作）: '%s' -> '%s'", dependent, service_name)

    def unregister_dependency(self, service_name: str, dependent: str) -> None:  # noqa: PYL-R0201
        """注销模块对服务的依赖关系（兼容接口）。"""
        pass

    def resolve_order(self) -> list:
        """返回模块解析顺序（按 mid 从低到高排序）。

        v6 mid 体系: kernel(0) → daemon(100-199) → service(200-299) → app(300-399)
        无需复杂的图拓扑排序。
        """
        # 从服务注册表中提取模块名并排 mid
        modules = []
        for name in list(self._service_mids.keys()):
            if not name.startswith('_') and name not in ('config', 'event_bus',
                    'command', 'tool', 'adapter', 'message', 'package',
                    'recovery', 'uid_lookup', 'group_config', 'group_filter',
                    'dedup', 'debug', 'market_server', 'market', 'ws_client'):
                modules.append((self._service_mids.get(name, 400), name))
        modules.sort()
        return [name for _, name in modules]

    def list_accessible(self) -> Dict[str, int]:
        """列出当前 mid 可访问的所有服务及 mid。"""
        return {
            name: mid
            for name, mid in self._service_mids.items()
            if self._mid == MID_KERNEL or self._mid <= mid
        }

    def register_required_services(self, mid: int, services: List[str]) -> None:
        """注册模块对服务的依赖声明 (v6 declarative)。

        在 Module.__init__ 中自动调用，填充 _required_services 表。
        后续 get() 调用时检查声明式依赖。
        """
        with self._lock:
            self._required_services[mid] = list(services)


# ═══════════════════════════════════════════════════════════════
# v1.4.3: 交互式会话追踪器
# ═══════════════════════════════════════════════════════════════

class InteractiveSessionTracker:
    """追踪哪些用户处于交互式会话中 — 通用交互式对话约定。

    v6 增强:
      - 新增 capture_module — 标记哪个模块在捕获用户输入
      - 新增 capture_command — 是否拦截其他命令路由（默认 True）
      - 支持超时自动退出
      - CommandRouter 在 handle_message 中检查此约定：
        若用户处于交互式会话且 capture_command=True，
        跳过所有命令匹配，消息仅发布为 GroupMessageEvent。

    用法（任何模块）:
      tracker = services.get("session_tracker")
      tracker.enter(uid, gid, session_type="my_flow", capture_module="my_module")
      ... 用户在交互模式下的所有输入不会被命令路由拦截 ...
      tracker.leave(uid)
    """

    DEFAULT_TIMEOUT = 300  # 5 分钟无输入自动退出

    def __init__(self):
        self._sessions: Dict[str, dict] = {}

    def enter(self, user_id: int, group_id: int = 0,
              session_type: str = "", capture_module: str = "",
              capture_command: bool = True):
        """用户进入交互式会话。

        Args:
            user_id: QQ 用户 ID
            group_id: 群号
            session_type: 会话类型标识（如 'rule_create', 'bind_flow'）
            capture_module: 捕获输入的模块名（用于审计和冲突检测）
            capture_command: True 时拦截其他命令路由
        """
        key = str(user_id)
        import time
        self._sessions[key] = {
            "user_id": user_id,
            "group_id": group_id,
            "type": session_type,
            "capture_module": capture_module,
            "capture_command": capture_command,
            "ts": time.time(),
        }

    def leave(self, user_id: int):
        """用户退出交互式会话。"""
        self._sessions.pop(str(user_id), None)

    def is_active(self, user_id: int) -> bool:
        """用户是否处于交互式会话中（含超时检查）。"""
        key = str(user_id)
        session = self._sessions.get(key)
        if session is None:
            return False
        import time
        if time.time() - session.get("ts", 0) > self.DEFAULT_TIMEOUT:
            self._sessions.pop(key, None)
            return False
        return True

    def touch(self, user_id: int):
        """刷新会话时间戳（收到用户输入时调用）。"""
        key = str(user_id)
        session = self._sessions.get(key)
        if session is not None:
            import time
            session["ts"] = time.time()

    def get_session(self, user_id: int) -> Optional[dict]:
        """获取用户的交互式会话信息（含超时检查）。"""
        key = str(user_id)
        session = self._sessions.get(key)
        if session is None:
            return None
        import time
        if time.time() - session.get("ts", 0) > self.DEFAULT_TIMEOUT:
            self._sessions.pop(key, None)
            return None
        return dict(session)

    def active_users(self) -> list:
        """所有交互式会话中的用户 ID 列表（排除超时）。"""
        import time
        now = time.time()
        expired = []
        for key, session in list(self._sessions.items()):
            if now - session.get("ts", 0) > self.DEFAULT_TIMEOUT:
                expired.append(key)
        for key in expired:
            self._sessions.pop(key, None)
        return [int(k) for k in self._sessions]

    def should_capture_commands(self, user_id: int) -> bool:
        """是否应该拦截该用户的命令路由。由 CommandRouter 调用。"""
        session = self.get_session(user_id)
        if session is None:
            return False
        return bool(session.get("capture_command", True))

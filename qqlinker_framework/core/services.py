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
from typing import Any, Callable, Dict, Optional, Set

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
    """返回 UID 所属层级名。"""  # noqa: PYL-R1705
    if uid == UID_ROOT:
        return "root"
    if uid <= UID_DAEMON_MAX:
        return "daemon"
    if uid <= UID_SERVICE_MAX:
        return "service"
    if uid <= UID_APP_MAX:
        return "app"
    return "nobody"


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


# ── 白名单：可信的框架内核文件路径前缀 ──────────────────────
# 只有这些路径下的代码可以在启动时注册 daemon 级服务
_DAEMON_TRUSTED_PATHS: Set[str] = {
    "qqlinker_framework.core.",
    "qqlinker_framework.managers.",
}


def is_daemon_trusted(caller_module: str) -> bool:  # noqa: PY-W0074
    """检查调用方是否来自可信的内核/守护路径。"""
    return any(caller_module.startswith(p) for p in _DAEMON_TRUSTED_PATHS)


class ServiceContainer:
    """服务的注册与获取容器，Linux 风格 UID 权限体系。

    每个服务和调用方都有 UID 等级。低级别调用方无法获取高级别服务。
    root(uid=0) 始终拥有一切权限。
    """

    def __init__(self, uid: int = UID_ROOT):
        self._uid = uid
        self._services: Dict[str, Any] = {}
        self._service_uids: Dict[str, int] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}

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

        if callable(instance_or_factory):
            self._factories[name] = instance_or_factory
        else:
            self._services[name] = instance_or_factory
        self._service_uids[name] = uid

    def get(self, name: str) -> Any:
        """获取服务实例，校验 UID 访问权限。

        Raises:
            KeyError: 服务未注册。
            PermissionError: 调用方 UID 不足（不是 root 且 uid < 所需等级）。
        """
        req_uid = self._service_uids.get(name)
        if req_uid is None:
            raise KeyError(f"服务 '{name}' 未注册")

        # root 拥有一切权限
        if self._uid != UID_ROOT and self._uid < req_uid:
            raise PermissionError(
                f"{self.uid_name}(uid={self._uid}) "
                f"无权访问 '{name}' "
                f"(需要 {uid_label(req_uid)}/uid≥{req_uid})"
            )

        if name in self._services:
            return self._services[name]
        instance = self._factories[name]()
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

    def list_accessible(self) -> Dict[str, int]:
        """列出当前 UID 可访问的所有服务及等级。"""
        return {
            name: uid
            for name, uid in self._service_uids.items()
            if self._uid == UID_ROOT or self._uid >= uid
        }

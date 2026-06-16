"""模块基类 — 约定优于配置 

═══════════════════════════════════════════════════════════════════════════
 约定属性               │ 框架自动执行
═══════════════════════════════════════════════════════════════════════════
 default_config         │ 注册配置节
 config_schema          │ 自动注入类型安全配置为 self.cfg_<name>
 exports                │ 静态服务注册
 create_exports() → dict│ 动态服务工厂
 tools                  │ 声明式工具定义列表，自动注册到 ToolManager
 scheduled              │ 声明式定时任务，自动启动/停止
 hot_reload_state       │ 序列化热重载状态，自动持久化
 dependencies           │ 拓扑排序加载顺序
 required_services      │ 自动注入为 self.<name>
 enabled                │ False 跳过加载
 default_cooldown       │ 命令默认冷却
═══════════════════════════════════════════════════════════════════════════

框架注入属性:
  self.logger           │ 模块专用 logger
  self.data_dir         │ 模块数据目录（自动创建）
  self.db               │ JSON 数据库代理（自动创建 collections）
═══════════════════════════════════════════════════════════════════════════
"""
import asyncio
import enum
import json
import logging
import os
import sys
import tempfile
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .kernel.services import ServiceContainer, mid_label, validate_module_mid as validate_module_uid, MID_KERNEL, MID_DAEMON
from .kernel.bus import EventBus
from .kernel.error_hints import hint
from .kernel.degradation import DEGRADABLE_SERVICES, CRITICAL_SERVICES
from .kernel.gatekeeper import GatekeeperProxy, ALLOWED_EVENTS as _ALLOWED_EVENTS_FOR_MODULE


# ── FrozenState 枚举 ─────────────────────────────────────────

class FrozenState(enum.Enum):
    """模块冻结状态枚举。"""
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    SUSPENDED = "SUSPENDED"


# ── JSON 数据库代理 ──────────────────────────────────────────

class JsonCollection:
    """单个 JSON 集合的 CRUD 代理，自动持久化。"""

    def __init__(self, filepath: str):
        self._file = filepath
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        """从磁盘加载 JSON 数据。"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}

    def _save(self):
        """持久化当前数据到磁盘（原子写入：临时文件 + os.replace）。"""
        dirname = os.path.dirname(self._file) or "."
        os.makedirs(dirname, exist_ok=True)
        tmpfd, tmppath = tempfile.mkstemp(
            dir=dirname,
            prefix=os.path.basename(self._file) + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmpfd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmppath, self._file)
        except Exception:
            # 清理临时文件，避免泄漏
            try:
                os.unlink(tmppath)
            except OSError:
                pass
            raise

    # ── CRUD ──

    def get(self, key: str, default: Any = None) -> Any:
        """读取指定键的值。"""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """写入键值对并持久化。"""
        with self._lock:
            self._data[key] = value
            self._save()

    def delete(self, key: str) -> bool:
        """删除指定键，返回是否成功。"""
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()
                return True
            return False

    def all(self) -> Dict[str, Any]:
        """返回所有键值对的浅拷贝。"""
        with self._lock:
            return dict(self._data)

    def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        with self._lock:
            return key in self._data

    def count(self) -> int:
        """返回存储条目数量。"""
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        """清空所有数据。"""
        with self._lock:
            self._data.clear()
            self._save()

    def keys(self) -> List[str]:
        """返回所有键的列表。"""
        with self._lock:
            return list(self._data.keys())

    def values(self) -> List[Any]:
        """返回所有值的列表。"""
        with self._lock:
            return list(self._data.values())

    def update(self, items: Dict[str, Any]) -> None:
        """批量更新键值对。"""
        with self._lock:
            self._data.update(items)
            self._save()

    def __repr__(self):
        return f"<JsonCollection keys={len(self._data)}>"


class JsonDatabase:
    """JSON 数据库代理 — 按模块自动管理 collections。"""

    def __init__(self, data_dir: str, collections: List[str]):
        os.makedirs(data_dir, exist_ok=True)
        for name in collections:
            filepath = os.path.join(data_dir, f"{name}.json")
            setattr(self, name, JsonCollection(filepath))


# ── 定时任务定义 ─────────────────────────────────────────────

class ScheduledTask:
    """声明式定时任务定义。"""

    def __init__(
        self,
        name: str,
        handler: Callable,
        *,
        interval: float | None = None,
        cron: str | None = None,
        run_on_start: bool = False,
        enabled: bool = True,
    ):
        self.name = name
        self.handler = handler
        self.interval = interval          # 间隔秒数（None = cron 模式）
        self.cron = cron                  # cron 表达式（None = interval 模式）
        self.run_on_start = run_on_start
        self.enabled = enabled
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> Optional[asyncio.Task]:
        """启动定时任务。"""
        if self._task and not self._task.done():
            return self._task

        async def _runner():
            """定时任务主循环: 间隔等待并执行回调。"""
            if self.run_on_start:
                await _safe_call(self.handler)
            while not self._stop_event.is_set():
                try:
                    if self.interval:
                        await asyncio.wait_for(
                            self._stop_event.wait(), timeout=self.interval
                        )
                        if self._stop_event.is_set():
                            break
                    else:
                        # cron 模式简化：按最近整分钟触发
                        await asyncio.sleep(60)
                    if self.enabled:
                        await _safe_call(self.handler)
                except asyncio.TimeoutError:
                    if self.enabled:
                        await _safe_call(self.handler)
                except asyncio.CancelledError:
                    break
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 无运行中事件循环（热插拔/非 async 上下文）→ 用 get_event_loop fallback
            loop = asyncio.get_event_loop()
        self._task = loop.create_task(_runner())
        return self._task

    def stop(self):
        """停止定时任务并取消异步任务。"""
        self._stop_event.set()
        if self._task:
            self._task.cancel()


async def _safe_call(handler: Callable):
    """安全调用处理器，捕获异常并记录日志。"""
    try:
        if asyncio.iscoroutinefunction(handler):
            await handler()
        else:
            await asyncio.get_running_loop().run_in_executor(None, handler)
    except Exception:
        logging.getLogger(__name__).exception("定时任务异常。%s", hint["UNEXPECTED_ERROR"])


# ── 热重载状态 ──────────────────────────────────────────────

class HotReloadState:
    """热重载状态管理器 — 自动从磁盘序列化/反序列化。"""

    def __init__(self, filepath: str, defaults: Dict[str, Any] = None):
        self._file = filepath
        self._defaults = defaults or {}
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self):
        """从磁盘加载状态，合并默认值。"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data = {**self._defaults, **loaded}
            except (json.JSONDecodeError, IOError):
                self._data = dict(self._defaults)
        else:
            self._data = dict(self._defaults)

    def save(self):
        """持久化当前状态到磁盘。"""
        os.makedirs(os.path.dirname(self._file), exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """读取指定键的值。"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """写入键值对并持久化。"""
        self._data[key] = value
        self.save()

    def all(self) -> Dict[str, Any]:
        """返回所有键值对的浅拷贝。"""
        return dict(self._data)


# ── 事件白名单（非 root 模块可订阅的受限事件）──
# v5: 统一从 gatekeeper.py 导入，单一数据源


# ── 模块基类 ─────────────────────────────────────────────────

class Module(ABC):
    """所有业务模块的抽象基类。

    声明式约定属性（全部可选，框架自动处理）:
        config_schema: Tuple[str, Any] 映射 → 自动注入 self.cfg_<name>
        tools: List[dict] → 自动注册到 ToolManager
        scheduled: List[ScheduledTask] → 自动启动/停止
        hot_reload_state: Dict[str, Any] → 自动持久化

    ── 配置读取指南 ──
    推荐使用 **self.config.get("路径")** 作为主要配置读取方式：
        # 推荐：按路径读取，支持 "节.键" 点号表示法
        value = self.config.get("AI助手.温度", 0.7)
        # 也支持忽略默认值
        value = self.config.get("AI助手.温度")

    self.cfg_<name> 是 config_schema 注入的便捷别名（声明式简写）：
        # 在 config_schema 中声明后可用：
        config_schema = {"temperature": ("AI助手.温度", 0.7)}
        # 然后直接 self.cfg_temperature 即可（但此值在 on_init 时快照，
        # 不反映运行时动态修改）。

    因此：
    - **self.config.get()** → 适用于需要动态读取最新配置的场景
    - **self.cfg_<name>**  → 适用于启动时固定、后续不变的便捷值
    - 新手建议统一使用 self.config.get()，避免混淆
    """

    # ── 必须声明 ──
    name: str = ""
    mid: int = 300  # v6: 模块 ID, 0=kernel, 100-199=daemon, 200-299=service, 300-399=app, 400-499=nobody
    group: str = "standalone"  # 模块所属组，自动从包 __init__.py 读取

    # ── 可选覆写 ──
    # uid/tier 为 property → self.mid; 子类可声明类属性覆盖默认值
    uid: int = 300  # noqa: F811  # deprecated, alias for mid
    tier: int = 300  # noqa: F811  # deprecated, alias for mid
    version: tuple = (0, 0, 1)
    dependencies: list[str] = []
    required_services: list[str] = []
    default_config: Dict[str, Dict[str, Any]] = {}
    config_schema: Dict[str, Tuple[str, Any]] = {}
    config_scope: Dict[str, str] = {}  # section → "global"|"group"，默认 "group"
    exports: Dict[str, Any] = {}
    tools: List[Dict[str, Any]] = []
    scheduled: List[ScheduledTask] = []
    hot_reload_state: Dict[str, Any] = {}
    db_collections: List[str] = []
    enabled: bool = True
    default_cooldown: float = 0.0
    background: bool = False  # True = 预加载常驻，False = 仅扫描装饰器，按需懒加载

    # ── FREEZE/THAW ──
    frozen: bool = False

    # ── 框架内部 ──
    _conventions_applied: bool = False
    _scheduled_tasks: List[ScheduledTask] = []
    _hot_state: HotReloadState | None = None

    def __init__(self, services: ServiceContainer, event_bus: EventBus | None = None):
        # H1 修复: root 容器引用以名称修饰存储，防止外部直接访问。
        # _root_services 属性 (property, 见下方) 根据 mid 返回受限视图或 root 视图:
        #   - daemon (mid≤100): 返回 root 容器（完整权限）
        #   - 其余: 返回 self.services（受限视图）
        self.__root_services = services
        self.event_bus = event_bus
        # ── v6: 统一 mid 字段 — uid/tier 兼容读取，默认取 mid ──
        # 注意: uid/tier 在 Module 上定义为 property，
        # 子类可能用类属性覆写。用 __dict__ 读取避免捕获 property descriptor。
        cls_dict = self.__class__.__dict__
        declared_mid = cls_dict.get('mid', 300)
        declared_uid = cls_dict.get('uid', None)
        declared_tier = cls_dict.get('tier', None)
        # 兼容: uid 或 tier 如果被显式声明且不同于默认值, 采纳
        if declared_uid is not None and not isinstance(declared_uid, property) and declared_uid != 300:
            declared_mid = declared_uid
        if declared_tier is not None and not isinstance(declared_tier, property) and declared_tier != 300:
            declared_mid = declared_tier
        self.mid = declared_mid
        # v1.5.1: 自动从包 __init__.py 读取 MODULE_GROUP
        _module_has_own_mid = (
            'mid' in cls_dict
            or (declared_uid is not None and not isinstance(declared_uid, property))
            or (declared_tier is not None and not isinstance(declared_tier, property))
        )
        if self.group == "standalone":
            try:
                pkg = sys.modules.get(type(self).__module__)
                if pkg:
                    pkg_name = type(self).__module__.rsplit('.', 1)[0]
                    parent_pkg = sys.modules.get(pkg_name)
                    if parent_pkg and hasattr(parent_pkg, 'MODULE_GROUP'):
                        grp = parent_pkg.MODULE_GROUP
                        self.group = grp.get("name", "standalone")
                        # 组 mid 作为默认值，模块显式声明的 mid 优先
                        if "mid" in grp and not _module_has_own_mid:
                            self.mid = grp["mid"]
            except Exception:
                pass
        if self.mid <= 0:
            layer = "kernel"
        elif self.mid <= 100:
            layer = "daemon"
        elif self.mid <= 200:
            layer = "service"
        elif self.mid <= 300:
            layer = "app"
        else:
            layer = "nobody"
        self.mid = validate_module_uid(self.mid, self.name, layer=layer)

        # ── MID 受限的服务容器视图 (v6: scope 替代 view) ──
        self.services = services.scope(self.mid)

        # ── v6: 注册声明式服务依赖 ──
        if self.required_services:
            services.register_required_services(self.mid, self.required_services)

        # ── 命令/事件/工具注册表 ──
        self._commands: dict = {}
        self._event_handlers: list = []
        self._tool_defs: list = []

        # ── 便利属性（在服务注入前初始化，因为降级警告需要 logger）──
        self.logger = logging.getLogger(
            f"{__name__.rsplit('.', 1)[0]}.{self.name}" or __name__
        )

        # ── 服务注入（含 mid 权限校验 + v5 优雅降级）──
        # Fix: 通过受限视图 self.services 获取服务，而非直接使用 root 容器
        # services。self.services 是 mid 视图，自动过滤无权限的服务。
        # v5: 非关键服务缺失时降级运行而非崩溃。
        for srv_name in self.required_services:
            if not self.services.has(srv_name):
                # v5 降级判断: 非关键服务缺失 → 降级运行
                if srv_name in DEGRADABLE_SERVICES:
                    self.logger.warning(
                        "🔶 模块 '%s': 非关键服务 '%s' 未注册，以降级模式运行",
                        self.name, srv_name,
                    )
                    # 设置占位属性为 None，模块代码需自行 null-check
                    setattr(self, srv_name, None)
                    continue
                # 关键服务缺失 → 仍抛异常（框架级错误）
                raise RuntimeError(
                    f"模块 '{self.name}' 需要服务 '{srv_name}'，但未注册。"
                    f"{hint['SERVICE_NOT_FOUND']}"
                )
            try:
                setattr(self, srv_name, self.services.get(srv_name))
            except PermissionError as e:
                # v5 降级判断: 非关键服务无权限 → 降级运行
                if srv_name in DEGRADABLE_SERVICES:
                    self.logger.warning(
                        "🔶 模块 '%s': 无权访问非关键服务 '%s' (%s)，以降级模式运行",
                        self.name, srv_name, e,
                    )
                    setattr(self, srv_name, None)
                    continue
                raise PermissionError(
                    f"模块 '{self.name}' (mid={self.mid}/{mid_label(self.mid)}) "
                    f"无权访问服务 '{srv_name}': {e}"
                )

        # ── 便利属性 ──
        self._data_dir: str | None = None
        self.db: JsonDatabase | None = None

        # ── 魔法属性（简化开发）──
        # H1 修复: 框架初始化注入使用 root 容器，
        # 注入的代理（_ConfigProxy, _GameProxy 等）自带 caller_mid 权限检查。
        self._inject_magic_attrs(self.__root_services)

        # ── 能力安全桥梁（私有属性，不注册到服务容器）──
        # _resolve_bridge 需要访问 _host (uid=0) 服务，
        # 因此使用 root 容器。bridge 返回给 daemon 级模块使用；
        # 外部模块通过 _root_services property（受限视图）无法获取。
        self._bridge = self._resolve_bridge(services)

        # ── 配置注入：初始化 self.cfg_* 属性 ──
        if self.config_schema:
            config_svc = getattr(self, 'config', None)
            for attr_name, (config_path, default) in self.config_schema.items():
                try:
                    value = config_svc.get(config_path, default) if config_svc else default
                except Exception:
                    value = default
                setattr(self, f"cfg_{attr_name}", value)

        # ── 配置热重载：自动更新 self.cfg_* 属性 ──
        if self.config_schema and self.event_bus is not None:
            self.event_bus.subscribe("ConfigReloadEvent", self._on_config_reloaded)

    @staticmethod
    def _resolve_bridge(services):
        """从 FrameworkHost 中解析 GatekeeperBridge 实例。

        _host 服务为 uid=0 (root)，只能通过 root 容器访问。
        此方法从 __init__ 调用时传入 root 容器参数，
        外部模块无法通过 _root_services property 调用此路径。
        """
        try:
            host = services.get("_host")
            return getattr(host, "gatekeeper", None)
        except Exception:
            return None

    async def _on_config_reloaded(self, event):
        """配置热重载时自动更新 self.cfg_<name> 属性。

        Fix 4: asyncio.wait_for(timeout=5.0) 超时保护 — 防止坏模块
        阻塞事件循环中后续模块的配置热更新。
        """
        try:
            await asyncio.wait_for(self._do_config_reload(), timeout=5.0)
        except asyncio.TimeoutError:
            self.logger.warning(
                "配置热更新超时 (5s)，模块 '%s' 可能存在阻塞操作，已跳过",
                self.name,
            )
        except Exception as e:
            self.logger.warning(
                "配置热更新异常 '%s': %s", self.name, e
            )

    async def _do_config_reload(self):
        """实际执行配置重载逻辑。"""
        config_svc = getattr(self, 'config', None)
        if not config_svc or not self.config_schema:
            return
        for attr_name, (config_path, default) in self.config_schema.items():
            try:
                value = config_svc.get(config_path, default)
                setattr(self, f"cfg_{attr_name}", value)
            except Exception:
                self.logger.debug(
                    "配置热更新 '%s' (路径=%s) 失败，保留旧值", attr_name, config_path
                )
        self.logger.info("配置已热更新 (%d 个 cfg_* 属性)", len(self.config_schema))

    def _inject_magic_attrs(self, services: ServiceContainer) -> None:
        """注入便捷属性: self.game / self.qq / self.cfg / self.adapter。

        模块可以直接 self.game.say(target, text) 代替
        self.services.get('adapter').send_game_message(target, text)

        H1 修复: 通过受限视图（self.services）注入，防止低权限模块
        以 root 权限越权操作。无人模块无权访问时优雅降级为 None。

        v6: 使用 ConfigStore 替代 _ConfigProxy。
        """
        # self.adapter — 通过受限视图获取
        try:
            self.adapter = services.get("adapter")
        except (KeyError, PermissionError):
            self.adapter = None

        # self.config — v6: 从 ConfigStore 获取 namespace 视图
        try:
            raw_cfg = services.get("config")
            # v6: 优先使用 ConfigStore；fallback 到旧 _ConfigProxy
            if hasattr(raw_cfg, '_cfg') and hasattr(raw_cfg._cfg, '_data_path'):
                # 旧版 _ConfigProxy — 保留兼容
                self.config = _ConfigProxy(raw_cfg, caller_mid=self.mid)
            else:
                self.config = _ConfigProxy(raw_cfg, caller_mid=self.mid)
        except (KeyError, PermissionError):
            self.config = None

        # self.group_config — 传入 caller_mid 防止越权
        try:
            raw_gcfg = services.get("group_config")
            self.group_config = _GroupConfigProxy(raw_gcfg, caller_mid=self.mid)
        except (KeyError, PermissionError):
            self.group_config = None

        # self.game — 游戏操作快捷方式（传入 caller_mid 用于白名单检查）
        self.game = _GameProxy(self.adapter, caller_mid=self.mid, config=self.config)

        # self.qq — QQ 操作快捷方式（传入模块 mid 用于审计）
        self.message = None
        try:
            self.message = services.get("message")
        except (KeyError, PermissionError):
            pass
        self.qq = _QQProxy(self.adapter, self.services, caller_mid=self.mid)

        # ── ★ Gatekeeper 代理 — 业务模块访问框架核心的唯一通道 ──
        # 每个模块持有自己的 GatekeeperProxy 实例，
        # 所有核心 API 调用必须经过此代理。
        # 代理内部做三重检查:
        #   1. MID 级别检查（继承自 ServiceContainer.scope）
        #   2. 资源配额检查（委托给 ResourceGuardian）
        #   3. 审计记录（委托给 AuditTrail）
        guardian = services.try_get("guardian")
        audit_trail = services.try_get("audit_trail")

        self.gatekeeper = GatekeeperProxy(
            services=self.services,
            mid=self.mid,
            module_name=self.name,
            guardian=guardian,
            audit=audit_trail,
            config=self.config,
            message=self.message,
            event_bus=self.event_bus,
            q_callbacks=self._commands,
        )

    # ── 属性 ──

    @property
    def uid(self) -> int:  # noqa: F811
        """旧名别名 → self.mid（兼容旧代码）。"""
        return self.mid

    @uid.setter
    def uid(self, value: int):  # noqa: F811
        self.mid = value

    @property
    def tier(self) -> int:  # noqa: F811
        """旧名别名 → self.mid（兼容旧代码）。"""
        return self.mid

    @tier.setter
    def tier(self, value: int):  # noqa: F811
        self.mid = value

    @property
    def _root_services(self) -> ServiceContainer:
        """H1 修复: 根据模块 mid 返回适当权限的服务容器。

        kernel 级 (mid=0) 返回 root 容器。
        daemon 级 (mid≤100) 返回受限视图 — 与 kernel 区分，
        防止 daemon 模块通过 _root_services 绕过权限检查。
        其余模块返回受限视图 self.services。
        """
        if self.mid == MID_KERNEL:
            return self.__root_services
        return self.services

    @property
    def data_dir(self) -> str:
        """模块数据目录。"""
        if self._data_dir is None:
            # 优先使用初始化注入的 self.config（bypass UID 限制）
            # fallback 到运行时 root 容器（仅初始化阶段可能发生）
            base = None
            cfg_proxy = getattr(self, 'config', None)
            if cfg_proxy is not None:
                try:
                    base = cfg_proxy.get_data_dir()
                except Exception:
                    pass
            # H1 修复: 使用 self.services（受限视图）代替 __root_services
            if base is None and self.services is not None:
                try:
                    base = self.services.get("config").get_data_dir()
                except Exception:
                    base = "data"
            if base is None:
                base = "data"
            path = os.path.join(base, "模块", self.name)
            os.makedirs(path, exist_ok=True)
            self._data_dir = path
        return self._data_dir

    def check_file_access(self, path: str, mode: str = "r") -> bool:
        """文件访问沙箱检查（v5 资源守护者集成）。

        非 root 模块调用此方法校验文件路径是否在允许范围内。
        返回 True 表示允许访问，False 表示拒绝。
        """
        guardian = self.services.try_get("guardian") if hasattr(self, 'services') and self.services else None
        if guardian and hasattr(guardian, 'check_file_access'):
            return guardian.check_file_access(path, self.mid, mode)
        return True  # guardian 未启用时允许

    def resolve_secrets(self, text: str) -> str:
        """解析文本中的 {配置:节.键} 占位符为实际配置值。

        mid≤100 的模块（daemon+）可用此方法间接引用安全配置
        （如 API 密钥），无需直接读取敏感值。

        示例:
            api_key = self.resolve_secrets("{配置:模块市场.上传密钥}")
        """
        if '{配置:' not in text:
            return text
        config_svc = getattr(self, 'config', None)
        if config_svc is None:
            return text
        return config_svc._cfg.resolve_placeholders(text)

    # ── 约定执行 ──

    def _apply_conventions(self) -> None:
        """执行全部约定（ModuleManager 在 on_init / on_start 前调用）。"""
        if self._conventions_applied:
            return
        self._conventions_applied = True

        # 使用初始化注入的服务引用（bypass UID view 限制）
        cfg_svc = getattr(self, 'config', None)
        group_cfg_svc = getattr(self, 'group_config', None)

        # ── A: default_config → register_section (with scope) ──
        if cfg_svc and self.default_config:
            # Fix: 框架初始化阶段使用 root bypass 注册配置节。
            # _ConfigProxy 传入了 caller_mid 用于运行时校验，但
            # _apply_conventions 是框架初始化路径，应使用 root 免检。
            raw_cfg = cfg_svc._cfg  # 绕过 _ConfigProxy 的 caller_mid 限制
            for section, defaults in self.default_config.items():
                raw_cfg.register_section(section, defaults, caller_uid=0)
                # 同时向 GroupConfigManager 注册 scope
                scope = self.config_scope.get(section, "group")
                if group_cfg_svc:
                    group_cfg_svc.register_module_schema(section, defaults, scope)

        # ── B: config_schema → self.cfg_<name> ──
        if cfg_svc and self.config_schema:
            for attr_name, (config_path, default) in self.config_schema.items():
                value = cfg_svc.get(config_path, default)
                setattr(self, f"cfg_{attr_name}", value)
                self.logger.debug(
                    "配置注入: self.cfg_%s = %s", attr_name, repr(value)[:60]
                )

        # ── C: exports + create_exports → services.register ──
        if hasattr(self, "create_exports") and callable(
            getattr(self, "create_exports", None)
        ):
            dynamic = self.create_exports()
            if isinstance(dynamic, dict):
                for name, inst in dynamic.items():
                    self.services.register(name, inst)
        if self.exports:
            for name, inst in self.exports.items():
                self.services.register(name, inst)

        # ── D: db_collections → self.db ──
        if self.db_collections:
            db_dir = os.path.join(self.data_dir, "数据")
            self.db = JsonDatabase(db_dir, self.db_collections)
            self.logger.debug(
                "数据库已初始化: %s", ", ".join(self.db_collections)
            )

        # ── E: hot_reload_state → self.state ──
        if self.hot_reload_state is not None or self.hot_reload_state:
            state_file = os.path.join(self.data_dir, "__reload_state__.json")
            self._hot_state = HotReloadState(state_file, self.hot_reload_state)
            self.logger.debug("热重载状态已加载: %d 项", len(self._hot_state.all()))

        # ── F: enabled 检查 ──
        if not self.enabled:
            self.logger.info("模块已禁用（enabled=False）")

        # ── G: gatekeeper 命令/事件收集 ──
        # 业务模块可通过 self.gatekeeper.register_command/listen
        # 注册命令和事件，在此统一收集并合并到 _commands/_event_handlers
        gatekeeper = getattr(self, 'gatekeeper', None)
        if gatekeeper is not None:
            gk_commands = gatekeeper._collect_commands()
            for trigger, cmd_info in gk_commands.items():
                if trigger not in self._commands:
                    self._commands[trigger] = cmd_info
                    self.logger.debug(
                        "Gatekeeper 命令已收集: %s", trigger,
                    )
            gk_events = gatekeeper._collect_events()
            for evt_type, handler, priority in gk_events:
                # 委托给 Module.listen 做实际订阅（含 GroupMessageEvent 包装）
                # 但需要绕过 listen 内部的白名单检查，因为门卫已做过
                # 使用 _apply_gatekeeper_event 绕过重复检查
                self._apply_gatekeeper_event(evt_type, handler, priority)

    async def _post_init_conventions(self) -> None:
        """on_init 之后执行的约定（依赖 on_init 中创建的资源）。"""
        # ── G: tools → ToolManager（v5: 降级处理）──
        tool_mgr = getattr(self, 'tool', None)
        if tool_mgr and self.tools:
            for tool_def in self.tools:
                try:
                    tool_mgr.register_tool(tool_def)
                    self.logger.debug("工具已注册: %s", tool_def.get("name"))
                except Exception as e:
                    self.logger.warning(
                        "🔶 工具 '%s' 注册失败（降级）: %s",
                        tool_def.get("name", "?"), e,
                    )

        # ── H: scheduled → 启动定时任务 ──
        if self.scheduled:
            for task_def in self.scheduled:
                self._scheduled_tasks.append(task_def)
                task_def.start()
                self.logger.debug(
                    "定时任务已启动: %s (间隔=%s秒)", task_def.name, task_def.interval
                )

    async def _cleanup_conventions(self) -> None:
        """模块卸载时清理约定资源。"""
        for task in self._scheduled_tasks:
            task.stop()
        self._scheduled_tasks.clear()

    def _apply_gatekeeper_event(self, event_type: str,
                                handler: Callable, priority: int) -> None:
        """应用由 Gatekeeper 代理注册的事件（绕过双重白名单检查）。

        事件已经过 GatekeeperProxy.listen() 的 ALLOWED_EVENTS 校验，
        此处只负责实际订阅 — GroupMessageEvent 自动包装群级过滤。
        """
        wrapped = handler
        if event_type == "GroupMessageEvent":
            original = handler
            module_name = self.name
            group_filter = getattr(self, 'group_filter', None)

            async def _filtered_handler(event):
                if group_filter is None:
                    await original(event)
                    return
                if group_filter.is_module_enabled(event.group_id, module_name):
                    await original(event)

            wrapped = _filtered_handler

        if self.event_bus is not None:
            self.event_bus.subscribe(event_type, wrapped, priority)
        self._event_handlers.append((event_type, handler, priority))

    # ── 生命周期 ──

    @abstractmethod
    async def on_init(self):
        """模块初始化。框架已处理: 服务注入 · 配置注册 · 装饰器扫描 · DB初始化。"""

    async def on_start(self):
        """模块启动时额外逻辑。框架在 on_init 后执行 _post_init_conventions。"""

    async def on_stop(self):
        """模块停止时清理。框架自动停止定时任务。"""
        await self._cleanup_conventions()

    # ── FREEZE / THAW 生命周期 ──

    async def on_freeze(self) -> None:
        """冻结时调用（默认：取消事件订阅、取消命令注册）。

        子模块可覆写以添加额外清理逻辑（如暂停定时任务、释放临时资源）。
        框架会在此方法返回后执行事件/命令的取消注册。
        """

    async def on_thaw(self) -> None:
        """解冻时调用（默认：重新注册事件/命令）。

        子模块可覆写以添加额外恢复逻辑（如重启定时任务、重建连接）。
        框架会在此方法调用前重新注册事件/命令。
        """

    # ── 崩溃恢复约定 ──

    @staticmethod
    def checkpoint() -> dict | None:
        """崩溃恢复检查点。

        覆写此方法返回需要持久化的关键状态（如会话历史、计数器等）。
        框架每 30 秒调用一次并原子写入磁盘。

        Returns:
            可 JSON 序列化的字典，None 表示无需检查点。
        """
        return None

    async def restore_checkpoint(self, data: dict) -> None:
        """从检查点恢复状态。

        框架在崩溃后启动恢复模式时调用。
        覆写此方法以从 data 中恢复关键状态。

        Args:
            data: checkpoint() 返回的数据字典。
        """
        pass

    # ── 声明式 API ──

    # ── 非 root 模块命令/工具 mid 下限 ──
    # 计算属性: daemon(mid≤100)可注册 daemon 级命令, service(mid≤200)可注册 service 级,
    # app(mid≤300)限注册 app+ 级, nobody(mid>300)限 nobody 级。
    # 动态取值，跟随模块自身 mid 而非硬编码。
    @property
    def _MIN_CMD_UID(self) -> int:
        """模块可注册命令的最低 mid 要求 = 模块自身 mid。"""
        return self.mid

    @property
    def _MIN_TOOL_UID(self) -> int:
        return self.mid

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
        min_uid: int = 400,
    ):
        """注册一个命令处理器。

        沙箱: 非 root 模块（uid > 0）只能注册 min_uid ≥ 自身 uid 的命令，
        防止低权限模块注册比自己权限更高的命令。
        """
        # ── 沙箱检查 ──
        if self.mid > 0 and min_uid < self._MIN_CMD_UID:
            self.logger.warning(
                "模块 '%s' (mid=%d) 尝试注册命令 '%s' (min_uid=%d < %d)，已拒绝",
                self.name, self.mid, trigger, min_uid, self._MIN_CMD_UID,
            )
            return
        if cooldown is None:
            cooldown = self.default_cooldown
        self._commands[trigger] = {
            "trigger": trigger,
            "cmd_type": cmd_type,
            "callback": callback,
            "description": description,
            "op_only": op_only,
            "required_role": required_role,
            "argument_hint": argument_hint,
            "cooldown": cooldown,
            "min_uid": min_uid,
        }

    def listen(self, event_type: str, handler: Callable, priority: int = 0):
        """订阅事件并记录到事件处理器列表。

        对于 GroupMessageEvent，自动包装群级模块过滤中间件。

        沙箱: 非 root 模块（uid > 0）只能订阅白名单事件：
        GroupMessageEvent, PlayerJoinEvent, PlayerLeaveEvent, GameChatEvent。
        """
        # ── 沙箱检查：非 root 模块受限事件白名单 ──
        if self.mid > 0 and event_type not in _ALLOWED_EVENTS_FOR_MODULE:
            self.logger.warning(
                "模块 '%s' (mid=%d) 尝试订阅受限事件 '%s'，已拒绝",
                self.name, self.mid, event_type,
            )
            return
        wrapped = handler
        if event_type == "GroupMessageEvent":
            original = handler
            module_name = self.name
            # 通过 services 获取 GroupModuleFilter（避免循环导入）
            group_filter = getattr(self, 'group_filter', None)

            async def _filtered_handler(event):
                """群级模块过滤包装：检查该群是否禁用当前模块。"""
                if group_filter is None:
                    # 没有 filter 服务时不过滤
                    await original(event)
                    return
                if group_filter.is_module_enabled(event.group_id, module_name):
                    await original(event)

            wrapped = _filtered_handler

        self.event_bus.subscribe(event_type, wrapped, priority)
        self._event_handlers.append((event_type, handler, priority))

    def register_tool(self, tool_definition: dict):
        """编程式注册工具定义。

        沙箱: 非 root 模块（uid > 0）只能注册 uid ≥ 300 的工具，
        防止低权限模块以高权限注册。
        """
        tool_uid = tool_definition.get("uid", 300)
        if self.mid > 0 and tool_uid < self._MIN_TOOL_UID:
            self.logger.warning(
                "模块 '%s' (mid=%d) 尝试注册工具 '%s' (uid=%d < %d)，已拒绝",
                self.name, self.mid,
                tool_definition.get("name", "<unnamed>"),
                tool_uid, self._MIN_TOOL_UID,
            )
            return
        self._tool_defs.append(tool_definition)

    def listen_packet(self, packet_id: int, handler: Callable[[dict], bool]):
        """监听游戏数据包（通过 ToolDelta ListenPacket 桥接）。

        Args:
            packet_id: Bedrock 数据包 ID（如 PlayerAuthInput=144）。
            handler: 回调函数，签名 def handler(packet: dict) -> bool。
                     返回 True 拦截该包，False 继续传递。
        """
        if self.adapter and hasattr(self.adapter, 'listen_dict_packet'):
            self.adapter.listen_dict_packet(packet_id, handler)
            self._event_handlers.append(('_packet', packet_id, handler))
        else:
            self.logger.warning(
                "模块 '%s' 尝试监听数据包 %d，但适配器不支持",
                self.name, packet_id,
            )


# ═══════════════════════════════════════════════════════════════
# 魔法属性代理 — 让模块开发者用 self.game.say(...) 等直觉 API
# ═══════════════════════════════════════════════════════════════

class _ConfigProxy:
    """配置代理: self.config.键 自动调用 config.get("键")。

    Fix: 传入 caller_mid 防止越权 — 任何 mid≥300 的模块
    只能以其自身身份读写配置，不能以 mid=0 绕过权限。
    """

    __slots__ = ("_cfg", "_caller_mid")

    def __init__(self, config_svc, caller_mid=400):
        self._cfg = config_svc
        self._caller_mid = caller_mid

    def __getattr__(self, key: str):
        if key.startswith("_"):
            raise AttributeError(key)
        return self._cfg.get(key, requester_uid=self._caller_mid)

    def get(self, key: str, default=None):
        """获取配置值。"""
        return self._cfg.get(key, default, requester_uid=self._caller_mid)

    def set(self, key: str, value):
        """设置配置值。"""
        return self._cfg.set(key, value, requester_uid=self._caller_mid)

    def save(self):
        """保存配置。"""
        return self._cfg.save()

    def register_section(self, section: str, defaults: dict):
        """Fix M2: 传入 caller_mid 阻止低权限模块注册高权限配置节。"""
        return self._cfg.register_section(section, defaults, caller_uid=self._caller_mid)

    def get_data_dir(self):
        """获取数据目录路径。"""
        return self._cfg.get_data_dir()


class _GroupConfigProxy:
    """群配置代理: self.group_config.get(group_id, key) / .for_group(group_id).

    传入 caller_mid 防止越权。
    """

    __slots__ = ("_gcfg", "_caller_mid")

    def __init__(self, group_config_svc, caller_mid=400):
        self._gcfg = group_config_svc
        self._caller_mid = caller_mid

    def __getattr__(self, key: str):
        """代理底层 GroupConfigManager 的属性（如 repair_dir）。"""
        if key.startswith("_"):
            raise AttributeError(key)
        return getattr(self._gcfg, key)

    def get(self, group_id: int, key: str, default=None):
        """获取指定群的配置值。"""
        return self._gcfg.get(group_id, key, default, requester_uid=self._caller_mid)

    def for_group(self, group_id: int) -> "_SingleGroupConfigProxy":
        """返回单群配置代理，方便链式调用。"""
        return _SingleGroupConfigProxy(self._gcfg, group_id, caller_mid=self._caller_mid)

    def get_module_config(self, group_id: int, section: str) -> dict:
        """获取指定群的模块节配置。"""
        return self._gcfg.get_group_module_config(group_id, section, requester_uid=self._caller_mid)


class _SingleGroupConfigProxy:
    """单群配置代理。"""

    __slots__ = ("_gcfg", "_group_id", "_caller_mid")

    def __init__(self, gcfg, group_id: int, caller_mid=400):
        self._gcfg = gcfg
        self._group_id = group_id
        self._caller_mid = caller_mid

    def get(self, key: str, default=None):
        """获取单群配置值。"""
        return self._gcfg.get(self._group_id, key, default, requester_uid=self._caller_mid)


class _GameProxy:
    """游戏操作代理: self.game.say/send/cmd/players。

    Fix: cmd() 强制 mid 检查 — mid≤100 (daemon+) 放行，
    mid>100 检查是否在 "游戏管理.允许执行命令的模块" 白名单中。
    """

    __slots__ = ("_adapter", "_caller_mid", "_config")

    def __init__(self, adapter, caller_mid=400, config=None):
        self._adapter = adapter
        self._caller_mid = caller_mid
        self._config = config

    def _check_cmd_permission(self) -> bool:
        """检查当前调用者是否有权限执行游戏命令。

        Returns:
            True 表示允许执行。
        """
        if self._caller_mid <= 100:
            return True  # daemon+ 放行
        if not self._config:
            return False
        whitelist = self._config.get("游戏管理.允许执行命令的模块", [])
        if not isinstance(whitelist, list):
            whitelist = []
        # 白名单为空则只有框架内置模块可执行
        if not whitelist:
            return False
        # 当前模块名需在白名单中
        import inspect
        # 尝试从调用栈获取模块名
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            mod = frame_locals.get('self')
            if mod is not None and hasattr(mod, 'name') and hasattr(mod, 'mid'):
                if mod.mid == self._caller_mid:
                    return mod.name in whitelist
        return False

    def say(self, target: str, text: str):
        """向游戏内目标发送消息。"""
        if self._adapter:
            self._adapter.send_game_message(target, text)

    def cmd(self, command: str):
        """发送游戏指令（需 mid 白名单检查）。"""
        if not self._check_cmd_permission():
            logging.getLogger(__name__).warning(
                "游戏命令拒绝: mid=%d 不在白名单中 (cmd=%s)",
                self._caller_mid, command[:80],
            )
            return
        if self._adapter:
            self._adapter.send_game_command(command)

    def title(self, target: str, text: str):
        """显示标题栏消息。"""
        if self._adapter:
            self._adapter.send_game_title(target, text)

    def subtitle(self, target: str, text: str):
        """显示副标题消息。"""
        if self._adapter:
            self._adapter.send_game_subtitle(target, text)

    def actionbar(self, target: str, text: str):
        """显示行动栏消息。"""
        if self._adapter:
            self._adapter.send_game_actionbar(target, text)

    @property
    def players(self) -> list:
        """在线玩家列表。"""
        return self._adapter.get_online_players() if self._adapter else []

    def cmd_with_resp(self, cmd: str, timeout: float = 5.0):
        """发送指令并等响应。"""
        if self._adapter:
            return self._adapter.send_game_command_with_resp(cmd, timeout)
        return None


class _QQProxy:
    """QQ 操作代理: self.qq.send_group(gid, text) / self.qq.send_private(uid, text)。

    Fix: 移除 fallback 到 adapter 的路径，该路径绕过 MessageManager 的
    限流和审计。消息发送只走 message 服务（内建 guardian 检查）。
    传入 caller_mid 用于审计追踪。
    """

    __slots__ = ("_adapter", "_services", "_caller_mid")

    def __init__(self, adapter, services=None, caller_mid=400):
        self._adapter = adapter
        self._services = services
        self._caller_mid = caller_mid

    @property
    def _msg(self):
        """动态获取 message 服务（避免构造时捕获 None）。"""
        if self._services:
            try:
                return self._services.get("message")
            except (KeyError, PermissionError):
                return None
        return None

    async def send_group(self, group_id: int, text: str):
        """发送群消息（仅通过 MessageManager，绕过即拒绝）。

        message 服务内部已包含 guardian 限流和审计追踪。
        """
        if self._msg:
            await self._msg.send_group(group_id, text, requester_uid=self._caller_mid)
        else:
            logging.getLogger(__name__).error(
                "QQ代理: message 服务不可用，消息发送被拒绝 (group_id=%s, mid=%d)",
                group_id, self._caller_mid,
            )

    async def send_private(self, user_id: int, text: str):
        """发送私聊消息（仅通过 MessageManager，绕过即拒绝）。

        message 服务内部已包含 guardian 限流和审计追踪。
        """
        if self._msg:
            await self._msg.send_private(user_id, text, requester_uid=self._caller_mid)
        else:
            logging.getLogger(__name__).error(
                "QQ代理: message 服务不可用，消息发送被拒绝 (user_id=%s, mid=%d)",
                user_id, self._caller_mid,
            )

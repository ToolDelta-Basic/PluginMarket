"""模块基类 — 约定优于配置 (v1.2)

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
import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .services import ServiceContainer
from .bus import EventBus


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
        """持久化当前数据到磁盘。"""
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

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

    def start(self) -> asyncio.Task:
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
        self._task = asyncio.create_task(_runner())
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
        logging.getLogger(__name__).exception("定时任务异常")


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


# ── 模块基类 ─────────────────────────────────────────────────

class Module(ABC):
    """所有业务模块的抽象基类。

    声明式约定属性（全部可选，框架自动处理）:
        config_schema: Tuple[str, Any] 映射 → 自动注入 self.cfg_<name>
        tools: List[dict] → 自动注册到 ToolManager
        scheduled: List[ScheduledTask] → 自动启动/停止
        hot_reload_state: Dict[str, Any] → 自动持久化
    """

    # ── 必须声明 ──
    name: str = ""

    # ── 可选覆写 ──
    version: tuple = (0, 0, 1)
    dependencies: list[str] = []
    required_services: list[str] = []
    default_config: Dict[str, Dict[str, Any]] = {}
    config_schema: Dict[str, Tuple[str, Any]] = {}
    exports: Dict[str, Any] = {}
    tools: List[Dict[str, Any]] = []
    scheduled: List[ScheduledTask] = []
    hot_reload_state: Dict[str, Any] = {}
    db_collections: List[str] = []
    enabled: bool = True
    default_cooldown: float = 0.0

    # ── 框架内部 ──
    _conventions_applied: bool = False
    _scheduled_tasks: List[ScheduledTask] = []
    _hot_state: HotReloadState | None = None

    def __init__(self, services: ServiceContainer, event_bus: EventBus):
        self.services = services
        self.event_bus = event_bus
        self._commands: dict = {}
        self._event_handlers: list = []
        self._tool_defs: list = []

        # ── 服务注入 ──
        for srv_name in self.required_services:
            if not services.has(srv_name):
                raise RuntimeError(
                    f"模块 '{self.name}' 需要服务 '{srv_name}'，但未注册"
                )
            setattr(self, srv_name, services.get(srv_name))

        # ── 便利属性 ──
        self.logger = logging.getLogger(
            f"{__name__.rsplit('.', 1)[0]}.{self.name}" or __name__
        )
        self._data_dir: str | None = None
        self.db: JsonDatabase | None = None

    # ── 属性 ──

    @property
    def data_dir(self) -> str:
        if self._data_dir is None:
            cfg_svc = self.services.get("config")
            base = cfg_svc.get_data_dir()
            path = os.path.join(base, "模块", self.name)
            os.makedirs(path, exist_ok=True)
            self._data_dir = path
        return self._data_dir

    # ── 约定执行 ──

    def _apply_conventions(self) -> None:
        """执行全部约定（ModuleManager 在 on_init / on_start 前调用）。"""
        if self._conventions_applied:
            return
        self._conventions_applied = True

        cfg_svc = None
        try:
            cfg_svc = self.services.get("config")
        except KeyError:
            pass

        # ── A: default_config → register_section ──
        if cfg_svc and self.default_config:
            for section, defaults in self.default_config.items():
                cfg_svc.register_section(section, defaults)

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
            db_dir = os.path.join(self.data_dir, "db")
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

    async def _post_init_conventions(self) -> None:
        """on_init 之后执行的约定（依赖 on_init 中创建的资源）。"""
        # ── G: tools → ToolManager ──
        tool_mgr = None
        try:
            tool_mgr = self.services.get("tool")
        except KeyError:
            pass
        if tool_mgr and self.tools:
            for tool_def in self.tools:
                tool_mgr.register_tool(tool_def)
                self.logger.debug("工具已注册: %s", tool_def.get("name"))

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

    # ── 生命周期 ──

    @abstractmethod
    async def on_init(self):
        """模块初始化。框架已处理: 服务注入 · 配置注册 · 装饰器扫描 · DB初始化。"""

    async def on_start(self):
        """模块启动时额外逻辑。框架在 on_init 后执行 _post_init_conventions。"""

    async def on_stop(self):
        """模块停止时清理。框架自动停止定时任务。"""
        await self._cleanup_conventions()

    # ── 声明式 API ──

    def register_command(
        self,
        trigger: str,
        callback: Callable,
        *,
        cmd_type: str = "group",
        description: str = "",
        op_only: bool = False,
        argument_hint: str = "",
        cooldown: float | None = None,
    ):
        """注册一个命令处理器。"""
        if cooldown is None:
            cooldown = self.default_cooldown
        self._commands[trigger] = {
            "trigger": trigger,
            "cmd_type": cmd_type,
            "callback": callback,
            "description": description,
            "op_only": op_only,
            "argument_hint": argument_hint,
            "cooldown": cooldown,
        }

    def listen(self, event_type: str, handler: Callable, priority: int = 0):
        """订阅事件并记录到事件处理器列表。"""
        self.event_bus.subscribe(event_type, handler, priority)
        self._event_handlers.append((event_type, handler, priority))

    def register_tool(self, tool_definition: dict):
        """编程式注册工具定义。"""
        self._tool_defs.append(tool_definition)

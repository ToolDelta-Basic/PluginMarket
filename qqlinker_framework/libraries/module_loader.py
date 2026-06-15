"""模块加载库 — 信道化重写。

职责：
- 定义 Module 业务模块基类（零旧代码依赖）
- 从 modules/ 目录扫描并发现 Module 子类
- 通过 JSON 注册表管理模块启用/禁用
- 初始化启用的模块并注入信道引用
"""
import importlib.util
import inspect
import json
import logging
import os
import threading
from typing import List, Optional, Type

from ..core.channel import Library

_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Module 基类
# ═══════════════════════════════════════════════════════════

class Module:
    """业务模块基类（信道版）。

    模块生命周期:
      1. 发现: 扫描 modules/ 目录找到 Module 子类
      2. 实例化: 创建实例并注入 services/events/config/messages/commands
      3. on_init(): 模块注册命令、事件等
      4. 运行
      5. on_stop(): 模块清理资源

    属性:
        name: 唯一模块名称（必填）
        version: 模块版本号
        dependencies: 依赖的库名列表
    """

    name: str = ""
    version: str = "1.0.0"
    dependencies: list = []

    def __init__(self):
        self.services: Optional[object] = None
        self.events: Optional[object] = None
        self.config: Optional[object] = None
        self.messages: Optional[object] = None
        self.commands: Optional[object] = None

    async def on_init(self):
        """模块初始化回调。在此注册命令、订阅事件等。"""

    async def on_stop(self):
        """模块卸载回调。在此清理资源、取消订阅等。"""

    def __repr__(self):
        return f"<Module:{self.name}>"


# ═══════════════════════════════════════════════════════════
# 模块注册表
# ═══════════════════════════════════════════════════════════

class _ModuleRegistry:
    """基于 JSON 文件的模块启用状态注册表。

    存储位置: data_path/注册表/模块注册表.json

    结构:
        {"模块注册表": {"module_name": {"启用": true/false, "首次发现": "auto"}}}
    """

    def __init__(self, data_path: str):
        self._path = os.path.join(data_path, "注册表", "模块注册表.json")
        self._lock = threading.Lock()
        self._entries: dict = {}
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._load()

    def _load(self):
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._entries = json.load(f).get("模块注册表", {})
            except Exception:
                _log.warning("模块注册表损坏，已重置", exc_info=True)
                self._entries = {}

    def is_enabled(self, name: str) -> bool:
        """检查模块是否启用。未注册的模块默认启用。"""
        return self._entries.get(name, {}).get("启用", True)

    def auto_register(self, names: list):
        """自动注册新发现的模块（不存在的条目追加）。"""
        changed = False
        for n in names:
            if n not in self._entries:
                self._entries[n] = {"启用": True, "首次发现": "auto"}
                changed = True
        if changed:
            self._save()

    def set_enabled(self, name: str, enabled: bool):
        """手动设置模块启用状态。"""
        entry = self._entries.get(name)
        if entry is None:
            self._entries[name] = {"启用": enabled, "首次发现": "manual"}
        else:
            entry["启用"] = enabled
        self._save()

    def _save(self):
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"模块注册表": self._entries},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            os.replace(tmp, self._path)
        except OSError:
            _log.warning("保存模块注册表失败", exc_info=True)

    def list_modules(self) -> dict:
        """返回模块注册表副本。"""
        return dict(self._entries)


# ═══════════════════════════════════════════════════════════
# 模块加载库
# ═══════════════════════════════════════════════════════════

class ModuleLoaderLibrary(Library):
    """模块加载库 — 发现并初始化业务模块。

    依赖:
        - core: 框架核心
        - message_bus: 命令注册（模块通过 self.commands 使用）
    """

    name = "module_loader"
    version = "1.0.0"
    dependencies = ["core", "message_bus"]

    async def mount(self) -> None:
        data_path = getattr(self, "_data_path", ".")

        # 创建注册表
        registry = _ModuleRegistry(data_path)
        self.services.register("module_registry", registry)

        modules_dir = os.path.join(data_path, "modules")
        if not os.path.isdir(modules_dir):
            _log.info("modules/ 目录不存在 (%s)，跳过模块加载", modules_dir)
            return

        # 发现模块
        discovered = self._discover(modules_dir)
        _log.info("发现 %d 个模块: %s", len(discovered), [m.name for m in discovered])

        # 自动注册新模块
        registry.auto_register([m.name for m in discovered if m.name])

        # 加载启用的模块
        for mod_cls in discovered:
            name = mod_cls.name
            if not name:
                _log.warning("模块类 %s 缺少 name，跳过", mod_cls)
                continue

            if not registry.is_enabled(name):
                _log.info("模块 %s 已禁用，跳过", name)
                continue

            try:
                instance = mod_cls()
                # 注入信道引用
                instance.services = self.services
                instance.events = self.events
                instance.config = self.config
                instance.messages = self.messages
                instance.commands = self.commands

                await instance.on_init()
                _log.info("模块加载成功: %s v%s", name, mod_cls.version)
            except Exception:
                _log.error("模块 %s 初始化失败", name, exc_info=True)

    async def unmount(self) -> None:
        pass

    # ---- 发现 ----

    def _discover(self, modules_dir: str) -> List[Type[Module]]:
        """扫描 modules/ 目录，找到所有 Module 子类。"""
        result: List[Type[Module]] = []

        try:
            for entry in os.listdir(modules_dir):
                full = os.path.join(modules_dir, entry)
                if os.path.isdir(full):
                    self._scan_directory(full, result)
                elif entry.endswith(".py") and not entry.startswith("_"):
                    self._scan_file(full, result)
        except OSError:
            _log.warning("列出模块目录失败: %s", modules_dir, exc_info=True)

        return result

    def _scan_file(self, filepath: str, result: List[Type[Module]]):
        """动态导入单个 .py 文件并收集 Module 子类。"""
        try:
            name = os.path.splitext(os.path.basename(filepath))[0]
            spec = importlib.util.spec_from_file_location(
                f"qqlinker.module.{name}", filepath
            )
            if spec is None or spec.loader is None:
                return

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            for _attr_name, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, Module) and obj is not Module and obj.name:
                    result.append(obj)
        except Exception:
            _log.debug("扫描文件失败: %s", filepath, exc_info=True)

    def _scan_directory(self, dirpath: str, result: List[Type[Module]]):
        """扫描子目录下的 .py 文件。"""
        try:
            for entry in os.listdir(dirpath):
                if entry.endswith(".py") and not entry.startswith("_"):
                    self._scan_file(os.path.join(dirpath, entry), result)
        except OSError:
            _log.debug("扫描目录失败: %s", dirpath, exc_info=True)

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Set, Optional

_log = logging.getLogger(__name__)

REGISTRY_FILENAME = "模块注册表.json"
REGISTRY_DIR = "注册表"


class ModuleRegistry:
    """模块注册表：线程安全的模块启用状态管理器。

    允则逻辑：
      - 注册表中标记"启用": true 的模块 → 允许加载
      - 注册表中标记"启用": false 或不在注册表中的模块 → 拒绝加载
      - 扫描到新模块时自动注册并默认启用（auto_register）
    """

    def __init__(self, data_path: str):
        self._data_path = data_path
        self._file_path = os.path.join(data_path, REGISTRY_DIR, REGISTRY_FILENAME)
        self._lock = threading.Lock()
        self._entries: Dict[str, dict] = {}
        self._load()

    # ═══════════════════════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════════════════════

    def _load(self) -> None:
        """从磁盘加载注册表。"""
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data.get("模块注册表", {})
                if not isinstance(self._entries, dict):
                    self._entries = {}
                _log.info(
                    "注册表已加载: %d 个条目 (%d 启用)",
                    len(self._entries),
                    sum(1 for e in self._entries.values() if e.get("启用", False)),
                )
            except (json.JSONDecodeError, IOError) as e:
                _log.warning("注册表加载失败，使用空注册表: %s", e)
                self._entries = {}
        else:
            _log.info("注册表文件不存在，创建空注册表")
            self._entries = {}
            self._save()

    def _save(self) -> None:
        """持久化注册表到磁盘（原子写入：先写临时文件再 rename）。"""
        try:
            tmp_path = self._file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"模块注册表": self._entries},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            os.replace(tmp_path, self._file_path)
        except OSError as e:
            _log.error("注册表保存失败: %s", e)

    # ═══════════════════════════════════════════════════════════
    # 查询 API
    # ═══════════════════════════════════════════════════════════

    def is_enabled(self, module_name: str) -> bool:
        """检查模块是否启用。不在注册表中的模块视为禁用。"""
        with self._lock:
            entry = self._entries.get(module_name)
            if entry is None:
                return False
            return entry.get("启用", False)

    def reload(self) -> bool:
        """从磁盘重新加载注册表（用于热重载场景）。

        Returns:
            True 如果注册表有变化。
        """
        old_entries = dict(self._entries)
        self._load()
        return old_entries != self._entries

    def get_all_enabled(self) -> Set[str]:
        """返回所有已启用模块名集合。"""
        with self._lock:
            return {
                name
                for name, entry in self._entries.items()
                if entry.get("启用", False)
            }

    def get_all_entries(self) -> Dict[str, dict]:
        """返回注册表完整快照（用于调试/面板展示）。"""
        with self._lock:
            return dict(self._entries)

    def get_entry(self, module_name: str) -> Optional[dict]:
        """获取单个模块的注册表条目。"""
        with self._lock:
            return self._entries.get(module_name)

    # ═══════════════════════════════════════════════════════════
    # 修改 API
    # ═══════════════════════════════════════════════════════════

    def set_enabled(self, module_name: str, enabled: bool) -> bool:
        """设置模块启用状态（持久化）。

        Returns:
            True 表示状态已变更并保存。
        """
        with self._lock:
            entry = self._entries.get(module_name)
            if entry is None:
                _log.warning(
                    "模块 '%s' 不在注册表中，拒绝设置启用状态", module_name
                )
                return False
            old = entry.get("启用", False)
            if old == enabled:
                return False  # 无变化
            entry["启用"] = enabled
            self._save()
            _log.info(
                "注册表: 模块 '%s' 启用状态 %s → %s",
                module_name, old, enabled,
            )
            return True

    def auto_register(self, module_names: list) -> Set[str]:
        """自动注册新发现的模块（默认启用）。

        对于已在注册表中的模块不做任何更改。
        返回本次新注册的模块名集合。
        """
        new_modules: Set[str] = set()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            for name in module_names:
                if name not in self._entries:
                    self._entries[name] = {
                        "启用": True,
                        "首次发现": now,
                    }
                    new_modules.add(name)
            if new_modules:
                self._save()
                _log.info(
                    "注册表: 自动注册 %d 个新模块: %s",
                    len(new_modules), ", ".join(sorted(new_modules)),
                )
        return new_modules

    def remove_entry(self, module_name: str) -> bool:
        """从注册表删除模块条目。"""
        with self._lock:
            if module_name not in self._entries:
                return False
            del self._entries[module_name]
            self._save()
            _log.info("注册表: 模块 '%s' 已删除", module_name)
            return True

    # ═══════════════════════════════════════════════════════════
    # 统计
    # ═══════════════════════════════════════════════════════════

    def stats(self) -> dict:
        """返回注册表统计信息。"""
        with self._lock:
            total = len(self._entries)
            enabled = sum(1 for e in self._entries.values() if e.get("启用", False))
            return {
                "总模块数": total,
                "已启用": enabled,
                "已禁用": total - enabled,
            }


# ═══════════════════════════════════════════════════════════
# ServiceRegistry — 宿主服务注册表
# ═══════════════════════════════════════════════════════════

SERVICE_REGISTRY_FILENAME = "服务注册表.json"


class ServiceRegistry:
    """宿主服务注册表：线程安全的服务注册允则控制。

    允则逻辑：
      - 注册表中标记"启用": true 的服务 → 允许注册
      - 注册表中标记"启用": false 或不在注册表中 → 拒绝注册
      - 内核级服务（mid ≤ TIER_KERNEL）始终免检
    """

    def __init__(self, data_path: str):
        self._data_path = data_path
        self._file_path = os.path.join(data_path, REGISTRY_DIR, SERVICE_REGISTRY_FILENAME)
        self._lock = threading.Lock()
        self._entries: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data.get("服务注册表", {})
                if not isinstance(self._entries, dict):
                    self._entries = {}
            except (json.JSONDecodeError, IOError) as e:
                _log.warning("服务注册表加载失败: %s", e)
                self._entries = {}
        else:
            self._entries = {}
            self._save()

    def _save(self) -> None:
        try:
            tmp_path = self._file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"服务注册表": self._entries},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            os.replace(tmp_path, self._file_path)
        except OSError as e:
            _log.error("服务注册表保存失败: %s", e)

    def is_allowed(self, service_name: str, mid: int = 0) -> bool:
        """检查服务是否允许注册。

        规则：
          1. 内核级（mid ≤ 0）始终免检
          2. 注册表中存在且启用 → 允许
          3. 注册表为空（首次启动）→ 允许注册并自动签署
          4. 不在注册表中或禁用 → 拒绝
        """
        if mid <= 0:
            return True
        with self._lock:
            # 注册表为空 → 首次启动兜底
            if not self._entries:
                return True
            entry = self._entries.get(service_name)
            return entry is not None and entry.get("启用", False)

    def auto_sign(self, service_name: str) -> bool:
        """首次发现新服务时自动签署为启用。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if service_name in self._entries:
                return True  # 已存在，不重复签署
            self._entries[service_name] = {
                "启用": True,
                "首次签署": now,
            }
            self._save()
            _log.info("服务注册表: 新服务 '%s' 已签署启用", service_name)
            return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                return False
            if entry.get("启用") == enabled:
                return False
            entry["启用"] = enabled
            self._save()
            return True

    def get_all_entries(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._entries)

    def stats(self) -> dict:
        with self._lock:
            total = len(self._entries)
            enabled = sum(1 for e in self._entries.values() if e.get("启用"))
            return {"总服务数": total, "已启用": enabled, "已禁用": total - enabled}


# ═══════════════════════════════════════════════════════════
# ConventionRegistry — 约定注册表
# ═══════════════════════════════════════════════════════════

CONVENTION_REGISTRY_FILENAME = "约定注册表.json"

# 框架内置约定列表
_BUILTIN_CONVENTIONS = {
    "演示模式": "DemoModule — .演示 命令，硬编码交互演示",
    "规则引擎": "RuleEngineModule — 用户自定义消息匹配+动作链",
    "模板引擎": "TemplateModule — .模板 命令，配置模板切换",
    "内存守护": "MemoryGuard — RSS 监控+智能重启",
    "配置检查": "ConfigRouter — 启动时配置完整性校验",
    "CMD会话": "KernelCMDsModule — .cmd 管理控制台",
    "群级人设": "GroupPersonaModule — 不同群独立人设",
    "Web面板": "PanelModule — HTTP 管理面板",
    "调试引擎": "DebugEngine — 消息/API 记录调试",
}


class ConventionRegistry:
    """约定注册表：控制哪些框架约定（系统功能）被启用。

    与模块/服务注册表的区别：约定是框架级的功能开关，
    不直接对应一个 .py 文件，而是控制某个子系统的启用与否。

    允则逻辑：
      - 注册表中启用 → 允许加载
      - 注册表中禁用 → 跳过
      - 新约定默认启用并自动签署
    """

    def __init__(self, data_path: str):
        self._data_path = data_path
        self._file_path = os.path.join(data_path, REGISTRY_DIR,
                                       CONVENTION_REGISTRY_FILENAME)
        self._lock = threading.Lock()
        self._entries: Dict[str, dict] = {}
        self._load()
        self._auto_sign_builtins()

    def _load(self) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data.get("约定注册表", {})
                if not isinstance(self._entries, dict):
                    self._entries = {}
            except (json.JSONDecodeError, IOError) as e:
                _log.warning("约定注册表加载失败: %s", e)
                self._entries = {}
        else:
            self._entries = {}

    def _save(self) -> None:
        try:
            tmp_path = self._file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({"约定注册表": self._entries}, f,
                          ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._file_path)
        except OSError as e:
            _log.error("约定注册表保存失败: %s", e)

    def _auto_sign_builtins(self) -> None:
        """新内置约定自动签署启用。"""
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        with self._lock:
            for name in _BUILTIN_CONVENTIONS:
                if name not in self._entries:
                    self._entries[name] = {
                        "启用": True,
                        "描述": _BUILTIN_CONVENTIONS[name],
                        "首次签署": now,
                    }
                    changed = True
        if changed:
            self._save()
            _log.info("约定注册表: 签署 %d 个新内置约定",
                      sum(1 for n in _BUILTIN_CONVENTIONS
                          if n not in self._entries if changed))

    def is_enabled(self, name: str) -> bool:
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                return True  # 未注册的约定默认启用
            return entry.get("启用", False)

    def set_enabled(self, name: str, enabled: bool) -> bool:
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                return False
            if entry.get("启用") == enabled:
                return False
            entry["启用"] = enabled
            self._save()
            return True

    def get_all_entries(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._entries)

    def stats(self) -> dict:
        with self._lock:
            total = len(self._entries)
            enabled = sum(1 for e in self._entries.values() if e.get("启用"))
            return {"总约定数": total, "已启用": enabled, "已禁用": total - enabled}

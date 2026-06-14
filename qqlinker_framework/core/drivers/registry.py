"""模块注册表 — 线程安全的模块启用/禁用状态持久化

═══════════════════════════════════════════════════════════════════════════
 设计
═══════════════════════════════════════════════════════════════════════════
 · 注册表是模块加载的唯一权威来源 — 只有注册表中明确标记"启用"的模块才运行
 · 允则（allowlist）逻辑：新发现的模块默认写入注册表并自动启用
 · 线程安全：所有读写操作内部加锁，主线程和子线程均可安全访问
 · 持久化：JSON 文件，变化时立即写入磁盘

 JSON 结构:
 {
   "模块注册表": {
     "acg_image": {"启用": true, "首次发现": "2026-06-10T07:00:00"},
     "help":      {"启用": true, "首次发现": "2026-06-03T00:00:00"},
     "forwarder": {"启用": false, "首次发现": "2026-06-10T08:00:00"}
   }
 }

 使用:
   reg = ModuleRegistry(data_path)
   reg.is_enabled("acg_image")     → True
   reg.set_enabled("forwarder", False)  → 持久化写入
   reg.auto_register(["acg_image", "new_mod"])  → 新模块默认启用
   reg.get_all_enabled()           → {"acg_image", "help"}
═══════════════════════════════════════════════════════════════════════════
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Set, Optional

_log = logging.getLogger(__name__)

REGISTRY_FILENAME = "模块注册表.json"


class ModuleRegistry:
    """模块注册表：线程安全的模块启用状态管理器。

    允则逻辑：
      - 注册表中标记"启用": true 的模块 → 允许加载
      - 注册表中标记"启用": false 或不在注册表中的模块 → 拒绝加载
      - 扫描到新模块时自动注册并默认启用（auto_register）
    """

    def __init__(self, data_path: str):
        self._data_path = data_path
        self._file_path = os.path.join(data_path, "数据", REGISTRY_FILENAME)
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

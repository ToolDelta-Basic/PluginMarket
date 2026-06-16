"""模块组注册表 — 控制哪些模块组允许加载。

持久化文件：注册表/模块组.json

结构：
{
  "模块组": {
    "system": {"启用": true, "保护": true, "描述": "系统功能模块组"},
    "security": {"启用": true, "保护": true, "描述": "安全反制模块组"},
    "ai": {"启用": true, "保护": false, "描述": "AI 智能核心模块组"},
    "game": {"启用": true, "保护": false, "描述": "游戏互通模块组"},
    "logging": {"启用": true, "保护": false, "描述": "日志记录模块组"}
  }
}

保护机制：
  - "保护": true 的组不可被用户禁用或卸载
  - system 和 security 组始终受保护
  - 首次发现新组自动签署启用
"""
import json
import logging
import os
import threading
from typing import Dict, Optional, Set

_log = logging.getLogger(__name__)

REGISTRY_DIR = "注册表"
GROUP_REGISTRY_FILENAME = "模块组.json"

# 安全基线：这些组始终受保护，不可被用户禁用
PROTECTED_GROUPS = frozenset({"system", "security"})


class ModuleGroupRegistry:
    """模块组注册表：控制组的启用/禁用，保护关键组。"""

    def __init__(self, data_path: str):
        self._file_path = os.path.join(data_path, REGISTRY_DIR,
                                       GROUP_REGISTRY_FILENAME)
        self._lock = threading.Lock()
        self._entries: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        if os.path.isfile(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data.get("模块组", {})
                if not isinstance(self._entries, dict):
                    self._entries = {}
            except (json.JSONDecodeError, IOError) as e:
                _log.warning("模块组注册表加载失败: %s", e)
                self._entries = {}
        else:
            self._entries = {}
            self._save()

    def _save(self) -> None:
        try:
            tmp = self._file_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"模块组": self._entries}, f,
                          ensure_ascii=False, indent=2)
            os.replace(tmp, self._file_path)
        except OSError as e:
            _log.error("模块组注册表保存失败: %s", e)

    # ── 查询 API ──

    def is_enabled(self, group_name: str) -> bool:
        """检查组是否启用。未注册的组默认启用（首次发现兜底）。"""
        with self._lock:
            entry = self._entries.get(group_name)
            if entry is None:
                return True  # 未注册 → 默认启用
            return entry.get("启用", True)

    def is_protected(self, group_name: str) -> bool:
        """检查组是否受保护（不可被用户禁用/卸载）。"""
        if group_name in PROTECTED_GROUPS:
            return True
        with self._lock:
            entry = self._entries.get(group_name)
            return entry.get("保护", False) if entry else False

    def get_entry(self, group_name: str) -> Optional[dict]:
        with self._lock:
            return self._entries.get(group_name)

    def get_all_entries(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._entries)

    def get_all_enabled(self) -> Set[str]:
        with self._lock:
            return {
                name for name, entry in self._entries.items()
                if entry.get("启用", True)
            }

    # ── 修改 API ──

    def set_enabled(self, group_name: str, enabled: bool) -> bool:
        """设置组启用状态。受保护的组不可被禁用。"""
        if not enabled and self.is_protected(group_name):
            _log.warning("拒绝禁用受保护组: %s", group_name)
            return False
        with self._lock:
            entry = self._entries.get(group_name)
            if entry is None:
                return False
            if entry.get("启用") == enabled:
                return False
            entry["启用"] = enabled
            self._save()
            _log.info("模块组 '%s' 启用状态 → %s", group_name, enabled)
            return True

    def auto_register(self, groups: Dict[str, dict]) -> Set[str]:
        """自动注册新发现的组（默认启用）。

        Args:
            groups: {组名: {"mid": int, "description": str}}

        Returns:
            本次新注册的组名集合。
        """
        new_groups: Set[str] = set()
        with self._lock:
            for name, info in groups.items():
                if name not in self._entries:
                    self._entries[name] = {
                        "启用": True,
                        "保护": name in PROTECTED_GROUPS,
                        "mid": info.get("mid", 300),
                        "描述": info.get("description", ""),
                    }
                    new_groups.add(name)
                else:
                    # 确保保护标记
                    if name in PROTECTED_GROUPS:
                        self._entries[name]["保护"] = True
            if new_groups:
                self._save()
                _log.info("模块组注册表: 新注册 %d 个组: %s",
                          len(new_groups), ", ".join(sorted(new_groups)))
        return new_groups

    def stats(self) -> dict:
        with self._lock:
            total = len(self._entries)
            enabled = sum(1 for e in self._entries.values()
                          if e.get("启用", True))
            protected = sum(1 for e in self._entries.values()
                            if e.get("保护", False))
            return {
                "总组数": total,
                "已启用": enabled,
                "已禁用": total - enabled,
                "受保护": protected,
            }

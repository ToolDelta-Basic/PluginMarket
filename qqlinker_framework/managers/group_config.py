"""群聊子配置管理器 — 继承模型 + 类型校验 + 字段自动传播 + 文件热重载 + v6 多文件分化

═══════════════════════════════════════════════════════════════════════════
 设计
═══════════════════════════════════════════════════════════════════════════
 · 主配置 config.json                             → 默认值 + 参考模板
 · 群子配置 data/groups/<群号>/<section>.json     → 每模块节独立文件
 · 加载优先级: 子配置 > 主配置（deep merge）
 · 新群首次触发: 从主配置 copy 到子配置目录
 · 主配置变更: 不影响已存在的子配置（propagate_new_fields 手动传播）
 · 模块新增字段: 自动追加到所有群子配置
 · 类型校验失败: 备份原配置 → fallback 主配置该群 → 终端报告
 · 多文件分化 (v6): 每群每模块节独立文件，避免单文件过大 + 并行 I/O
═══════════════════════════════════════════════════════════════════════════
"""
import hashlib
import hmac
import json
import logging
import os
import shutil
import threading
import time

from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Optional

from qqlinker_framework.core.kernel.error_hints import hint
from .config_mgr import ConfigManager

_log = logging.getLogger(__name__)

# 模块 config_schema 中 scope 键名
SCOPE_GLOBAL = "global"
SCOPE_GROUP = "group"

# v6: 多文件分化 — 是否启用 per-section 文件模式
# True:  data/groups/<群号>/<section>.json（推荐，可并行 I/O）
# False: data/groups/<群号>/config.json（旧版单文件兼容）
MULTI_FILE_MODE = True


class GroupConfigManager:
    """管理群聊子配置的加载、合并、类型校验和字段传播。

    v6 新增：多文件分化模式，每模块节独立 JSON 文件。
    """

    def __init__(self, config_mgr, data_dir: str):
        """初始化群配置管理器。

        Args:
            config_mgr: 主 ConfigManager 实例（持有主配置）。
            data_dir: 框架数据根目录（如 "./"）。
        """
        self._main_cfg = config_mgr
        self._groups_dir = os.path.join(data_dir, "数据", "群组")
        self._repair_dir = os.path.join(data_dir, "数据", "修复备份")
        os.makedirs(self._groups_dir, exist_ok=True)
        os.makedirs(self._repair_dir, exist_ok=True)

        # 内存缓存: group_id → merged_config_dict (LRU 淘汰, 默认 200)
        self._cache: dict[int, dict] = {}
        self._cache_order: list[int] = []
        self._cache_max: int = 200
        self._cache_lock = threading.Lock()

        # 文件 mtime 追踪（用于热重载）
        self._mtime_cache: dict[str, float] = {}

        # 模块声明的 schema（scope → {section: defaults}）
        self._global_schemas: dict[str, dict] = {}   # 仅在主配置
        self._group_schemas: dict[str, dict] = {}     # 允许追加到子配置

        # 热重载
        self._on_reload_callback: Optional[Callable] = None
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_stop: Optional[threading.Event] = None

    @property
    def repair_dir(self) -> str:
        """公开的修复备份目录路径。"""
        return self._repair_dir

    @property
    def multi_file_mode(self) -> bool:  # noqa: PYL-R0201
        """是否启用多文件分化模式。"""
        return MULTI_FILE_MODE

    # ═══════════════════════════════════════════════════════════
    # Schema 注册
    # ═══════════════════════════════════════════════════════════

    def register_module_schema(
        self,
        section: str,
        defaults: dict[str, Any],
        scope: str = SCOPE_GROUP,
    ):
        """注册模块的配置 schema。

        Args:
            section: 配置节名称（如 "acg_image"）。
            defaults: 默认值字典。
            scope: "global" 仅在主配置 / "group" 允许追加到子配置（默认）。
        """
        if scope == SCOPE_GLOBAL:
            self._global_schemas[section] = defaults
        else:
            self._group_schemas[section] = defaults

    def get_scope(self, section: str) -> str:
        """查询配置节的 scope。"""
        if section in self._global_schemas:
            return SCOPE_GLOBAL
        if section in self._group_schemas:
            return SCOPE_GROUP
        return SCOPE_GROUP  # 无声明默认 group

    # ═══════════════════════════════════════════════════════════
    # 子配置加载 (v6 多文件分化)
    # ═══════════════════════════════════════════════════════════

    def _group_dir(self, group_id: int) -> str:
        """获取群数据目录路径。"""
        return os.path.join(self._groups_dir, str(group_id))

    def _section_path(self, group_id: int, section: str) -> str:
        """获取群子配置中某模块节的独立文件路径。"""
        return os.path.join(self._group_dir(group_id), f"{section}.json")

    def _group_config_path(self, group_id: int) -> str:
        """获取群子配置的旧版单文件路径（兼容）。"""
        return os.path.join(self._group_dir(group_id), "config.json")

    # ── v6: 多文件读写 ──

    def _load_section_file(self, group_id: int, section: str) -> Optional[dict]:
        """加载单个模块节的配置文件。"""
        path = self._section_path(group_id, section)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            _log.warning("群 %d 节 '%s' 配置读取失败: %s", group_id, section, e)
            return None
        # HMAC 签名校验
        if not ConfigManager._verify_hmac(data, path):
            _log.warning("群 %d 节 '%s' 签名校验失败", group_id, section)
            restored = ConfigManager._restore_from_backup(path)
            if restored is not None:
                data = restored
            else:
                return None
        return data

    def _save_section_file(self, group_id: int, section: str, data: dict):
        """保存单个模块节的配置文件。"""
        path = self._section_path(group_id, section)
        group_dir = self._group_dir(group_id)
        os.makedirs(group_dir, exist_ok=True)

        write_data = deepcopy(data)
        write_data.pop("__signature", None)
        write_data.pop("__signature_data_keys", None)
        ConfigManager._compute_hmac(write_data)

        tmp = path + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(write_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # ── 加载合并 ──

    def load_group_config(self, group_id: int) -> dict:
        """加载指定群的合并后配置。

        流程:
          1. 子配置存在 → deep merge(主配置当前快照, 子配置)
          2. 子配置不存在 → 从主配置 copy → 返回主配置
          3. 类型校验失败 → 备份 + fallback 主配置 + 报警
        """
        with self._cache_lock:
            if group_id in self._cache:
                return self._cache[group_id]

        merged = self._load_and_merge(group_id)
        with self._cache_lock:
            # LRU 淘汰: 超过上限时删除最旧的
            if len(self._cache) >= self._cache_max and group_id not in self._cache:
                oldest = self._cache_order.pop(0) if self._cache_order else None
                if oldest is not None and oldest in self._cache:
                    del self._cache[oldest]
            self._cache[group_id] = merged
            if group_id in self._cache_order:
                self._cache_order.remove(group_id)
            self._cache_order.append(group_id)
        return merged

    def _load_and_merge(self, group_id: int) -> dict:
        """内部加载流程（不含缓存检查）。

        v6: 多文件模式下逐 section 加载，单文件模式下走旧逻辑。
        """
        main_data = self._main_cfg._data

        if MULTI_FILE_MODE:
            return self._load_and_merge_multi(group_id, main_data)
        else:
            return self._load_and_merge_single(group_id, main_data)

    def _load_and_merge_multi(self, group_id: int, main_data: dict) -> dict:
        """多文件模式：每模块节独立加载。"""
        group_dir = self._group_dir(group_id)

        # 检查是否有任何子配置文件存在
        any_section_exists = False
        if os.path.isdir(group_dir):
            for fname in os.listdir(group_dir):
                if fname.endswith(".json") and fname != "config.json":
                    any_section_exists = True
                    break

        if not any_section_exists:
            # 首次：从主配置 seed 所有 group-scope 节
            self._seed_group_config_multi(group_id, main_data)
            return deepcopy(main_data)

        # 逐节加载合并
        merged = {}
        for section, main_section in main_data.items():
            if not isinstance(main_section, dict):
                merged[section] = deepcopy(main_section)
                continue
            if section in self._global_schemas:
                # global scope: 直接用主配置
                merged[section] = deepcopy(main_section)
                continue

            sub_data = self._load_section_file(group_id, section)
            if sub_data is None:
                # 文件缺失 — seed 一节
                self._save_section_file(group_id, section, main_section)
                merged[section] = deepcopy(main_section)
            else:
                # 类型校验
                sub_data, _ = self._validate_section(sub_data, main_section,
                                                     group_id, section)
                merged[section] = GroupConfigManager._deep_merge(
                    main_section, sub_data
                )

        return merged

    def _load_and_merge_single(self, group_id: int, main_data: dict) -> dict:
        """单文件模式：旧逻辑（兼容）。"""
        sub_path = self._group_config_path(group_id)

        if not os.path.exists(sub_path):
            self._seed_group_config(group_id, main_data)
            return deepcopy(main_data)

        try:
            with open(sub_path, 'r', encoding='utf-8') as f:
                sub_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            _log.warning(
                "群 %d 子配置 JSON 解析失败: %s。%s",
                group_id, e, hint["CONFIG_FILE_CORRUPTED"],
            )
            self._repair_and_report(group_id, sub_path, "JSON解析失败")
            return deepcopy(main_data)

        if not ConfigManager._verify_hmac(sub_data, sub_path):
            _log.warning("群 %d 子配置签名校验失败，尝试从备份恢复", group_id)
            restored = ConfigManager._restore_from_backup(sub_path)
            if restored is not None:
                sub_data = restored
            else:
                _log.error("群 %d 子配置签名无效且无可用备份，回退主配置", group_id)
                self._repair_and_report(group_id, sub_path, "签名校验失败")
                return deepcopy(main_data)

        sub_data, repaired = self._validate_and_repair(sub_data, sub_path, group_id)
        merged = self._deep_merge(main_data, sub_data)
        return merged

    # ── Seed ──

    def _seed_group_config_multi(self, group_id: int, template: dict):
        """多文件模式：为每个 group-scope 节创建独立文件。"""
        group_dir = self._group_dir(group_id)
        os.makedirs(group_dir, exist_ok=True)
        for section, data in template.items():
            if section in self._global_schemas or not isinstance(data, dict):
                continue
            self._save_section_file(group_id, section, data)
        _log.info("群 %d 子配置已创建 (多文件模式, %d 节)", group_id,
                  len([s for s in template if s not in self._global_schemas]))

    def _seed_group_config(self, group_id: int, template: dict):
        """单文件模式：为新群从主配置复制一份子配置。"""
        sub_path = self._group_config_path(group_id)
        group_dir = self._group_dir(group_id)
        os.makedirs(group_dir, exist_ok=True)

        seed = {}
        for section, data in template.items():
            if section in self._global_schemas:
                continue
            seed[section] = deepcopy(data)

        seed.pop("__signature", None)
        seed.pop("__signature_data_keys", None)
        ConfigManager._compute_hmac(seed)

        tmp = sub_path + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(seed, f, ensure_ascii=False, indent=2)
        os.replace(tmp, sub_path)
        _log.info("群 %d 子配置已创建: %s", group_id, sub_path)

    def invalidate_cache(self, group_id: int = None):
        """清除缓存。

        Args:
            group_id: 指定群号，None 清除全部。
        """
        with self._cache_lock:
            if group_id is None:
                self._cache.clear()
            else:
                self._cache.pop(group_id, None)

    # ═══════════════════════════════════════════════════════════
    # 类型校验
    # ═══════════════════════════════════════════════════════════

    def _validate_section(self, sub_data: dict, main_section: dict,
                          group_id: int, section: str) -> tuple[dict, int]:
        """校验单个 section 的类型。返回 (fix_data, fix_count)。"""
        from .config_mgr import _config_smart_cast
        fixed = 0
        for key, main_val in main_section.items():
            if key not in sub_data:
                sub_data[key] = deepcopy(main_val)
                continue
            sub_val = sub_data[key]
            if not isinstance(sub_val, type(main_val)):
                repaired = _config_smart_cast(sub_val, type(main_val))
                if repaired is not None:
                    sub_data[key] = repaired
                    _log.info("[配置修复] 群%d.%s.%s: %s → %s",
                              group_id, section, key,
                              type(sub_val).__name__, type(main_val).__name__)
                else:
                    sub_data[key] = deepcopy(main_val)
                    _log.info("[配置修复] 群%d.%s.%s: %s 无法转换→回退默认",
                              group_id, section, key, type(sub_val).__name__)
                fixed += 1
            elif isinstance(main_val, dict) and isinstance(sub_val, dict):
                # 递归
                sub_data[key], sub_fix = self._validate_section(
                    sub_val, main_val, group_id, f"{section}.{key}"
                )
                fixed += sub_fix
        return sub_data, fixed

    def _validate_and_repair(self, sub_data: dict, sub_path: str,
                             group_id: int) -> tuple[dict, int]:
        """校验并自动修复子配置中的类型错误（单文件模式）。"""
        repaired = self._auto_repair_section(sub_data, self._main_cfg._data)
        if repaired > 0:
            try:
                sub_data.pop("__signature", None)
                sub_data.pop("__signature_data_keys", None)
                ConfigManager._compute_hmac(sub_data)
                tmp = sub_path + ".tmp"
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(sub_data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, sub_path)
                _log.info(
                    "群 %d 子配置自动修复 %d 处类型错误，已写回",
                    group_id, repaired
                )
            except OSError:
                pass
        return sub_data, repaired

    def _auto_repair_section(self, sub_data: dict, main_data: dict,
                             path: str = "") -> int:
        """递归修复子配置中类型不匹配的字段（单文件模式）。"""
        from .config_mgr import _config_smart_cast
        fixed = 0
        for section in list(sub_data):
            if section not in main_data or not isinstance(main_data.get(section), dict):
                continue
            main_section = main_data[section]
            sub_section = sub_data[section]
            if not isinstance(sub_section, dict):
                continue
            for key, main_val in main_section.items():
                if key not in sub_section:
                    continue
                sub_val = sub_section[key]
                if not isinstance(sub_val, type(main_val)):
                    repaired = _config_smart_cast(sub_val, type(main_val))
                    p = f"{path}{section}.{key}" if path else f"{section}.{key}"
                    if repaired is not None:
                        sub_section[key] = repaired
                        _log.info(
                            "[配置修复] 群子配置 %s: %s → %s",
                            p, type(sub_val).__name__, type(main_val).__name__
                        )
                        fixed += 1
                    else:
                        sub_section[key] = main_val
                        _log.info(
                            "[配置修复] 群子配置 %s: %s 无法转换→回退默认值",
                            p, type(sub_val).__name__
                        )
                        fixed += 1
                elif isinstance(main_val, dict) and isinstance(sub_val, dict):
                    np = path or f"{section}.{key}."
                    fixed += self._auto_repair_section(
                        {key: sub_val},
                        {key: main_val},
                        np
                    )
        return fixed

    # ═══════════════════════════════════════════════════════════
    # 修复与备份
    # ═══════════════════════════════════════════════════════════

    def _repair_and_report(self, group_id: int, sub_path: str, reason: str):
        """备份损坏的子配置并报告。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"config_group_{group_id}_{ts}.json"
        backup_path = os.path.join(self._repair_dir, backup_name)

        try:
            shutil.copy2(sub_path, backup_path)
            _log.info("群 %d 损坏配置已备份: %s", group_id, backup_path)
        except OSError as e:
            _log.error("备份群 %d 配置失败: %s", group_id, e)

        try:
            if MULTI_FILE_MODE:
                self._seed_group_config_multi(group_id, self._main_cfg._data)
            else:
                self._seed_group_config(group_id, self._main_cfg._data)
        except OSError as e:
            _log.error("重写群 %d 配置失败: %s", group_id, e)

        print(
            f"\n⚠️  [配置] 群 {group_id} 子配置{reason}，已自动修复。\n"
            f"   备份位置: {backup_path}\n"
            f"   该群已回退至主配置默认值。如需恢复自定义配置，"
            f"请手动编辑修复后从备份合并。\n"
        )

    # ═══════════════════════════════════════════════════════════
    # 字段传播
    # ═══════════════════════════════════════════════════════════

    def propagate_new_fields(self) -> list[str]:
        """将模块新增的 group-scope 字段追加到所有群子配置。

        Returns:
            受影响的群号列表（字符串形式）。
        """
        affected = []
        main_data = self._main_cfg._data

        if not os.path.isdir(self._groups_dir):
            return affected

        for entry in sorted(os.listdir(self._groups_dir)):
            group_dir = os.path.join(self._groups_dir, entry)
            if not os.path.isdir(group_dir):
                continue
            try:
                group_id = int(entry)
            except ValueError:
                continue

            if MULTI_FILE_MODE:
                if self._propagate_multi(group_id, group_dir, main_data):
                    affected.append(entry)
            else:
                if self._propagate_single(group_id, group_dir, main_data):
                    affected.append(entry)

        if affected:
            self.invalidate_cache()
        return affected

    def _propagate_multi(self, group_id: int, group_dir: str,
                         main_data: dict) -> bool:
        """多文件模式：逐 section 传播新字段。"""
        changed = False
        for section, defaults in main_data.items():
            if section in self._global_schemas or not isinstance(defaults, dict):
                continue
            path = self._section_path(group_id, section)
            existing = {}
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                except (json.JSONDecodeError, IOError):
                    continue
                existing.pop("__signature", None)
                existing.pop("__signature_data_keys", None)
            if GroupConfigManager._apply_missing_fields(existing, defaults):
                self._save_section_file(group_id, section, existing)
                changed = True
        return changed

    def _propagate_single(self, group_id: int, group_dir: str,
                          main_data: dict) -> bool:
        """单文件模式：旧传播逻辑。"""
        sub_path = os.path.join(group_dir, "config.json")
        if not os.path.isfile(sub_path):
            return False
        try:
            with open(sub_path, 'r', encoding='utf-8') as f:
                sub_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return False

        changed = False
        for section, defaults in main_data.items():
            if section in self._global_schemas or not isinstance(defaults, dict):
                continue
            existing = sub_data.setdefault(section, {})
            if not isinstance(existing, dict):
                continue
            if self._apply_missing_fields(existing, defaults):
                changed = True

        if changed:
            try:
                sub_data.pop("__signature", None)
                sub_data.pop("__signature_data_keys", None)
                ConfigManager._compute_hmac(sub_data)
                tmp = sub_path + ".tmp"
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(sub_data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, sub_path)
                _log.info("群 %s 子配置已补全新字段", group_id)
            except IOError as e:
                _log.error("写入群 %s 子配置失败: %s", group_id, e)
        return changed

    @staticmethod
    def _apply_missing_fields(target: dict, defaults: dict) -> bool:
        """递归将 defaults 中缺失的键补全到 target。"""
        changed = False
        for key, default_value in defaults.items():
            if key not in target:
                target[key] = deepcopy(default_value)
                changed = True
            elif isinstance(default_value, dict) and isinstance(target[key], dict):
                changed |= GroupConfigManager._apply_missing_fields(
                    target[key], default_value
                )
        return changed

    # ═══════════════════════════════════════════════════════════
    # 修复模块 API
    # ═══════════════════════════════════════════════════════════

    def repair_group_config(self, group_id: int, backup_first: bool = True) -> dict:
        """手动触发修复：从主配置重新 seed 子配置。"""
        if backup_first:
            self._backup_group(group_id)
        if MULTI_FILE_MODE:
            self._seed_group_config_multi(group_id, self._main_cfg._data)
        else:
            self._seed_group_config(group_id, self._main_cfg._data)
        self.invalidate_cache(group_id)
        return self.load_group_config(group_id)

    def _backup_group(self, group_id: int):
        """备份指定群的当前配置。"""
        group_dir = self._group_dir(group_id)
        if not os.path.isdir(group_dir):
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for fname in os.listdir(group_dir):
            if not fname.endswith(".json"):
                continue
            src = os.path.join(group_dir, fname)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(
                self._repair_dir,
                f"config_group_{group_id}_{fname.replace('.json', '')}_{ts}.json",
            )
            try:
                shutil.copy2(src, dst)
            except OSError as e:
                _log.error("备份 %s 失败: %s", src, e)
        _log.info("群 %d 配置已备份到 %s", group_id, self._repair_dir)

    def list_group_configs(self) -> list[dict]:
        """列出所有群的子配置状态。"""
        result = []
        if not os.path.isdir(self._groups_dir):
            return result
        for entry in sorted(os.listdir(self._groups_dir)):
            group_dir = os.path.join(self._groups_dir, entry)
            if not os.path.isdir(group_dir):
                continue
            try:
                group_id = int(entry)
            except ValueError:
                continue
            files = [
                f for f in os.listdir(group_dir)
                if f.endswith(".json")
            ]
            total_size = sum(
                os.path.getsize(os.path.join(group_dir, f))
                for f in files
            )
            result.append({
                "group_id": group_id,
                "has_config": len(files) > 0,
                "file_count": len(files),
                "total_size": total_size,
            })
        return result

    # ═══════════════════════════════════════════════════════════
    # 热重载
    # ═══════════════════════════════════════════════════════════

    def reload_group(self, group_id: int) -> bool:
        """重载指定群的子配置（如有变更）。"""
        self.invalidate_cache(group_id)
        self.load_group_config(group_id)
        return True

    def reload_all(self):
        """重载全部群子配置。"""
        self.invalidate_cache()
        if self._on_reload_callback:
            try:
                self._on_reload_callback()
            except Exception as e:
                _log.error("群配置重载回调异常: %s", e)

    def set_reload_callback(self, callback: Callable):
        """设置热重载回调。"""
        self._on_reload_callback = callback

    # ═══════════════════════════════════════════════════════════
    # 配置查询（按群）
    # ═══════════════════════════════════════════════════════════

    def get(self, group_id: int, key: str, default=None, requester_uid: int = 0) -> Any:
        """从群的合并后配置中获取值。

        Args:
            group_id: 群号。
            key: 点号分隔的键（如 "acg_image.冷却秒"）。
            default: 未命中时的默认值。
            requester_uid: 调用方 UID（预留，当前不做权限校验）。
        """
        cfg = self.load_group_config(group_id)
        keys = key.split('.')
        value = cfg
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def get_group_module_config(self, group_id: int, section: str, requester_uid: int = 0) -> dict:
        """获取群配置中指定模块节的合并值。

        Args:
            group_id: 群号。
            section: 配置节名。
            requester_uid: 调用方 UID（预留，当前不做权限校验）。

        Returns:
            合并后的配置字典。
        """
        cfg = self.load_group_config(group_id)
        return cfg.get(section, {})

    # ═══════════════════════════════════════════════════════════
    # 工具
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """深度合并：base 为基础，override 覆盖。"""
        merged = deepcopy(base)
        for k, v in override.items():
            if (
                k in merged
                and isinstance(merged[k], dict)
                and isinstance(v, dict)
            ):
                merged[k] = GroupConfigManager._deep_merge(merged[k], v)
            else:
                merged[k] = deepcopy(v)
        return merged

    # ═══════════════════════════════════════════════════════════
    # 文件监控（子配置热重载）
    # ═══════════════════════════════════════════════════════════

    def start_watching(self, interval: float = 3.0):
        """启动群子配置目录监控线程。"""
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._watcher_stop = threading.Event()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop, args=(interval,), daemon=True,
        )
        self._watcher_thread.start()
        _log.info("群子配置监控已启动 (间隔 %.1fs)", interval)

    def stop_watching(self):
        """停止目录监控线程。"""
        if self._watcher_stop:
            self._watcher_stop.set()
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=5)

    def _watch_loop(self, interval: float):
        """目录轮询循环：检测所有群 config 文件的 mtime 变化。"""
        while not self._watcher_stop.is_set():
            self._watcher_stop.wait(interval)
            if self._watcher_stop.is_set():
                break
            self._check_all_changed()

    def _check_all_changed(self):
        """扫描所有群子配置文件的 mtime，重载有变更的。"""
        if not os.path.isdir(self._groups_dir):
            return
        changed = set()
        for entry in os.listdir(self._groups_dir):
            group_dir = os.path.join(self._groups_dir, entry)
            if not os.path.isdir(group_dir):
                continue
            try:
                group_id = int(entry)
            except ValueError:
                continue

            # 扫描该群目录下所有 JSON 文件
            any_changed = False
            for fname in os.listdir(group_dir):
                if not fname.endswith(".json"):
                    continue
                fp = os.path.join(group_dir, fname)
                try:
                    mtime = os.path.getmtime(fp)
                except OSError:
                    continue
                if mtime != self._mtime_cache.get(fp, 0):
                    self._mtime_cache[fp] = mtime
                    any_changed = True
            if any_changed:
                changed.add(group_id)

        if changed:
            with self._cache_lock:
                for gid in changed:
                    self._cache.pop(gid, None)
            for gid in changed:
                merged = self._load_and_merge(gid)
                with self._cache_lock:
                    self._cache[gid] = merged
            _log.info("群子配置热重载: %s", sorted(changed))
            if self._on_reload_callback:
                try:
                    self._on_reload_callback()
                except Exception as e:
                    _log.error("群配置重载回调异常: %s", e)

"""群聊子配置管理器 — 继承模型 + 类型校验 + 字段自动传播 + 文件热重载

═══════════════════════════════════════════════════════════════════════════
 设计
═══════════════════════════════════════════════════════════════════════════
 · 主配置 config.json                             → 默认值 + 参考模板
 · 群子配置 data/groups/<群号>/config.json        → 只覆盖差异项
 · 加载优先级: 子配置 > 主配置（deep merge）
 · 新群首次触发: 从主配置 copy 到子配置目录
 · 主配置变更: 不影响已存在的子配置
 · 模块新增字段: 自动追加到所有群子配置
 · 类型校验失败: 备份原配置 → fallback 主配置该群 → 终端报告
═══════════════════════════════════════════════════════════════════════════
"""
import json
import logging
import os
import shutil
import threading
import time

from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Optional

from ..core.error_hints import hint

_log = logging.getLogger(__name__)

# 模块 config_schema 中 scope 键名
SCOPE_GLOBAL = "global"
SCOPE_GROUP = "group"


class GroupConfigManager:
    """管理群聊子配置的加载、合并、类型校验和字段传播。"""

    def __init__(self, config_mgr, data_dir: str):
        """初始化群配置管理器。

        Args:
            config_mgr: 主 ConfigManager 实例（持有主配置）。
            data_dir: 框架数据根目录（如 "./"）。
        """
        self._main_cfg = config_mgr
        self._groups_dir = os.path.join(data_dir, "data", "groups")
        self._repair_dir = os.path.join(data_dir, "data", "repair_backups")
        os.makedirs(self._groups_dir, exist_ok=True)
        os.makedirs(self._repair_dir, exist_ok=True)

        # 内存缓存: group_id → merged_config_dict
        self._cache: dict[int, dict] = {}
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
    # 子配置加载
    # ═══════════════════════════════════════════════════════════

    def _group_dir(self, group_id: int) -> str:
        """获取群数据目录路径。"""
        return os.path.join(self._groups_dir, str(group_id))

    def _group_config_path(self, group_id: int) -> str:
        """获取群子配置文件路径。"""
        return os.path.join(self._group_dir(group_id), "config.json")

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
            self._cache[group_id] = merged
        return merged

    def _load_and_merge(self, group_id: int) -> dict:
        """内部加载流程（不含缓存检查）。"""
        sub_path = self._group_config_path(group_id)
        main_data = self._main_cfg._data

        if not os.path.exists(sub_path):
            # 首次：从主配置复制
            self._seed_group_config(group_id, main_data)
            return deepcopy(main_data)

        # 子配置存在：加载
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

        # 类型校验
        type_errors = self._validate_types(sub_data)
        if type_errors:
            _log.warning(
                "群 %d 子配置类型错误 %d 处: %s",
                group_id, len(type_errors), "; ".join(type_errors[:3]),
            )
            self._repair_and_report(group_id, sub_path, "类型校验失败")
            return deepcopy(main_data)

        # Deep merge: 主配置为基础，子配置覆盖
        merged = self._deep_merge(main_data, sub_data)
        return merged

    def _seed_group_config(self, group_id: int, template: dict):
        """为新群从主配置复制一份子配置。"""
        sub_path = self._group_config_path(group_id)
        group_dir = self._group_dir(group_id)
        os.makedirs(group_dir, exist_ok=True)

        # 过滤掉全局 scope 的节，只复制 group scope 的
        seed = {}
        for section, data in template.items():
            if section in self._global_schemas:
                continue
            seed[section] = deepcopy(data)

        with open(sub_path, 'w', encoding='utf-8') as f:
            json.dump(seed, f, ensure_ascii=False, indent=2)
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

    def _validate_types(self, sub_data: dict) -> list[str]:
        """校验子配置的值类型是否与主配置一致。

        Returns:
            错误描述列表，空列表表示通过。
        """
        errors = []
        main_data = self._main_cfg._data

        for section in sub_data:
            if section not in main_data:
                continue
            main_section = main_data[section]
            sub_section = sub_data[section]
            if not isinstance(main_section, dict) or not isinstance(sub_section, dict):
                continue
            errors.extend(
                self._validate_section_types(
                    section, sub_section, main_section
                )
            )
        return errors

    @staticmethod
    def _validate_section_types(
        section: str, sub: dict, main: dict, prefix: str = "",
    ) -> list[str]:
        """递归校验配置节内的类型。"""
        errors = []
        for key, main_val in main.items():
            path = f"{prefix}{section}.{key}"
            if key not in sub:
                continue
            sub_val = sub[key]
            expected_type = type(main_val)
            if not isinstance(sub_val, expected_type):
                errors.append(
                    f"{path}: 期望{expected_type.__name__}, "
                    f"实际{type(sub_val).__name__}"
                )
            elif isinstance(main_val, dict) and isinstance(sub_val, dict):
                errors.extend(
                    GroupConfigManager._validate_section_types(
                        "", sub_val, main_val, prefix=f"{path}."
                    )
                )
        return errors

    # ═══════════════════════════════════════════════════════════
    # 修复与备份
    # ═══════════════════════════════════════════════════════════

    def _repair_and_report(self, group_id: int, sub_path: str, reason: str):
        """备份损坏的子配置并报告。

        Args:
            group_id: 群号。
            sub_path: 子配置文件路径。
            reason: 失败原因描述。
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"config_group_{group_id}_{ts}.json"
        backup_path = os.path.join(self._repair_dir, backup_name)

        try:
            shutil.copy2(sub_path, backup_path)
            _log.info("群 %d 损坏配置已备份: %s", group_id, backup_path)
        except OSError as e:
            _log.error("备份群 %d 配置失败: %s", group_id, e)

        # 重新从主配置 seed（覆盖损坏文件）
        try:
            self._seed_group_config(group_id, self._main_cfg._data)
        except OSError as e:
            _log.error("重写群 %d 配置失败: %s", group_id, e)

        # 向终端报告
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

        扫描每个群子配置，查找主配置中存在但子配置中缺失的键，
        自动补全并保存。

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

            sub_path = os.path.join(group_dir, "config.json")
            if not os.path.isfile(sub_path):
                continue

            try:
                with open(sub_path, 'r', encoding='utf-8') as f:
                    sub_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            changed = False
            for section, defaults in main_data.items():
                # 跳过 global scope
                if section in self._global_schemas:
                    continue
                if not isinstance(defaults, dict):
                    continue
                existing = sub_data.setdefault(section, {})
                if not isinstance(existing, dict):
                    # 类型不匹配，跳过（下次 load 时会校验修复）
                    continue
                section_changed = self._apply_missing_fields(existing, defaults)
                if section_changed:
                    changed = True

            if changed:
                try:
                    with open(sub_path, 'w', encoding='utf-8') as f:
                        json.dump(sub_data, f, ensure_ascii=False, indent=2)
                    affected.append(entry)
                    _log.info("群 %s 子配置已补全新字段", entry)
                except IOError as e:
                    _log.error("写入群 %s 子配置失败: %s", entry, e)

        # 清除所有受影响群的缓存
        if affected:
            self.invalidate_cache()
        return affected

    @staticmethod
    def _apply_missing_fields(target: dict, defaults: dict) -> bool:
        """递归将 defaults 中缺失的键补全到 target。

        Returns:
            是否有变更。
        """
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
        """手动触发修复：从主配置重新 seed 子配置。

        Args:
            group_id: 群号。
            backup_first: 是否先备份旧配置（默认 True）。

        Returns:
            新的合并配置。
        """
        sub_path = self._group_config_path(group_id)
        if backup_first and os.path.exists(sub_path):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(
                self._repair_dir,
                f"config_group_{group_id}_{ts}.json",
            )
            try:
                shutil.copy2(sub_path, backup_path)
                _log.info("手动修复前备份: %s", backup_path)
            except OSError as e:
                _log.error("备份失败: %s", e)

        self._seed_group_config(group_id, self._main_cfg._data)
        self.invalidate_cache(group_id)
        return self.load_group_config(group_id)

    def list_group_configs(self) -> list[dict]:
        """列出所有群的子配置状态。

        Returns:
            [{"group_id": int, "has_config": bool, "file_size": int}, ...]
        """
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
            sub_path = os.path.join(group_dir, "config.json")
            has = os.path.isfile(sub_path)
            size = os.path.getsize(sub_path) if has else 0
            result.append({
                "group_id": group_id,
                "has_config": has,
                "file_size": size,
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

    def get(self, group_id: int, key: str, default=None) -> Any:
        """从群的合并后配置中获取值。

        Args:
            group_id: 群号。
            key: 点号分隔的键（如 "acg_image.冷却秒"）。
            default: 未命中时的默认值。
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

    def get_group_module_config(self, group_id: int, section: str) -> dict:
        """获取群配置中指定模块节的合并值。

        Args:
            group_id: 群号。
            section: 配置节名。

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
        """目录轮询循环：检测所有群 config.json 的 mtime 变化。"""
        while not self._watcher_stop.is_set():
            self._watcher_stop.wait(interval)
            if self._watcher_stop.is_set():
                break
            self._check_all_changed()

    def _check_all_changed(self):
        """扫描所有群子配置文件的 mtime，重载有变更的。"""
        if not os.path.isdir(self._groups_dir):
            return
        changed = []
        for entry in os.listdir(self._groups_dir):
            group_dir = os.path.join(self._groups_dir, entry)
            if not os.path.isdir(group_dir):
                continue
            try:
                group_id = int(entry)
            except ValueError:
                continue
            sub_path = os.path.join(group_dir, "config.json")
            if not os.path.isfile(sub_path):
                continue
            try:
                mtime = os.path.getmtime(sub_path)
            except OSError:
                continue
            if mtime != self._mtime_cache.get(sub_path, 0):
                self._mtime_cache[sub_path] = mtime
                changed.append(group_id)
        if changed:
            with self._cache_lock:
                for gid in changed:
                    self._cache.pop(gid, None)
                    # 预热缓存（同一锁内）
                    self._load_and_merge(gid)
            _log.info("群子配置热重载: %s", changed)
            if self._on_reload_callback:
                try:
                    self._on_reload_callback()
                except Exception as e:
                    _log.error("群配置重载回调异常: %s", e)

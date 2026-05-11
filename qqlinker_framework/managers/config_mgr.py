"""配置管理器（支持动态注册节，仅在必要时自动持久化）"""
import json
import os
from typing import Any


class ConfigManager:
    """基于 JSON 文件的配置管理器，支持默认值自动合并和动态注册节。

    配置文件仅在以下情况被写入：
    1. 首次创建配置文件时。
    2. 外部调用 save() 时。
    3. 注册新配置节且该节在文件中不存在时。
    """

    def __init__(self, file_path: str = "config.json", data_dir: str = None):
        self._file_path = file_path
        self._data: dict = {}
        self._defaults: dict = {}
        self._loaded = False
        self.data_dir = data_dir or os.path.dirname(
            os.path.abspath(file_path)
        )

    def register_section(self, section: str, defaults: dict[str, Any]):
        """注册一个配置节及其默认值。若配置已加载且文件缺少该节或字段，则自动补全并保存。"""
        if section not in self._defaults:
            self._defaults[section] = defaults

        if not self._loaded:
            return

        # 确保内存中有该节
        section_data = self._data.setdefault(section, {})
        # 补全缺失的字段，返回是否有新增
        changed = self._apply_defaults(section_data, defaults)
        if changed:
            self.save()

    def load(self):
        """加载配置文件并与默认值深度合并。文件不存在时创建默认配置。"""
        if os.path.exists(self._file_path):
            with open(self._file_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            self._data = self._deep_merge(self._defaults, loaded)
        else:
            self._data = dict(self._defaults)
            # 首次创建才保存
            self.save()
        self._loaded = True
        # 补全所有已注册节的缺失字段（仅内存，不写磁盘）
        for section, defaults in self._defaults.items():
            section_data = self._data.setdefault(section, {})
            self._apply_defaults(section_data, defaults)

    def save(self):
        """强制保存当前内存配置到文件。"""
        with open(self._file_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default=None):
        """通过点号分隔的键获取配置值。"""
        keys = key.split('.')
        value = self._data
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any):
        """通过点号分隔的键设置配置值，并自动创建中间字典。"""
        keys = key.split('.')
        data = self._data
        for k in keys[:-1]:
            data = data.setdefault(k, {})
        data[keys[-1]] = value

    def get_data_dir(self) -> str:
        """返回数据目录路径。"""
        return self.data_dir

    # ----------------------------------------------------------------
    # 内部工具
    # ----------------------------------------------------------------
    @staticmethod
    def _apply_defaults(target: dict, defaults: dict) -> bool:
        """递归将 defaults 中缺失的键添加到 target 中，不覆盖已有值。"""
        changed = False
        for key, default_value in defaults.items():
            if key not in target:
                target[key] = default_value
                changed = True
            elif isinstance(default_value, dict) and isinstance(target[key], dict):
                changed |= ConfigManager._apply_defaults(target[key], default_value)
        return changed

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """深度合并两个字典，override 优先。"""
        merged = {}
        for k in set(base) | set(override):
            if (
                k in base
                and k in override
                and isinstance(base[k], dict)
                and isinstance(override[k], dict)
            ):
                merged[k] = ConfigManager._deep_merge(base[k], override[k])
            else:
                merged[k] = override.get(k) if k in override else base[k]
        return merged

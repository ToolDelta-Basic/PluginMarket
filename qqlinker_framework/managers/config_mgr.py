"""配置管理器（支持动态注册节，自动持久化）"""
import json
import os
from typing import Any

class ConfigManager:
    """基于 JSON 文件的配置管理器，支持默认值自动合并和动态注册节。"""

    def __init__(self, file_path: str = "config.json", data_dir: str = None):
        """初始化配置管理器。

        Args:
            file_path: 配置文件路径。
            data_dir: 数据目录，用于推断文件路径。
        """
        self._file_path = file_path
        self._data: dict = {}
        self._defaults: dict = {}
        self.data_dir = data_dir or os.path.dirname(os.path.abspath(file_path))

    def register_section(self, section: str, defaults: dict[str, Any]):
        """注册一个配置节及其默认值，如果配置文件中缺少则写入默认值。

        Args:
            section: 节名称（顶层键）。
            defaults: 默认值字典。
        """
        if section not in self._defaults:
            self._defaults[section] = defaults
        if self._data and section not in self._data:
            self._data[section] = defaults
            self.save()

    def load(self):
        """加载配置文件，与默认值深度合并后保存。"""
        if os.path.exists(self._file_path):
            with open(self._file_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            self._data = self._deep_merge(self._defaults, loaded)
        else:
            self._data = dict(self._defaults)
        self.save()

    def save(self):
        """保存当前配置到文件。"""
        with open(self._file_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default=None):
        """通过点号分隔的键获取配置值。

        Args:
            key: 如 '节.子键'。
            default: 未找到时返回的默认值。

        Returns:
            配置值。
        """
        keys = key.split('.')
        value = self._data
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any):
        """通过点号分隔的键设置配置值，并自动创建中间字典。

        Args:
            key: 如 '节.子键'。
            value: 新值。
        """
        keys = key.split('.')
        data = self._data
        for k in keys[:-1]:
            data = data.setdefault(k, {})
        data[keys[-1]] = value

    def get_data_dir(self) -> str:
        """返回数据目录路径。"""
        return self.data_dir

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """深度合并两个字典，override 优先。

        Args:
            base: 基础字典。
            override: 覆盖字典。

        Returns:
            合并结果。
        """
        merged = {}
        for k in set(base) | set(override):
            if k in base and k in override and isinstance(base[k], dict) and isinstance(override[k], dict):
                merged[k] = ConfigManager._deep_merge(base[k], override[k])
            else:
                merged[k] = override.get(k) if k in override else base[k]
        return merged
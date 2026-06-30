import json
import logging
import os
import threading
from typing import Any, Dict

from ..channel_host import Library

_log = logging.getLogger(__name__)


class GroupConfigManager:
    """群级子配置管理 — 每个群一个 JSON 文件。"""

    def __init__(self, data_path: str):
        self._dir = os.path.join(data_path, "群配置")
        os.makedirs(self._dir, exist_ok=True)
        self._cache: Dict[int, dict] = {}
        self._lock = threading.Lock()

    def get(self, group_id: int, path: str, default: Any = None, **kwargs) -> Any:
        """读取群配置。

        kwargs 允许传入 requester_uid 等元数据（兼容旧代码）。
        """
        with self._lock:
            data = self._load_group(group_id)
        parts = path.split(".")
        d = data
        for p in parts:
            if isinstance(d, dict) and p in d:
                d = d[p]
            else:
                return default
        return d

    def get_group_module_config(self, group_id: int, section: str, **kwargs) -> dict:
        """获取指定群的模块节配置。

        Args:
            group_id: 群号。
            section: 模块配置节名。

        Returns:
            该模块节的配置字典，不存在则返回空字典。
        """
        data = self.get(group_id, section, {})
        return data if isinstance(data, dict) else {}

    def set(self, group_id: int, path: str, value: Any) -> None:
        """写入群配置。"""
        with self._lock:
            data = self._load_group(group_id)
            parts = path.split(".")
            d = data
            for p in parts[:-1]:
                if p not in d or not isinstance(d[p], dict):
                    d[p] = {}
                d = d[p]
            d[parts[-1]] = value
            self._save_group(group_id, data)

    def register_module_schema(self, section: str, defaults: dict, scope: str = "group") -> None:
        """注册模块配置 schema（兼容旧接口）。"""
        # 暂存 schema 定义，后续群配置初始化时使用
        if not hasattr(self, '_schemas'):
            self._schemas = {}
        self._schemas[section] = {"defaults": defaults, "scope": scope}

    def get_all_groups(self) -> list:
        """列出所有已配置的群号。"""
        result = []
        for f in os.listdir(self._dir):
            if f.endswith(".json"):
                try:
                    result.append(int(f[:-5]))
                except ValueError as e:
                    _log.debug("group_config.get_all_groups: %s", e)
        return result

    def _load_group(self, group_id: int) -> dict:
        if group_id in self._cache:
            return self._cache[group_id]
        path = os.path.join(self._dir, f"{group_id}.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._cache[group_id] = data
                return data
            except (json.JSONDecodeError, OSError) as e:
                _log.debug("group_config._load_group: %s", e)
        data = {}
        self._cache[group_id] = data
        return data

    def _save_group(self, group_id: int, data: dict) -> None:
        self._cache[group_id] = data
        path = os.path.join(self._dir, f"{group_id}.json")
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError as e:
            _log.error("群配置保存失败 [%d]: %s", group_id, e)


class GroupConfigLibrary(Library):
    """群级子配置库。"""

    name = "group_config"
    version = "1.6.0"
    dependencies = ["config_store"]

    async def mount(self) -> None:
        data_path = self.services.get("_data_path")
        mgr = GroupConfigManager(data_path)
        self.services.register("group_config", mgr, mid=300)

    async def unmount(self) -> None:
        pass

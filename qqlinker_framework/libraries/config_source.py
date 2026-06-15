"""配置管理库 — 信道实现（纯实现，不依赖旧配置管理器）。
"""
import json
import os
import threading
from typing import Any

from ..core.channel import Library


class _ConfigStore:
    """线程安全的 JSON 配置存储。"""

    def __init__(self, file_path: str):
        self._file_path = file_path
        self._data: dict = {}
        self._sections: dict = {}
        self._lock = threading.Lock()
        self.load()

    def register_section(self, section: str, defaults: dict) -> None:
        with self._lock:
            self._sections[section] = defaults
            if section not in self._data:
                self._data[section] = dict(defaults)

    def get(self, path: str, default: Any = None) -> Any:
        with self._lock:
            return self._resolve(path, default)

    def set(self, path: str, value: Any) -> None:
        with self._lock:
            parts = path.split(".")
            d = self._data
            for p in parts[:-1]:
                if p not in d or not isinstance(d[p], dict):
                    d[p] = {}
                d = d[p]
            d[parts[-1]] = value
            self._save()

    def load(self) -> None:
        if os.path.isfile(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        tmp = self._file_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._file_path)
        except OSError:
            pass

    def _resolve(self, path: str, default: Any) -> Any:
        parts = path.split(".")
        d = self._data
        for p in parts:
            if isinstance(d, dict) and p in d:
                d = d[p]
            else:
                return default
        return d

    def get_data_dir(self) -> str:
        return os.path.dirname(self._file_path)


class ConfigSourceLibrary(Library):
    """配置管理库。"""

    name = "config_source"
    version = "1.0.0"
    dependencies = ["core"]

    async def mount(self) -> None:
        data_path = getattr(self, '_data_path', '.')
        store = _ConfigStore(
            os.path.join(data_path, "config.json")
        )
        self.services.register("config", store)
        self.config = store
        self._store = store

    async def unmount(self) -> None:
        pass

from __future__ import annotations

import fnmatch
import importlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union

_log = logging.getLogger(__name__)

T = TypeVar("T")


class Scanner:
    """统一目录扫描器 — 替代 18 个文件中的 os.listdir 重复逻辑。

    用法:
        scanner = Scanner("/data/path")
        scanner.find("*.json")                    → [Path, ...]
        scanner.find("*.py", recursive=True)      → [Path, ...]
        scanner.find_classes(Library, "*.py")     → [Library实例, ...]
        scanner.find_json("*.json", schema=None)  → [(Path, dict), ...]
    """

    def __init__(self, directory: str):
        """初始化扫描器。

        Args:
            directory: 扫描目标目录路径。
        """
        self._directory = Path(directory).resolve()
        self._mtime_cache: Dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def directory(self) -> Path:
        """返回扫描的根目录（绝对路径）。"""
        return self._directory

    # ── find ─────────────────────────────────────────────────

    def find(
        self,
        pattern: str,
        *,
        recursive: bool = False,
        exclude: Optional[List[str]] = None,
        max_size_mb: Optional[float] = None,
        track_mtime: bool = False,
    ) -> Union[List[Path], List[Tuple[Path, float]]]:
        """扫描匹配 glob 模式的文件。

        Args:
            pattern: glob 模式（如 "*.py"、"data*.json"）。
            recursive: 是否递归扫描子目录。
            exclude: 排除模式列表（如 ["__*", "*test*"]），
                     使用 fnmatch 匹配文件名。
            max_size_mb: 最大文件大小（MB），超限跳过。
            track_mtime: 返回 (Path, mtime) 元组而非纯 Path。
                         同时更新内部的 mtime 缓存（线程安全）。

        Returns:
            track_mtime=False 时返回排序的 Path 列表；
            track_mtime=True 时返回排序的 (Path, mtime) 列表。
        """
        if not self._directory.is_dir():
            _log.warning("扫描目录不存在: %s", self._directory)
            return []

        entries: List[Tuple[Path, float]] = []
        iterator = (
            self._directory.rglob(pattern)
            if recursive
            else self._directory.glob(pattern)
        )

        for path in iterator:
            if not path.is_file():
                continue

            name = path.name
            if exclude and any(fnmatch.fnmatch(name, ex) for ex in exclude):
                _log.debug("排除文件: %s", path)
                continue

            if max_size_mb is not None:
                try:
                    size_mb = path.stat().st_size / (1024 * 1024)
                    if size_mb > max_size_mb:
                        _log.debug(
                            "跳过超大文件: %s (%.1fMB > %.1fMB)",
                            path, size_mb, max_size_mb,
                        )
                        continue
                except OSError:
                    continue

            mtime = 0.0
            if track_mtime:
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    mtime = 0.0
                with self._lock:
                    self._mtime_cache[str(path)] = mtime

            entries.append((path, mtime))
            _log.debug("发现文件: %s", path)

        entries.sort(key=lambda x: x[0].name)

        if track_mtime:
            return [(p, m) for p, m in entries]
        return [p for p, _ in entries]

    # ── find_classes ─────────────────────────────────────────

    def find_classes(
        self,
        base_class: Type[T],
        pattern: str = "*.py",
        *,
        recursive: bool = False,
        import_prefix: Optional[str] = None,
        exclude: Optional[List[str]] = None,
    ) -> List[T]:
        """扫描目录，导入 .py 模块，返回 base_class 子类的实例。

        类似 channel_host._scan_directory 的行为。

        Args:
            base_class: 基类，只返回其子类。
            pattern: 匹配的文件 pattern（默认 "*.py"）。
            recursive: 是否递归扫描。
            import_prefix: 模块导入前缀
                           （如 "qqlinker_framework.libraries.core"）。
            exclude: 排除的文件名模式。

        Returns:
            base_class 子类的实例列表。
        """
        results: List[T] = []
        paths = self.find(pattern, recursive=recursive, exclude=exclude)

        if not paths and isinstance(paths, list):
            return results

        for path in paths:
            stem = path.stem  # filename without .py
            if stem.startswith("_"):
                continue

            if import_prefix:
                module_name = f"{import_prefix}.{stem}"
            else:
                module_name = stem

            try:
                mod = importlib.import_module(module_name)

                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, base_class)
                        and attr is not base_class
                        and getattr(attr, "name", "")
                    ):
                        instance = attr()
                        results.append(instance)
                        _log.debug(
                            "发现类: %s (来自 %s)", attr.__name__, module_name,
                        )
            except Exception as e:
                _log.warning("扫描模块失败 [%s]: %s", module_name, e)

        return results

    # ── find_json ────────────────────────────────────────────

    def find_json(
        self,
        pattern: str = "*.json",
        *,
        recursive: bool = False,
        schema: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Path, Dict[str, Any]]]:
        """扫描 JSON 文件并返回解析后的数据。

        Args:
            pattern: 匹配的文件 pattern（默认 "*.json"）。
            recursive: 是否递归扫描。
            schema: 保留参数（未来可用于 JSON Schema 校验）。

        Returns:
            (Path, parsed_dict) 元组列表，按文件名排序。
        """
        results: List[Tuple[Path, Dict[str, Any]]] = []
        paths = self.find(pattern, recursive=recursive)

        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append((path, data))
                _log.debug("加载 JSON: %s", path)
            except json.JSONDecodeError as e:
                _log.warning("JSON 解析失败 [%s]: %s", path, e)
            except OSError as e:
                _log.warning("读取文件失败 [%s]: %s", path, e)

        return results

    # ── mtime 缓存 ───────────────────────────────────────────

    def get_mtime(self, filepath: Union[str, Path]) -> Optional[float]:
        """获取缓存的文件 mtime（需要先调用 find(track_mtime=True)）。

        Args:
            filepath: 文件路径。

        Returns:
            缓存的 mtime，不存在返回 None。
        """
        key = str(Path(filepath))
        with self._lock:
            return self._mtime_cache.get(key)

    def is_changed(self, filepath: Union[str, Path]) -> bool:
        """检查文件是否自上次 scan 后发生变化。

        Args:
            filepath: 文件路径。

        Returns:
            True 如果文件 mtime 与缓存不一致。
        """
        key = str(Path(filepath))
        cached = self.get_mtime(key)
        if cached is None:
            return True  # 首次出现视为变化
        try:
            current = os.path.getmtime(key)
            return current != cached
        except OSError:
            return True

    def refresh_mtime(self, filepath: Union[str, Path]) -> bool:
        """刷新单个文件的 mtime 缓存。

        Args:
            filepath: 文件路径。

        Returns:
            True 如果成功读取 mtime。
        """
        key = str(Path(filepath))
        try:
            mtime = os.path.getmtime(key)
            with self._lock:
                self._mtime_cache[key] = mtime
            return True
        except OSError:
            return False

    def clear_mtime_cache(self) -> None:
        """清空 mtime 缓存。"""
        with self._lock:
            self._mtime_cache.clear()

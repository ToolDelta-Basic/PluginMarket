import asyncio
import json
import logging
import os
import tempfile
import threading
from typing import Any, Callable, Dict, List, Optional

from .kernel.error_hints import hint

_log = logging.getLogger(__name__)


# ── JSON 数据库代理 ──────────────────────────────────────────

class JsonCollection:
    """单个 JSON 集合的 CRUD 代理，自动持久化。"""

    def __init__(self, filepath: str):
        self._file = filepath
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        """从磁盘加载 JSON 数据。"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}

    def _save(self):
        """持久化当前数据到磁盘（原子写入：临时文件 + os.replace）。"""
        dirname = os.path.dirname(self._file) or "."
        os.makedirs(dirname, exist_ok=True)
        tmpfd, tmppath = tempfile.mkstemp(
            dir=dirname,
            prefix=os.path.basename(self._file) + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmpfd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmppath, self._file)
        except Exception:
            try:
                os.unlink(tmppath)
            except OSError as e:
                _log.debug("清理临时文件失败: %s", e)
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """读取指定键的值。"""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """写入键值对并持久化。"""
        with self._lock:
            self._data[key] = value
            self._save()

    def delete(self, key: str) -> bool:
        """删除指定键，返回是否成功。"""
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()
                return True
            return False

    def all(self) -> Dict[str, Any]:
        """返回所有键值对的浅拷贝。"""
        with self._lock:
            return dict(self._data)

    def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        with self._lock:
            return key in self._data

    def count(self) -> int:
        """返回存储条目数量。"""
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        """清空所有数据。"""
        with self._lock:
            self._data.clear()
            self._save()

    def keys(self) -> List[str]:
        """返回所有键的列表。"""
        with self._lock:
            return list(self._data.keys())

    def values(self) -> List[Any]:
        """返回所有值的列表。"""
        with self._lock:
            return list(self._data.values())

    def update(self, items: Dict[str, Any]) -> None:
        """批量更新键值对。"""
        with self._lock:
            self._data.update(items)
            self._save()

    def __repr__(self):
        return f"<JsonCollection keys={len(self._data)}>"


class JsonDatabase:
    """JSON 数据库代理 — 按模块自动管理 collections。"""

    def __init__(self, data_dir: str, collections: List[str]):
        os.makedirs(data_dir, exist_ok=True)
        for name in collections:
            filepath = os.path.join(data_dir, f"{name}.json")
            setattr(self, name, JsonCollection(filepath))


# ── 定时任务定义 ─────────────────────────────────────────────

class ScheduledTask:
    """声明式定时任务定义。"""

    def __init__(
        self,
        name: str,
        handler: Callable,
        *,
        interval: float | None = None,
        cron: str | None = None,
        run_on_start: bool = False,
        enabled: bool = True,
    ):
        self.name = name
        self.handler = handler
        self.interval = interval
        self.cron = cron
        self.run_on_start = run_on_start
        self.enabled = enabled
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> Optional[asyncio.Task]:
        """启动定时任务。"""
        if self._task and not self._task.done():
            return self._task

        async def _runner():
            if self.run_on_start:
                await _safe_call(self.handler)
            while not self._stop_event.is_set():
                try:
                    if self.interval:
                        await asyncio.wait_for(
                            self._stop_event.wait(), timeout=self.interval
                        )
                        if self._stop_event.is_set():
                            break
                    else:
                        await asyncio.sleep(60)
                    if self.enabled:
                        await _safe_call(self.handler)
                except asyncio.TimeoutError:
                    if self.enabled:
                        await _safe_call(self.handler)
                except asyncio.CancelledError:
                    break

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        self._task = loop.create_task(_runner())
        return self._task

    def stop(self):
        """停止定时任务并取消异步任务。"""
        self._stop_event.set()
        if self._task:
            self._task.cancel()


async def _safe_call(handler: Callable):
    """安全调用处理器，捕获异常并记录日志。"""
    try:
        if asyncio.iscoroutinefunction(handler):
            await handler()
        else:
            await asyncio.get_running_loop().run_in_executor(None, handler)
    except Exception:
        logging.getLogger(__name__).exception("定时任务异常。%s", hint["UNEXPECTED_ERROR"])


# ── 热重载状态 ──────────────────────────────────────────────

class HotReloadState:
    """热重载状态管理器 — 自动从磁盘序列化/反序列化。"""

    def __init__(self, filepath: str, defaults: Dict[str, Any] = None):
        self._file = filepath
        self._defaults = defaults or {}
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self):
        """从磁盘加载状态，合并默认值。"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data = {**self._defaults, **loaded}
            except (json.JSONDecodeError, IOError):
                self._data = dict(self._defaults)
        else:
            self._data = dict(self._defaults)

    def save(self):
        """持久化当前状态到磁盘。"""
        os.makedirs(os.path.dirname(self._file), exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """读取指定键的值。"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """写入键值对并持久化。"""
        self._data[key] = value
        self.save()

    def all(self) -> Dict[str, Any]:
        """返回所有键值对的浅拷贝。"""
        return dict(self._data)

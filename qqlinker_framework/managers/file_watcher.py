"""薄导入层 — 实际实现在 core/drivers/file_watcher.py。

此文件为兼容性保留。所有导入应从统一入口
  `from qqlinker_framework.core.drivers.file_watcher import ...`
"""

from ..core.drivers.file_watcher import (
    ModuleFileWatcher,
    file_watcher_main,
    WATCH_SUBDIR,
    DEFAULT_SCAN_INTERVAL,
)

__all__ = [
    "ModuleFileWatcher",
    "file_watcher_main",
    "WATCH_SUBDIR",
    "DEFAULT_SCAN_INTERVAL",
]

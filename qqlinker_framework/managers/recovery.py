"""薄导入层 — 实际实现在 core/drivers/recovery.py。

此文件为兼容性保留。所有导入应从统一入口
  `from qqlinker_framework.core.drivers.recovery import ...`
"""

from ..core.drivers.recovery import (
    RecoveryEngine,
    RESTART_WINDOW_SECONDS,
    RESTART_MAX_IN_WINDOW,
    MAX_CHECKPOINT_SIZE,
)

__all__ = [
    "RecoveryEngine",
    "RESTART_WINDOW_SECONDS",
    "RESTART_MAX_IN_WINDOW",
    "MAX_CHECKPOINT_SIZE",
]

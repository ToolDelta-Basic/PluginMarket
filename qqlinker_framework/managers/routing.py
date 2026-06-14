"""薄导入层 — 实际实现在 core/drivers/routing.py。

此文件为兼容性保留。所有导入应从统一入口
  `from qqlinker_framework.core.drivers.routing import ...`
"""

from ..core.drivers.routing import (
    CommandRouter,
    USER_LOCK_TIMEOUT,
    CIRCUIT_BREAKER_WINDOW,
    CIRCUIT_BREAKER_THRESHOLD,
    CIRCUIT_BREAKER_COOLDOWN,
)

__all__ = [
    "CommandRouter",
    "USER_LOCK_TIMEOUT",
    "CIRCUIT_BREAKER_WINDOW",
    "CIRCUIT_BREAKER_THRESHOLD",
    "CIRCUIT_BREAKER_COOLDOWN",
]

"""ToolDelta 热重载时同步刷新红包子模块。"""

from __future__ import annotations

import importlib
import sys


RELOAD_ORDER = (
    "text_validation",
    "models",
    "configuration",
    "interaction",
    "economy",
    "storage",
    "messages",
    "broadcasting",
    "service",
)


def reload_plugin_modules(package_name: str) -> None:
    """按依赖顺序刷新已缓存的红包模块。"""

    for module_suffix in RELOAD_ORDER:
        module_name = f"{package_name}.{module_suffix}"
        cached_module = sys.modules.get(module_name)
        if cached_module is not None:
            importlib.reload(cached_module)

"""薄导入层 — 实际实现在 modules/system/template_engine.py。

此文件为兼容性保留。所有导入应从统一入口
  `from qqlinker_framework.modules.system.template_engine import ...`
"""

from ..modules.system.template_engine import (
    TemplateEngine,
    TEMPLATE_TYPES,
    FIELD_MARKERS,
    TEMPLATES_DIR,
    BACKUPS_DIR,
)

__all__ = [
    "TemplateEngine",
    "TEMPLATE_TYPES",
    "FIELD_MARKERS",
    "TEMPLATES_DIR",
    "BACKUPS_DIR",
]

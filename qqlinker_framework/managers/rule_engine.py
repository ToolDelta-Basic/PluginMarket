"""薄导入层 — 实际实现在 modules/system/rule_engine.py。

此文件为兼容性保留。所有导入应从统一入口
  `from qqlinker_framework.modules.system.rule_engine import ...`
"""

from ..modules.system.rule_engine import (
    RuleService,
    RuleEngineModule,
    RULE_MANAGE_UID,
    RULE_EXEC_UID,
    DEFAULT_COOLDOWN_GLOBAL,
    DEFAULT_COOLDOWN_GROUP,
)

__all__ = [
    "RuleService",
    "RuleEngineModule",
    "RULE_MANAGE_UID",
    "RULE_EXEC_UID",
    "DEFAULT_COOLDOWN_GLOBAL",
    "DEFAULT_COOLDOWN_GROUP",
]

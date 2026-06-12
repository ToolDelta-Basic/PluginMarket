# 管理/__init__.py — 管理层统一导出
"""管理模块 — 框架所有管理类和驱动类的统一入口。

通过 `from qqlinker_framework.管理 import X` 导入所有管理类。
"""

# ── 核心管理器 ──
from .config_mgr import ConfigManager, register_config_bridge, TIER_KERNEL, UID_DAEMON, UID_SERVICE, UID_APP, UID_NOBODY
from .source_mgr import SourceManager, MAX_MODULE_MGR_DEPTH
from .package_mgr import PackageManager
from .command_mgr import CommandManager
from .tool_mgr import ToolManager, ToolType, ToolDefinition
from .message_mgr import MessageManager, SendPriority, DISPATCH_TIMEOUT
from .group_config import GroupConfigManager, SCOPE_GLOBAL, SCOPE_GROUP, MULTI_FILE_MODE
from .group_filter import GroupModuleFilter, SECTION, MODE_BLACKLIST, MODE_WHITELIST
from .console import ConsoleCommands

# ── 核心驱动 ──
from .routing import CommandRouter, USER_LOCK_TIMEOUT, CIRCUIT_BREAKER_WINDOW, CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_COOLDOWN
from .recovery import RecoveryEngine, RESTART_WINDOW_SECONDS, RESTART_MAX_IN_WINDOW, MAX_CHECKPOINT_SIZE
from .file_watcher import ModuleFileWatcher, file_watcher_main, WATCH_SUBDIR, DEFAULT_SCAN_INTERVAL
from .network import NetworkManager, NetworkConfig
from .retry_policy import RetryPolicy
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError, CircuitState

# ── AI 引擎 ──
from .ai_engine import AIEngine
from .tool_policy import ToolPolicy, register_policy, unregister_policy, get_policy, filter_tools, READONLY_POLICY, NO_TOOLS_POLICY

# ── 其他模块级管理器 ──
from .template_engine import TemplateEngine, TEMPLATE_TYPES, FIELD_MARKERS, TEMPLATES_DIR, BACKUPS_DIR
from .rule_engine import RuleService, RuleEngineModule, RULE_MANAGE_UID, RULE_EXEC_UID, DEFAULT_COOLDOWN_GLOBAL, DEFAULT_COOLDOWN_GROUP

# ── 管理工具子模块 ──
from .admin_tools import AdminToolManager

__all__ = [
    # 核心管理器
    "ConfigManager", "register_config_bridge",
    "TIER_KERNEL", "UID_DAEMON", "UID_SERVICE", "UID_APP", "UID_NOBODY",
    "SourceManager", "MAX_MODULE_MGR_DEPTH",
    "PackageManager",
    "CommandManager",
    "ToolManager", "ToolType", "ToolDefinition",
    "MessageManager", "SendPriority", "DISPATCH_TIMEOUT",
    "GroupConfigManager", "SCOPE_GLOBAL", "SCOPE_GROUP", "MULTI_FILE_MODE",
    "GroupModuleFilter", "SECTION", "MODE_BLACKLIST", "MODE_WHITELIST",
    "ConsoleCommands",
    # 核心驱动
    "CommandRouter", "USER_LOCK_TIMEOUT", "CIRCUIT_BREAKER_WINDOW",
    "CIRCUIT_BREAKER_THRESHOLD", "CIRCUIT_BREAKER_COOLDOWN",
    "RecoveryEngine", "RESTART_WINDOW_SECONDS", "RESTART_MAX_IN_WINDOW", "MAX_CHECKPOINT_SIZE",
    "ModuleFileWatcher", "file_watcher_main", "WATCH_SUBDIR", "DEFAULT_SCAN_INTERVAL",
    "NetworkManager", "NetworkConfig",
    "RetryPolicy",
    "CircuitBreaker", "CircuitBreakerConfig", "CircuitBreakerOpenError", "CircuitState",
    # AI 引擎
    "AIEngine",
    "ToolPolicy", "register_policy", "unregister_policy", "get_policy", "filter_tools",
    "READONLY_POLICY", "NO_TOOLS_POLICY",
    # 其他
    "TemplateEngine", "TEMPLATE_TYPES", "FIELD_MARKERS", "TEMPLATES_DIR", "BACKUPS_DIR",
    "RuleService", "RuleEngineModule",
    "RULE_MANAGE_UID", "RULE_EXEC_UID",
    "DEFAULT_COOLDOWN_GLOBAL", "DEFAULT_COOLDOWN_GROUP",
    "AdminToolManager",
]

import logging
from typing import Optional

_log = logging.getLogger(__name__)

SECTION = "模块管理"
MODE_BLACKLIST = "黑名单"
MODE_WHITELIST = "白名单"


class GroupModuleFilter:
    """按群号决定模块/命令是否可用。"""

    def __init__(self, group_config_mgr):
        self._gcfg = group_config_mgr
        self._module_names: set[str] = set()

    def set_module_names(self, names: set[str]) -> None:
        """注入已知模块名列表，供 get_disabled_modules 白名单模式下计算差集。

        Args:
            names: 所有已注册的模块名称集合。
        """
        self._module_names = set(names)

    # ── 模块过滤 ──

    def is_module_enabled(self, group_id: int, module_name: str, caller_uid: int = 400) -> bool:
        """检查指定模块在指定群是否启用。

        root(uid=0) 不受群级别过滤限制。

        逻辑:
          1. root → 直接放行
          2. 群配置 "禁用模块" 列表 → 命中则禁用
          3. 群配置 "启用模块" 白名单 → 非空且不在列表中 → 禁用
          4. 否则启用
        """
        if caller_uid == 0:
            return True
        mgr = self._get_mgr(group_id)
        if mgr is None:
            return True

        mode = mgr.get("模式", MODE_BLACKLIST)
        disabled = mgr.get("禁用模块", [])
        enabled = mgr.get("启用模块", [])

        if not isinstance(disabled, list):
            disabled = []
        if not isinstance(enabled, list):
            enabled = []

        if mode == MODE_WHITELIST and enabled:
            return module_name in enabled

        if mode == MODE_BLACKLIST and disabled:
            if module_name in disabled:
                _log.debug(
                    "群 %d 禁用模块 '%s'", group_id, module_name
                )
                return False

        return True

    # ── 命令过滤 ──

    def is_command_enabled(
        self, group_id: int, module_name: str, trigger: str, caller_uid: int = 400
    ) -> bool:
        """检查指定群是否启用了某个命令。

        root(uid=0) 不受群级别过滤限制。
        先检查模块是否启用，再检查命令级黑/白名单。
        """
        if caller_uid == 0:
            return True
        if not self.is_module_enabled(group_id, module_name, caller_uid=caller_uid):
            return False

        mgr = self._get_mgr(group_id)
        if mgr is None:
            return True

        mode = mgr.get("模式", MODE_BLACKLIST)
        disabled_cmds = mgr.get("禁用命令", [])
        enabled_cmds = mgr.get("启用命令", [])

        if not isinstance(disabled_cmds, list):
            disabled_cmds = []
        if not isinstance(enabled_cmds, list):
            enabled_cmds = []

        if mode == MODE_WHITELIST and enabled_cmds:
            return trigger in enabled_cmds

        if mode == MODE_BLACKLIST and disabled_cmds:
            if trigger in disabled_cmds:
                _log.debug(
                    "群 %d 禁用命令 '%s' (模块 '%s')",
                    group_id, trigger, module_name,
                )
                return False

        return True

    # ── 辅助 ──

    def _get_mgr(self, group_id: int) -> Optional[dict]:
        """获取群的模块管理配置。"""
        try:
            cfg = self._gcfg.get(group_id, SECTION, {})
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            return {}

    def get_disabled_modules(self, group_id: int) -> list[str]:
        """返回指定群禁用的模块列表。

        黑名单模式: 直接返回"禁用模块"列表。
        白名单模式: 返回已注册但不在启用列表中的模块（需要先通过
                     set_module_names() 注入模块名列表）。
                     若未注入模块名，返回空列表并记录 debug 日志。
        """
        mgr = self._get_mgr(group_id)
        if not mgr:
            return []
        mode = mgr.get("模式", MODE_BLACKLIST)
        if mode == MODE_BLACKLIST:
            return mgr.get("禁用模块", [])
        # 白名单模式: 未启用的模块视为禁用
        enabled = mgr.get("启用模块", [])
        if not self._module_names:
            _log.debug(
                "白名单模式但未注入模块名列表 (群 %d)，"
                "get_disabled_modules 返回空。"
                "请调用 set_module_names() 注入已知模块。",
                group_id,
            )
            return []
        return sorted(self._module_names - set(enabled))

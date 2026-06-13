"""QQ group menu and command handlers for Ultra."""

import time
from typing import Any

from tooldelta import utils

try:
    from tooldelta.utils.mc_translator import translate
except ImportError:
    translate = None


# 日常群聊交互放在这一层：帮助、背包查询、管理员菜单、联动检查菜单。
class QQLinkerQQMixin:
    """负责群聊菜单、查询类功能以及白名单联动命令。"""

    @utils.thread_func("群服执行指令并获取返回")
    def on_qq_execute_cmd(self, group_id: int, qqid: int, cmd: list[str]):
        """在群里执行 Minecraft 指令，并把执行结果回发到群里。"""
        if not self._can_use_group_permission(group_id, qqid, "发送指令权限"):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        res = self.execute_cmd_and_get_zhcn_cb(" ".join(cmd))
        self.sendmsg(group_id, res)

    def _reply_to_qq(self, group_id: int, qqid: int, text: str):
        """向指定群成员回复一条文本消息。"""
        self.sendmsg(
            group_id,
            f"[CQ:at,qq={qqid}] {text}",
            do_remove_cq_code=False,
        )

    def _reply_result(self, group_id: int, qqid: int, ok: bool, msg: str):
        """统一回发成功/失败结果。"""
        self._reply_to_qq(group_id, qqid, f"{'😄' if ok else '😭'} {msg}")

    def _can_use_group_permission(
        self,
        group_id: int,
        qqid: int,
        permission_name: str,
    ) -> bool:
        """Implement the can use group permission operation."""
        if hasattr(self, "_has_group_permission"):
            return self._has_group_permission(group_id, qqid, permission_name)
        return self.has_group_permission(group_id, qqid, permission_name)

    def _can_use_any_group_permission(
        self,
        group_id: int,
        qqid: int,
        permission_names: tuple[str, ...],
    ) -> bool:
        """Implement the can use any group permission operation."""
        return any(
            self._can_use_group_permission(group_id, qqid, permission_name)
            for permission_name in permission_names
        )

    def _reply_menu_permission_denied(self, group_id: int, qqid: int):
        """Implement the reply menu permission denied operation."""
        if hasattr(self, "_reply_permission_denied"):
            self._reply_permission_denied(group_id, qqid)
            return
        self._reply_to_qq(group_id, qqid, "你没有权限执行此指令")

    def _ensure_group_permission(
        self,
        group_id: int,
        qqid: int,
        permission_name: str,
    ) -> bool:
        """Implement the ensure group permission operation."""
        if self._can_use_group_permission(group_id, qqid, permission_name):
            return True
        self._reply_menu_permission_denied(group_id, qqid)
        return False

    def _append_permission_action(
        self,
        group_id: int,
        qqid: int,
        options: list[str],
        actions: list[Any],
        permission_name: str,
        label: str,
        action,
    ):
        """Implement the append permission action operation."""
        if self._can_use_group_permission(group_id, qqid, permission_name):
            options.append(label)
            actions.append(action)

    def _has_help_admin_actions(self, group_id: int, qqid: int) -> bool:
        """Implement the has help admin actions operation."""
        permission_names = [
            "QQ普通管理员菜单权限",
            "QQ超级管理员菜单权限",
            "发送指令权限",
            "配置配置文件权限",
            "查询背包权限",
            "封禁/解封玩家权限",
            "白名单&管理员检测权限",
            "领地系统权限",
            "公会系统权限",
        ]
        if self.task_system is not None:
            permission_names.append("任务系统权限")
        return self._can_use_any_group_permission(
            group_id,
            qqid,
            tuple(permission_names),
        )

    @staticmethod
    def _extract_plugin_enabled_flag(plugin: Any):  # skipcq: PY-R1000
        """读取联动插件明确暴露的整体启用状态；缺少该项时返回 None。"""
        for method_name in ("_plugin_enabled", "is_plugin_enabled"):
            method = getattr(plugin, method_name, None)
            if callable(method):
                try:
                    return bool(method())
                except Exception:
                    return None

        enabled = getattr(plugin, "enabled", None)
        if isinstance(enabled, bool):
            return enabled

        for method_name in ("api_get_runtime_status", "get_runtime_status"):
            method = getattr(plugin, method_name, None)
            if not callable(method):
                continue
            try:
                status = method()
            except Exception:
                continue
            if isinstance(status, tuple) and len(status) >= 3:
                status = status[2]
            if isinstance(status, dict):
                for key in ("enabled", "是否启用", "是否启用插件"):
                    if isinstance(status.get(key), bool):
                        return status[key]

        for attr_name in ("config", "cfg", "_cfg"):
            config = getattr(plugin, attr_name, None)
            if not isinstance(config, dict):
                continue
            for key in ("是否启用", "是否启用插件"):
                if isinstance(config.get(key), bool):
                    return config[key]
            base_config = config.get("基础配置")
            if isinstance(base_config, dict):
                for key in ("是否启用", "是否启用插件"):
                    if isinstance(base_config.get(key), bool):
                        return base_config[key]

        return None

    def ensure_linked_plugin_enabled(
            self,
            plugin: Any,
            group_id: int,
            sender: int) -> bool:
        """联动插件明确配置为禁用时，不进入群内管理菜单。"""
        enabled = self._extract_plugin_enabled_flag(plugin)
        if not enabled and enabled is not None:
            self._reply_to_qq(group_id, sender, "相关插件未启用")
            return False
        return True

    def on_qq_help(self, group_id: int, sender: int, _):
        """打开可交互的群帮助主菜单。"""
        self.qq_help_main_menu(group_id, sender)

    def _is_menu_exit(self, user_input: str, group_id: int | None = None):
        """Implement the is menu exit operation."""
        return self.is_menu_exit_input(user_input, group_id)

    def _is_menu_back(self, user_input: str, group_id: int | None = None):
        """Implement the is menu back operation."""
        return self.is_menu_back_input(user_input, group_id)

    def _prompt_help_menu(
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        options: list[str],
        hints: list[str],
        allow_back: bool = False,
    ):
        """Implement the prompt help menu operation."""
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                subtitle,
                options,
                hints,
                group_id),
            timeout=120,
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return None
        choice = choice.strip()
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        if allow_back and self._is_menu_back(choice, group_id):
            return "back"
        return choice

    def _parse_help_choice(
            self,
            group_id: int,
            qqid: int,
            choice: str,
            count: int):
        """Implement the parse help choice operation."""
        selected = self.parse_displayed_menu_choice(choice, count)
        if selected is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
        return selected

    def _prompt_paginated_help_actions(  # skipcq: PY-R1000
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        options: list[str],
        actions: list[Any],
        per_page: int,
    ):
        """Implement the prompt paginated help actions operation."""
        if len(options) != len(actions):
            self._reply_to_qq(group_id, qqid, "❀ 菜单配置错误")
            return None
        if not options:
            self._reply_to_qq(group_id, qqid, "当前没有可用功能")
            return None
        page = 1
        while True:
            total_pages, start_index, end_index = (
                utils.paginate(len(options), per_page, page)
                if hasattr(utils, "paginate")
                else self.simple_paginate(len(options), per_page, page)
            )
            page_options = options[start_index - 1: end_index]
            text = self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                subtitle,
                page_options,
                [
                    f"当前第 {page}/{total_pages} 页",
                    f"输入 [1-{len(page_options)}] 之间的数字以选择 对应功能",
                    "输入 - 转到上一页",
                    "输入 + 转到下一页",
                    "输入 正整数+页 转到对应页",
                    "输入 0 返回上级菜单",
                    "输入 . 退出",
                ],
                group_id,
            )
            user_input = self.qq_prompt(group_id, qqid, text, timeout=120)
            if user_input is None:
                self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
                return None
            user_input = user_input.strip()
            if self._is_menu_exit(user_input, group_id):
                self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
                return None
            if self._is_menu_back(user_input, group_id):
                return "back"
            if user_input == "+":
                if page < total_pages:
                    page += 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是最后一页啦~")
                continue
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是第一页啦~")
                continue
            if page_num := self.parse_page_jump(user_input):
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self._reply_to_qq(group_id, qqid, f"❀ 不存在第 {page_num} 页")
                continue
            selected = self._parse_help_choice(
                group_id,
                qqid,
                user_input,
                len(page_options),
            )
            if selected is None:
                continue
            result = actions[start_index + selected - 2]()
            return result if result == "back" else None

    def qq_help_main_menu(self, group_id: int, qqid: int):
        """群帮助主菜单，负责路由到各个二级菜单。"""
        options = ["非管理功能"]
        handlers = [self.qq_help_basic_menu]
        if self._has_help_admin_actions(group_id, qqid):
            options.append("管理功能")
            handlers.append(self.qq_help_admin_menu)
        options.append("命令说明")
        handlers.append(self.qq_help_show_all_reference)
        while True:
            choice = self._prompt_help_menu(
                group_id,
                qqid,
                "帮助主菜单",
                options,
                [f"输入 [1-{len(options)}] 之间的数字以选择 对应菜单", "输入 . 退出"],
            )
            if choice is None:
                return
            selected = self._parse_help_choice(
                group_id, qqid, choice, len(options))
            if selected is None:
                continue
            if handlers[selected - 1](group_id, qqid) == "back":
                continue
            return

    def qq_help_basic_menu(self, group_id: int, qqid: int):
        """非管理功能二级菜单。"""
        options = []
        actions = []
        if self.group_cfgs[group_id]["指令设置"]["是否允许查看玩家列表"] and (
            self._can_use_group_permission(group_id, qqid, "查看玩家人数权限")
        ):
            options.append("查看在线玩家列表")
            actions.append(lambda: self.on_qq_player_list(group_id, qqid, []))
        options.append("公会系统菜单")
        actions.append(lambda: self.qq_guild_player_menu(group_id, qqid))
        options.append("查看非管理功能触发词")
        actions.append(
            lambda: self.qq_help_show_basic_reference(
                group_id, qqid))
        return self._prompt_paginated_help_actions(
            group_id,
            qqid,
            "非管理功能",
            options,
            actions,
            self.get_group_help_non_admin_items_per_page(group_id),
        )

    def qq_help_admin_menu(self, group_id: int, qqid: int):
        """管理功能二级菜单。"""
        options = []
        actions = []
        if self._can_use_any_group_permission(
            group_id,
            qqid,
            ("QQ普通管理员菜单权限", "QQ超级管理员菜单权限"),
        ):
            options.append("QQ群管理员管理菜单")
            actions.append(lambda: self.qq_admin_menu(group_id, qqid))
        self._append_permission_action(
            group_id,
            qqid,
            options,
            actions,
            "发送指令权限",
            "发送 Minecraft 指令",
            lambda: self.qq_help_execute_command_prompt(group_id, qqid),
        )
        self._append_permission_action(
            group_id,
            qqid,
            options,
            actions,
            "配置配置文件权限",
            "配置中心",
            lambda: self.qq_config_center_menu(group_id, qqid),
        )
        self._append_permission_action(
            group_id,
            qqid,
            options,
            actions,
            "查询背包权限",
            "查询在线玩家背包",
            lambda: self.qq_inventory_menu(group_id, qqid),
        )
        self._append_permission_action(
            group_id,
            qqid,
            options,
            actions,
            "封禁/解封玩家权限",
            "Orion QQ 封禁菜单",
            lambda: self.qq_orion_ban_menu(group_id, qqid),
        )
        self._append_permission_action(
            group_id,
            qqid,
            options,
            actions,
            "封禁/解封玩家权限",
            "Orion QQ 解封菜单",
            lambda: self.qq_orion_unban_menu(group_id, qqid),
        )
        self._append_permission_action(
            group_id,
            qqid,
            options,
            actions,
            "白名单&管理员检测权限",
            "白名单&管理员检测管理菜单",
            lambda: self.qq_checker_menu(group_id, qqid),
        )
        if self.task_system is not None:
            self._append_permission_action(
                group_id,
                qqid,
                options,
                actions,
                "任务系统权限",
                "任务系统管理菜单",
                lambda: self.qq_task_system_menu(group_id, qqid),
            )
        self._append_permission_action(
            group_id,
            qqid,
            options,
            actions,
            "领地系统权限",
            "领地系统云链联动版管理菜单",
            lambda: self.qq_land_system_menu(group_id, qqid),
        )
        self._append_permission_action(
            group_id,
            qqid,
            options,
            actions,
            "公会系统权限",
            "公会系统管理菜单",
            lambda: self.qq_guild_system_menu(group_id, qqid),
        )
        options.append("查看管理功能触发词")
        actions.append(
            lambda: self.qq_help_show_admin_reference(
                group_id, qqid))
        return self._prompt_paginated_help_actions(
            group_id,
            qqid,
            "管理功能",
            options,
            actions,
            self.get_group_help_admin_items_per_page(group_id),
        )

    def qq_help_integration_menu(self, group_id: int, qqid: int):
        """联动系统二级菜单。"""
        while True:
            options = []
            actions = []
            self._append_permission_action(
                group_id,
                qqid,
                options,
                actions,
                "封禁/解封玩家权限",
                "Orion QQ 封禁菜单",
                lambda: self.qq_orion_ban_menu(group_id, qqid),
            )
            self._append_permission_action(
                group_id,
                qqid,
                options,
                actions,
                "封禁/解封玩家权限",
                "Orion QQ 解封菜单",
                lambda: self.qq_orion_unban_menu(group_id, qqid),
            )
            self._append_permission_action(
                group_id,
                qqid,
                options,
                actions,
                "白名单&管理员检测权限",
                "白名单&管理员检测管理菜单",
                lambda: self.qq_checker_menu(group_id, qqid),
            )
            if self.task_system is not None:
                self._append_permission_action(
                    group_id,
                    qqid,
                    options,
                    actions,
                    "任务系统权限",
                    "任务系统管理菜单",
                    lambda: self.qq_task_system_menu(group_id, qqid),
                )
            self._append_permission_action(
                group_id,
                qqid,
                options,
                actions,
                "领地系统权限",
                "领地系统云链联动版管理菜单",
                lambda: self.qq_land_system_menu(group_id, qqid),
            )
            self._append_permission_action(
                group_id,
                qqid,
                options,
                actions,
                "公会系统权限",
                "公会系统管理菜单",
                lambda: self.qq_guild_system_menu(group_id, qqid),
            )
            if not options:
                self._reply_to_qq(group_id, qqid, "当前没有可用功能")
                return None
            choice = self._prompt_help_menu(
                group_id,
                qqid,
                "联动系统",
                options,
                [
                    f"输入 [1-{len(options)}] 之间的数字以选择 对应功能",
                    "输入 0 返回上级菜单",
                    "输入 . 退出",
                ],
                allow_back=True,
            )
            if choice is None:
                return None
            if choice == "back":
                return "back"
            selected = self._parse_help_choice(
                group_id, qqid, choice, len(options))
            if selected is None:
                continue
            actions[selected - 1]()
            return None

    def qq_help_show_all_reference(self, group_id: int, qqid: int):
        """直接分页展示本群当前可用的全部命令触发词。"""
        lines = self.qq_help_build_all_reference_lines(group_id, qqid)
        if not lines:
            self._reply_to_qq(group_id, qqid, "当前没有可展示的命令触发词")
            return None
        page = 1
        per_page = self.get_group_command_help_items_per_page(group_id)
        while True:
            total_pages, start_index, end_index = (
                utils.paginate(len(lines), per_page, page)
                if hasattr(utils, "paginate")
                else self.simple_paginate(len(lines), per_page, page)
            )
            page_lines = lines[start_index - 1: end_index]
            text = self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "命令说明",
                page_lines,
                [
                    f"当前第 {page}/{total_pages} 页",
                    "输入 - 转到上一页",
                    "输入 + 转到下一页",
                    "输入 正整数+页 转到对应页",
                    "输入 0 返回上级菜单",
                    "输入 . 退出",
                ],
                group_id,
            )
            user_input = self.qq_prompt(group_id, qqid, text, timeout=120)
            if user_input is None:
                self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
                return None
            if self._is_menu_exit(user_input, group_id):
                self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
                return None
            if self._is_menu_back(user_input, group_id):
                return "back"
            if user_input == "+":
                if page < total_pages:
                    page += 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是最后一页啦~")
                continue
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是第一页啦~")
                continue
            if page_num := self.parse_page_jump(user_input):
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self._reply_to_qq(group_id, qqid, f"❀ 不存在第 {page_num} 页")
                continue
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")

    def qq_help_build_all_reference_lines(  # skipcq: PY-R1000
        self,
        group_id: int,
        qqid: int,
    ):
        """按运行时触发分发入口整理全部命令触发词说明。"""
        cmd_prefix = self.get_group_cmd_prefix(group_id)
        lines = [
            f"{' / '.join(self.get_group_help_triggers(group_id))} - 打开帮助菜单",
        ]
        if self.group_cfgs[group_id]["指令设置"]["是否允许查看玩家列表"] and (
            self._can_use_group_permission(group_id, qqid, "查看玩家人数权限")
        ):
            lines.append(
                f"{' / '.join(self.get_group_player_list_triggers(group_id))} - 查看玩家列表"
            )
        lines.append(
            (
                f"{' / '.join(self.get_group_guild_menu_triggers(group_id))} - "
                "公会系统菜单（普通成员需绑定游戏账号；管理员进入管理菜单）"
            )
        )
        if self._can_use_group_permission(group_id, qqid, "查询背包权限"):
            lines.append(
                (
                    f"{' / '.join(self.get_group_inventory_menu_triggers(group_id))} - "
                    "查询在线玩家背包"
                )
            )
        if self._can_use_group_permission(group_id, qqid, "发送指令权限"):
            lines.append(f"{cmd_prefix}[指令] - 向租赁服发送指令")
        if self._can_use_any_group_permission(
            group_id,
            qqid,
            ("QQ普通管理员菜单权限", "QQ超级管理员菜单权限"),
        ):
            lines.append(
                (
                    f"{' / '.join(self.get_group_admin_menu_triggers(group_id))} - "
                    "QQ群管理员管理菜单"
                )
            )
        if self._can_use_group_permission(group_id, qqid, "配置配置文件权限"):
            lines.append(
                f"{' / '.join(self.get_group_config_menu_triggers(group_id))} - 配置中心"
            )
        if self._can_use_group_permission(group_id, qqid, "封禁/解封玩家权限"):
            lines.extend(
                [
                    (
                        f"{' / '.join(self.get_group_orion_ban_triggers(group_id))} "
                        "[玩家名/xuid] [封禁时间] [原因可选] - Orion QQ 封禁"
                    ),
                    (
                        f"{' / '.join(self.get_group_orion_unban_triggers(group_id))} "
                        "[玩家名/xuid] - Orion QQ 解封"
                    ),
                ]
            )
        if self._can_use_group_permission(group_id, qqid, "白名单&管理员检测权限"):
            lines.append(
                (
                    f"{' / '.join(self.get_group_checker_menu_triggers(group_id))} - "
                    "白名单&管理员检测管理菜单"
                )
            )
        if self.task_system is not None and self._can_use_group_permission(
            group_id,
            qqid,
            "任务系统权限",
        ):
            lines.append(
                f"{' / '.join(self.get_group_task_menu_triggers(group_id))} - 任务系统管理菜单"
            )
        if self._can_use_group_permission(group_id, qqid, "领地系统权限"):
            lines.append(
                (
                    f"{' / '.join(self.get_group_land_menu_triggers(group_id))} - "
                    "领地系统云链联动版管理菜单"
                )
            )
        if self._can_use_group_permission(group_id, qqid, "公会系统权限"):
            lines.append(
                (
                    f"{' / '.join(self.get_group_guild_menu_triggers(group_id))} - "
                    "公会系统管理菜单（管理员）"
                )
            )
        for trigger in self.triggers:
            if trigger.op_only and not self.is_group_admin(group_id, qqid):
                continue
            trigger_text = " / ".join(trigger.triggers)
            argument_hint = f" {
                trigger.argument_hint}" if trigger.argument_hint else ""
            permission_hint = "（管理员）" if trigger.op_only else ""
            lines.append(
                f"外部｜{trigger_text}{argument_hint} - {trigger.usage}{permission_hint}"
            )
        return lines

    def qq_help_reference_menu(self, group_id: int, qqid: int):
        """命令说明二级菜单。"""
        while True:
            options = ["非管理功能触发词"]
            actions = [
                lambda: self.qq_help_show_basic_reference(
                    group_id, qqid)]
            if self._has_help_admin_actions(group_id, qqid):
                options.append("管理功能触发词")
                actions.append(
                    lambda: self.qq_help_show_admin_reference(group_id, qqid))
            choice = self._prompt_help_menu(
                group_id,
                qqid,
                "命令说明",
                options,
                [
                    f"输入 [1-{len(options)}] 之间的数字以查看 对应说明",
                    "输入 0 返回上级菜单",
                    "输入 . 退出",
                ],
                allow_back=True,
            )
            if choice is None:
                return None
            if choice == "back":
                return "back"
            selected = self._parse_help_choice(
                group_id, qqid, choice, len(options))
            if selected is None:
                continue
            actions[selected - 1]()
            return None

    def qq_help_execute_command_prompt(self, group_id: int, qqid: int):
        """通过帮助菜单交互式发送一条 Minecraft 指令。"""
        if not self._can_use_group_permission(group_id, qqid, "发送指令权限"):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        cmd_prefix = self.get_group_cmd_prefix(group_id)
        command = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "发送 Minecraft 指令",
                ["在下一条消息中输入要发送到租赁服的指令"],
                [f"可以省略或保留前缀 {cmd_prefix}", "输入 . 退出"],
                group_id,
            ),
            timeout=120,
        )
        if command is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        command = command.strip()
        if self._is_menu_exit(command, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        if command.startswith(cmd_prefix):
            command = command.removeprefix(cmd_prefix).strip()
        if not command:
            self._reply_to_qq(group_id, qqid, f"参数错误，格式：{cmd_prefix}[指令]")
            return
        self.on_qq_execute_cmd(group_id, qqid, command.split())

    def qq_help_show_basic_reference(self, group_id: int, qqid: int):
        """Handle the qq help show basic reference QQ menu operation."""
        options = [
            f"{' / '.join(self.get_group_help_triggers(group_id))} - 打开帮助菜单",
        ]
        if self.group_cfgs[group_id]["指令设置"]["是否允许查看玩家列表"] and (
            self._can_use_group_permission(group_id, qqid, "查看玩家人数权限")
        ):
            options.append(
                f"{' / '.join(self.get_group_player_list_triggers(group_id))} - 查看玩家列表"
            )
        options.append(
            (
                f"{' / '.join(self.get_group_guild_menu_triggers(group_id))} - "
                "公会系统菜单（需绑定游戏账号）"
            )
        )
        self._reply_to_qq(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "非管理功能触发词",
                options,
                ["输入帮助菜单唤醒词可重新打开菜单"],
                group_id,
            ),
        )

    def qq_help_show_admin_reference(self, group_id: int, qqid: int):
        """Handle the qq help show admin reference QQ menu operation."""
        cmd_prefix = self.get_group_cmd_prefix(group_id)
        options = []
        if self._can_use_group_permission(group_id, qqid, "发送指令权限"):
            options.append(f"{cmd_prefix}[指令] - 向租赁服发送指令")
        if self._can_use_any_group_permission(
            group_id,
            qqid,
            ("QQ普通管理员菜单权限", "QQ超级管理员菜单权限"),
        ):
            options.append(
                (
                    f"{' / '.join(self.get_group_admin_menu_triggers(group_id))} - "
                    "QQ群管理员管理菜单"
                )
            )
        if self._can_use_group_permission(group_id, qqid, "配置配置文件权限"):
            options.append(
                f"{' / '.join(self.get_group_config_menu_triggers(group_id))} - 配置中心"
            )
        if self._can_use_group_permission(group_id, qqid, "查询背包权限"):
            options.append(
                (
                    f"{' / '.join(self.get_group_inventory_menu_triggers(group_id))} - "
                    "查询在线玩家背包"
                )
            )
        if self._can_use_group_permission(group_id, qqid, "封禁/解封玩家权限"):
            orion_ban_triggers = " / ".join(
                self.get_group_orion_ban_triggers(group_id)
            )
            orion_unban_triggers = " / ".join(
                self.get_group_orion_unban_triggers(group_id)
            )
            options.extend(
                [
                    f"{orion_ban_triggers} - Orion QQ 封禁菜单",
                    f"{orion_unban_triggers} - Orion QQ 解封菜单",
                ]
            )
        if self._can_use_group_permission(group_id, qqid, "白名单&管理员检测权限"):
            options.append(
                (
                    f"{' / '.join(self.get_group_checker_menu_triggers(group_id))} - "
                    "白名单&管理员检测管理菜单"
                )
            )
        if self.task_system is not None and self._can_use_group_permission(
            group_id,
            qqid,
            "任务系统权限",
        ):
            options.append(
                f"{' / '.join(self.get_group_task_menu_triggers(group_id))} - 任务系统管理菜单"
            )
        if self._can_use_group_permission(group_id, qqid, "领地系统权限"):
            options.append(
                (
                    f"{' / '.join(self.get_group_land_menu_triggers(group_id))} - "
                    "领地系统云链联动版管理菜单"
                )
            )
        if self._can_use_group_permission(group_id, qqid, "公会系统权限"):
            options.append(
                (
                    f"{' / '.join(self.get_group_guild_menu_triggers(group_id))} - "
                    "公会系统管理菜单（管理员）"
                )
            )
        if not options:
            self._reply_to_qq(group_id, qqid, "当前没有可展示的管理功能触发词")
            return
        self._reply_to_qq(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "管理功能触发词",
                options,
                ["这些功能需要本群所有者、超级管理员或普通管理员权限"],
                group_id,
            ),
        )

    def qq_help_show_integration_reference(self, group_id: int, qqid: int):
        """Handle the qq help show integration reference QQ menu operation."""
        options = []
        if self._can_use_group_permission(group_id, qqid, "封禁/解封玩家权限"):
            orion_ban_triggers = " / ".join(
                self.get_group_orion_ban_triggers(group_id)
            )
            orion_unban_triggers = " / ".join(
                self.get_group_orion_unban_triggers(group_id)
            )
            options.extend(
                [
                    f"{orion_ban_triggers} - Orion QQ 封禁菜单",
                    f"{orion_unban_triggers} - Orion QQ 解封菜单",
                ]
            )
        if self._can_use_group_permission(group_id, qqid, "白名单&管理员检测权限"):
            options.append(
                (
                    f"{' / '.join(self.get_group_checker_menu_triggers(group_id))} - "
                    "白名单&管理员检测管理菜单"
                )
            )
        if self.task_system is not None and self._can_use_group_permission(
            group_id,
            qqid,
            "任务系统权限",
        ):
            options.append(
                f"{' / '.join(self.get_group_task_menu_triggers(group_id))} - 任务系统管理菜单"
            )
        if self._can_use_group_permission(group_id, qqid, "领地系统权限"):
            options.append(
                (
                    f"{' / '.join(self.get_group_land_menu_triggers(group_id))} - "
                    "领地系统云链联动版管理菜单"
                )
            )
        if self._can_use_group_permission(group_id, qqid, "公会系统权限"):
            options.append(
                (
                    f"{' / '.join(self.get_group_guild_menu_triggers(group_id))} - "
                    "公会系统菜单（普通成员需绑定；管理员进入管理菜单）"
                )
            )
        if not options:
            self._reply_to_qq(group_id, qqid, "当前没有可展示的联动系统触发词")
            return
        self._reply_to_qq(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "联动系统触发词",
                options,
                ["公会系统普通菜单需要 QQ 绑定游戏账号，管理菜单需要本群管理员权限"],
                group_id,
            ),
        )

    def on_qq_player_list(self, group_id: int, _sender: int, _):
        """把在线玩家列表和可用 TPS 信息发到群里。"""
        if not self._can_use_group_permission(group_id, _sender, "查看玩家人数权限"):
            self._reply_menu_permission_denied(group_id, _sender)
            return
        group_cfg = self.group_cfgs[group_id]
        if not group_cfg["指令设置"]["是否允许查看玩家列表"]:
            self.sendmsg(group_id, "当前群未启用玩家列表查询")
            return
        players = [f"{i + 1}.{j}" for i,
                   j in enumerate(self.game_ctrl.allplayers)]
        fmt_msg = (
            f"在线玩家有 {len(players)} 人：\n "
            + "\n ".join(players)
            + (
                f"\n当前 TPS： {round(self.tps_calc.get_tps(), 1)}/20"
                if self.tps_calc
                else ""
            )
        )
        self.sendmsg(group_id, fmt_msg)

    def qq_inventory_menu(self, group_id: int, qqid: int):
        """分页展示在线玩家，并允许在群里进一步查询某个人的背包。"""
        if not self._can_use_group_permission(group_id, qqid, "查询背包权限"):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        online_names = list(self.game_ctrl.allplayers)
        if not online_names:
            self._reply_to_qq(group_id, qqid, "当前没有在线玩家")
            return
        page = 1
        per_page = self.get_group_inventory_items_per_page(group_id)
        while True:
            # 这里保留一个循环式菜单，避免每次翻页都重新走一遍入口指令。
            total_pages, start_index, end_index = (
                utils.paginate(len(online_names), per_page, page)
                if hasattr(utils, "paginate")
                else self.simple_paginate(len(online_names), per_page, page)
            )
            page_names = online_names[start_index - 1: end_index]
            text = self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "查询背包",
                page_names,
                [
                    f"当前第 {page}/{total_pages} 页",
                    f"输入 [1-{len(page_names)}] 之间的数字以选择 对应玩家",
                    "输入 - 转到上一页",
                    "输入 + 转到下一页",
                    "输入 正整数+页 转到对应页",
                    "输入 . 退出",
                ],
                group_id,
            )
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] {text}",
                do_remove_cq_code=False)
            user_input = self.waitMsg(qqid, timeout=120, group_id=group_id)
            if user_input is None:
                self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
                return
            user_input = user_input.strip()
            if self._is_menu_exit(user_input, group_id):
                self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
                return
            if user_input == "+":
                # 菜单保持在同一条交互链里，翻页只改当前页码。
                if page < total_pages:
                    page += 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是最后一页啦~")
                continue
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是第一页啦~")
                continue
            if page_num := self.parse_page_jump(user_input):
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self._reply_to_qq(
                        group_id,
                        qqid,
                        f"❀ 不存在第 {page_num} 页！请重新输入！",
                    )
                continue
            choice = self.parse_displayed_menu_choice(
                user_input, len(page_names))
            if choice is None:
                self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
                continue
            self.show_player_inventory(group_id, qqid, page_names[choice - 1])
            return

    @staticmethod
    def simple_paginate(total_len: int, per_page: int, page: int):
        """在缺少 utils.paginate 时使用的本地分页兜底实现。"""
        total_pages = max(1, (total_len + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start_index = (page - 1) * per_page + 1
        end_index = min(page * per_page, total_len)
        return total_pages, start_index, end_index

    @staticmethod
    def parse_displayed_menu_choice(user_input: str, displayed_count: int):
        """Parse a choice using the numbers shown on the current menu page."""
        choice = utils.try_int(user_input.strip().strip("[]"))
        if choice is None or choice not in range(1, displayed_count + 1):
            return None
        return choice

    @staticmethod
    def parse_page_jump(user_input: str):
        """Parse page jumps only when the input explicitly ends with a page suffix."""
        text = user_input.strip()
        if len(text) < 2 or text[-1] not in ("页", "頁", "椤"):
            return None
        return utils.try_int(text[:-1])

    def show_player_inventory(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """把背包槽位整理成适合群聊阅读的文本。"""
        player_obj = self.game_ctrl.players.getPlayerByName(player_name)
        if player_obj is None:
            self._reply_to_qq(group_id, qqid, f"玩家 {player_name} 当前已不在线")
            return
        try:
            inventory = player_obj.queryInventory()
        except Exception as err:
            self._reply_to_qq(group_id, qqid, f"查询背包失败: {err}")
            return
        items: list[str] = []
        for idx, slot in enumerate(inventory.slots):
            if slot is None:
                continue
            # 这里把原始槽位信息尽量整理成适合群内阅读的文本。
            item_id = getattr(slot, "id", "未知ID")
            display_name = self.translate_item_name(item_id)
            stack_size = getattr(slot, "stackSize", 0)
            aux = getattr(slot, "aux", 0)
            line = f"槽位 {idx}: {display_name} x{stack_size}"
            if display_name != item_id:
                line += f" ({item_id})"
            if aux not in (None, -1, 0):
                line += f" (数据值:{aux})"
            custom_name = self.get_item_custom_name(slot)
            if custom_name:
                line += f" (命名:{custom_name})"
            ench_text = self.get_item_enchantments_text(slot)
            if ench_text:
                line += f" (附魔:{ench_text})"
            items.append(line)
        if not items:
            items = ["该玩家背包为空"]
        text = self.plugin_ui_menu(
            "群服互通云链版Ultra版",
            f"背包查询 - {player_name}",
            items,
            ["输入 . 退出"],
            group_id,
        )
        self.sendmsg(
            group_id,
            f"[CQ:at,qq={qqid}] {text}",
            do_remove_cq_code=False)

    def ensure_task_system(self, group_id: int, sender: int):
        """Implement the ensure task system operation."""
        if self.task_system is None:
            self._reply_to_qq(group_id, sender, "相关插件未安装：任务系统云链联动版")
            return False
        return self.ensure_linked_plugin_enabled(
            self.task_system, group_id, sender)

    @staticmethod
    def _format_task_time(timestamp: int):
        """Implement the format task time operation."""
        try:
            return time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(timestamp))
        except Exception:
            return str(timestamp)

    @staticmethod
    def _format_task_label(task_info: dict[str, Any]):
        """Implement the format task label operation."""
        show_name = str(task_info.get("show_name", "")).strip()
        tag_name = str(task_info.get("tag_name", "")).strip()
        if not show_name or show_name == tag_name:
            return tag_name or show_name or "<未知任务>"
        return f"{show_name} ({tag_name})"

    def _format_task_menu_item(self, task_info: dict[str, Any], status: str):
        """Implement the format task menu item operation."""
        label = self._format_task_label(task_info)
        lines = [f"{status} {label}"]
        description = str(task_info.get("description", "")).strip()
        if description:
            lines.append(f"  {description}")
        if "finished_time" in task_info:
            try:
                finished_time = self._format_task_time(
                    int(task_info["finished_time"]))
            except Exception:
                finished_time = str(task_info.get("finished_time", "未知时间"))
            lines.append(f"  完成时间：{finished_time}")
        return "\n".join(lines)

    def _format_task_progress_text(
            self, progress: dict[str, Any], group_id: int):
        """Implement the format task progress text operation."""
        in_progress = progress.get("in_progress", [])
        completed = progress.get("completed", [])
        options = []
        if in_progress:
            for task_info in in_progress:
                options.append(self._format_task_menu_item(task_info, "未完成"))
        else:
            options.append("未完成任务：无")
        if completed:
            for task_info in completed:
                options.append(self._format_task_menu_item(task_info, "已完成"))
        else:
            options.append("已完成任务：无")
        player_name = progress.get("player_name", "<未知玩家>")
        return self.plugin_ui_menu(
            "群服互通云链版Ultra版",
            f"任务进度 - {player_name}",
            options,
            [
                f"未完成任务：{len(in_progress)} 个",
                f"已完成任务：{len(completed)} 个",
                "输入 . 退出",
            ],
            group_id,
        )

    def qq_task_system_menu(self, group_id: int, qqid: int):
        """Handle the qq task system menu QQ menu operation."""
        if not self._can_use_group_permission(group_id, qqid, "任务系统权限"):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        if not self.ensure_task_system(group_id, qqid):
            return
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "任务系统菜单",
                ["查看在线玩家任务进度", "给在线玩家下发任务", "直接完成在线玩家任务"],
                ["输入 [1-3] 之间的数字以选择 对应功能", "输入 . 退出"],
                group_id,
            ),
            timeout=120,
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时，已退出菜单")
            return
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        if choice == "1":
            player_name = self.qq_select_online_player(
                group_id, qqid, "查看任务进度")
            if player_name is None:
                return
            self.on_qq_task_progress(group_id, qqid, [player_name])
            return
        if choice == "2":
            player_name = self.qq_select_online_player(group_id, qqid, "下发任务")
            if player_name is None:
                return
            quest_tag = self.qq_select_task_from_catalog(group_id, qqid)
            if quest_tag is None:
                return
            self.on_qq_task_add(group_id, qqid, [player_name, quest_tag])
            return
        if choice == "3":
            player_name = self.qq_select_online_player(group_id, qqid, "完成任务")
            if player_name is None:
                return
            quest_tag = self.qq_select_in_progress_task(
                group_id, qqid, player_name)
            if quest_tag is None:
                return
            self.on_qq_task_finish(group_id, qqid, [player_name, quest_tag])
            return
        self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")

    def qq_select_online_player(self, group_id: int, qqid: int, subtitle: str):
        """Handle the qq select online player QQ menu operation."""
        online_names = list(self.game_ctrl.allplayers)
        if not online_names:
            self._reply_to_qq(group_id, qqid, "当前没有在线玩家")
            return None
        page = 1
        per_page = self.get_group_task_player_items_per_page(group_id)
        while True:
            total_pages, start_index, end_index = (
                utils.paginate(len(online_names), per_page, page)
                if hasattr(utils, "paginate")
                else self.simple_paginate(len(online_names), per_page, page)
            )
            page_names = online_names[start_index - 1: end_index]
            text = self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                f"任务系统 - {subtitle}",
                page_names,
                [
                    f"当前第 {page}/{total_pages} 页",
                    f"输入 [1-{len(page_names)}] 之间的数字以选择 对应玩家",
                    "输入 - 转到上一页",
                    "输入 + 转到下一页",
                    "输入 正整数+页 转到对应页",
                    "输入 . 退出",
                ],
                group_id,
            )
            user_input = self.qq_prompt(group_id, qqid, text, timeout=120)
            if user_input is None:
                self._reply_to_qq(group_id, qqid, "❀ 回复超时，已退出菜单")
                return None
            if self._is_menu_exit(user_input, group_id):
                self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
                return None
            if user_input == "+":
                if page < total_pages:
                    page += 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是最后一页啦~")
                continue
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是第一页啦~")
                continue
            if page_num := self.parse_page_jump(user_input):
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self._reply_to_qq(group_id, qqid, f"❀ 不存在第 {page_num} 页")
                continue
            choice = self.parse_displayed_menu_choice(
                user_input, len(page_names))
            if choice is None:
                self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
                continue
            return page_names[choice - 1]

    def qq_select_task_from_catalog(self, group_id: int, qqid: int):
        """Handle the qq select task from catalog QQ menu operation."""
        quests = self.task_system.list_available_quests()
        if not quests:
            self._reply_to_qq(group_id, qqid, "任务系统中暂无可用任务")
            return None
        page = 1
        per_page = self.get_group_task_items_per_page(group_id)
        while True:
            total_pages, start_index, end_index = (
                utils.paginate(len(quests), per_page, page)
                if hasattr(utils, "paginate")
                else self.simple_paginate(len(quests), per_page, page)
            )
            page_quests = quests[start_index - 1: end_index]
            options = []
            for quest_info in page_quests:
                label = self._format_task_label(quest_info)
                description = str(quest_info.get("description", "")).strip()
                options.append(
                    label if not description else f"{label}\n  {description}")
            text = self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "任务系统 - 选择任务",
                options,
                [
                    f"当前第 {page}/{total_pages} 页",
                    f"输入 [1-{len(page_quests)}] 之间的数字以选择 对应任务",
                    "输入 - 转到上一页",
                    "输入 + 转到下一页",
                    "输入 正整数+页 转到对应页",
                    "输入 . 退出",
                ],
                group_id,
            )
            user_input = self.qq_prompt(group_id, qqid, text, timeout=120)
            if user_input is None:
                self._reply_to_qq(group_id, qqid, "❀ 回复超时，已退出菜单")
                return None
            if self._is_menu_exit(user_input, group_id):
                self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
                return None
            if user_input == "+":
                if page < total_pages:
                    page += 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是最后一页啦~")
                continue
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是第一页啦~")
                continue
            if page_num := self.parse_page_jump(user_input):
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self._reply_to_qq(group_id, qqid, f"❀ 不存在第 {page_num} 页")
                continue
            choice = self.parse_displayed_menu_choice(
                user_input, len(page_quests))
            if choice is None:
                self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
                continue
            return page_quests[choice - 1]["tag_name"]

    def qq_select_in_progress_task(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq select in progress task QQ menu operation."""
        ok, result = self.task_system.get_online_player_task_progress(
            player_name)
        if not ok:
            self._reply_to_qq(group_id, qqid, str(result))
            return None
        in_progress = result.get("in_progress", [])
        if not in_progress:
            self._reply_to_qq(group_id, qqid, f"玩家 {player_name} 当前没有进行中的任务")
            return None
        options = []
        for task_info in in_progress:
            label = self._format_task_label(task_info)
            description = str(task_info.get("description", "")).strip()
            options.append(
                label if not description else f"{label}\n  {description}")
        text = self.plugin_ui_menu(
            "群服互通云链版Ultra版",
            f"任务系统 - 完成任务 - {player_name}",
            options,
            [f"输入 [1-{len(options)}] 之间的数字以选择 对应任务", "输入 . 退出"],
            group_id,
        )
        user_input = self.qq_prompt(group_id, qqid, text, timeout=120)
        if user_input is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时，已退出菜单")
            return None
        if self._is_menu_exit(user_input, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        choice = self.parse_displayed_menu_choice(user_input, len(options))
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return None
        return in_progress[choice - 1]["tag_name"]

    def on_qq_task_progress(self, group_id: int, sender: int, args: list[str]):
        """Implement the on qq task progress operation."""
        if not self._can_use_group_permission(group_id, sender, "任务系统权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_task_system(group_id, sender):
            return
        ok, result = self.task_system.get_online_player_task_progress(args[0])
        if not ok:
            self._reply_to_qq(group_id, sender, str(result))
            return
        self._reply_to_qq(
            group_id,
            sender,
            self._format_task_progress_text(result, group_id),
        )

    def on_qq_task_add(self, group_id: int, sender: int, args: list[str]):
        """Implement the on qq task add operation."""
        if not self._can_use_group_permission(group_id, sender, "任务系统权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_task_system(group_id, sender):
            return
        player_name = args[0]
        quest_query = " ".join(args[1:]).strip()
        ok, msg = self.task_system.add_quest_to_online_player(
            player_name, quest_query)
        self._reply_result(group_id, sender, ok, msg)

    def on_qq_task_finish(self, group_id: int, sender: int, args: list[str]):
        """Implement the on qq task finish operation."""
        if not self._can_use_group_permission(group_id, sender, "任务系统权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_task_system(group_id, sender):
            return
        player_name = args[0]
        quest_query = " ".join(args[1:]).strip()
        ok, msg = self.task_system.finish_quest_for_online_player(
            player_name, quest_query
        )
        self._reply_result(group_id, sender, ok, msg)

    def ensure_guild_system(self, group_id: int, sender: int):
        """检查公会系统云链联动版 API 是否可用。"""
        if self.guild_system is None:
            self._reply_to_qq(group_id, sender, "相关插件未安装：公会系统云链联动版")
            return False
        return self.ensure_linked_plugin_enabled(
            self.guild_system, group_id, sender)

    @staticmethod
    def _guild_actor(group_id: int, qqid: int):
        """Implement the guild actor operation."""
        return f"QQ群{group_id}:{qqid}"

    def _qq_guild_prompt(
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        options: list[str],
        hints: list[str],
    ):
        """Implement the qq guild prompt operation."""
        return self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "公会系统云链联动版",
                subtitle,
                options,
                hints,
                group_id,
            ),
            timeout=120,
        )

    def _qq_guild_prompt_text(
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        prompt: str,
        allow_empty: bool = False,
    ):
        """Implement the qq guild prompt text operation."""
        value = self._qq_guild_prompt(
            group_id, qqid, subtitle, [], [
                prompt, "输入 . 退出"])
        if value is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return None
        value = value.strip()
        if self._is_menu_exit(value, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        if not allow_empty and not value:
            self._reply_to_qq(group_id, qqid, "❀ 输入不能为空")
            return None
        return value

    def _qq_guild_prompt_optional_query(
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        prompt: str,
    ):
        """Implement the qq guild prompt optional query operation."""
        value = self._qq_guild_prompt_text(
            group_id, qqid, subtitle, prompt, allow_empty=True)
        if value is None:
            return None
        if value in ("", "全部", "全服", "all", "*", "-"):
            return ""
        return value

    def _qq_guild_prompt_int(
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        prompt: str,
        minimum: int | None = None,
        default: int | None = None,
    ):
        """Implement the qq guild prompt int operation."""
        hints = [prompt, "输入 . 退出"]
        if default is not None:
            hints.insert(1, f"输入 默认 使用 {default}")
        value = self._qq_guild_prompt(group_id, qqid, subtitle, [], hints)
        if value is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return None
        value = value.strip()
        if self._is_menu_exit(value, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        if default is not None and value in ("", "默认", "default"):
            return default
        parsed = utils.try_int(value)
        if parsed is None:
            self._reply_to_qq(group_id, qqid, "❀ 请输入整数")
            return None
        if minimum is not None and parsed < minimum:
            self._reply_to_qq(group_id, qqid, f"❀ 数值不能小于 {minimum}")
            return None
        return parsed

    def _qq_guild_confirm(
            self,
            group_id: int,
            qqid: int,
            subtitle: str,
            detail: str):
        """Implement the qq guild confirm operation."""
        choice = self._qq_guild_prompt(
            group_id,
            qqid,
            subtitle,
            [detail],
            ["请输入 确认 继续执行", "输入 . 取消"],
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已取消")
            return False
        choice = choice.strip()
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已取消")
            return False
        if choice != "确认":
            self._reply_to_qq(group_id, qqid, "❀ 已取消")
            return False
        return True

    def _reply_guild_api_result(self, group_id: int, qqid: int, result):
        """Implement the reply guild api result operation."""
        if not isinstance(result, tuple) or not result:
            self._reply_to_qq(group_id, qqid, "公会系统接口返回异常")
            return
        ok = bool(result[0])
        msg = str(
            result[1]) if len(result) >= 2 else (
            "操作成功" if ok else "操作失败")
        if len(result) >= 3 and isinstance(result[2], str) and result[2]:
            msg = f"{msg}\n{result[2]}"
        self._reply_result(group_id, qqid, ok, msg)

    @staticmethod
    def _format_guild_base(base: dict[str, Any] | None):
        """Implement the format guild base operation."""
        if not base:
            return "未设置"
        return f"{
            base.get(
                'dimension',
                0)} ({
            base.get(
                'x',
                0):.1f}, {
                    base.get(
                        'y',
                        0):.1f}, {
                            base.get(
                                'z',
                                0):.1f})"

    @staticmethod
    def _format_guild_line(item: dict[str, Any], index: int):
        """Implement the format guild line operation."""
        frozen = " 冻结" if item.get("frozen") else ""
        return (
            f"{index}. {item.get('name', '<未知>')} Lv.{item.get('level', 0)} "
            f"成员 {item.get('member_count', 0)}/{item.get('max_members', 0)} "
            f"会长 {item.get('owner', '<未知>')}{frozen}"
        )

    def _format_guild_summary(self, guild: dict[str, Any], group_id: int):
        """Implement the format guild summary operation."""
        effects = guild.get("purchased_effects", {})
        effect_text = "无"
        if isinstance(effects, dict) and effects:
            effect_text = "、".join(
                f"{key}:{level}" for key,
                level in effects.items())
        return self.plugin_ui_menu(
            "公会系统云链联动版",
            f"公会信息 - {guild.get('name', '<未知>')}",
            [
                f"ID：{guild.get('guild_id', '<未知>')}",
                f"会长：{guild.get('owner', '<未知>')}",
                f"等级/经验：{guild.get('level', 0)} / {guild.get('exp', 0)}",
                f"成员：{guild.get('member_count', 0)}/{guild.get('max_members', 0)}",
                f"仓库：{guild.get('vault_count', 0)}/{guild.get('vault_capacity', 0)}",
                f"资金：{guild.get('funds', 0)}",
                f"据点：{self._format_guild_base(guild.get('base'))}",
                f"据点锁定：{'是' if guild.get('base_locked') else '否'}",
                f"冻结：{'是' if guild.get('frozen') else '否'}",
                f"冻结原因：{guild.get('frozen_reason') or '无'}",
                (
                    f"活跃/完成任务：{guild.get('active_tasks', 0)} / "
                    f"{guild.get('completed_tasks', 0)}"
                ),
                f"总贡献：{guild.get('total_contribution', 0)}",
                f"效果：{effect_text}",
                f"公告：{guild.get('announcement') or '无'}",
            ],
            ["输入 . 退出"],
            group_id,
        )

    def _reply_guild_lines(
        self,
        group_id: int,
        qqid: int,
        title: str,
        lines: list[str],
        hints: list[str] | None = None,
    ):
        """Implement the reply guild lines operation."""
        self._reply_to_qq(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "公会系统云链联动版",
                title,
                lines or ["暂无数据"],
                hints or ["输入 . 退出"],
                group_id,
            ),
        )

    def _qq_guild_run_menu(
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        options: list[str],
        actions: list[Any],
        allow_back: bool = False,
    ):
        """Implement the qq guild run menu operation."""
        if len(options) != len(actions):
            self._reply_to_qq(group_id, qqid, "❀ 菜单配置错误")
            return None
        hints = [f"输入 [1-{len(options)}] 之间的数字以选择 对应功能"]
        if allow_back:
            hints.append("输入 0 返回上级菜单")
        hints.append("输入 . 退出")
        choice = self._qq_guild_prompt(
            group_id,
            qqid,
            subtitle,
            options,
            hints,
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return None
        choice = choice.strip()
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        if allow_back and self._is_menu_back(choice, group_id):
            return "back"
        selected = self.parse_displayed_menu_choice(choice, len(options))
        if selected is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return None
        return actions[selected - 1]()

    def qq_guild_entry_menu(self, group_id: int, qqid: int):
        """公会系统统一入口：群管理员进管理菜单，普通成员进绑定账号菜单。"""
        if self._can_use_group_permission(group_id, qqid, "公会系统权限"):
            self.qq_guild_system_menu(group_id, qqid)
            return
        self.qq_guild_player_menu(group_id, qqid)

    def _qq_guild_select_bound_player(self, group_id: int, qqid: int):
        """选择一个 QQ 已绑定的游戏账号，返回玩家名。"""
        bound_players = self.api_get_bound_players_by_qq(qqid)
        usable_players = [
            item
            for item in bound_players
            if str(item.get("player_name", "")).strip()
        ]
        if not usable_players:
            bind_hint = " / ".join(self.get_group_binding_triggers(group_id))
            if not self.api_is_binding_enabled(group_id):
                self._reply_to_qq(
                    group_id,
                    qqid,
                    "请先绑定游戏账号后再使用公会菜单；当前群的 QQ 绑定功能未开启，请联系管理员。",
                )
                return None
            self._reply_to_qq(
                group_id,
                qqid,
                f"请先绑定游戏账号后再使用公会菜单。绑定触发词：{bind_hint}",
            )
            return None
        if len(usable_players) == 1:
            return str(usable_players[0].get("player_name", "")).strip()

        options = [
            f"{item.get('player_name', '<未知玩家>')} ({item.get('xuid', '<未知XUID>')})"
            for item in usable_players
        ]
        choice = self._qq_guild_prompt(
            group_id,
            qqid,
            "选择绑定账号",
            options,
            [f"输入 [1-{len(options)}] 之间的数字以选择 游戏账号", "输入 . 退出"],
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return None
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        selected = self.parse_displayed_menu_choice(choice, len(options))
        if selected is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return None
        return str(usable_players[selected - 1].get("player_name", "")).strip()

    def _qq_guild_player_state(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Implement the qq guild player state operation."""
        result = self.guild_system.api_get_player_guild_menu_state(player_name)
        if not isinstance(result, tuple) or len(result) < 3:
            self._reply_to_qq(group_id, qqid, "公会系统接口返回异常")
            return None
        ok, msg, state = result
        if not ok or not isinstance(state, dict):
            self._reply_result(group_id, qqid, bool(ok), str(msg))
            return None
        return state

    def qq_guild_player_menu(self, group_id: int, qqid: int):  # skipcq: PY-R1000
        """普通群成员可使用的公会菜单，要求 QQ 已绑定游戏账号。"""
        if not self.ensure_guild_system(group_id, qqid):
            return
        player_name = self._qq_guild_select_bound_player(group_id, qqid)
        if not player_name:
            return
        while True:
            state = self._qq_guild_player_state(group_id, qqid, player_name)
            if state is None:
                return
            if state.get("in_guild"):
                guild = state.get("guild") if isinstance(
                    state.get("guild"), dict) else {}
                member = state.get("member") if isinstance(
                    state.get("member"), dict) else {}
                permissions = set(state.get("permissions") or [])
                is_owner = bool(state.get("is_owner"))
                is_frozen = bool(state.get("is_frozen"))
                subtitle = (
                    f"玩家菜单 - {player_name} | {guild.get('name', '<未知公会>')} "
                    f"({member.get('rank_name', member.get('rank', '成员'))})"
                )
                options = [
                    "我的公会信息",
                    "查看成员列表",
                    "查看公会日志",
                    "查看公会公告",
                    "查看公会排行",
                    "查看贡献排行",
                ]
                actions = [
                    lambda: self.qq_guild_player_show_self(
                        group_id, qqid, player_name),
                    lambda: self.qq_guild_player_show_members(
                        group_id, qqid, player_name),
                    lambda: self.qq_guild_player_show_logs(
                        group_id, qqid, player_name),
                    lambda: self.qq_guild_player_show_announcement(
                        group_id, qqid, player_name),
                    lambda: self.qq_guild_show_rankings(group_id, qqid),
                    lambda: self.qq_guild_show_donation_rankings(
                        group_id, qqid),]
                if not is_frozen:
                    if "announce" in permissions:
                        options.append("设置公会公告")
                        actions.append(
                            lambda: self.qq_guild_player_set_announcement(
                                group_id, qqid, player_name))
                    if "vault" in permissions:
                        options.append("查看公会仓库")
                        actions.append(lambda: self.qq_guild_player_show_vault(
                            group_id, qqid, player_name))
                    options.append("查看公会任务")
                    actions.append(lambda: self.qq_guild_player_show_tasks(
                        group_id, qqid, player_name))
                    options.append("参与公会任务")
                    actions.append(lambda: self.qq_guild_player_join_task(
                        group_id, qqid, player_name))
                    if "return_base" in permissions:
                        options.append("返回公会据点")
                        actions.append(
                            lambda: self.qq_guild_player_return_base(
                                group_id, qqid, player_name))
                    if not is_owner:
                        options.append("退出公会")
                        actions.append(lambda: self.qq_guild_player_leave(
                            group_id, qqid, player_name))
                if is_owner and not is_frozen:
                    options.append("解散我的公会")
                    actions.append(lambda: self.qq_guild_player_disband(
                        group_id, qqid, player_name))
            else:
                subtitle = f"玩家菜单 - {player_name} | 未加入公会"
                options = ["查看公会列表", "申请加入公会", "查看公会排行", "查看贡献排行"]
                actions = [
                    lambda: self.qq_guild_list(group_id, qqid),
                    lambda: self.qq_guild_player_request_join(
                        group_id, qqid, player_name
                    ),
                    lambda: self.qq_guild_show_rankings(group_id, qqid),
                    lambda: self.qq_guild_show_donation_rankings(group_id, qqid),
                ]
            result = self._qq_guild_run_menu(
                group_id, qqid, subtitle, options, actions)
            if result == "back":
                continue
            return

    def qq_guild_player_show_self(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player show self QQ menu operation."""
        state = self._qq_guild_player_state(group_id, qqid, player_name)
        if state is None:
            return
        guild = state.get("guild") if isinstance(
            state.get("guild"), dict) else {}
        member = state.get("member") if isinstance(
            state.get("member"), dict) else {}
        if not guild:
            self._reply_to_qq(group_id, qqid, f"{player_name} 暂未加入公会")
            return
        self._reply_guild_lines(
            group_id,
            qqid,
            f"我的公会 - {player_name}",
            [
                f"公会：{guild.get('name', '<未知>')} ({guild.get('guild_id', '<未知>')})",
                f"职位：{member.get('rank_name', member.get('rank', '<未知>'))}",
                f"贡献：{member.get('contribution', 0)}",
                f"会长：{guild.get('owner', '<未知>')}",
                f"等级/经验：{guild.get('level', 0)} / {guild.get('exp', 0)}",
                f"成员：{guild.get('member_count', 0)}/{guild.get('max_members', 0)}",
                f"仓库：{guild.get('vault_count', 0)}/{guild.get('vault_capacity', 0)}",
                f"据点：{self._format_guild_base(guild.get('base'))}",
                f"冻结：{'是' if guild.get('frozen') else '否'}",
                f"公告：{guild.get('announcement') or '无'}",
            ],
        )

    def qq_guild_player_show_members(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player show members QQ menu operation."""
        state = self._qq_guild_player_state(group_id, qqid, player_name)
        if state is None:
            return
        guild = state.get("guild") if isinstance(
            state.get("guild"), dict) else {}
        guild_id = str(guild.get("guild_id", "")).strip()
        if not guild_id:
            self._reply_to_qq(group_id, qqid, "你尚未加入任何公会")
            return
        ok, msg, data = self.guild_system.api_get_guild(guild_id)
        if not ok or not data:
            self._reply_result(group_id, qqid, False, msg)
            return
        members = data.get("members", [])
        lines = []
        for index, member in enumerate(members[:30], start=1):
            rank = member.get("rank_name", member.get("rank", "成员"))
            name = member.get("name", "<未知>")
            contribution = member.get("contribution", 0)
            lines.append(f"{index}. {rank} {name} 贡献 {contribution}")
        self._reply_guild_lines(
            group_id, qqid, f"{
                data.get(
                    'name', guild_id)} 成员", lines or ["暂无成员"], [
                f"共 {
                    len(members)} 名成员"])

    def qq_guild_player_show_logs(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player show logs QQ menu operation."""
        ok, msg, data = self.guild_system.api_get_own_guild_logs(
            player_name, 20)
        if not ok or not data:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = [str(item) for item in data.get("logs", [])[-20:]]
        audit_logs = data.get("audit_logs", [])
        if audit_logs:
            lines.append("--- 审计日志 ---")
            for item in audit_logs[-10:]:
                action = item.get("action", "<未知>")
                actor = item.get("actor", "")
                target = item.get("target", "")
                detail = item.get("detail", "")
                lines.append(f"{action} {actor} -> {target} {detail}".strip())
        self._reply_guild_lines(
            group_id, qqid, f"{player_name} 的公会日志", lines or ["暂无日志"])

    def qq_guild_player_show_announcement(
            self, group_id: int, qqid: int, player_name: str):
        """Handle the qq guild player show announcement QQ menu operation."""
        state = self._qq_guild_player_state(group_id, qqid, player_name)
        if state is None:
            return
        guild = state.get("guild") if isinstance(
            state.get("guild"), dict) else {}
        if not guild:
            self._reply_to_qq(group_id, qqid, "你尚未加入任何公会")
            return
        self._reply_guild_lines(
            group_id,
            qqid,
            f"{guild.get('name', '<未知公会>')} 公告",
            [guild.get("announcement") or "当前没有公告"],
        )

    def qq_guild_player_set_announcement(
            self, group_id: int, qqid: int, player_name: str):
        """Handle the qq guild player set announcement QQ menu operation."""
        text = self._qq_guild_prompt_text(
            group_id, qqid, "设置公会公告", "请输入新的公告内容（不超过200字符）")
        if text is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_announcement_as_player(
                player_name, text), )

    def qq_guild_player_show_vault(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player show vault QQ menu operation."""
        ok, msg, data = self.guild_system.api_get_own_guild_vault(player_name)
        if not ok or data is None:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = []
        for index, item in enumerate(data[:30], start=1):
            item_index = item.get("index", index)
            item_id = item.get("item_id", "<未知>")
            count = item.get("count", 0)
            price = item.get("price", 0)
            seller = item.get("seller", "<未知>")
            lines.append(f"{item_index}. {item_id} x{count} 价格 {price} 卖家 {seller}")
        self._reply_guild_lines(group_id, qqid, msg, lines or ["仓库为空"])

    def qq_guild_player_show_tasks(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player show tasks QQ menu operation."""
        ok, msg, data = self.guild_system.api_get_own_guild_tasks(player_name)
        if not ok or data is None:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = []
        for index, task in enumerate(data[:30], start=1):
            status = "已完成" if task.get("completed") else f"进行中 {task.get(
                'current_count', 0)} /{task.get('target_count', 0)} "
            joined = " 已参与" if player_name in task.get(
                "participants", []) else ""
            lines.append(
                f"{index}. {
                    task.get(
                        'name',
                        '<未知任务>')} [{status}{joined}] 奖励 {
                    task.get(
                        'reward_contribution',
                        0)}贡献/{
                    task.get(
                        'reward_exp',
                        0)}经验")
        self._reply_guild_lines(group_id, qqid, msg, lines or ["暂无任务"])

    def qq_guild_player_join_task(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player join task QQ menu operation."""
        ok, msg, data = self.guild_system.api_get_own_guild_tasks(player_name)
        if not ok or data is None:
            self._reply_result(group_id, qqid, False, msg)
            return
        active_tasks = [task for task in data if not task.get("completed")]
        if not active_tasks:
            self._reply_to_qq(group_id, qqid, "暂无可参与的任务")
            return
        options = [
            (
                f"{task.get('name', '<未知任务>')} "
                f"({task.get('current_count', 0)}/{task.get('target_count', 0)})"
            )
            for task in active_tasks[:20]
        ]
        choice = self._qq_guild_prompt(
            group_id,
            qqid,
            "参与公会任务",
            options,
            [f"输入 [1-{len(options)}] 之间的数字以选择 任务", "输入 . 退出"],
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        selected = self.parse_displayed_menu_choice(choice, len(options))
        if selected is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return
        task = active_tasks[selected - 1]
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_join_guild_task_as_player(
                player_name,
                task.get("task_id") or task.get("name", ""),
            ),
        )

    def qq_guild_player_return_base(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player return base QQ menu operation."""
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_return_to_guild_base_as_player(player_name),
        )

    def qq_guild_player_request_join(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player request join QQ menu operation."""
        guild = self._qq_guild_prompt_text(
            group_id, qqid, "申请加入公会", "请输入公会名称或ID")
        if guild is None:
            return
        reason = self._qq_guild_prompt_text(
            group_id,
            qqid,
            "申请加入公会",
            "请输入申请理由，可输入 无 跳过",
            allow_empty=True,
        )
        if reason is None:
            return
        if reason == "无":
            reason = ""
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_request_join_guild_as_player(
                player_name, guild, reason),
        )

    def qq_guild_player_leave(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player leave QQ menu operation."""
        if not self._qq_guild_confirm(
                group_id, qqid, "退出公会", f"{player_name} 将退出当前公会"):
            return
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_leave_guild_as_player(player_name),
        )

    def qq_guild_player_disband(
            self,
            group_id: int,
            qqid: int,
            player_name: str):
        """Handle the qq guild player disband QQ menu operation."""
        if not self._qq_guild_confirm(
            group_id,
            qqid,
            "解散公会",
                f"{player_name} 将解散自己担任会长的公会"):
            return
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_disband_owned_guild_as_player(player_name),
        )

    def qq_guild_system_menu(self, group_id: int, qqid: int):
        """在群里打开公会系统云链联动版管理菜单。"""
        if not self._can_use_group_permission(group_id, qqid, "公会系统权限"):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        if not self.ensure_guild_system(group_id, qqid):
            return
        while True:
            result = self._qq_guild_run_menu(
                group_id,
                qqid,
                "管理菜单",
                ["查询与排行", "公会与成员管理", "仓库与效果管理", "任务与据点管理", "数据维护与活动"],
                [
                    lambda: self.qq_guild_query_menu(group_id, qqid),
                    lambda: self.qq_guild_member_manage_menu(group_id, qqid),
                    lambda: self.qq_guild_vault_effect_menu(group_id, qqid),
                    lambda: self.qq_guild_task_base_menu(group_id, qqid),
                    lambda: self.qq_guild_data_activity_menu(group_id, qqid),
                ],
            )
            if result == "back":
                continue
            return

    def qq_guild_query_menu(self, group_id: int, qqid: int):
        """Handle the qq guild query menu QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "公会系统权限"):
            return
        if not self.ensure_guild_system(group_id, qqid):
            return
        self._qq_guild_run_menu(
            group_id,
            qqid,
            "查询与排行",
            [
                "查看公会列表",
                "查看公会信息",
                "查看公会成员",
                "查看公会仓库",
                "查看公会日志",
                "查询玩家公会记录",
                "查看系统统计",
                "查看公会排行",
                "查看贡献排行",
                "查看异常交易",
            ],
            [
                lambda: self.qq_guild_list(group_id, qqid),
                lambda: self.qq_guild_show_info(group_id, qqid),
                lambda: self.qq_guild_show_members(group_id, qqid),
                lambda: self.qq_guild_show_vault(group_id, qqid),
                lambda: self.qq_guild_show_logs(group_id, qqid),
                lambda: self.qq_guild_show_player_record(group_id, qqid),
                lambda: self.qq_guild_show_statistics(group_id, qqid),
                lambda: self.qq_guild_show_rankings(group_id, qqid),
                lambda: self.qq_guild_show_donation_rankings(group_id, qqid),
                lambda: self.qq_guild_show_abnormal_trades(group_id, qqid),
            ],
            allow_back=True,
        )

    def qq_guild_member_manage_menu(self, group_id: int, qqid: int):
        """Handle the qq guild member manage menu QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "公会系统权限"):
            return
        if not self.ensure_guild_system(group_id, qqid):
            return
        self._qq_guild_run_menu(
            group_id,
            qqid,
            "公会与成员管理",
            [
                "强制解散公会",
                "修改公会名称",
                "设置公会等级",
                "设置公会经验",
                "转让公会会长",
                "强制玩家加入公会",
                "强制玩家退出公会",
                "冻结公会",
                "解冻公会",
                "调整公会资金",
                "设置公会资金",
                "调整成员贡献",
                "设置成员贡献",
                "清空公会贡献",
                "发送全服公会公告",
            ],
            [
                lambda: self.qq_guild_force_disband(group_id, qqid),
                lambda: self.qq_guild_rename(group_id, qqid),
                lambda: self.qq_guild_set_level(group_id, qqid),
                lambda: self.qq_guild_set_exp(group_id, qqid),
                lambda: self.qq_guild_transfer_owner(group_id, qqid),
                lambda: self.qq_guild_force_join(group_id, qqid),
                lambda: self.qq_guild_force_leave(group_id, qqid),
                lambda: self.qq_guild_set_frozen(group_id, qqid, True),
                lambda: self.qq_guild_set_frozen(group_id, qqid, False),
                lambda: self.qq_guild_add_funds(group_id, qqid),
                lambda: self.qq_guild_set_funds(group_id, qqid),
                lambda: self.qq_guild_add_member_contribution(group_id, qqid),
                lambda: self.qq_guild_set_member_contribution(group_id, qqid),
                lambda: self.qq_guild_reset_contributions(group_id, qqid),
                lambda: self.qq_guild_broadcast_announcement(group_id, qqid),
            ],
            allow_back=True,
        )

    def qq_guild_vault_effect_menu(self, group_id: int, qqid: int):
        """Handle the qq guild vault effect menu QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "公会系统权限"):
            return
        if not self.ensure_guild_system(group_id, qqid):
            return
        self._qq_guild_run_menu(
            group_id,
            qqid,
            "仓库与效果管理",
            [
                "备份公会仓库",
                "清空公会仓库",
                "删除仓库物品",
                "回滚仓库备份",
                "导出仓库数据",
                "重置市场价格",
                "清空公会效果",
                "设置公会效果",
            ],
            [
                lambda: self.qq_guild_backup_vault(group_id, qqid),
                lambda: self.qq_guild_clear_vault(group_id, qqid),
                lambda: self.qq_guild_delete_vault_item(group_id, qqid),
                lambda: self.qq_guild_rollback_vault(group_id, qqid),
                lambda: self.qq_guild_export_vault(group_id, qqid),
                lambda: self.qq_guild_reset_market_prices(group_id, qqid),
                lambda: self.qq_guild_clear_effects(group_id, qqid),
                lambda: self.qq_guild_set_effect(group_id, qqid),
            ],
            allow_back=True,
        )

    def qq_guild_task_base_menu(self, group_id: int, qqid: int):
        """Handle the qq guild task base menu QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "公会系统权限"):
            return
        if not self.ensure_guild_system(group_id, qqid):
            return
        self._qq_guild_run_menu(
            group_id,
            qqid,
            "任务与据点管理",
            [
                "刷新公会任务",
                "创建全服任务",
                "删除公会任务",
                "重置任务进度",
                "强制完成任务",
                "传送玩家到公会据点",
                "删除公会据点",
                "设置公会据点",
                "锁定公会据点",
                "解锁公会据点",
            ],
            [
                lambda: self.qq_guild_refresh_tasks(group_id, qqid),
                lambda: self.qq_guild_create_global_task(group_id, qqid),
                lambda: self.qq_guild_delete_task(group_id, qqid),
                lambda: self.qq_guild_reset_task(group_id, qqid),
                lambda: self.qq_guild_complete_task(group_id, qqid),
                lambda: self.qq_guild_teleport_base(group_id, qqid),
                lambda: self.qq_guild_delete_base(group_id, qqid),
                lambda: self.qq_guild_set_base(group_id, qqid),
                lambda: self.qq_guild_set_base_locked(group_id, qqid, True),
                lambda: self.qq_guild_set_base_locked(group_id, qqid, False),
            ],
            allow_back=True,
        )

    def qq_guild_data_activity_menu(self, group_id: int, qqid: int):
        """Handle the qq guild data activity menu QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "公会系统权限"):
            return
        if not self.ensure_guild_system(group_id, qqid):
            return
        self._qq_guild_run_menu(
            group_id, qqid, "数据维护与活动",
            ["重载公会配置", "保存公会数据", "备份公会数据", "修复公会数据", "查看活动状态", "开启双倍经验",
             "开启双倍贡献", "开启公会争霸", "停止活动", "结算排行奖励",],
            [lambda: self._reply_guild_api_result(
                group_id, qqid, self.guild_system.api_reload_guild_config()),
             lambda: self._reply_guild_api_result(
                 group_id, qqid, self.guild_system.api_save_guild_data()),
             lambda: self._reply_guild_api_result(
                 group_id, qqid, self.guild_system.api_backup_guild_data()),
             lambda: self._reply_guild_api_result(
                 group_id, qqid, self.guild_system.api_repair_guild_data(
                     self._guild_actor(group_id, qqid))),
             lambda: self.qq_guild_show_activity_status(group_id, qqid),
             lambda: self.qq_guild_start_activity(
                 group_id, qqid, "exp", 2.0),
             lambda: self.qq_guild_start_activity(
                 group_id, qqid, "contribution", 2.0),
             lambda: self.qq_guild_start_activity(
                 group_id, qqid, "contest", 1.0),
             lambda: self.qq_guild_stop_activity(group_id, qqid),
             lambda: self.qq_guild_settle_rewards(group_id, qqid),],
            allow_back=True,)

    def qq_guild_list(self, group_id: int, qqid: int):
        """Handle the qq guild list QQ menu operation."""
        ok, msg, guilds = self.guild_system.api_list_guilds()
        if not ok:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = [self._format_guild_line(item, index)
                 for index, item in enumerate(guilds[:20], start=1)]
        self._reply_guild_lines(group_id, qqid, msg, lines or ["暂无公会"])

    def qq_guild_show_info(self, group_id: int, qqid: int):
        """Handle the qq guild show info QQ menu operation."""
        query = self._qq_guild_prompt_text(
            group_id, qqid, "查看公会信息", "请输入公会名称或ID")
        if query is None:
            return
        ok, msg, data = self.guild_system.api_get_guild(query)
        self._reply_to_qq(group_id, qqid, self._format_guild_summary(
            data, group_id) if ok and data else msg)

    def qq_guild_show_members(self, group_id: int, qqid: int):
        """Handle the qq guild show members QQ menu operation."""
        query = self._qq_guild_prompt_text(
            group_id, qqid, "查看公会成员", "请输入公会名称或ID")
        if query is None:
            return
        ok, msg, data = self.guild_system.api_get_guild(query)
        if not ok or not data:
            self._reply_result(group_id, qqid, False, msg)
            return
        members = data.get("members", [])
        lines = []
        for index, member in enumerate(members[:30], start=1):
            rank = member.get("rank_name", member.get("rank", "成员"))
            name = member.get("name", "<未知>")
            contribution = member.get("contribution", 0)
            lines.append(f"{index}. {rank} {name} 贡献 {contribution}")
        self._reply_guild_lines(
            group_id, qqid, f"{
                data.get(
                    'name', query)} 成员", lines or ["暂无成员"], [
                f"共 {
                    len(members)} 名成员"])

    def qq_guild_show_vault(self, group_id: int, qqid: int):
        """Handle the qq guild show vault QQ menu operation."""
        query = self._qq_guild_prompt_text(
            group_id, qqid, "查看公会仓库", "请输入公会名称或ID")
        if query is None:
            return
        ok, msg, data = self.guild_system.api_get_guild_vault(query)
        if not ok or data is None:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = []
        for index, item in enumerate(data[:30], start=1):
            item_index = item.get("index", index)
            item_id = item.get("item_id", "<未知>")
            count = item.get("count", 0)
            price = item.get("price", 0)
            seller = item.get("seller", "<未知>")
            lines.append(f"{item_index}. {item_id} x{count} 价格 {price} 卖家 {seller}")
        self._reply_guild_lines(group_id, qqid, msg, lines or ["仓库为空"])

    def qq_guild_show_logs(self, group_id: int, qqid: int):
        """Handle the qq guild show logs QQ menu operation."""
        query = self._qq_guild_prompt_text(
            group_id, qqid, "查看公会日志", "请输入公会名称或ID")
        if query is None:
            return
        limit = self._qq_guild_prompt_int(
            group_id, qqid, "查看公会日志", "请输入日志数量", minimum=1, default=10)
        if limit is None:
            return
        ok, msg, data = self.guild_system.api_get_guild_logs(query, limit)
        if not ok or not data:
            self._reply_result(group_id, qqid, False, msg)
            return
        logs = [str(item) for item in data.get("logs", [])]
        logs = logs[-int(limit):]
        self._reply_guild_lines(
            group_id,
            qqid,
            f"{query} 日志",
            logs or ["暂无日志"])

    def qq_guild_show_player_record(self, group_id: int, qqid: int):
        """Handle the qq guild show player record QQ menu operation."""
        player_name = self._qq_guild_prompt_text(
            group_id, qqid, "查询玩家公会记录", "请输入玩家名")
        if player_name is None:
            return
        ok, msg, data = self.guild_system.api_get_player_record(player_name)
        if not ok or not data:
            self._reply_result(group_id, qqid, False, msg)
            return
        member = data.get("member", {})
        guild = data.get("guild", {})
        self._reply_guild_lines(
            group_id,
            qqid,
            f"玩家记录 - {member.get('name', player_name)}",
            [
                f"所属公会：{guild.get('name', '<未知>')}",
                f"职位：{member.get('rank_name', member.get('rank', '<未知>'))}",
                f"贡献：{member.get('contribution', 0)}",
                f"相关审计：{len(data.get('audit_logs', []))} 条",
                f"仓库交易：{len(data.get('vault_trade_logs', []))} 条",
            ],
        )

    def qq_guild_show_statistics(self, group_id: int, qqid: int):
        """Handle the qq guild show statistics QQ menu operation."""
        ok, msg, data = self.guild_system.api_get_guild_statistics()
        if not ok:
            self._reply_result(group_id, qqid, False, msg)
            return
        self._reply_guild_lines(
            group_id,
            qqid,
            "公会系统统计",
            [
                f"公会：{data.get('guild_count', 0)}",
                f"成员：{data.get('member_count', 0)}",
                f"仓库物品：{data.get('vault_item_count', 0)}",
                f"任务：{data.get('task_count', 0)}",
                f"活跃任务：{data.get('active_task_count', 0)}",
                f"冻结公会：{data.get('frozen_guild_count', 0)}",
            ],
        )

    def qq_guild_show_rankings(self, group_id: int, qqid: int):
        """Handle the qq guild show rankings QQ menu operation."""
        sort_choice = self._qq_guild_prompt(
            group_id,
            qqid,
            "查看公会排行",
            ["等级", "成员", "贡献", "活跃"],
            ["输入 [1-4] 之间的数字以选择 排行类型", "输入 . 退出"],
        )
        if sort_choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(sort_choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        sort_map = {
            "1": "level",
            "2": "members",
            "3": "contribution",
            "4": "activity"}
        sort_by = sort_map.get(sort_choice.strip())
        if sort_by is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return
        ok, msg, data = self.guild_system.api_get_guild_rankings(sort_by, 10)
        if not ok:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = [
            f"{
                item.get(
                    'rank', index)}. {
                item.get(
                    'name', '<未知>')} 分值 {
                        item.get(
                            'score', 0)} 会长 {
                                item.get(
                                    'owner', '<未知>')}" for index, item in enumerate(
                                        data, start=1)]
        self._reply_guild_lines(group_id, qqid, msg, lines or ["暂无排行"])

    def qq_guild_show_donation_rankings(self, group_id: int, qqid: int):
        """Handle the qq guild show donation rankings QQ menu operation."""
        query = self._qq_guild_prompt_optional_query(
            group_id, qqid, "查看贡献排行", "请输入公会名/ID，输入 全部 查看全服")
        if query is None:
            return
        ok, msg, data = self.guild_system.api_get_donation_rankings(
            query or None, 10)
        if not ok:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = [
            f"{index}. {
                item.get(
                    'player_name',
                    '<未知>')} {
                item.get(
                    'guild_name',
                    '<未知>')} 贡献 {
                        item.get(
                            'contribution',
                            0)}" for index,
            item in enumerate(
                data,
                start=1)]
        self._reply_guild_lines(group_id, qqid, msg, lines or ["暂无排行"])

    def qq_guild_show_abnormal_trades(self, group_id: int, qqid: int):
        """Handle the qq guild show abnormal trades QQ menu operation."""
        query = self._qq_guild_prompt_optional_query(
            group_id, qqid, "查看异常交易", "请输入公会名/ID，输入 全部 查看全服")
        if query is None:
            return
        ok, msg, data = self.guild_system.api_get_abnormal_trades(
            query or None)
        if not ok:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = []
        for item in data[:20]:
            guild_name = item.get("guild_name", "<未知>")
            item_id = item.get("item_id", "<未知>")
            count = item.get("count", 0)
            price = item.get("price", 0)
            ratio = item.get("ratio", 0)
            lines.append(f"{guild_name} {item_id} x{count} 价格 {price} 倍率 {ratio}")
        self._reply_guild_lines(group_id, qqid, msg, lines or ["暂无异常交易"])

    def _qq_guild_prompt_guild(self, group_id: int, qqid: int, subtitle: str):
        """Implement the qq guild prompt guild operation."""
        return self._qq_guild_prompt_text(
            group_id, qqid, subtitle, "请输入公会名称或ID")

    def qq_guild_force_disband(self, group_id: int, qqid: int):
        """Handle the qq guild force disband QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "强制解散公会")
        if guild is None:
            return
        if not self._qq_guild_confirm(
                group_id, qqid, "强制解散公会", f"即将解散公会：{guild}"):
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_force_disband_guild(
                guild, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_rename(self, group_id: int, qqid: int):
        """Handle the qq guild rename QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "修改公会名称")
        if guild is None:
            return
        new_name = self._qq_guild_prompt_text(
            group_id, qqid, "修改公会名称", "请输入新公会名")
        if new_name is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_rename_guild(
                guild, new_name, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_set_level(self, group_id: int, qqid: int):
        """Handle the qq guild set level QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "设置公会等级")
        if guild is None:
            return
        level = self._qq_guild_prompt_int(
            group_id, qqid, "设置公会等级", "请输入等级", minimum=1)
        if level is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_guild_level(
                guild, level, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_set_exp(self, group_id: int, qqid: int):
        """Handle the qq guild set exp QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "设置公会经验")
        if guild is None:
            return
        exp = self._qq_guild_prompt_int(
            group_id, qqid, "设置公会经验", "请输入经验值", minimum=0)
        if exp is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_guild_exp(
                guild, exp, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_transfer_owner(self, group_id: int, qqid: int):
        """Handle the qq guild transfer owner QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "转让公会会长")
        if guild is None:
            return
        player = self._qq_guild_prompt_text(
            group_id, qqid, "转让公会会长", "请输入新会长玩家名")
        if player is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_transfer_guild_owner(
                guild, player, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_force_join(self, group_id: int, qqid: int):
        """Handle the qq guild force join QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "强制玩家加入公会")
        if guild is None:
            return
        player = self._qq_guild_prompt_text(
            group_id, qqid, "强制玩家加入公会", "请输入玩家名")
        if player is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_force_join_guild(
                guild, player, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_force_leave(self, group_id: int, qqid: int):
        """Handle the qq guild force leave QQ menu operation."""
        player = self._qq_guild_prompt_text(
            group_id, qqid, "强制玩家退出公会", "请输入玩家名")
        if player is None:
            return
        if not self._qq_guild_confirm(
            group_id,
            qqid,
            "强制玩家退出公会",
                f"即将移出玩家：{player}"):
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_force_leave_guild(
                player, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_set_frozen(self, group_id: int, qqid: int, frozen: bool):
        """Handle the qq guild set frozen QQ menu operation."""
        title = "冻结公会" if frozen else "解冻公会"
        guild = self._qq_guild_prompt_guild(group_id, qqid, title)
        if guild is None:
            return
        reason = ""
        if frozen:
            reason = self._qq_guild_prompt_text(
                group_id, qqid, title, "请输入冻结原因，可输入 无", allow_empty=True)
            if reason is None:
                return
            if reason == "无":
                reason = ""
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_guild_frozen(
                guild, frozen, reason, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_add_funds(self, group_id: int, qqid: int):
        """Handle the qq guild add funds QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "调整公会资金")
        if guild is None:
            return
        amount = self._qq_guild_prompt_int(
            group_id, qqid, "调整公会资金", "请输入调整数量，可为负数")
        if amount is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_add_guild_funds(
                guild, amount, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_set_funds(self, group_id: int, qqid: int):
        """Handle the qq guild set funds QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "设置公会资金")
        if guild is None:
            return
        amount = self._qq_guild_prompt_int(
            group_id, qqid, "设置公会资金", "请输入资金余额", minimum=0)
        if amount is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_guild_funds(
                guild, amount, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_add_member_contribution(self, group_id: int, qqid: int):
        """Handle the qq guild add member contribution QQ menu operation."""
        player = self._qq_guild_prompt_text(group_id, qqid, "调整成员贡献", "请输入玩家名")
        if player is None:
            return
        amount = self._qq_guild_prompt_int(
            group_id, qqid, "调整成员贡献", "请输入调整数量，可为负数")
        if amount is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_add_member_contribution(
                player, amount, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_set_member_contribution(self, group_id: int, qqid: int):
        """Handle the qq guild set member contribution QQ menu operation."""
        player = self._qq_guild_prompt_text(group_id, qqid, "设置成员贡献", "请输入玩家名")
        if player is None:
            return
        amount = self._qq_guild_prompt_int(
            group_id, qqid, "设置成员贡献", "请输入贡献值", minimum=0)
        if amount is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_member_contribution(
                player, amount, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_reset_contributions(self, group_id: int, qqid: int):
        """Handle the qq guild reset contributions QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "清空公会贡献")
        if guild is None:
            return
        if not self._qq_guild_confirm(
                group_id, qqid, "清空公会贡献", f"即将清空公会贡献：{guild}"):
            return
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_reset_guild_contributions(
                guild,
                self._guild_actor(
                    group_id,
                    qqid)))

    def qq_guild_broadcast_announcement(self, group_id: int, qqid: int):
        """Handle the qq guild broadcast announcement QQ menu operation."""
        message = self._qq_guild_prompt_text(
            group_id, qqid, "发送全服公会公告", "请输入公告内容")
        if message is None:
            return
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_broadcast_guild_announcement(
                message,
                self._guild_actor(
                    group_id,
                    qqid)))

    def qq_guild_backup_vault(self, group_id: int, qqid: int):
        """Handle the qq guild backup vault QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "备份公会仓库")
        if guild is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_backup_guild_vault(
                guild, "qq", self._guild_actor(
                    group_id, qqid)))

    def qq_guild_clear_vault(self, group_id: int, qqid: int):
        """Handle the qq guild clear vault QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "清空公会仓库")
        if guild is None:
            return
        if not self._qq_guild_confirm(
                group_id, qqid, "清空公会仓库", f"即将清空仓库：{guild}"):
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_clear_guild_vault(
                guild, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_delete_vault_item(self, group_id: int, qqid: int):
        """Handle the qq guild delete vault item QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "删除仓库物品")
        if guild is None:
            return
        index = self._qq_guild_prompt_int(
            group_id, qqid, "删除仓库物品", "请输入仓库序号", minimum=1)
        if index is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_delete_guild_vault_item(
                guild, index, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_rollback_vault(self, group_id: int, qqid: int):
        """Handle the qq guild rollback vault QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "回滚仓库备份")
        if guild is None:
            return
        index = self._qq_guild_prompt_int(
            group_id, qqid, "回滚仓库备份", "请输入备份序号", minimum=1, default=1)
        if index is None:
            return
        if not self._qq_guild_confirm(
            group_id,
            qqid,
            "回滚仓库备份",
                f"即将回滚 {guild} 的仓库备份 {index}"):
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_rollback_guild_vault(
                guild, index, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_export_vault(self, group_id: int, qqid: int):
        """Handle the qq guild export vault QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "导出仓库数据")
        if guild is None:
            return
        ok, msg, data = self.guild_system.api_export_guild_vault(guild)
        if not ok or not data:
            self._reply_result(group_id, qqid, False, msg)
            return
        items = data.get("vault_items", [])
        trade_logs = data.get("vault_trade_logs", [])
        self._reply_guild_lines(
            group_id,
            qqid,
            msg,
            [f"仓库物品：{len(items)} 件", f"交易日志：{len(trade_logs)} 条"],
        )

    def qq_guild_reset_market_prices(self, group_id: int, qqid: int):
        """Handle the qq guild reset market prices QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "重置市场价格")
        if guild is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_reset_market_prices(
                guild, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_clear_effects(self, group_id: int, qqid: int):
        """Handle the qq guild clear effects QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "清空公会效果")
        if guild is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_clear_guild_effects(
                guild, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_set_effect(self, group_id: int, qqid: int):
        """Handle the qq guild set effect QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "设置公会效果")
        if guild is None:
            return
        effect = self._qq_guild_prompt_text(
            group_id, qqid, "设置公会效果", "请输入效果ID或名称")
        if effect is None:
            return
        level = self._qq_guild_prompt_int(
            group_id, qqid, "设置公会效果", "请输入效果等级，0 表示移除", minimum=0)
        if level is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_guild_effect(
                guild, effect, level, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_refresh_tasks(self, group_id: int, qqid: int):
        """Handle the qq guild refresh tasks QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "刷新公会任务")
        if guild is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_refresh_guild_tasks(
                guild, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_create_global_task(self, group_id: int, qqid: int):
        """Handle the qq guild create global task QQ menu operation."""
        name = self._qq_guild_prompt_text(group_id, qqid, "创建全服任务", "请输入任务名称")
        if name is None:
            return
        task_type = self._qq_guild_prompt_text(
            group_id, qqid, "创建全服任务", "请输入任务类型，如 trade/collect/kill/build")
        if task_type is None:
            return
        target = self._qq_guild_prompt_text(
            group_id, qqid, "创建全服任务", "请输入任务目标")
        if target is None:
            return
        target_count = self._qq_guild_prompt_int(
            group_id, qqid, "创建全服任务", "请输入目标数量", minimum=1)
        if target_count is None:
            return
        reward_exp = self._qq_guild_prompt_int(
            group_id, qqid, "创建全服任务", "请输入经验奖励", minimum=0, default=0)
        if reward_exp is None:
            return
        reward_contribution = self._qq_guild_prompt_int(
            group_id, qqid, "创建全服任务", "请输入贡献奖励", minimum=0, default=0)
        if reward_contribution is None:
            return
        description = self._qq_guild_prompt_text(
            group_id, qqid, "创建全服任务", "请输入任务描述，可输入 默认", allow_empty=True)
        if description is None:
            return
        if description == "默认":
            description = name
        deadline = self._qq_guild_prompt_int(
            group_id, qqid, "创建全服任务", "请输入截止秒数，0 表示无限期", minimum=0, default=0)
        if deadline is None:
            return
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_create_global_task(
                name,
                task_type,
                target,
                target_count,
                reward_exp,
                reward_contribution,
                description,
                deadline,
                self._guild_actor(group_id, qqid),
            ),
        )

    def qq_guild_delete_task(self, group_id: int, qqid: int):
        """Handle the qq guild delete task QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "删除公会任务")
        if guild is None:
            return
        task = self._qq_guild_prompt_text(
            group_id, qqid, "删除公会任务", "请输入任务ID或名称")
        if task is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_delete_guild_task(
                guild, task, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_reset_task(self, group_id: int, qqid: int):
        """Handle the qq guild reset task QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "重置任务进度")
        if guild is None:
            return
        task = self._qq_guild_prompt_text(
            group_id, qqid, "重置任务进度", "请输入任务ID或名称")
        if task is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_reset_guild_task_progress(
                guild, task, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_complete_task(self, group_id: int, qqid: int):
        """Handle the qq guild complete task QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "强制完成任务")
        if guild is None:
            return
        task = self._qq_guild_prompt_text(
            group_id, qqid, "强制完成任务", "请输入任务ID或名称")
        if task is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_force_complete_guild_task(
                guild, task, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_teleport_base(self, group_id: int, qqid: int):
        """Handle the qq guild teleport base QQ menu operation."""
        player = self._qq_guild_prompt_text(
            group_id, qqid, "传送玩家到公会据点", "请输入玩家名")
        if player is None:
            return
        guild = self._qq_guild_prompt_optional_query(
            group_id, qqid, "传送玩家到公会据点", "请输入公会名/ID，输入 全部 使用玩家所在公会")
        if guild is None:
            return
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_teleport_player_to_guild_base(
                player,
                guild or None))

    def qq_guild_delete_base(self, group_id: int, qqid: int):
        """Handle the qq guild delete base QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "删除公会据点")
        if guild is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_delete_guild_base(
                guild, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_set_base(self, group_id: int, qqid: int):
        """Handle the qq guild set base QQ menu operation."""
        guild = self._qq_guild_prompt_guild(group_id, qqid, "设置公会据点")
        if guild is None:
            return
        dimension = self._qq_guild_prompt_int(
            group_id, qqid, "设置公会据点", "请输入维度ID")
        if dimension is None:
            return
        x = self._qq_guild_prompt_text(group_id, qqid, "设置公会据点", "请输入 x 坐标")
        if x is None:
            return
        y = self._qq_guild_prompt_text(group_id, qqid, "设置公会据点", "请输入 y 坐标")
        if y is None:
            return
        z = self._qq_guild_prompt_text(group_id, qqid, "设置公会据点", "请输入 z 坐标")
        if z is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_guild_base(
                guild, dimension, x, y, z, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_set_base_locked(self, group_id: int, qqid: int, locked: bool):
        """Handle the qq guild set base locked QQ menu operation."""
        title = "锁定公会据点" if locked else "解锁公会据点"
        guild = self._qq_guild_prompt_guild(group_id, qqid, title)
        if guild is None:
            return
        self._reply_guild_api_result(
            group_id, qqid, self.guild_system.api_set_guild_base_locked(
                guild, locked, self._guild_actor(
                    group_id, qqid)))

    def qq_guild_show_activity_status(self, group_id: int, qqid: int):
        """Handle the qq guild show activity status QQ menu operation."""
        ok, msg, data = self.guild_system.api_get_guild_activity_status()
        if not ok:
            self._reply_result(group_id, qqid, False, msg)
            return
        lines = []
        for key, event in data.items():
            lines.append(
                f"{key}: 倍率 {
                    event.get(
                        'multiplier',
                        1)} 剩余 {
                    event.get(
                        'remaining_seconds',
                        0)} 秒 发起 {
                    event.get(
                        'actor',
                        '<未知>')}")
        self._reply_guild_lines(group_id, qqid, msg, lines or ["暂无活动"])

    def qq_guild_start_activity(
            self,
            group_id: int,
            qqid: int,
            activity: str,
            multiplier: float):
        """Handle the qq guild start activity QQ menu operation."""
        duration = self._qq_guild_prompt_int(
            group_id, qqid, "开启公会活动", "请输入持续秒数", minimum=1, default=3600)
        if duration is None:
            return
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_start_guild_activity(
                activity,
                duration,
                multiplier,
                self._guild_actor(
                    group_id,
                    qqid)))

    def qq_guild_stop_activity(self, group_id: int, qqid: int):
        """Handle the qq guild stop activity QQ menu operation."""
        choice = self._qq_guild_prompt(
            group_id,
            qqid,
            "停止活动",
            ["双倍经验", "双倍贡献", "公会争霸"],
            ["输入 [1-3] 之间的数字以选择 活动", "输入 . 退出"],
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        activity = {
            "1": "exp",
            "2": "contribution",
            "3": "contest"}.get(
            choice.strip())
        if activity is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return
        self._reply_guild_api_result(
            group_id, qqid,
            self.guild_system.api_stop_guild_activity(activity))

    def qq_guild_settle_rewards(self, group_id: int, qqid: int):
        """Handle the qq guild settle rewards QQ menu operation."""
        sort_by = self._qq_guild_prompt_text(
            group_id, qqid, "结算排行奖励",
            "请输入排行类型：level/members/contribution/activity")
        if sort_by is None:
            return
        top = self._qq_guild_prompt_int(
            group_id, qqid, "结算排行奖励", "请输入结算名次", minimum=1, default=3)
        if top is None:
            return
        reward_exp = self._qq_guild_prompt_int(
            group_id, qqid, "结算排行奖励", "请输入经验奖励", minimum=0, default=0)
        if reward_exp is None:
            return
        reward_funds = self._qq_guild_prompt_int(
            group_id, qqid, "结算排行奖励", "请输入资金奖励", minimum=0, default=0)
        if reward_funds is None:
            return
        self._reply_guild_api_result(
            group_id,
            qqid,
            self.guild_system.api_settle_guild_ranking_rewards(
                sort_by,
                top,
                reward_exp,
                reward_funds,
                self._guild_actor(
                    group_id,
                    qqid)))

    def ensure_land_system(self, group_id: int, sender: int):
        """检查领地系统云链联动版 API 是否可用。"""
        if self.land_system is None:
            self._reply_to_qq(group_id, sender, "相关插件未安装：领地系统云链联动版")
            return False
        return self.ensure_linked_plugin_enabled(
            self.land_system, group_id, sender)

    def _format_land_summary(self, land: dict[str, Any], group_id: int):
        """Implement the format land summary operation."""
        center = land.get("center", (0, 0, 0))
        admins = "、".join(land.get("admins", [])) or "无"
        members = "、".join(land.get("members", [])) or "无"
        return self.plugin_ui_menu(
            "领地系统云链联动版",
            f"领地信息 - {land.get('name', '<未知>')}",
            [
                f"领主：{land.get('owner', '<未知>')}",
                f"中心：{center[0]}, {center[1]}, {center[2]}",
                f"范围：{land.get('range_text', '<未知>')}",
                f"管理员：{admins}",
                f"成员：{members}",
            ],
            ["输入 . 退出"],
            group_id,
        )

    def _qq_land_prompt(
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        options: list[str],
        hints: list[str],
    ):
        """Implement the qq land prompt operation."""
        return self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "领地系统云链联动版",
                subtitle,
                options,
                hints,
                group_id,
            ),
            timeout=120,
        )

    def qq_land_system_menu(self, group_id: int, qqid: int):
        """在群里打开领地系统云链联动版管理菜单。"""
        if not self._can_use_group_permission(group_id, qqid, "领地系统权限"):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        if not self.ensure_land_system(group_id, qqid):
            return
        choice = self._qq_land_prompt(
            group_id,
            qqid,
            "管理菜单",
            [
                "查看领地列表",
                "查看领地信息",
                "新增玩家领地",
                "删除玩家领地",
                "添加领地成员",
                "移除领地成员",
                "添加领地管理员",
                "移除领地管理员",
                "修改领地所有者",
                "修改领地中心点",
                "修改领地范围",
            ],
            ["输入 [1-11] 之间的数字以选择 对应功能", "输入 . 退出"],
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        handler_map = {
            "1": self.qq_land_list,
            "2": self.qq_land_show_info,
            "3": self.qq_land_add,
            "4": self.qq_land_delete,
            "5": lambda gid,
            qid: self.qq_land_member_action(
                gid,
                qid,
                is_add=True,
                rank="member"),
            "6": lambda gid,
            qid: self.qq_land_member_action(
                gid,
                qid,
                is_add=False,
                rank="member"),
            "7": lambda gid,
            qid: self.qq_land_member_action(
                gid,
                qid,
                is_add=True,
                rank="admin"),
            "8": lambda gid,
            qid: self.qq_land_member_action(
                gid,
                qid,
                is_add=False,
                rank="admin"),
            "9": self.qq_land_transfer_owner,
            "10": self.qq_land_update_center,
            "11": self.qq_land_update_range,
        }
        handler = handler_map.get(choice)
        if handler is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return
        handler(group_id, qqid)

    def qq_land_list(self, group_id: int, qqid: int):  # skipcq: PY-R1000
        """Handle the qq land list QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "领地系统权限"):
            return
        if not self.ensure_land_system(group_id, qqid):
            return
        ok, msg, lands = self.land_system.api_list_lands()
        if not ok:
            self._reply_result(group_id, qqid, False, msg)
            return
        if not lands:
            self._reply_to_qq(group_id, qqid, "暂无任何领地")
            return
        page = 1
        per_page = self.get_group_land_items_per_page(group_id)
        while True:
            total_pages, start_index, end_index = (
                utils.paginate(len(lands), per_page, page)
                if hasattr(utils, "paginate")
                else self.simple_paginate(len(lands), per_page, page)
            )
            page_lands = lands[start_index - 1: end_index]
            text = self.plugin_ui_menu(
                "领地系统云链联动版",
                "领地列表",
                [
                    f"{land['name']} - 领主: {land['owner']}, {land['range_text']}"
                    for land in page_lands
                ],
                [
                    f"当前第 {page}/{total_pages} 页",
                    f"输入 [1-{len(page_lands)}] 之间的数字查看详情",
                    "输入 - 转到上一页",
                    "输入 + 转到下一页",
                    "输入 正整数+页 转到对应页",
                    "输入 . 退出",
                ],
                group_id,
            )
            user_input = self.qq_prompt(group_id, qqid, text, timeout=120)
            if user_input is None:
                self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
                return
            if self._is_menu_exit(user_input, group_id):
                self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
                return
            if user_input == "+":
                if page < total_pages:
                    page += 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是最后一页啦~")
                continue
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    self._reply_to_qq(group_id, qqid, "❀ 已经是第一页啦~")
                continue
            if page_num := self.parse_page_jump(user_input):
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self._reply_to_qq(group_id, qqid, f"❀ 不存在第 {page_num} 页")
                continue
            choice = self.parse_displayed_menu_choice(
                user_input, len(page_lands))
            if choice is None:
                self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
                continue
            self._reply_to_qq(
                group_id,
                qqid,
                self._format_land_summary(page_lands[choice - 1], group_id),
            )
            return

    def _qq_land_prompt_text(
            self,
            group_id: int,
            qqid: int,
            subtitle: str,
            prompt: str):
        """Implement the qq land prompt text operation."""
        value = self._qq_land_prompt(
            group_id, qqid, subtitle, [], [
                prompt, "输入 . 退出"])
        if value is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return None
        if self._is_menu_exit(value, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        return value

    @staticmethod
    def _parse_land_pos(raw: str):
        """Implement the parse land pos operation."""
        parts = raw.replace(",", " ").replace("，", " ").split()
        if len(parts) != 3:
            return None
        try:
            return (float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            return None

    @staticmethod
    def _parse_land_size(raw: str):
        """Implement the parse land size operation."""
        parts = raw.replace(",", " ").replace("，", " ").split()
        if len(parts) != 3:
            return None
        try:
            size = (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
        if any(value <= 0 for value in size):
            return None
        return size

    def qq_land_show_info(self, group_id: int, qqid: int):
        """Handle the qq land show info QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "领地系统权限"):
            return
        query = self._qq_land_prompt_text(group_id, qqid, "查看领地信息", "请输入领地名称")
        if query is None:
            return
        ok, msg, land = self.land_system.api_get_land(query)
        self._reply_to_qq(
            group_id,
            qqid,
            self._format_land_summary(land, group_id) if ok else msg,
        )

    def qq_land_add(self, group_id: int, qqid: int):
        """Handle the qq land add QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "领地系统权限"):
            return
        owner = self._qq_land_prompt_text(
            group_id, qqid, "新增玩家领地", "请输入领地主人玩家名")
        if owner is None:
            return
        name = self._qq_land_prompt_text(group_id, qqid, "新增玩家领地", "请输入领地名称")
        if name is None:
            return
        center_text = self._qq_land_prompt_text(
            group_id, qqid, "新增玩家领地", "请输入领地中心坐标，格式：x y z")
        if center_text is None:
            return
        center = self._parse_land_pos(center_text)
        if center is None:
            self._reply_to_qq(group_id, qqid, "❀ 坐标格式有误")
            return
        shape_choice = self._qq_land_prompt(
            group_id,
            qqid,
            "新增玩家领地",
            ["圆形领地", "方形领地"],
            ["输入 [1-2] 之间的数字以选择 领地类型", "输入 . 退出"],
        )
        if shape_choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(shape_choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        if shape_choice == "1":
            radius_text = self._qq_land_prompt_text(
                group_id, qqid, "新增圆形领地", "请输入领地半径")
            if radius_text is None:
                return
            try:
                radius = int(radius_text)
            except ValueError:
                self._reply_to_qq(group_id, qqid, "❀ 半径必须为整数")
                return
            ok, msg, _land = self.land_system.api_add_land(
                owner, name, center, "圆形", radius=radius)
        elif shape_choice == "2":
            size_text = self._qq_land_prompt_text(
                group_id, qqid, "新增方形领地", "请输入 长 高 宽")
            if size_text is None:
                return
            size = self._parse_land_size(size_text)
            if size is None:
                self._reply_to_qq(group_id, qqid, "❀ 方形尺寸格式有误")
                return
            ok, msg, _land = self.land_system.api_add_land(
                owner, name, center, "方形", size=size)
        else:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return
        self._reply_result(group_id, qqid, ok, msg)

    def qq_land_delete(self, group_id: int, qqid: int):
        """Handle the qq land delete QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "领地系统权限"):
            return
        query = self._qq_land_prompt_text(group_id, qqid, "删除玩家领地", "请输入领地名称")
        if query is None:
            return
        ok, msg, _data = self.land_system.api_delete_land(query)
        self._reply_result(group_id, qqid, ok, msg)

    def qq_land_member_action(
            self,
            group_id: int,
            qqid: int,
            is_add: bool,
            rank: str):
        """Handle the qq land member action QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "领地系统权限"):
            return
        title = "添加" if is_add else "移除"
        role = "管理员" if rank == "admin" else "成员"
        query = self._qq_land_prompt_text(
            group_id, qqid, f"{title}领地{role}", "请输入领地名称")
        if query is None:
            return
        player_name = self._qq_land_prompt_text(
            group_id, qqid, f"{title}领地{role}", "请输入玩家名称")
        if player_name is None:
            return
        if is_add:
            ok, msg, _land = self.land_system.api_add_member(
                query, player_name, rank=rank)
        elif rank == "admin":
            ok, msg, _land = self.land_system.api_set_member_rank(
                query, player_name, "member")
        else:
            ok, msg, _land = self.land_system.api_remove_member(
                query, player_name)
        self._reply_result(group_id, qqid, ok, msg)

    def qq_land_transfer_owner(self, group_id: int, qqid: int):
        """Handle the qq land transfer owner QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "领地系统权限"):
            return
        query = self._qq_land_prompt_text(group_id, qqid, "修改领地所有者", "请输入领地名称")
        if query is None:
            return
        owner = self._qq_land_prompt_text(
            group_id, qqid, "修改领地所有者", "请输入新所有者玩家名")
        if owner is None:
            return
        ok, msg, _land = self.land_system.api_transfer_owner(query, owner)
        self._reply_result(group_id, qqid, ok, msg)

    def qq_land_update_center(self, group_id: int, qqid: int):
        """Handle the qq land update center QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "领地系统权限"):
            return
        query = self._qq_land_prompt_text(group_id, qqid, "修改领地中心点", "请输入领地名称")
        if query is None:
            return
        center_text = self._qq_land_prompt_text(
            group_id, qqid, "修改领地中心点", "请输入新中心坐标，格式：x y z")
        if center_text is None:
            return
        center = self._parse_land_pos(center_text)
        if center is None:
            self._reply_to_qq(group_id, qqid, "❀ 坐标格式有误")
            return
        ok, msg, _land = self.land_system.api_update_land_center(query, center)
        self._reply_result(group_id, qqid, ok, msg)

    def qq_land_update_range(self, group_id: int, qqid: int):
        """Handle the qq land update range QQ menu operation."""
        if not self._ensure_group_permission(group_id, qqid, "领地系统权限"):
            return
        query = self._qq_land_prompt_text(group_id, qqid, "修改领地范围", "请输入领地名称")
        if query is None:
            return
        ok, msg, land = self.land_system.api_get_land(query)
        if not ok:
            self._reply_result(group_id, qqid, False, msg)
            return
        if land.get("shape") == "方形":
            size_text = self._qq_land_prompt_text(
                group_id, qqid, "修改方形领地范围", "请输入新的 长 高 宽")
            if size_text is None:
                return
            size = self._parse_land_size(size_text)
            if size is None:
                self._reply_to_qq(group_id, qqid, "❀ 方形尺寸格式有误")
                return
            ok, msg, _land = self.land_system.api_update_land_range(
                query, size=size)
        else:
            radius_text = self._qq_land_prompt_text(
                group_id, qqid, "修改圆形领地范围", "请输入新的半径")
            if radius_text is None:
                return
            try:
                radius = int(radius_text)
            except ValueError:
                self._reply_to_qq(group_id, qqid, "❀ 半径必须为整数")
                return
            ok, msg, _land = self.land_system.api_update_land_range(
                query, radius=radius)
        self._reply_result(group_id, qqid, ok, msg)

    @staticmethod
    def translate_item_name(item_id: str):
        """尽量把物品 ID 翻译成中文显示名，失败时退回原始 ID。"""
        if not isinstance(item_id, str) or item_id == "":
            return "未知物品"
        item_tail = item_id.split(":")[-1]
        if translate is None:
            return item_id
        for key in (f"item.{item_tail}.name", f"tile.{item_tail}.name"):
            try:
                translated = translate(key)
            except Exception:
                continue
            if isinstance(
                    translated,
                    str) and translated and translated != key:
                return translated
        return item_id

    @staticmethod
    def get_item_custom_name(slot: Any):
        """尝试从物品槽位对象里提取自定义名称。"""
        for attr in ("customName", "custom_name", "name"):
            value = getattr(slot, attr, None)
            if (
                isinstance(value, str)
                and value.strip()
                and value.strip() != getattr(slot, "id", "")
            ):
                return value.strip()
        return ""

    @staticmethod
    def get_item_enchantments_text(slot: Any):
        """把槽位上的附魔信息整理成单行文字。"""
        enchants = getattr(slot, "enchantments", None)
        if not isinstance(enchants, list) or not enchants:
            return ""
        outputs: list[str] = []
        for enchant in enchants:
            if enchant is None:
                continue
            name = getattr(enchant, "name", None)
            level = getattr(enchant, "level", None)
            if isinstance(name, str) and name.strip():
                if isinstance(level, int):
                    outputs.append(f"{name.strip()} {level}")
                else:
                    outputs.append(name.strip())
            else:
                etype = getattr(enchant, "type", None)
                if etype is not None:
                    if isinstance(level, int):
                        outputs.append(f"ID{etype} {level}")
                    else:
                        outputs.append(f"ID{etype}")
        return "、".join(outputs)

    def on_qq_add_admin(self, group_id: int, sender: int, args: list[str]):
        """给当前群添加普通管理员。"""
        if not self._can_use_group_permission(group_id, sender, "QQ普通管理员菜单权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        try:
            qqid = int(args[0])
        except (TypeError, ValueError):
            self._reply_to_qq(group_id, sender, "QQ号格式有误")
            return
        _ok, msg = self.add_group_role(group_id, qqid, is_super=False)
        self._reply_to_qq(group_id, sender, msg)

    def qq_admin_menu(self, group_id: int, qqid: int):
        """QQ群管理员菜单。

        可管理的层级由“权限设置”中的管理员菜单权限决定。
        """
        options = []
        actions = []
        if self._can_use_group_permission(group_id, qqid, "QQ普通管理员菜单权限"):
            options.append("普通管理员管理")
            actions.append(lambda: self.qq_admin_role_menu(
                group_id, qqid, is_super=False))
        if self._can_use_group_permission(group_id, qqid, "QQ超级管理员菜单权限"):
            options.append("超级管理员管理")
            actions.append(lambda: self.qq_admin_role_menu(
                group_id, qqid, is_super=True))
        if not options:
            self._reply_menu_permission_denied(group_id, qqid)
            return

        if len(options) == 1:
            actions[0]()
            return

        choice = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "QQ群管理员 管理菜单",
                options,
                [f"输入 [1-{len(options)}] 之间的数字以选择 对应功能", "输入 . 退出"],
                group_id,
            ),
            timeout=120,
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        choice = choice.strip()
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        selected = self.parse_displayed_menu_choice(choice, len(options))
        if selected is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return
        actions[selected - 1]()

    def qq_admin_role_menu(self, group_id: int, qqid: int, is_super: bool):
        """增删指定层级的群管理员。"""
        permission_name = "QQ超级管理员菜单权限" if is_super else "QQ普通管理员菜单权限"
        if not self._can_use_group_permission(group_id, qqid, permission_name):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        role_name = "超级管理员" if is_super else "普通管理员"
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                f"{role_name} 管理菜单",
                [f"添加{role_name}", f"删除{role_name}"],
                ["输入 [1-2] 之间的数字以选择 对应功能", "输入 . 退出"],
                group_id,
            ),
            timeout=120,
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        if choice not in ("1", "2"):
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return
        qq_text = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                f"{role_name} 管理菜单",
                [],
                [f"请输入要{'添加' if choice == '1' else '删除'}的 QQ 号", "输入 . 退出"],
                group_id,
            ),
            timeout=120,
        )
        if qq_text is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(qq_text, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        qqid_target = utils.try_int(qq_text)
        if qqid_target is None or qqid_target <= 0:
            self._reply_to_qq(group_id, qqid, "❀ QQ号格式有误")
            return
        if choice == "1":
            ok, msg = self.add_group_role(
                group_id, qqid_target, is_super=is_super)
        else:
            ok, msg = self.remove_group_role(
                group_id, qqid_target, is_super=is_super)
        self._reply_result(group_id, qqid, ok, msg)

    def ensure_whitelist_checker(self, group_id: int, sender: int):
        """检查白名单联动插件是否可用，避免菜单点进去后才报空引用。"""
        if self.whitelist_checker is None:
            self._reply_to_qq(group_id, sender, "相关插件未安装：白名单&管理员检测云链联动版")
            return False
        return self.ensure_linked_plugin_enabled(
            self.whitelist_checker, group_id, sender)

    def on_qq_whitelist_add(self, group_id: int, sender: int, args: list[str]):
        """通过群命令把玩家加入白名单。"""
        if not self._can_use_group_permission(group_id, sender, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.add_whitelist_player(args[0])
        self._reply_result(group_id, sender, ok, msg)

    def on_qq_whitelist_remove(
            self,
            group_id: int,
            sender: int,
            args: list[str]):
        """通过群命令把玩家移出白名单。"""
        if not self._can_use_group_permission(group_id, sender, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.remove_whitelist_player(args[0])
        self._reply_result(group_id, sender, ok, msg)

    def on_qq_server_admin_add(
            self,
            group_id: int,
            sender: int,
            args: list[str]):
        """通过群命令把玩家登记为服务器管理员。"""
        if not self._can_use_group_permission(group_id, sender, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.add_admin_player(args[0])
        self._reply_result(group_id, sender, ok, msg)

    def on_qq_server_admin_remove(
            self,
            group_id: int,
            sender: int,
            args: list[str]):
        """通过群命令把玩家从服务器管理员名单中移除。"""
        if not self._can_use_group_permission(group_id, sender, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.remove_admin_player(args[0])
        self._reply_result(group_id, sender, ok, msg)

    def on_qq_whitelist_toggle(
            self,
            group_id: int,
            sender: int,
            args: list[str]):
        """通过群命令切换白名单检测开关。"""
        if not self._can_use_group_permission(group_id, sender, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        action = args[0].strip()
        if action not in ("开启", "关闭", "on", "off"):
            self._reply_to_qq(group_id, sender, "参数错误，格式：白名单检测 [开启/关闭]")
            return
        ok, msg = self.whitelist_checker.set_whitelist_enabled(
            action in ("开启", "on"))
        self._reply_result(group_id, sender, ok, msg)

    def on_qq_admin_check_toggle(
            self,
            group_id: int,
            sender: int,
            args: list[str]):
        """通过群命令切换管理员检测开关。"""
        if not self._can_use_group_permission(group_id, sender, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        action = args[0].strip()
        if action not in ("开启", "关闭", "on", "off"):
            self._reply_to_qq(group_id, sender, "参数错误，格式：管理员检测 [开启/关闭]")
            return
        ok, msg = self.whitelist_checker.set_admin_check_enabled(
            action in ("开启", "on"))
        self._reply_result(group_id, sender, ok, msg)

    def on_qq_check_interval(
            self,
            group_id: int,
            sender: int,
            args: list[str]):
        """通过群命令修改联动插件的轮询周期。"""
        if not self._can_use_group_permission(group_id, sender, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        try:
            seconds = float(args[0])
        except (TypeError, ValueError):
            self._reply_to_qq(group_id, sender, "参数错误，格式：检测周期 [秒数]")
            return
        ok, msg = self.whitelist_checker.set_check_interval(seconds)
        self._reply_result(group_id, sender, ok, msg)

    def on_qq_check_status(self, group_id: int, sender: int, _args: list[str]):
        """把联动插件当前状态摘要发回群里。"""
        if not self._can_use_group_permission(group_id, sender, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, sender)
            return
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        status = self.whitelist_checker.get_runtime_status()
        output = (
            f"[CQ:at,qq={sender}] 白名单&管理员检测云链联动版状态：\n"
            f"检测周期：{status['check_interval']} 秒\n"
            f"白名单检测：{'开启' if status['whitelist_enabled'] else '关闭'}\n"
            f"白名单人数：{status['whitelist_count']}\n"
            f"管理员检测：{'开启' if status['admin_check_enabled'] else '关闭'}\n"
            f"管理员人数：{status['admin_count']}"
        )
        self.sendmsg(group_id, output, do_remove_cq_code=False)

    def _qq_checker_prompt(
        self,
        group_id: int,
        qqid: int,
        subtitle: str,
        options: list[str],
        hints: list[str],
    ):
        """统一构造白名单联动菜单提示并等待回复。"""
        return self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "白名单&管理员检测云链联动版",
                subtitle,
                options,
                hints,
                group_id,
            ),
            timeout=120,
        )

    def _qq_checker_handle_player_action(
            self, group_id: int, qqid: int, choice: str):
        """处理添加/移除白名单与服务器管理员这四类玩家操作。"""
        title_map = {
            "1": "白名单 添加玩家",
            "2": "白名单 移除玩家",
            "3": "管理员 添加玩家",
            "4": "管理员 移除玩家",
        }
        handler_map = {
            "1": self.on_qq_whitelist_add,
            "2": self.on_qq_whitelist_remove,
            "3": self.on_qq_server_admin_add,
            "4": self.on_qq_server_admin_remove,
        }
        player_name = self._qq_checker_prompt(
            group_id,
            qqid,
            title_map[choice],
            [],
            ["请输入玩家名称", "输入 . 退出"],
        )
        if player_name is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(player_name, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        handler_map[choice](group_id, qqid, [player_name])

    def _qq_checker_handle_toggle_action(
            self, group_id: int, qqid: int, choice: str):
        """处理白名单检测和管理员检测的开关菜单。"""
        subtitle = "白名单检测 设置" if choice == "5" else "管理员检测 设置"
        handler = (
            self.on_qq_whitelist_toggle
            if choice == "5"
            else self.on_qq_admin_check_toggle
        )
        action = self._qq_checker_prompt(
            group_id,
            qqid,
            subtitle,
            ["开启", "关闭"],
            ["输入 [1-2] 之间的数字以选择 对应操作", "输入 . 退出"],
        )
        if action is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(action, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        action_arg = {"1": ["开启"], "2": ["关闭"]}.get(action)
        if action_arg is None:
            self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")
            return
        handler(group_id, qqid, action_arg)

    def _qq_checker_handle_interval_action(self, group_id: int, qqid: int):
        """处理检测周期设置菜单。"""
        seconds = self._qq_checker_prompt(
            group_id,
            qqid,
            "检测周期 设置",
            [],
            ["请输入检测周期秒数", "输入 . 退出"],
        )
        if seconds is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(seconds, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        self.on_qq_check_interval(group_id, qqid, [seconds])

    def qq_checker_menu(self, group_id: int, qqid: int):
        """在群里打开白名单与管理员检测联动菜单。"""
        if not self._can_use_group_permission(group_id, qqid, "白名单&管理员检测权限"):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        if not self.ensure_whitelist_checker(group_id, qqid):
            return
        # 这个菜单本质上是把白名单插件暴露出来的 API 做了一层群聊版操作面板。
        # 这样权限仍然统一归群服互通管理，而不是把原插件的控制台能力原样暴露出来。
        choice = self._qq_checker_prompt(
            group_id,
            qqid,
            "管理系统",
            [
                "添加玩家到白名单",
                "从白名单中移除玩家",
                "添加服务器管理员",
                "移除服务器管理员",
                "开启/关闭 白名单检测",
                "开启/关闭 管理员检测",
                "设置检测周期",
                "查看当前状态",
            ],
            ["输入 [1-8] 之间的数字以选择 对应功能", "输入 . 退出"],
        )
        if choice is None:
            self._reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if self._is_menu_exit(choice, group_id):
            self._reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return

        if choice in ("1", "2", "3", "4"):
            self._qq_checker_handle_player_action(group_id, qqid, choice)
            return

        if choice in ("5", "6"):
            self._qq_checker_handle_toggle_action(group_id, qqid, choice)
            return

        if choice == "7":
            self._qq_checker_handle_interval_action(group_id, qqid)
            return

        if choice == "8":
            self.on_qq_check_status(group_id, qqid, [])
            return

        self._reply_to_qq(group_id, qqid, "❀ 您的输入有误")

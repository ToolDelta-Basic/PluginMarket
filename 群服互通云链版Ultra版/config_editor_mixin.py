"""Q 群与控制台配置编辑中心。"""

import json
import os
import shutil
import time
from typing import Any

from tooldelta import cfg, fmts


class QQLinkerConfigEditorMixin:
    """提供 Ultra 版和联动插件配置的菜单化编辑能力。"""

    CONFIG_MENU_TRIGGERS = ["配置中心", "配置菜单", "群服配置"]
    CONFIG_FILE_DIR = "插件配置文件"
    CONFIG_BACKUP_DIR = "配置文件备份"
    CONFIG_BACKUP_INDEX = "backups.json"
    CONFIG_EXIT = object()
    CONFIG_BACK = object()

    def get_group_config_menu_triggers(self, group_id: int):
        group_cfg = self.group_cfgs.get(group_id)
        if not group_cfg:
            return list(self.CONFIG_MENU_TRIGGERS)
        raw = group_cfg["指令设置"].get("配置中心唤醒词", self.CONFIG_MENU_TRIGGERS)
        return self.normalize_string_triggers(raw, self.CONFIG_MENU_TRIGGERS)

    def qq_config_center_menu(self, group_id: int, qqid: int):
        """Q 群侧配置中心入口。"""
        if not self._can_use_group_permission(group_id, qqid, "配置配置文件权限"):
            self._reply_menu_permission_denied(group_id, qqid)
            return
        self._config_center_menu(
            {"mode": "qq", "group_id": group_id, "qqid": qqid})

    def on_console_config_center(self, _args: list[str]):
        """控制台侧配置中心入口。"""
        self._config_center_menu({"mode": "console"})

    def _config_group_id(self, ctx: dict[str, Any]) -> int | None:
        return int(ctx["group_id"]) if ctx.get(
            "mode") == "qq" and "group_id" in ctx else None

    def _config_exit_hint(
            self, ctx: dict[str, Any], action: str = "退出") -> str:
        return self.menu_exit_hint(self._config_group_id(ctx), action)

    def _config_back_hint(
            self, ctx: dict[str, Any], action: str = "返回上级菜单") -> str:
        return self.menu_back_hint(self._config_group_id(ctx), action)

    def _config_normalize_control_hints(
        self,
        ctx: dict[str, Any],
        hints: list[str],
    ) -> list[str]:
        normalized: list[str] = []
        for hint in hints:
            if hint == "输入 . 退出":
                normalized.append(self._config_exit_hint(ctx))
            elif hint == "输入 . 取消":
                normalized.append(self._config_back_hint(ctx, "取消"))
            elif hint == "输入 0 返回上级":
                normalized.append(self._config_back_hint(ctx, "返回上级"))
            elif hint == "输入 0 返回上级菜单":
                normalized.append(self._config_back_hint(ctx))
            else:
                normalized.append(hint)
        return normalized

    def _config_center_menu(self, ctx: dict[str, Any]):
        while True:
            options = [
                "模式1：整文件修改配置",
                "模式2：暂未开放",
            ]
            choice = self._config_prompt(
                ctx,
                "配置中心",
                options,
                [f"输入 [1-{len(options)}] 选择配置模式", "输入 . 退出"],
            )
            if choice is self.CONFIG_EXIT:
                return
            selected = self.parse_displayed_menu_choice(choice, len(options))
            if selected is None:
                self._config_error(ctx, "输入有误")
                continue
            if selected == 1:
                result = self._config_file_mode_menu(ctx)
                if result is self.CONFIG_EXIT:
                    return
                continue
            if selected == 2:
                self._config_error(ctx, "模式2暂未开放")
                continue

    def _config_file_mode_menu(self, ctx: dict[str, Any]):
        while True:
            choice = self._config_prompt(
                ctx,
                "模式1：整文件修改",
                ["修改配置文件", "还原配置文件备份"],
                ["输入 [1-2] 选择操作", "输入 0 返回上级", "输入 . 退出"],
                allow_back=True,
            )
            if choice is self.CONFIG_EXIT:
                return self.CONFIG_EXIT
            if choice is self.CONFIG_BACK:
                return
            if choice == "1":
                result = self._config_file_select_menu(ctx)
                if result is self.CONFIG_EXIT:
                    return self.CONFIG_EXIT
                continue
            if choice == "2":
                result = self._config_restore_backup_menu(ctx)
                if result is self.CONFIG_EXIT:
                    return self.CONFIG_EXIT
                continue
            self._config_error(ctx, "输入有误")

    def _config_file_select_menu(self, ctx: dict[str, Any]):
        page = 1
        while True:
            files = self._discover_config_files()
            if not files:
                self._config_error(
                    ctx, f"未找到 {
                        self.CONFIG_FILE_DIR}/*.json 配置文件")
                return
            per_page = self.get_group_config_file_items_per_page(
                self._config_group_id(ctx))
            total_pages, start_index, end_index = self.simple_paginate(
                len(files),
                per_page,
                page,
            )
            page = min(page, total_pages)
            page_files = files[start_index - 1: end_index]
            options = [item["display"] for item in page_files]
            choice = self._config_prompt(
                ctx,
                "选择配置文件",
                options,
                [
                    f"当前第 {page}/{total_pages} 页",
                    f"输入 [1-{len(options)}] 选择要整文件修改的配置",
                    "输入 - 转到上一页",
                    "输入 + 转到下一页",
                    "输入 正整数+页 转到对应页",
                    "输入 0 返回上级",
                    "输入 . 退出",
                ],
                allow_back=True,
            )
            if choice is self.CONFIG_EXIT:
                return self.CONFIG_EXIT
            if choice is self.CONFIG_BACK:
                return
            if choice == "+":
                if page < total_pages:
                    page += 1
                else:
                    self._config_error(ctx, "已经是最后一页啦~")
                continue
            if choice == "-":
                if page > 1:
                    page -= 1
                else:
                    self._config_error(ctx, "已经是第一页啦~")
                continue
            if page_num := self.parse_page_jump(choice):
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self._config_error(ctx, f"不存在第 {page_num} 页")
                continue
            selected = self.parse_displayed_menu_choice(
                choice, len(page_files))
            if selected is None:
                self._config_error(ctx, "输入有误")
                continue
            result = self._edit_config_file_whole(
                ctx, files[start_index + selected - 2])
            if result is self.CONFIG_EXIT:
                return self.CONFIG_EXIT

    def _edit_config_file_whole(
            self, ctx: dict[str, Any], item: dict[str, str]):
        try:
            with open(item["path"], "r", encoding="utf-8-sig") as file:
                content = file.read()
        except Exception as err:
            self._config_error(ctx, f"读取配置文件失败: {err}")
            return
        try:
            original_config = json.loads(content)
        except json.JSONDecodeError:
            original_config = None

        if ctx["mode"] == "qq":
            prompt_text = self._config_whole_file_prompt_text(
                ctx,
                item["name"],
                content,
            )
            raw = self._config_input_result(
                ctx,
                self.qq_prompt(
                    ctx["group_id"],
                    ctx["qqid"],
                    prompt_text,
                    timeout=600),
            )
        else:
            self.print_console_card(
                "群服互通 配置中心",
                f"整文件修改 / {item['name']}",
                [
                    "当前配置文件内容如下，复制并修改后粘贴回控制台",
                    "机器人会在替换前自动备份原配置文件",
                    "多行 JSON 可直接粘贴，读取到完整 JSON 后会自动提交",
                    "输入 END 单独一行可强制提交并检查格式",
                    self._config_back_hint(ctx, "返回上级"),
                    self._config_exit_hint(ctx, "退出本次修改"),
                    content,
                ],
                level="info",
            )
            raw = self._read_console_config_json_text(ctx)

        if raw is self.CONFIG_EXIT:
            return self.CONFIG_EXIT
        if raw is self.CONFIG_BACK:
            return

        try:
            parsed = json.loads(self._normalize_config_json_text(str(raw)))
        except json.JSONDecodeError as err:
            self._config_error(ctx, f"JSON 格式错误，未替换配置文件: {err}")
            return

        if not isinstance(parsed, dict):
            self._config_error(ctx, "配置文件根节点必须是 JSON 对象，未替换配置文件")
            return
        if not self._config_file_shape_matches(original_config, parsed):
            self._config_error(ctx, "请发送完整配置文件，不能只发送配置项内容")
            return

        try:
            if not self._is_safe_config_path(item["path"]):
                self._config_error(ctx, "配置文件路径不在允许的插件配置目录内")
                return
            backup = self._backup_config_file(item)
            with open(item["path"], "w", encoding="utf-8") as file:
                json.dump(parsed, file, ensure_ascii=False, indent=4)
                file.write("\n")
        except Exception as err:
            self._config_error(ctx, f"替换配置文件失败: {err}")
            return

        apply_msg = self._apply_runtime_config_file(item, parsed)
        self._config_success(
            ctx,
            f"配置文件已替换，备份编号 {backup['id']}。{apply_msg}",
        )

    def _config_whole_file_prompt_text(
        self,
        ctx: dict[str, Any],
        config_name: str,
        content: str,
    ) -> str:
        parts = [
            self.orion_ui_border(),
            f"❐ 『群服互通云链版Ultra版』 整文件修改 / {config_name}",
            "❀ 请复制下面的完整 JSON，修改后作为下一条消息发送",
            "❀ 机器人会在替换前自动备份原配置文件",
            f"❀ {self._config_back_hint(ctx, '返回上级')}",
            f"❀ {self._config_exit_hint(ctx, '退出本次修改')}",
            self.orion_ui_border(),
            content,
        ]
        return "\n".join(parts)

    def _config_restore_backup_menu(self, ctx: dict[str, Any]):
        while True:
            backups = self._load_config_backup_index()
            backups = [item for item in backups if os.path.isfile(
                item.get("backup_path", ""))]
            if not backups:
                self._config_error(ctx, "暂无可还原的配置文件备份")
                return
            backups = list(reversed(backups[-30:]))
            options = [
                f"{item['id']} / {item['config_name']} / {item.get('created_at', '')}"  # noqa: E501
                for item in backups
            ]
            choice = self._config_prompt(
                ctx,
                "还原配置文件备份",
                options,
                [
                    f"输入 [1-{len(options)}] 选择要还原的备份",
                    "还原前也会备份当前配置文件",
                    "输入 0 返回上级",
                    "输入 . 退出",
                ],
                allow_back=True,
            )
            if choice is self.CONFIG_EXIT:
                return self.CONFIG_EXIT
            if choice is self.CONFIG_BACK:
                return
            selected = self.parse_displayed_menu_choice(choice, len(backups))
            if selected is None:
                self._config_error(ctx, "输入有误")
                continue
            self._restore_config_backup(ctx, backups[selected - 1])
            return

    def _restore_config_backup(
            self, ctx: dict[str, Any], backup: dict[str, str]):
        current_item = {
            "name": backup["config_name"],
            "path": backup["original_path"],
            "display": backup["config_name"],
        }
        try:
            if not self._is_safe_config_path(current_item["path"]):
                self._config_error(ctx, "备份记录指向的配置文件路径不在允许目录内")
                return
            if not self._is_safe_backup_path(backup["backup_path"]):
                self._config_error(ctx, "备份文件路径不在允许的备份目录内")
                return
            if os.path.isfile(current_item["path"]):
                self._backup_config_file(current_item, reason="restore-before")
            os.makedirs(os.path.dirname(current_item["path"]), exist_ok=True)
            shutil.copy2(backup["backup_path"], current_item["path"])
            with open(current_item["path"], "r", encoding="utf-8-sig") as file:
                restored = json.load(file)
        except Exception as err:
            self._config_error(ctx, f"还原配置文件失败: {err}")
            return
        apply_msg = self._apply_runtime_config_file(current_item, restored)
        self._config_success(ctx, f"已还原备份 {backup['id']}。{apply_msg}")

    def _discover_config_files(self) -> list[dict[str, str]]:
        cfg_dir = os.path.abspath(self.CONFIG_FILE_DIR)
        if not os.path.isdir(cfg_dir):
            return []
        files: list[dict[str, str]] = []
        for name in sorted(os.listdir(cfg_dir), key=str.lower):
            path = os.path.join(cfg_dir, name)
            if not os.path.isfile(path) or not name.lower().endswith(".json"):
                continue
            config_name = os.path.splitext(name)[0]
            files.append(
                {
                    "name": config_name,
                    "path": path,
                    "display": f"{config_name} ({os.path.relpath(path)})",
                }
            )
        return files

    def _config_backup_root(self) -> str:
        path = self.format_data_path(self.CONFIG_BACKUP_DIR)
        os.makedirs(path, exist_ok=True)
        return path

    def _config_backup_index_path(self) -> str:
        return os.path.join(
            self._config_backup_root(),
            self.CONFIG_BACKUP_INDEX)

    def _load_config_backup_index(self) -> list[dict[str, str]]:
        path = self._config_backup_index_path()
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _save_config_backup_index(self, backups: list[dict[str, str]]):
        path = self._config_backup_index_path()
        with open(path, "w", encoding="utf-8") as file:
            json.dump(backups[-100:], file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _backup_config_file(
        self,
        item: dict[str, str],
        reason: str = "replace-before",
    ) -> dict[str, str]:
        if not self._is_safe_config_path(item["path"]):
            raise ValueError("配置文件路径不在允许的插件配置目录内")
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        stamp = time.strftime("%Y%m%d-%H%M%S") + \
            f"-{int(time.time() * 1000) % 1000:03d}"
        safe_name = self._safe_backup_name(item["name"])
        backup_id = f"{stamp}-{safe_name}"
        backup_dir = os.path.join(self._config_backup_root(), safe_name)
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"{backup_id}.json")
        shutil.copy2(item["path"], backup_path)
        backup = {
            "id": backup_id,
            "config_name": item["name"],
            "original_path": os.path.abspath(item["path"]),
            "backup_path": os.path.abspath(backup_path),
            "created_at": created_at,
            "reason": reason,
        }
        backups = self._load_config_backup_index()
        backups.append(backup)
        self._save_config_backup_index(backups)
        return backup

    @staticmethod
    def _safe_backup_name(name: str) -> str:
        return "".join(ch if ch.isalnum() or ch in ("-", "_")
                       else "_" for ch in name) or "config"

    def _read_console_config_json_text(self, ctx: dict[str, Any]):
        lines: list[str] = []
        while True:
            prompt = "请输入完整配置 JSON: " if not lines else "继续输入 JSON: "
            line = input(fmts.fmt_info(f"§a❀ §b{prompt}"))
            text_line = line.strip()
            group_id = self._config_group_id(ctx)
            if self.is_menu_exit_input(text_line, group_id):
                self._config_success(ctx, "已退出配置文件修改")
                return self.CONFIG_EXIT
            if self.is_menu_back_input(text_line, group_id):
                return self.CONFIG_BACK
            lowered = text_line.lower()
            if lines and lowered in ("end", "提交"):
                return "\n".join(lines)
            lines.append(line)
            text = "\n".join(lines)
            try:
                json.loads(self._normalize_config_json_text(text))
                return text
            except json.JSONDecodeError:
                continue

    @staticmethod
    def _normalize_config_json_text(raw: str) -> str:
        text = raw.strip()
        if not text.startswith("```") or not text.endswith("```"):
            return text
        lines = text.splitlines()
        if len(lines) < 2:
            return text
        if lines[0].strip().startswith("```") and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
        return text

    @staticmethod
    def _config_file_shape_matches(
            original: Any, new_config: dict[str, Any]) -> bool:
        if not isinstance(original, dict):
            return True
        if isinstance(original.get("配置项"), dict):
            return isinstance(new_config.get("配置项"), dict)
        return True

    def _is_safe_config_path(self, path: str) -> bool:
        cfg_dir = os.path.abspath(self.CONFIG_FILE_DIR)
        target = os.path.abspath(path)
        try:
            return os.path.commonpath(
                [cfg_dir, target]) == cfg_dir and target.lower().endswith(
                ".json")
        except ValueError:
            return False

    def _is_safe_backup_path(self, path: str) -> bool:
        backup_root = os.path.abspath(self._config_backup_root())
        target = os.path.abspath(path)
        try:
            return os.path.commonpath(
                [backup_root, target]) == backup_root and target.lower().endswith(".json")  # noqa: E501
        except ValueError:
            return False

    @staticmethod
    def _extract_config_items(full_config: dict[str, Any]) -> dict[str, Any]:
        config_items = full_config.get("配置项")
        if isinstance(config_items, dict):
            return config_items
        return full_config

    def _apply_runtime_config_file(
            self, item: dict[str, str], full_config: dict[str, Any]) -> str:
        config_name = item["name"]
        config_items = self._extract_config_items(full_config)
        try:
            if config_name == self.name:
                message = self.apply_ultra_runtime_config(config_items)
                self._runtime_config_path = item["path"]
                self._runtime_config_file_state = self.runtime_config_file_state(  # noqa: E501
                    item["path"])
                return message
            if (
                config_name == "白名单&管理员检测云链联动版"
                and self.whitelist_checker is not None
                and hasattr(self.whitelist_checker, "_cfg")
            ):
                plugin = self.whitelist_checker
                merged = plugin.merge_with_default(
                    config_items, plugin.DEFAULT_CFG)
                cfg.check_auto(plugin.STD_CFG, merged)
                plugin._cfg = merged
                return "白名单&管理员检测配置已动态载入"
            if (
                config_name == "任务系统云链联动版"
                and self.task_system is not None
                and hasattr(self.task_system, "cfg")
            ):
                self.task_system.cfg = config_items
                return "任务系统配置已动态载入"
            if (
                config_name == "领地系统云链联动版"
                and self.land_system is not None
                and hasattr(self.land_system, "cfg")
            ):
                self.land_system.cfg = config_items
                self._apply_land_runtime_config(self.land_system)
                return "领地系统配置已动态载入"
            if (
                config_name in ("『Orion System』违规与作弊行为综合反制系统", "Orion System 猎户座")  # noqa: E501
                and self.orion is not None
                and hasattr(self.orion, "config_mgr")
            ):
                mgr = self.orion.config_mgr
                mgr.config = config_items
                cfg.check_auto(mgr.CONFIG_STD, mgr.config)
                mgr.get_parsed_config()
                mgr.transfer_config()
                mgr.check_permission_mgr()
                mgr.concise_mode()
                return "Orion 配置已动态载入"
        except Exception as err:
            return f"配置文件已落盘，但动态载入失败: {err}。可使用备份还原或重启后查看报错"
        return "该配置所属插件未接入动态载入，通常需要重启 ToolDelta 或等待插件自行重新读取"

    @staticmethod
    def _apply_land_runtime_config(plugin):
        plugin.enabled = bool(plugin.cfg["是否启用"])
        plugin.wake_words = plugin._normalize_wake_words(plugin.cfg["唤醒词"])
        plugin.data_file = plugin.format_data_path(str(plugin.cfg["数据文件"]))
        plugin.check_interval = plugin.cfg["检测间隔"]
        plugin.buffer_dist = plugin.cfg["缓冲区距离"]
        plugin.tp_radius = plugin.cfg["传送半径"]
        plugin.max_radius = plugin.cfg["最大领地半径"]
        plugin.max_length = plugin.cfg["最大领地长"]
        plugin.max_height = plugin.cfg["最大领地高"]
        plugin.max_width = plugin.cfg["最大领地宽"]
        plugin.max_lands_per_player = plugin.cfg["最大领地数量"]
        plugin.whitelist = {name.lower() for name in plugin.cfg["白名单"]}
        plugin.lands.clear()
        plugin.player_land_cache.clear()
        plugin._load_data()

    def _config_prompt(
        self,
        ctx: dict[str, Any],
        subtitle: str,
        options: list[str],
        hints: list[str],
        allow_back: bool = False,
    ):
        hints = self._config_normalize_control_hints(ctx, hints)
        if ctx["mode"] == "qq":
            text = self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                subtitle,
                options,
                hints,
                self._config_group_id(ctx),
            )
            result = self.qq_prompt(
                ctx["group_id"], ctx["qqid"], text, timeout=120)
        else:
            lines = [f"[ {i + 1} ] {option}" for i,
                     option in enumerate(options)]
            lines.extend(hints)
            result = self.prompt_console_input(
                "群服互通 配置中心", subtitle, lines, "请输入")
        if result is None:
            self._config_error(ctx, "回复超时，已退出菜单")
            return self.CONFIG_EXIT
        result = str(result).strip()
        group_id = self._config_group_id(ctx)
        if self.is_menu_exit_input(result, group_id):
            self._config_success(ctx, "已退出菜单")
            return self.CONFIG_EXIT
        if allow_back and self.is_menu_back_input(result, group_id):
            return self.CONFIG_BACK
        return result

    def _config_input_result(self, ctx: dict[str, Any], result: Any):
        if result is None:
            self._config_error(ctx, "回复超时，已退出菜单")
            return self.CONFIG_EXIT
        text = str(result).strip()
        group_id = self._config_group_id(ctx)
        if self.is_menu_exit_input(text, group_id):
            self._config_success(ctx, "已退出菜单")
            return self.CONFIG_EXIT
        if self.is_menu_back_input(text, group_id):
            return self.CONFIG_BACK
        return text

    def _config_success(self, ctx: dict[str, Any], message: str):
        if ctx["mode"] == "qq":
            self._reply_to_qq(ctx["group_id"], ctx["qqid"], f"❀ {message}")
        else:
            self.print_console_success(message)

    def _config_error(self, ctx: dict[str, Any], message: str):
        if ctx["mode"] == "qq":
            self._reply_to_qq(ctx["group_id"], ctx["qqid"], f"❀ {message}")
        else:
            self.print_console_error(message)

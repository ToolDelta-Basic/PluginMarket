from __future__ import annotations

import datetime as _datetime
import queue
import threading
from typing import Any

try:
    from tooldelta import fmts
except ImportError:  # pragma: no cover
    fmts = None

try:
    from .core import menu_action, normalize_xuid, parse_flags
except ImportError:  # pragma: no cover
    from core import menu_action, normalize_xuid, parse_flags


class ConsoleMenuMixin:
    """Orion 风格同步控制台菜单；数字只在菜单循环内解释。"""

    _BORDER = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"

    def _orion(self, tag: str, message: str) -> None:
        marker = "§c❀" if tag in {"ALERT", "ERROR"} else "§6❀" if tag in {"WARN", "HELP"} else "§a❀"
        self._console_print(f"{marker} {message}")

    def _console_print(self, message: str) -> None:
        if fmts is not None:
            fmts.print_inf(message)
        else:
            self.print_inf(message)

    def _render_menu(self, menu: str) -> None:
        menus = {
            "main": ("总菜单", ("运行状态", "管理员列表", "设置权限", "快照管理", "实时管理")),
            "set": ("设置权限", ("管理员（11111111）", "成员（11111100）", "访客（00000000）", "自定义 8 位权限")),
            "snapshots": ("快照管理", ("新建快照", "还原快照", "删除快照")),
            "realtime": ("实时管理", ("运行详情", "启用或停用", "查看在线玩家权限", "管理托管玩家", "立即检查", "最近处理记录", "未授权管理员处理")),
        }
        title, items = menus.get(menu, menus["main"])
        self._console_print(self._BORDER)
        self._console_print(f"§l§d❐§f 『§6Libra-天秤座§f』 §b{title}§e管理 §d系统")
        for index, item in enumerate(items, 1):
            self._console_print(f"§l§b[ §e{index}§b ] §r§e{item}")
        self._console_print(self._BORDER)
        if menu == "main":
            self._console_print("§a❀ §b输入 §e[1-5]§b 之间的数字以选择功能，输入 §cq§b 退出")
        elif menu == "set":
            self._console_print("§a❀ §b输入 §e[1-4]§b 之间的数字以选择权限模板，输入 §e!§b 返回上一级，输入 §cq§b 退出")
        else:
            self._console_print("§a❀ §b输入 §e[1-3]§b 之间的数字，输入 §e!§b 返回上一级，输入 §cq§b 退出")

    def _open_menu(self) -> None:
        self._menu = "main"
        self._pending = None
        self._render_menu("main")

    def _close_menu(self) -> None:
        self._menu = "closed"
        self._pending = None
        self._orion("OK", "权限中心菜单已退出")

    def _input_timeout(self) -> float:
        try:
            return max(0.1, float(self.cfg.get("等待输入超时时间(秒)", 20)))
        except (TypeError, ValueError):
            return 20.0

    def _console_input(self, prompt: str) -> str | None:
        """带超时读取一行；超时通过 ``_input_timed_out`` 区分 EOF。"""
        self._input_timed_out = False
        if not prompt.startswith("§"):
            prompt = f"§a❀ §b{prompt}"
        rendered = fmts.fmt_info(prompt) if fmts is not None else prompt
        values: queue.Queue[str | BaseException] = queue.Queue(maxsize=1)

        def read_line() -> None:
            try:
                values.put(input(rendered).strip())
            except BaseException as exc:  # input 线程中的 EOF/中断
                values.put(exc)

        threading.Thread(target=read_line, name="libra-console-input", daemon=True).start()
        try:
            result = values.get(timeout=self._input_timeout())
        except queue.Empty:
            self._input_timed_out = True
            return None
        if isinstance(result, BaseException):
            return None
        return result

    def _finish_or_timeout(self) -> bool:
        value = self._console_input("输入任意字符继续，输入 q 退出：")
        if value is None:
            if self._input_timed_out:
                self._orion("WARN", "输入超时")
            self._close_menu()
            return False
        if value.lower() == "q":
            self._close_menu()
            return False
        return True

    def _show_player_results(self, query: str) -> list[dict[str, str]]:
        results = self.search_players(query)
        if not results:
            self._orion("ALERT", f"没有找到与“{query}”匹配的玩家")
            return []
        self._console_print(self._BORDER)
        self._console_print("§a❀ §b已发现以下玩家名称与 XUID")
        for index, item in enumerate(results, 1):
            self._console_print(f"§l§b[ §e{index}§b ] §r§e{item['name']} - {item['xuid']}")
        self._console_print(self._BORDER)
        return results

    def _ask(self, prompt: str) -> tuple[bool, str]:
        """读取一行输入，统一处理超时、``q`` 退出和 ``!`` 返回。

        返回 ``(是否继续, 输入内容)``；第一个元素为 ``False`` 时调用方应直接返回。
        """
        value = self._console_input(prompt)
        if value is None:
            if self._input_timed_out:
                self._orion("WARN", "输入超时")
            return False, ""
        if value.lower() == "q":
            self._close_menu()
            return False, ""
        if value in {"!", "！"}:
            return False, ""
        return True, value

    def _confirm_yes(self, prompt: str) -> bool | None:
        """确认类输入：``True`` 确认、``False`` 取消、``None`` 需中断当前流程。"""
        ok, value = self._ask(prompt)
        if not ok:
            return None
        return value.lower() == "y"

    def _read_token(self, prompt: str) -> tuple[str, str]:
        """读取一行并归一化控制指令，返回 ``(状态, 输入值)``。

        状态取值：``ok`` 正常输入、``back`` 输入 ``!`` 返回上一级、``closed``
        超时或输入 ``q``（两种情况都会关闭菜单）。
        """
        value = self._console_input(prompt)
        if value is None:
            if self._input_timed_out:
                self._orion("WARN", "输入超时")
            self._close_menu()
            return "closed", ""
        if value.lower() == "q":
            self._close_menu()
            return "closed", ""
        if value in {"!", "！"}:
            return "back", ""
        return "ok", value

    def _player_is_managed(self, normalized: str) -> bool:
        """判断玩家是否处于持续管理状态，兼容旧版布尔与字典两种存储。"""
        managed = self.state.get("持续管理玩家", {}).get(normalized, False)
        if isinstance(managed, dict):
            managed = managed.get("是否启用", managed.get("启用", True))
        return bool(managed)

    def _pick_player(self, prompt: str) -> dict[str, str] | None:
        """按名称/XUID 或搜索结果编号选定一个玩家。"""
        ok, query = self._ask(prompt)
        if not ok:
            return None
        try:
            results = [{"xuid": normalize_xuid(query), "name": query}]
        except ValueError:
            results = self._show_player_results(query)
        if not results:
            return None
        ok, choice = self._ask("请输入编号（! 返回，q 退出）：")
        if not ok:
            return None
        if not choice.isdigit() or not 1 <= int(choice) <= len(results):
            self._orion("ALERT", "无效的玩家编号")
            return None
        return results[int(choice) - 1]

    def _show_set_options(self, target: dict[str, str], flags: str) -> None:
        self._console_print(self._BORDER)
        self._console_print(f"§a❀ §b将设置 §e{target['name']}§b（{target['xuid']}）为 §e{flags}")
        self._console_print("§a❀ §b[ §e1§b ] 仅设置本次权限")
        self._console_print("§a❀ §b[ §e2§b ] 设置并持续管理")
        if self._player_is_managed(target["xuid"].lower()):
            self._console_print("§6❀ §b该玩家已启用持续管理，选择 1 将被拒绝；可先暂停管理")

    def _report_set_result(self, target: dict[str, str], flags: str, result: dict[str, Any]) -> None:
        if result.get("success"):
            self._orion("OK", f"已设置 {target['xuid']} -> {flags}")
        else:
            self._orion("ALERT", result.get("message", "设置失败"))

    def _select_player_interactive(self, flags: str) -> bool:
        target = self._pick_player("请输入玩家名称或 XUID（! 返回，q 退出）：")
        if target is None:
            return False
        self._show_set_options(target, flags)
        ok, mode_choice = self._ask("请输入设置方式（! 返回，q 退出）：")
        if not ok:
            return False
        management = {"1": "once", "2": "manage"}.get(mode_choice)
        if management is None:
            self._orion("ALERT", "无效的设置方式")
            return True
        self._console_print("§a❀ §b输入 §ey§b 确认，输入 §e!§b 返回，输入 §cq§b 退出")
        confirmed = self._confirm_yes("请输入确认：")
        if confirmed is None:
            return False
        if not confirmed:
            self._orion("WARN", "未确认，本次操作已取消")
            return True
        result = self.set_permission(
            target["xuid"], flags, actor="console", management=management
        )
        self._report_set_result(target, flags, result)
        return True

    def _snapshot_page_size(self) -> int:
        try:
            return max(1, int(self.cfg.get("控制台菜单每页显示几项", 20)))
        except (TypeError, ValueError):
            return 20

    def _snapshot_detail(self, item: dict[str, Any]) -> None:
        snapshot = item["快照"]
        name = snapshot.get("名称") or snapshot.get("name") or "未命名快照"
        created = snapshot.get("创建时间") or snapshot.get("时间") or snapshot.get("time") or "未知"
        desired = snapshot.get("期望权限", snapshot.get("desired", {})) or {}
        admins = snapshot.get("已发现管理员", snapshot.get("observed_admins", [])) or []
        self._console_print(self._BORDER)
        self._console_print(f"§a❀ §b快照名称：§e{name}")
        self._console_print(f"§a❀ §b创建时间：§e{created}")
        self._console_print(f"§a❀ §b管理员数量：§e{len(admins)}")
        self._console_print(f"§a❀ §b期望权限：§e{len(desired)} 个")
        self._console_print(self._BORDER)

    def _render_snapshot_page(self, items: dict[str, Any], operation: str, page: int) -> None:
        title = "还原" if operation == "restore" else "删除"
        self._console_print(self._BORDER)
        self._console_print(f"§l§d❐§f 『§6Libra-天秤座§f』 快照{title}列表 §7第 {page} 页")
        for index, item in enumerate(items.get("项目", []), 1):
            snapshot = item["快照"]
            name = snapshot.get("名称") or snapshot.get("name") or "未命名快照"
            desired = snapshot.get("期望权限", snapshot.get("desired", {})) or {}
            self._console_print(f"§l§b[ §e{index}§b ] §r§e{name} §7({len(desired)} 个权限)")
        self._console_print(self._BORDER)
        self._console_print("§a❀ §b输入序号选择，n 下一页，p 上一页，输入关键词查找，! 返回，q 退出")

    def _snapshot_operate(self, operation: str, selected: dict[str, Any]) -> str:
        """确认并执行单个快照的还原/删除，返回 ``done`` / ``back`` / ``closed``。"""
        self._snapshot_detail(selected)
        verb = "还原" if operation == "restore" else "删除"
        status, confirm = self._read_token(f"确认{verb}此快照？输入 y 确认，! 返回，q 退出：")
        if status in {"closed", "back"}:
            return status
        if confirm.lower() != "y":
            self._orion("WARN", "未确认，本次操作已取消")
            return "done"
        index = int(selected["索引"])
        if operation == "restore":
            result = self.restore_snapshot(index, actor="console")
        else:
            result = self.delete_snapshot(index, actor="console")
        if result.get("success"):
            self._orion("OK", f"快照{verb}完成")
        else:
            self._orion("ALERT", result.get("error", "操作失败"))
        return "done"

    def _choose_snapshot(self, operation: str) -> str:
        page = 1
        query = ""
        page_size = self._snapshot_page_size()
        while self._menu != "closed":
            items = self.list_snapshots(page=page, page_size=page_size, query=query)
            total = items.get("总数", 0)
            self._render_snapshot_page(items, operation, page)
            status, choice = self._read_token("请输入选项：")
            if status in {"closed", "back"}:
                return status
            lowered = choice.lower()
            if lowered == "n":
                if page * page_size < total:
                    page += 1
                continue
            if lowered == "p":
                page = max(1, page - 1)
                continue
            entries = items.get("项目", [])
            if choice.isdigit() and 1 <= int(choice) <= len(entries):
                outcome = self._snapshot_operate(operation, entries[int(choice) - 1])
                if outcome == "back":
                    continue
                return outcome
            query = choice.strip()
            page = 1
        return "closed"

    def _create_snapshot_interactive(self) -> bool:
        name = self._console_input("请输入快照名称，可留空：")
        if name is None:
            if self._input_timed_out:
                self._orion("WARN", "输入超时")
            return False
        if name.lower() == "q":
            self._close_menu()
            return False
        if name in {"!", "！"}:
            return True
        name = name.strip() or _datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        result = self.create_snapshot(name=name)
        self._orion("OK", f"快照已保存：{result.get('name', name)}")
        return True

    def _realtime_confirm(self, prompt: str) -> bool | None:
        value = self._console_input(prompt)
        if value is None:
            if self._input_timed_out:
                self._orion("WARN", "输入超时")
            return None
        if value.lower() == "q":
            self._close_menu()
            return None
        if value in {"!", "！"}:
            return False
        return value.lower() == "y"

    def _pick_manage_target(self, query: str) -> dict[str, str] | None:
        """把控制台输入解析为 ``{xuid, name}``；无法确定唯一玩家时返回 ``None``。"""
        try:
            normalized = normalize_xuid(query)
        except ValueError:
            matches = self._show_player_results(query)
            if not matches:
                return None
            status, choice = self._ask("请输入编号（! 返回，q 退出）：")
            if not status:
                return None
            if not choice.isdigit() or not 1 <= int(choice) <= len(matches):
                self._orion("ALERT", "无效的玩家编号")
                return None
            return matches[int(choice) - 1]
        return {"xuid": normalized, "name": self.resolve_player_name(normalized) or query}

    def _manage_realtime_player(self) -> None:
        status, query = self._ask("请输入玩家名称或 XUID（! 返回，q 退出）：")
        if not status:
            return
        target = self._pick_manage_target(query)
        if target is None:
            return
        status, flags = self._ask("请输入 8 位目标权限（0/1）：")
        if not status:
            return
        try:
            parse_flags(flags)
        except ValueError as exc:
            self._orion("ALERT", str(exc))
            return
        self._console_print(f"§a❀ §b将为 §e{target['name']}§b 建立持续规则：§e{flags}")
        if self._realtime_confirm("请输入 y 确认，! 返回，q 退出：") is not True:
            return
        result = self.realtime.set_managed_rule(target["xuid"], flags, actor="console")
        if result.get("success"):
            self._orion("OK", "持续管理规则已保存")
        else:
            self._orion("ALERT", result.get("message", "规则保存失败"))

    def _realtime_show_status(self) -> None:
        status = self.realtime.status()
        state = "运行中" if status["是否运行"] else "未运行"
        self._orion(
            "OK",
            f"实时管理：{state}，在线玩家 {status['在线玩家数']} 个，"
            f"观测 {status['权限观测数']} 个（已就绪 {status['已就绪观测数']} 个），"
            f"最近修正 {status['最近修正数量']} 条",
        )

    def _realtime_toggle(self) -> None:
        current = self.realtime.enabled()
        prompt = f"当前为{'启用' if current else '停用'}，确认切换？输入 y 确认："
        if self._realtime_confirm(prompt) is not True:
            return
        status = self.realtime.set_enabled(not current)
        self._orion("OK", f"实时管理已{'启用' if status['是否启用'] else '停用'}")

    @staticmethod
    def _permission_category(flags: Any) -> str:
        """把 8 位权限串归类为访客/成员/管理员/自定义，非法值归为未知。"""
        if not isinstance(flags, str) or len(flags) != 8 or any(c not in "01" for c in flags):
            return "未知"
        if flags == "00000000":
            return "访客"
        if flags == "11111100":
            return "成员"
        if flags == "11111111":
            return "管理员"
        return "自定义"

    def _realtime_show_online(self) -> None:
        for record in self.realtime.inspect_players():
            name = record.get("玩家名称", record.get("玩家名", "未知玩家"))
            xuid = str(record.get("XUID", "")).lower()
            flags = record.get("实际权限")
            category = self._permission_category(flags)
            shown = flags if category != "未知" else "未知"
            managed = "是" if self._player_is_managed(xuid) else "否"
            self._orion("SCAN", f"{name}：{managed} {category} {shown}")

    def _realtime_run_check(self) -> None:
        records = self.realtime.inspect_players()
        self._orion("SCAN", f"立即检查完成，共处理 {len(records)} 个在线玩家")

    def _realtime_show_recent_fixes(self) -> None:
        rows = self.realtime.recent_fix_records(self._snapshot_page_size())
        if not rows:
            self._orion("OK", "暂无实时权限修正记录")
            return
        for row in rows:
            name = row.get("玩家名称", row.get("玩家XUID"))
            self._orion(
                "SCAN",
                f"{name}：{row.get('实际权限')} -> {row.get('目标权限')}，{row.get('状态')}",
            )

    def _realtime_set_unauthorized_policy(self) -> None:
        self._console_print("§a❀ §b[ §e0§b ] 仅提醒  §b[ §e1§b ] 设为成员  §b[ §e2§b ] 设为访客")
        policy = self._console_input("请输入处理方式：")
        values = {"0": (0, "仅提醒"), "1": (1, "设为成员"), "2": (2, "设为访客")}
        if policy not in values:
            self._orion("ALERT", "无效的处理方式")
            return
        number, label = values[policy]
        key = "未授权管理员处理(0:仅提醒,1:设为成员,2:设为访客)"
        self.cfg.setdefault("实时管理", {})[key] = number
        self._save_config()
        self._orion("OK", f"未授权管理员处理已设置为：{number}（{label}）")

    def _run_realtime_menu(self, choice: str) -> bool:
        handlers = {
            "1": self._realtime_show_status,
            "2": self._realtime_toggle,
            "3": self._realtime_show_online,
            "4": self._manage_realtime_player,
            "5": self._realtime_run_check,
            "6": self._realtime_show_recent_fixes,
            "7": self._realtime_set_unauthorized_policy,
        }
        handler = handlers.get(choice)
        if handler is None:
            self._orion("HELP", "请输入实时管理菜单中的数字序号")
        else:
            handler()
        if self._menu != "closed":
            return self._finish_or_timeout()
        return False

    def _console_main_menu(self, choice: str) -> bool:
        """处理主菜单选项；返回 ``False`` 表示需要退出控制台菜单。"""
        action, _ = menu_action("main", choice)
        if action == "status":
            mode = "魔法指令模式" if self._use_magic_command() else "普通指令模式"
            admins = len(self.state.get("已发现管理员", []))
            desired = len(self.state.get("期望权限", {}))
            self._orion("OK", f"缓存管理员 {admins} 个，期望权限 {desired} 个，当前为{mode}")
        elif action == "list":
            self._run_list()
        elif action in {"set_menu", "snapshot_menu", "realtime_menu"}:
            self._menu = {
                "set_menu": "set",
                "snapshot_menu": "snapshots",
                "realtime_menu": "realtime",
            }[action]
            return True
        else:
            self._orion("HELP", "请输入菜单中的数字序号")
        return self._finish_or_timeout()

    def _console_set_custom(self) -> bool:
        """读取自定义权限串并进入玩家选择；返回 ``False`` 表示需要退出菜单。"""
        status, custom = self._read_token("请输入 8 位权限标志（0/1）：")
        if status == "closed":
            return False
        if status == "ok":
            try:
                parse_flags(custom)
            except ValueError as exc:
                self._orion("ALERT", str(exc))
                return True
            self._select_player_interactive(custom)
        return True

    def _console_set_menu(self, choice: str) -> bool:
        action, flags = menu_action("set", choice)
        if action in {"set_admin", "set_member", "set_guest"}:
            self._select_player_interactive(flags or "00000000")
        elif action == "set_custom":
            if not self._console_set_custom():
                return False
        else:
            self._orion("HELP", "请选择 1-4，或输入 ! 返回")
        if self._menu == "closed":
            return False
        return self._finish_or_timeout()

    def _console_snapshots_menu(self, choice: str) -> bool:
        action, _ = menu_action("snapshots", choice)
        if action == "snapshot_create":
            self._create_snapshot_interactive()
            if self._menu == "closed":
                return False
            return self._finish_or_timeout()
        if action not in {"snapshot_restore", "snapshot_delete"}:
            self._orion("HELP", "请选择 1-3，或输入 ! 返回")
            return True
        operation = "restore" if action == "snapshot_restore" else "delete"
        result = self._choose_snapshot(operation)
        if result == "closed":
            return False
        if result == "done":
            return self._finish_or_timeout()
        return True

    def _dispatch_console_choice(self, choice: str) -> bool:
        """按当前菜单层级分派输入；返回 ``False`` 表示需要退出控制台菜单。"""
        if self._menu == "main":
            return self._console_main_menu(choice)
        if self._menu == "set":
            return self._console_set_menu(choice)
        if self._menu == "snapshots":
            return self._console_snapshots_menu(choice)
        if self._menu == "realtime":
            return self._run_realtime_menu(choice)
        return True

    def _run_console_menu(self) -> None:
        self._menu = "main"
        self._pending = None
        while self._menu != "closed":
            self._render_menu(self._menu)
            status, choice = self._read_token("请输入选项：")
            if status == "closed":
                return
            if status == "back":
                if self._menu == "main":
                    self._close_menu()
                    return
                self._menu = "main"
                continue
            if not self._dispatch_console_choice(choice):
                return

    def on_menu_token(self, token: str, args: list[str] | None = None) -> None:
        if self._menu == "closed":
            return
        if token.lower() == "q":
            self._close_menu()
        elif token in {"!", "！"}:
            self._menu = "main" if self._menu != "main" else "closed"
        elif self._menu == "main" and token == "4":
            self._menu = "snapshots"
        elif self._menu == "main" and token == "5":
            self._menu = "realtime"

    def on_console(self, args: list[str]) -> None:
        self._run_console_menu()

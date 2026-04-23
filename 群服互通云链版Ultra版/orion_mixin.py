import os
import re

from tooldelta import fmts, utils


# 和 Orion_System 的联动全收在这里，主入口不用再关心封禁细节。
class QQLinkerOrionMixin:
    """负责 Orion_System 菜单、封禁与解封逻辑。"""

    @staticmethod
    def console_menu_header(title: str) -> str:
        """生成控制台使用的 Orion 风格标题栏。"""
        return (
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓"
            "§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧\n"
            f"§l§d❐§f 『§6群服互通云链版Ultra版§f』 §b{title}"
        )

    @staticmethod
    def console_menu_footer(page_label: str, body: str) -> str:
        """生成控制台使用的 Orion 风格页脚。"""
        return (
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓 "
            f"§r§7[ §b{page_label} §7] "
            "§l§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧\n"
            f"§r{body}"
        )

    def prompt_console_input(
        self,
        title: str,
        page_label: str,
        body_lines: list[str],
        prompt: str,
    ) -> str:
        """按 Orion 卡片样式展示控制台交互步骤，并读取输入。"""
        self.print_console_card(title, page_label, body_lines, level="info")
        return input(fmts.fmt_info(f"§a❀ §b{prompt}")).strip()

    def print_console_info(self, text: str):
        """按统一 UI 风格输出控制台普通信息。"""
        fmts.print_inf(f"§a❀ §b{text}")

    def print_console_success(self, text: str):
        """按统一 UI 风格输出控制台成功信息。"""
        fmts.print_suc(f"§a❀ §b{text}")

    def print_console_warn(self, text: str):
        """按统一 UI 风格输出控制台警告信息。"""
        fmts.print_war(f"§6❀ §e{text}")

    def print_console_error(self, text: str):
        """按统一 UI 风格输出控制台错误信息。"""
        fmts.print_err(f"§c❀ §e{text}")

    def print_console_card(
        self,
        title: str,
        page_label: str,
        body_lines: list[str],
        level: str = "info",
    ):
        """按 Orion 风格打印一张控制台信息卡片。"""
        card = (
            self.console_menu_header(title)
            + "\n"
            + self.console_menu_footer(
                page_label,
                "\n".join(
                    i if i.startswith("§") else f"§a❀ §b{i}" for i in body_lines
                ),
            )
        )
        {
            "info": fmts.print_inf,
            "success": fmts.print_suc,
            "warn": fmts.print_war,
            "error": fmts.print_err,
        }.get(level, fmts.print_inf)(card)

    def require_orion(self):
        """返回可用的 Orion 实例，不可用时抛出明确异常。"""
        if self.orion is None:
            raise RuntimeError("Orion_System 插件不可用")
        return self.orion

    def reply_to_qq(self, group_id: int, qqid: int, text: str):
        """向指定群成员回复一条文本消息。"""
        self.sendmsg(
            group_id,
            f"[CQ:at,qq={qqid}] {text}",
            do_remove_cq_code=False,
        )

    def reply_result(self, group_id: int, qqid: int, ok: bool, msg: str):
        """把统一格式的成功/失败结果回发到群里。"""
        prefix = "😄" if ok else "😭"
        self.reply_to_qq(group_id, qqid, f"{prefix} {msg}")

    def on_qq_orion_ban(self, group_id: int, sender: int, args: list[str]):
        """群聊侧的 Orion 封禁入口。

        支持两种调用方式：
        - 直接给参数：适合熟悉命令的管理人员
        - 不给参数：转到交互式菜单
        """
        if not self.is_group_admin(group_id, sender):
            self.reply_to_qq(group_id, sender, "你没有权限执行此指令")
            return
        if args == []:
            self.qq_orion_ban_menu(group_id, sender)
            return
        target = args[0]
        ban_time_raw = args[1]
        reason = " ".join(args[2:]).strip() or "群聊管理员封禁"
        ok, msg = self.orion_ban_player(target, ban_time_raw, reason)
        self.reply_result(group_id, sender, ok, msg)

    def on_qq_orion_unban(self, group_id: int, sender: int, args: list[str]):
        """群聊侧的 Orion 解封入口。"""
        if not self.is_group_admin(group_id, sender):
            self.reply_to_qq(group_id, sender, "你没有权限执行此指令")
            return
        if args == []:
            self.qq_orion_unban_menu(group_id, sender)
            return
        ok, msg = self.orion_unban_player(args[0])
        self.reply_result(group_id, sender, ok, msg)

    def qq_prompt(self, group_id: int, qqid: int, text: str, timeout: int = 60):
        """发送一段提示文本，并等待同群同 QQ 的下一条回复。"""
        self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {text}", do_remove_cq_code=False)
        resp = self.waitMsg(qqid, timeout=timeout, group_id=group_id)
        if isinstance(resp, str):
            return resp.strip()
        return None

    @staticmethod
    def orion_ui_border():
        """返回 Orion 菜单统一使用的装饰边框。"""
        return "✧✦〓〓〓〓〓〓〓〓〓〓〓✦✧"

    def orion_ui_menu(self, subtitle: str, options: list[str], hints: list[str]):
        """生成 Orion 风格的普通菜单文本。"""
        parts = [self.orion_ui_border(), f"❐ 『Orion System 猎户座』 {subtitle}"]
        parts.extend([f"[ {i + 1} ] {text}" for i, text in enumerate(options)])
        parts.append(self.orion_ui_border())
        parts.extend([f"❀ {hint}" for hint in hints])
        return "\n".join(parts)

    def plugin_ui_menu(
        self,
        system_name: str,
        subtitle: str,
        options: list[str],
        hints: list[str],
    ):
        """生成插件内部复用的菜单文本。"""
        parts = [self.orion_ui_border(), f"❐ 『{system_name}』 {subtitle}"]
        parts.extend([f"[ {i + 1} ] {text}" for i, text in enumerate(options)])
        parts.append(self.orion_ui_border())
        parts.extend([f"❀ {hint}" for hint in hints])
        return "\n".join(parts)

    def orion_ui_list(
        self,
        subtitle: str,
        items: list[str],
        page: int,
        total_pages: int,
        select_hint: str,
        search_hint: str | None = None,
    ):
        """生成带分页和搜索提示的列表菜单文本。"""
        parts = [self.orion_ui_border(), f"❐ 『Orion System 猎户座』 {subtitle}"]
        parts.extend([f"[ {i + 1} ] {text}" for i, text in enumerate(items)])
        parts.append(self.orion_ui_border())
        parts.append(f"❀ 当前第 {page}/{total_pages} 页")
        parts.append(f"❀ 输入 {select_hint}")
        if search_hint:
            parts.append(f"❀ 输入 {search_hint}")
        parts.append("❀ 输入 - 转到上一页")
        parts.append("❀ 输入 + 转到下一页")
        parts.append("❀ 输入 正整数+页 转到对应页")
        parts.append("❀ 输入 . 退出")
        return "\n".join(parts)

    def get_orion_items_per_page(self, group_id: int):
        """读取 Orion 菜单每页条数配置。"""
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["QQ群封禁/解封菜单每页显示个数"]),
                )
            except (KeyError, TypeError, ValueError):
                return 10
        return 10

    def orion_xuid_status_text(self, xuid: str):
        """读取某个 xuid 在 Orion 中的封禁状态摘要。"""
        orion = self.require_orion()
        path = f"{orion.data_path}/{orion.config_mgr.xuid_dir}/{xuid}.json"
        if not os.path.exists(path):
            return "未封禁"
        try:
            data = orion.utils.disk_read_need_exists(path)
        except Exception:
            return "状态异常"
        return f"封禁至: {data.get('ban_end_real_time', '未知')}"

    def orion_device_status_text(self, device_id: str):
        """读取某个设备号在 Orion 中的封禁状态摘要。"""
        orion = self.require_orion()
        path = f"{orion.data_path}/{orion.config_mgr.device_id_dir}/{device_id}.json"
        if not os.path.exists(path):
            return "未封禁"
        try:
            data = orion.utils.disk_read_need_exists(path)
        except Exception:
            return "状态异常"
        return f"封禁至: {data.get('ban_end_real_time', '未知')}"

    @staticmethod
    def format_device_history(player_data: dict[str, list[str]]):
        """把设备号关联历史压缩成适合列表展示的单行文本。"""
        outputs: list[str] = []
        for xuid, names in list(player_data.items())[:3]:
            if isinstance(names, list) and names:
                outputs.append(f"{xuid}:{'/'.join(names[-2:])}")
            else:
                outputs.append(f"{xuid}:[]")
        if len(player_data) > 3:
            outputs.append("...")
        return "; ".join(outputs)

    def build_online_xuid_data(self):
        """构建当前在线玩家的 xuid 映射。"""
        orion = self.require_orion()
        result: dict[str, str] = {}
        for player_name in self.game_ctrl.allplayers.copy():
            try:
                xuid = orion.xuid_getter.get_xuid_by_name(player_name)
            except Exception:
                continue
            result[xuid] = player_name
        return result

    def build_historical_xuid_data(self):
        """读取历史玩家名称到 xuid 的映射数据。"""
        path = os.path.join("插件数据文件", "前置-玩家XUID获取", "xuids.json")
        try:
            return self.orion.utils.disk_read_need_exists(path) if self.orion else {}
        except Exception:
            return {}

    def build_device_history_data(self):
        """读取 Orion 设备号与玩家历史的映射数据。"""
        orion = self.require_orion()
        path = f"{orion.data_path}/{orion.config_mgr.player_data_file}"
        try:
            data = orion.utils.disk_read_need_exists(path)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _show_paginated_orion_menu(
        self,
        group_id: int,
        qqid: int,
        title: str,
        matched_items: list[dict[str, object]],
        page: int,
        per_page: int,
        select_hint: str,
        search_hint: str | None,
    ):
        """渲染一页列表菜单，并返回用户输入与分页边界。"""
        total_pages, start_index, end_index = self.orion.utils.paginate(
            len(matched_items),
            per_page,
            page,
        )
        output_lines = [
            item["display"]
            for item in matched_items[start_index - 1 : end_index]
        ]
        self.sendmsg(
            group_id,
            f"[CQ:at,qq={qqid}] "
            + self.orion_ui_list(
                title,
                output_lines,
                page,
                total_pages,
                select_hint.format(start_index=start_index, end_index=end_index),
                search_hint,
            ),
            do_remove_cq_code=False,
        )
        user_input = self.waitMsg(qqid, timeout=60, group_id=group_id)
        return user_input, total_pages, start_index, end_index

    def _handle_paginated_orion_input(
        self,
        group_id: int,
        qqid: int,
        user_input: str | None,
        page: int,
        total_pages: int,
        allow_search: bool,
        search: str,
    ):
        """统一处理分页菜单中的翻页、退出、搜索和选择输入。"""
        if user_input is None:
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单",
                do_remove_cq_code=False,
            )
            return "exit", None

        user_input = user_input.strip()
        if user_input.lower() in ("q", ".", "。"):
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] ❀ 已退出菜单",
                do_remove_cq_code=False,
            )
            return "exit", None

        if user_input == "+":
            if page < total_pages:
                return "page", page + 1
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] ❀ 已经是最后一页啦~",
                do_remove_cq_code=False,
            )
            return "retry", None

        if user_input == "-":
            if page > 1:
                return "page", page - 1
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] ❀ 已经是第一页啦~",
                do_remove_cq_code=False,
            )
            return "retry", None

        if match := re.fullmatch(r"^([1-9]\d*)页$", user_input):
            page_num = int(match.group(1))
            if 1 <= page_num <= total_pages:
                return "page", page_num
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] ❀ 不存在第 {page_num} 页！请重新输入！",
                do_remove_cq_code=False,
            )
            return "retry", None

        choice = utils.try_int(user_input)
        if choice is not None:
            return "choice", choice

        if allow_search:
            return "search", user_input.replace("\\", "")

        self.sendmsg(
            group_id,
            f"[CQ:at,qq={qqid}] ❀ 您的输入有误",
            do_remove_cq_code=False,
        )
        return "retry", search

    def _select_paginated_orion_items(
        self,
        group_id: int,
        qqid: int,
        title: str,
        build_matches,
        empty_message: str,
        select_hint: str,
        search_hint: str | None,
        allow_search: bool = True,
    ):
        """执行一套通用的分页选择流程。"""
        search = ""
        page = 1
        per_page = self.get_orion_items_per_page(group_id)
        while True:
            matched_items = build_matches(search)
            if not matched_items:
                self.sendmsg(
                    group_id,
                    f"[CQ:at,qq={qqid}] {empty_message}",
                    do_remove_cq_code=False,
                )
                return None

            user_input, total_pages, start_index, end_index = (
                self._show_paginated_orion_menu(
                    group_id,
                    qqid,
                    title,
                    matched_items,
                    page,
                    per_page,
                    select_hint,
                    search_hint,
                )
            )
            action, value = self._handle_paginated_orion_input(
                group_id,
                qqid,
                user_input,
                page,
                total_pages,
                allow_search,
                search,
            )
            if action == "exit":
                return None
            if action == "page":
                page = value
                continue
            if action == "search":
                search = value
                page = 1
                continue
            if action == "retry":
                continue
            if action == "choice" and value in range(start_index, end_index + 1):
                return matched_items[value - 1]
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] ❀ 您的输入有误",
                do_remove_cq_code=False,
            )

    def qq_select_orion_xuid(
        self,
        group_id: int,
        qqid: int,
        title: str,
        xuid_data: dict[str, str],
        allow_search: bool = True,
    ):
        """从 xuid 列表里分页选择目标玩家。

        返回 `(xuid, 玩家名)`，失败或退出时返回 `(None, None)`。
        """
        selected = self._select_paginated_orion_items(
            group_id,
            qqid,
            title,
            lambda search: [
                {
                    "value": (xuid, name),
                    "display": (
                        f"{xuid} - {name}"
                        f" - {self.orion_xuid_status_text(xuid)}"
                    ),
                }
                for xuid, name in xuid_data.items()
                if search == "" or search in xuid or search in name
            ],
            "找不到您输入的 xuid 或玩家名称",
            "[{start_index}-{end_index}] 之间的数字以选择 对应玩家",
            "xuid、玩家名称或玩家部分名称 可尝试搜索",
            allow_search=allow_search,
        )
        if selected is None:
            return None, None
        return selected["value"]

    def qq_select_orion_device(
        self,
        group_id: int,
        qqid: int,
        title: str,
        device_data: dict[str, dict[str, list[str]]],
    ):
        """从设备号列表里分页选择目标设备。"""
        selected = self._select_paginated_orion_items(
            group_id,
            qqid,
            title,
            lambda search: [
                {
                    "value": (device_id, player_info),
                    "display": (
                        f"{device_id} - {self.format_device_history(player_info)}"
                        f" - {self.orion_device_status_text(device_id)}"
                    ),
                }
                for device_id, player_info in device_data.items()
                if search == ""
                or search in device_id
                or search in self.format_device_history(player_info)
            ],
            "找不到您输入的设备号或玩家名称",
            "[{start_index}-{end_index}] 之间的数字以选择 对应设备号",
            "设备号、玩家名称或玩家部分名称 可尝试搜索",
        )
        if selected is None:
            return None, None
        return selected["value"]

    def qq_get_orion_ban_time(self, group_id: int, qqid: int):
        """统一处理群里输入的封禁时长。"""
        prompt = self.orion_ui_menu(
            "封禁时间输入",
            [],
            [
                "输入 -1 表示永久封禁",
                "输入 正整数 表示封禁秒数",
                "输入 0年0月5日6时7分8秒 表示对应时长",
                "输入 . 退出",
            ],
        )
        user_input = self.qq_prompt(group_id, qqid, prompt, timeout=120)
        if user_input is None:
            self.reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return None
        if user_input.lower() in ("q", ".", "。"):
            self.reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        ban_time = self.orion.utils.ban_time_format(user_input) if self.orion else 0
        if ban_time == 0:
            self.reply_to_qq(group_id, qqid, "❀ 您输入的封禁时间有误")
            return None
        return ban_time

    def qq_get_orion_reason(self, group_id: int, qqid: int):
        """获取封禁原因，允许直接回车走默认文案。"""
        user_input = self.qq_prompt(
            group_id,
            qqid,
            self.orion_ui_menu(
                "封禁原因输入",
                [],
                [
                    "请输入封禁原因",
                    "直接回车使用默认原因“群聊管理员封禁”",
                    "输入 . 退出",
                ],
            ),
            timeout=120,
        )
        if user_input is None:
            self.reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return None
        if user_input.lower() in ("q", ".", "。"):
            self.reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return None
        return user_input or "群聊管理员封禁"

    def _select_orion_ban_target(self, group_id: int, qqid: int, choice: str):
        """根据封禁模式选择具体目标对象。"""
        if choice == "1":
            xuid, player_name = self.qq_select_orion_xuid(
                group_id,
                qqid,
                "在线玩家封禁",
                self.build_online_xuid_data(),
            )
            if not xuid or not player_name:
                return None
            return {
                "kind": "xuid",
                "payload": (xuid, player_name),
                "online_only": True,
            }
        if choice == "2":
            xuid, player_name = self.qq_select_orion_xuid(
                group_id,
                qqid,
                "历史玩家封禁",
                self.build_historical_xuid_data(),
            )
            if not xuid or not player_name:
                return None
            return {
                "kind": "xuid",
                "payload": (xuid, player_name),
                "online_only": False,
            }
        if choice == "3":
            device_id, player_info = self.qq_select_orion_device(
                group_id,
                qqid,
                "设备号封禁",
                self.build_device_history_data(),
            )
            if not device_id or not player_info:
                return None
            return {
                "kind": "device",
                "payload": (device_id, player_info),
            }
        self.reply_to_qq(group_id, qqid, "❀ 您的输入有误")
        return None

    def _apply_selected_orion_ban(self, group_id: int, qqid: int, ban_target: dict):
        """把封禁时间和封禁原因的通用交互流程复用到所有封禁模式。"""
        ban_time = self.qq_get_orion_ban_time(group_id, qqid)
        if ban_time is None:
            return
        reason = self.qq_get_orion_reason(group_id, qqid)
        if reason is None:
            return

        if ban_target["kind"] == "xuid":
            xuid, player_name = ban_target["payload"]
            ok, msg = self.apply_orion_xuid_ban(
                xuid,
                player_name,
                ban_time,
                reason,
                online_only=ban_target.get("online_only", False),
            )
        else:
            device_id, player_info = ban_target["payload"]
            ok, msg = self.apply_orion_device_ban(
                device_id,
                player_info,
                ban_time,
                reason,
            )
        self.reply_result(group_id, qqid, ok, msg)

    def qq_orion_ban_menu(self, group_id: int, qqid: int):
        """交互式 Orion 封禁菜单。"""
        if self.orion is None:
            self.reply_to_qq(group_id, qqid, "未检测到 Orion_System 插件")
            return
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.orion_ui_menu(
                "封禁管理系统",
                ["根据在线玩家名称和xuid封禁", "根据历史玩家名称和xuid封禁", "根据设备号封禁"],
                ["输入 [1-3] 之间的数字以选择 封禁模式", "输入 . 退出"],
            ),
            timeout=120,
        )
        if choice is None:
            self.reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if choice.lower() in ("q", ".", "。"):
            self.reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        ban_target = self._select_orion_ban_target(group_id, qqid, choice)
        if ban_target is None:
            return
        self._apply_selected_orion_ban(group_id, qqid, ban_target)

    def qq_orion_unban_menu(self, group_id: int, qqid: int):
        """交互式 Orion 解封菜单。"""
        if self.orion is None:
            self.reply_to_qq(group_id, qqid, "未检测到 Orion_System 插件")
            return
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.orion_ui_menu(
                "解封管理系统",
                ["根据玩家名称和xuid解封", "根据设备号解封"],
                ["输入 [1-2] 之间的数字以选择 解封模式", "输入 . 退出"],
            ),
            timeout=120,
        )
        if choice is None:
            self.reply_to_qq(group_id, qqid, "❀ 回复超时！ 已退出菜单")
            return
        if choice.lower() in ("q", ".", "。"):
            self.reply_to_qq(group_id, qqid, "❀ 已退出菜单")
            return
        if choice == "1":
            xuid_dir = f"{self.orion.data_path}/{self.orion.config_mgr.xuid_dir}"
            xuid_data: dict[str, str] = {}
            if os.path.isdir(xuid_dir):
                for xuid_json in os.listdir(xuid_dir):
                    xuid = xuid_json.replace(".json", "")
                    try:
                        xuid_data[xuid] = self.orion.xuid_getter.get_name_by_xuid(
                            xuid,
                            True,
                        )
                    except Exception:
                        xuid_data[xuid] = xuid
            xuid, player_name = self.qq_select_orion_xuid(
                group_id,
                qqid,
                "xuid 解封",
                xuid_data,
                allow_search=True,
            )
            if not xuid or not player_name:
                return
            ok, msg = self.apply_orion_xuid_unban(xuid, player_name)
            self.reply_result(group_id, qqid, ok, msg)
            return
        if choice == "2":
            device_dir = f"{self.orion.data_path}/{self.orion.config_mgr.device_id_dir}"
            player_data = self.build_device_history_data()
            device_data: dict[str, dict[str, list[str]]] = {}
            if os.path.isdir(device_dir):
                for device_json in os.listdir(device_dir):
                    device_id = device_json.replace(".json", "")
                    device_data[device_id] = player_data.get(device_id, {})
            device_id, player_info = self.qq_select_orion_device(
                group_id,
                qqid,
                "设备号解封",
                device_data,
            )
            if not device_id or player_info is None:
                return
            ok, msg = self.apply_orion_device_unban(device_id, player_info)
            self.reply_result(group_id, qqid, ok, msg)
            return
        self.reply_to_qq(group_id, qqid, "❀ 您的输入有误")

    def resolve_orion_target(self, target: str):
        """把群里的输入尽量解析成稳定的 `(xuid, 玩家名)` 组合。"""
        if self.orion is None:
            return None, None, "未检测到 Orion_System 插件"
        if not hasattr(self.orion, "xuid_getter"):
            return None, None, "Orion 插件尚未完成初始化"

        # 先按玩家名解析，失败再把输入当 xuid 处理，兼容群里两种用法。
        try:
            xuid = self.orion.xuid_getter.get_xuid_by_name(target, True)
            try:
                player_name = self.orion.xuid_getter.get_name_by_xuid(xuid, True)
            except Exception:
                player_name = target
        except Exception:
            xuid = target
            try:
                player_name = self.orion.xuid_getter.get_name_by_xuid(xuid, True)
            except Exception:
                player_name = target

        if not isinstance(xuid, str) or not xuid:
            return None, None, "无法解析玩家名称或 xuid"
        return xuid, player_name, None

    def orion_ban_player(self, target: str, ban_time_raw: str, reason: str):
        """非交互式封禁入口，给命令行式调用使用。"""
        xuid, player_name, error = self.resolve_orion_target(target)
        if error:
            return False, error
        orion = self.require_orion()
        ban_time = orion.utils.ban_time_format(ban_time_raw)
        return self.apply_orion_xuid_ban(xuid, player_name, ban_time, reason)

    def orion_unban_player(self, target: str):
        """非交互式解封入口，供命令式调用复用。"""
        xuid, player_name, error = self.resolve_orion_target(target)
        if error:
            return False, error
        return self.apply_orion_xuid_unban(xuid, player_name)

    def apply_orion_xuid_ban(
        self,
        xuid: str,
        player_name: str,
        ban_time: int | str,
        reason: str,
        online_only: bool = False,
    ):
        """写入 xuid 封禁记录，并在需要时踢出对应在线玩家。"""
        orion = self.require_orion()
        # 实际封禁前会先过一遍在线状态和 Orion 自己的白名单检查。
        if online_only and player_name not in self.game_ctrl.allplayers:
            return False, f"玩家 {player_name} 当前不在线"
        if orion.utils.in_whitelist(player_name):
            return False, f"玩家 {player_name} 位于 Orion 反制白名单内"
        timestamp_now, date_now = orion.utils.now()
        path = f"{orion.data_path}/{orion.config_mgr.xuid_dir}/{xuid}.json"
        with orion.lock_ban_xuid:
            ban_data = orion.utils.disk_read(path)
            timestamp_end, date_end = orion.utils.calculate_ban_end_time(
                ban_data,
                ban_time,
                timestamp_now,
            )
            if timestamp_end is False or date_end is False:
                return False, f"玩家 {player_name} 已经是永久封禁"
            orion.utils.disk_write(
                path,
                {
                    "xuid": xuid,
                    "name": player_name,
                    "ban_start_real_time": date_now,
                    "ban_start_timestamp": timestamp_now,
                    "ban_end_real_time": date_end,
                    "ban_end_timestamp": timestamp_end,
                    "ban_reason": reason,
                },
            )
        if player_name in self.game_ctrl.allplayers:
            orion.utils.kick(player_name, f"由于{reason}，您被系统封禁至：{date_end}")
        return True, f"已通过 Orion 封禁 {player_name} (xuid:{xuid}) 至 {date_end}"

    def apply_orion_device_ban(
        self,
        device_id: str,
        player_info: dict[str, list[str]],
        ban_time: int | str,
        reason: str,
    ):
        """写入设备号封禁记录，并处理命中该设备号的在线玩家。"""
        orion = self.require_orion()
        # 设备号封禁会顺手踢掉当前在线、且命中过这个设备号的玩家。
        timestamp_now, date_now = orion.utils.now()
        path = f"{orion.data_path}/{orion.config_mgr.device_id_dir}/{device_id}.json"
        with orion.lock_ban_device_id:
            ban_data = orion.utils.disk_read(path)
            timestamp_end, date_end = orion.utils.calculate_ban_end_time(
                ban_data,
                ban_time,
                timestamp_now,
            )
            if timestamp_end is False or date_end is False:
                return False, f"设备号 {device_id} 已经是永久封禁"
            orion.utils.disk_write(
                path,
                {
                    "device_id": device_id,
                    "xuid_and_player": player_info,
                    "ban_start_real_time": date_now,
                    "ban_start_timestamp": timestamp_now,
                    "ban_end_real_time": date_end,
                    "ban_end_timestamp": timestamp_end,
                    "ban_reason": reason,
                },
            )
        for _xuid, names in player_info.items():
            kick_name = None
            if isinstance(names, list):
                for name in reversed(names):
                    if name in self.game_ctrl.allplayers:
                        kick_name = name
                        break
            if kick_name:
                orion.utils.kick(kick_name, f"由于{reason}，您被系统封禁至：{date_end}")
        return True, f"已通过 Orion 封禁设备号 {device_id} 至 {date_end}"

    def apply_orion_xuid_unban(self, xuid: str, player_name: str):
        """删除 Orion 中某个 xuid 的封禁记录。"""
        orion = self.require_orion()
        path = f"{orion.data_path}/{orion.config_mgr.xuid_dir}/{xuid}.json"
        if not os.path.exists(path):
            return False, f"玩家 {player_name} 当前不在 Orion 的 xuid 封禁列表中"
        os.remove(path)
        return True, f"已通过 Orion 解封 {player_name} (xuid:{xuid})"

    def apply_orion_device_unban(
        self,
        device_id: str,
        player_info: dict[str, list[str]],
    ):
        """删除 Orion 中某个设备号的封禁记录。"""
        orion = self.require_orion()
        path = f"{orion.data_path}/{orion.config_mgr.device_id_dir}/{device_id}.json"
        if not os.path.exists(path):
            return False, f"设备号 {device_id} 当前不在 Orion 的设备号封禁列表中"
        os.remove(path)
        return True, f"已通过 Orion 解封设备号 {device_id}"

    def _prompt_console_group_id(self):
        """在控制台里选择要操作的目标群。"""
        while True:
            group_input = input(
                fmts.fmt_info("§a❀ §b请输入群序号，输入 q 退出: ")
            ).strip().lower()
            if group_input == "q":
                self.print_console_error("已退出QQ群管理员管理菜单")
                return None
            group_index = utils.try_int(group_input)
            if group_index is None or group_index not in range(
                1,
                len(self.group_order) + 1,
            ):
                self.print_console_error("群序号无效")
                continue
            return self.group_order[group_index - 1]

    def _prompt_console_remove_flag(self):
        """在控制台里选择是添加还是删除管理员。"""
        while True:
            action_input = self.prompt_console_input(
                "群服互通 控制台管理",
                "选择操作",
                ["输入 1 添加管理员", "输入 2 删除管理员", "输入 q 退出菜单"],
                "请输入操作类型 (1=添加, 2=删除, q=退出): ",
            ).lower()
            if action_input == "q":
                self.print_console_error("已退出QQ群管理员管理菜单")
                return None
            if action_input in ("1", "2"):
                return action_input == "2"
            self.print_console_error("操作类型无效")

    def _prompt_console_super_flag(self):
        """在控制台里选择普通管理员还是超级管理员。"""
        while True:
            role_input = self.prompt_console_input(
                "群服互通 控制台管理",
                "选择角色",
                ["输入 1 普通管理员", "输入 2 超级管理员", "输入 q 退出菜单"],
                "请输入角色类型 (1=普通管理员, 2=超级管理员, q=退出): ",
            ).lower()
            if role_input == "q":
                self.print_console_error("已退出QQ群管理员管理菜单")
                return None
            if role_input in ("1", "2"):
                return role_input == "2"
            self.print_console_error("角色类型无效")

    def _prompt_console_qqid(self, is_remove: bool):
        """在控制台里读取要增删的 QQ 号。"""
        while True:
            qq_input = self.prompt_console_input(
                "群服互通 控制台管理",
                "输入 QQ",
                [
                    f"请输入要{'删除' if is_remove else '添加'}的 QQ 号",
                    "输入 q 退出菜单",
                ],
                f"请输入要{'删除' if is_remove else '添加'}的QQ号，输入 q 退出: ",
            ).lower()
            if qq_input == "q":
                self.print_console_error("已退出QQ群管理员管理菜单")
                return None
            qqid = utils.try_int(qq_input)
            if qqid is None or qqid <= 0:
                self.print_console_error("QQ号无效")
                continue
            return qqid

    def on_console_add_qq_op(self, _args: list[str]):
        """控制台侧管理群管理员，主要给服主离线处理配置时使用。"""
        if not self.group_order:
            self.print_console_error("当前没有配置任何群聊")
            return
        summary_lines = []
        for index, group_id in enumerate(self.group_order, start=1):
            state = self.read_group_state(group_id)
            summary_lines.append(
                f"[ {index} ] 群 {group_id}"
                f" - 管理员:{len(state['admins'])}"
                f" / 超级管理员:{len(state['super_admins'])}"
            )
        summary_lines.extend(
            [
                "输入群序号继续操作",
                "输入 q 退出菜单",
            ]
        )
        self.print_console_card(
            "群服互通 控制台管理",
            "OPQQ",
            summary_lines,
            level="info",
        )
        target_group = self._prompt_console_group_id()
        if target_group is None:
            return
        is_remove = self._prompt_console_remove_flag()
        if is_remove is None:
            return
        is_super = self._prompt_console_super_flag()
        if is_super is None:
            return
        qqid = self._prompt_console_qqid(is_remove)
        if qqid is None:
            return

        if is_remove:
            ok, msg = self.remove_group_role(target_group, qqid, is_super=is_super)
        else:
            ok, msg = self.add_group_role(target_group, qqid, is_super=is_super)
        if ok:
            self.print_console_success(f"群 {target_group}: {msg}")
        else:
            self.print_console_error(f"群 {target_group}: {msg}")

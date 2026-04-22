import re
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

        if not self.is_group_admin(group_id, qqid):
            self.sendmsg(group_id, "你没有权限执行此指令")
            return
        res = self.execute_cmd_and_get_zhcn_cb(" ".join(cmd))
        self.sendmsg(group_id, res)

    def on_qq_help(self, group_id: int, sender: int, _):
        """根据当前群配置和权限状态动态生成帮助菜单。"""

        options: list[str] = []
        options.append(
            f"{'/'.join(self.get_group_help_triggers(group_id))} - 查看群服互通帮助菜单"
        )
        if self.is_group_super_admin(group_id, sender):
            options.append(
                f"{' / '.join(self.get_group_admin_menu_triggers(group_id))} - 打开普通管理员管理菜单"
            )
        options.append(
            f"{self.get_group_cmd_prefix(group_id)}[指令] - 向租赁服发送指令"
            + ("（本群管理员与超级管理员可用，无需额外配置 QQ 号）")
        )
        if self.group_cfgs[group_id]["指令设置"]["是否允许查看玩家列表"]:
            options.append(
                f"{' / '.join(self.get_group_player_list_triggers(group_id))} - 查看玩家列表"
            )
        options.append(
            f"{' / '.join(self.get_group_inventory_menu_triggers(group_id))} - 查询在线玩家背包"
        )
        options.append(
            f"{' / '.join(self.get_group_orion_ban_triggers(group_id))} - Orion QQ 封禁菜单"
        )
        options.append(
            f"{' / '.join(self.get_group_orion_unban_triggers(group_id))} - Orion QQ 解封菜单"
        )
        options.append(
            f"{' / '.join(self.get_group_checker_menu_triggers(group_id))} - 白名单&管理员检测云链联动版 管理菜单"
        )
        text = self.plugin_ui_menu(
            "群服互通云链版Ultra版",
            "帮助菜单",
            options,
            ["输入 . 退出"],
        )
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {text}", do_remove_cq_code=False)

    def on_qq_player_list(self, group_id: int, _sender: int, _):
        """把在线玩家列表和可用 TPS 信息发到群里。"""

        group_cfg = self.group_cfgs[group_id]
        if not group_cfg["指令设置"]["是否允许查看玩家列表"]:
            self.sendmsg(group_id, "当前群未启用玩家列表查询")
            return
        players = [f"{i + 1}.{j}" for i, j in enumerate(self.game_ctrl.allplayers)]
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

        online_names = list(self.game_ctrl.allplayers)
        if not online_names:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 当前没有在线玩家", do_remove_cq_code=False)
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
            page_names = online_names[start_index - 1 : end_index]
            text = self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "查询背包",
                page_names,
                [
                    f"当前第 {page}/{total_pages} 页",
                    f"输入 [{start_index}-{end_index}] 之间的数字以选择 对应玩家",
                    "输入 - 转到上一页",
                    "输入 + 转到下一页",
                    "输入 正整数+页 转到对应页",
                    "输入 . 退出",
                ],
            )
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {text}", do_remove_cq_code=False)
            user_input = self.waitMsg(qqid, timeout=120, group_id=group_id)
            if user_input is None:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
                return
            user_input = user_input.strip()
            if user_input.lower() in ("q", ".", "。"):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
                return
            if user_input == "+":
                # 菜单保持在同一条交互链里，翻页只改当前页码。
                if page < total_pages:
                    page += 1
                else:
                    self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已经是最后一页啦~", do_remove_cq_code=False)
                continue
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已经是第一页啦~", do_remove_cq_code=False)
                continue
            if match := re.fullmatch(r"^([1-9]\d*)页$", user_input):
                page_num = int(match.group(1))
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 不存在第 {page_num} 页！请重新输入！", do_remove_cq_code=False)
                continue
            choice = utils.try_int(user_input)
            if choice is None or choice not in range(start_index, end_index + 1):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 您的输入有误", do_remove_cq_code=False)
                continue
            self.show_player_inventory(group_id, qqid, online_names[choice - 1])
            return

    @staticmethod
    def simple_paginate(total_len: int, per_page: int, page: int):
        """在缺少 utils.paginate 时使用的本地分页兜底实现。"""

        total_pages = max(1, (total_len + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start_index = (page - 1) * per_page + 1
        end_index = min(page * per_page, total_len)
        return total_pages, start_index, end_index

    def show_player_inventory(self, group_id: int, qqid: int, player_name: str):
        """把背包槽位整理成适合群聊阅读的文本。"""

        player_obj = self.game_ctrl.players.getPlayerByName(player_name)
        if player_obj is None:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 玩家 {player_name} 当前已不在线", do_remove_cq_code=False)
            return
        try:
            inventory = player_obj.queryInventory()
        except Exception as err:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 查询背包失败: {err}", do_remove_cq_code=False)
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
        )
        self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {text}", do_remove_cq_code=False)

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
            if isinstance(translated, str) and translated and translated != key:
                return translated
        return item_id

    @staticmethod
    def get_item_custom_name(slot: Any):
        """尝试从物品槽位对象里提取自定义名称。"""
        for attr in ("customName", "custom_name", "name"):
            value = getattr(slot, attr, None)
            if isinstance(value, str) and value.strip() and value.strip() != getattr(slot, "id", ""):
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
        if not self.is_group_super_admin(group_id, sender):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 只有本群超级管理员可以添加管理员", do_remove_cq_code=False)
            return
        try:
            qqid = int(args[0])
        except (TypeError, ValueError):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] QQ号格式有误", do_remove_cq_code=False)
            return
        _ok, msg = self.add_group_role(group_id, qqid, is_super=False)
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {msg}", do_remove_cq_code=False)

    def qq_admin_menu(self, group_id: int, qqid: int):
        """给群超级管理员使用的普通管理员管理菜单。"""

        if not self.is_group_super_admin(group_id, qqid):
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] 只有本群超级管理员可以打开管理员菜单",
                do_remove_cq_code=False,
            )
            return
        # 普通管理员的增删统一走一个小菜单，避免群里散落多条半交互命令。
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "普通管理员 管理菜单",
                ["添加普通管理员", "删除普通管理员"],
                ["输入 [1-2] 之间的数字以选择 对应功能", "输入 . 退出"],
            ),
            timeout=120,
        )
        if choice is None:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
            return
        if choice.lower() in ("q", ".", "。"):
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
            return
        if choice not in ("1", "2"):
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 您的输入有误", do_remove_cq_code=False)
            return
        qq_text = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "普通管理员 管理菜单",
                [],
                [f"请输入要{'添加' if choice == '1' else '删除'}的 QQ 号", "输入 . 退出"],
            ),
            timeout=120,
        )
        if qq_text is None:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
            return
        if qq_text.lower() in ("q", ".", "。"):
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
            return
        qqid_target = utils.try_int(qq_text)
        if qqid_target is None or qqid_target <= 0:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ QQ号格式有误", do_remove_cq_code=False)
            return
        if choice == "1":
            ok, msg = self.add_group_role(group_id, qqid_target, is_super=False)
        else:
            ok, msg = self.remove_group_role(group_id, qqid_target, is_super=False)
        self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {'😄' if ok else '😭'} {msg}", do_remove_cq_code=False)

    def ensure_whitelist_checker(self, group_id: int, sender: int):
        """检查白名单联动插件是否可用，避免菜单点进去后才报空引用。"""

        if self.whitelist_checker is None:
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={sender}] 未检测到插件 白名单&管理员检测云链联动版",
                do_remove_cq_code=False,
            )
            return False
        return True

    def on_qq_whitelist_add(self, group_id: int, sender: int, args: list[str]):
        """通过群命令把玩家加入白名单。"""
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.add_whitelist_player(args[0])
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {'😄' if ok else '😭'} {msg}", do_remove_cq_code=False)

    def on_qq_whitelist_remove(self, group_id: int, sender: int, args: list[str]):
        """通过群命令把玩家移出白名单。"""
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.remove_whitelist_player(args[0])
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {'😄' if ok else '😭'} {msg}", do_remove_cq_code=False)

    def on_qq_server_admin_add(self, group_id: int, sender: int, args: list[str]):
        """通过群命令把玩家登记为服务器管理员。"""
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.add_admin_player(args[0])
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {'😄' if ok else '😭'} {msg}", do_remove_cq_code=False)

    def on_qq_server_admin_remove(self, group_id: int, sender: int, args: list[str]):
        """通过群命令把玩家从服务器管理员名单中移除。"""
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.remove_admin_player(args[0])
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {'😄' if ok else '😭'} {msg}", do_remove_cq_code=False)

    def on_qq_whitelist_toggle(self, group_id: int, sender: int, args: list[str]):
        """通过群命令切换白名单检测开关。"""
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        action = args[0].strip()
        if action not in ("开启", "关闭", "on", "off"):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 参数错误，格式：白名单检测 [开启/关闭]", do_remove_cq_code=False)
            return
        ok, msg = self.whitelist_checker.set_whitelist_enabled(action in ("开启", "on"))
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {'😄' if ok else '😭'} {msg}", do_remove_cq_code=False)

    def on_qq_admin_check_toggle(self, group_id: int, sender: int, args: list[str]):
        """通过群命令切换管理员检测开关。"""
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        action = args[0].strip()
        if action not in ("开启", "关闭", "on", "off"):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 参数错误，格式：管理员检测 [开启/关闭]", do_remove_cq_code=False)
            return
        ok, msg = self.whitelist_checker.set_admin_check_enabled(action in ("开启", "on"))
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {'😄' if ok else '😭'} {msg}", do_remove_cq_code=False)

    def on_qq_check_interval(self, group_id: int, sender: int, args: list[str]):
        """通过群命令修改联动插件的轮询周期。"""
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        try:
            seconds = float(args[0])
        except (TypeError, ValueError):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 参数错误，格式：检测周期 [秒数]", do_remove_cq_code=False)
            return
        ok, msg = self.whitelist_checker.set_check_interval(seconds)
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {'😄' if ok else '😭'} {msg}", do_remove_cq_code=False)

    def on_qq_check_status(self, group_id: int, sender: int, _args: list[str]):
        """把联动插件当前状态摘要发回群里。"""
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

    def qq_checker_menu(self, group_id: int, qqid: int):
        """在群里打开白名单与管理员检测联动菜单。"""
        if not self.ensure_whitelist_checker(group_id, qqid):
            return
        # 这个菜单本质上是把白名单插件暴露出来的 API 做了一层群聊版操作面板。
        # 这样权限仍然统一归群服互通管理，而不是把原插件的控制台能力原样暴露出来。
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "白名单&管理员检测云链联动版",
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
            ),
            timeout=120,
        )
        if choice is None:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
            return
        if choice.lower() in ("q", ".", "。"):
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
            return

        if choice in ("1", "2", "3", "4"):
            title_map = {
                "1": "白名单 添加玩家",
                "2": "白名单 移除玩家",
                "3": "管理员 添加玩家",
                "4": "管理员 移除玩家",
            }
            player_name = self.qq_prompt(
                group_id,
                qqid,
                self.plugin_ui_menu(
                    "白名单&管理员检测云链联动版",
                    title_map[choice],
                    [],
                    ["请输入玩家名称", "输入 . 退出"],
                ),
                timeout=120,
            )
            if player_name is None:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
                return
            if player_name.lower() in ("q", ".", "。"):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
                return
            if choice == "1":
                self.on_qq_whitelist_add(group_id, qqid, [player_name])
            elif choice == "2":
                self.on_qq_whitelist_remove(group_id, qqid, [player_name])
            elif choice == "3":
                self.on_qq_server_admin_add(group_id, qqid, [player_name])
            else:
                self.on_qq_server_admin_remove(group_id, qqid, [player_name])
            return

        if choice in ("5", "6"):
            subtitle = "白名单检测 设置" if choice == "5" else "管理员检测 设置"
            action = self.qq_prompt(
                group_id,
                qqid,
                self.plugin_ui_menu(
                    "白名单&管理员检测云链联动版",
                    subtitle,
                    ["开启", "关闭"],
                    ["输入 [1-2] 之间的数字以选择 对应操作", "输入 . 退出"],
                ),
                timeout=120,
            )
            if action is None:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
                return
            if action.lower() in ("q", ".", "。"):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
                return
            if action == "1":
                action_arg = ["开启"]
            elif action == "2":
                action_arg = ["关闭"]
            else:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 您的输入有误", do_remove_cq_code=False)
                return
            if choice == "5":
                self.on_qq_whitelist_toggle(group_id, qqid, action_arg)
            else:
                self.on_qq_admin_check_toggle(group_id, qqid, action_arg)
            return

        if choice == "7":
            seconds = self.qq_prompt(
                group_id,
                qqid,
                self.plugin_ui_menu(
                    "白名单&管理员检测云链联动版",
                    "检测周期 设置",
                    [],
                    ["请输入检测周期秒数", "输入 . 退出"],
                ),
                timeout=120,
            )
            if seconds is None:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
                return
            if seconds.lower() in ("q", ".", "。"):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
                return
            self.on_qq_check_interval(group_id, qqid, [seconds])
            return

        if choice == "8":
            self.on_qq_check_status(group_id, qqid, [])
            return

        self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 您的输入有误", do_remove_cq_code=False)

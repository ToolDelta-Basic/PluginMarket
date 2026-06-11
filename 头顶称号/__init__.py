import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from tooldelta import plugin_market, utils
from tooldelta.constants import TOOLDELTA_CLASSIC_PLUGIN_PATH
from tooldelta.internal.types import Chat, FrameExit, Player
from tooldelta.plugin_load import PluginRegData
from tooldelta.plugin_load.classic_plugin import Plugin, plugin_entry


class BelownameTitlePlugin(Plugin):
    """Manage purchasable belowname titles and console administration."""

    name = "头顶称号"
    version = (0, 2, 0)
    author = "南Nan"
    description = "支持购买、切换、管理玩家头顶称号，并接入前置_聊天栏菜单。"

    CHATBAR_PLUGIN_ID = "聊天栏菜单"
    CHATBAR_PLUGIN_DIRNAME = "前置_聊天栏菜单"
    DATA_FILE_NAME = "titles.json"

    def __init__(self, frame):
        super().__init__(frame)
        self.cfg: dict[str, Any] = {}
        self.titles_path: Path | None = None
        self.player_data: dict[str, dict[str, Any]] = {}
        self.player_current_objective: dict[str, str] = {}
        self.managed_objectives: set[str] = set()
        self.pending_console_selection: dict[str, Any] | None = None
        self.console_registered = False
        self.chatbar_registered = False
        self.chatbar_missing_warned = False
        self.scoreboard_checked = False
        self.refresh_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.loop_started = False

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenChat(self.on_chat)
        self.ListenFrameExit(self.on_frame_exit)

    def on_preload(self):
        """Load config, player data, and console command registration."""
        self.cfg, _ = self.get_config_and_version(
            self._config_schema(),
            self._default_config(),
        )
        self.titles_path = self.data_path / self.DATA_FILE_NAME
        self.player_data = self._load_player_data()
        self._rebuild_objective_cache()
        self._register_console_commands()

    def on_active(self):
        """Initialize dependencies and start title refresh after activation."""
        self._ensure_chatbar_plugin()
        self._register_chatbar_menu()
        self._validate_scoreboard_exists_or_raise()
        self.stop_event.clear()
        if not self.loop_started and float(self.cfg["刷新间隔秒"]) > 0:
            self.refresh_loop()
            self.loop_started = True
        self.refresh_all_later(1.0, True)

    def on_player_join(self, player: Player):
        """Initialize a joining player's score state and delayed title refresh."""
        self._ensure_player_default_score(player.name)
        self.refresh_player_later(
            player.name,
            float(self.cfg["进服后延迟刷新秒"]),
            True,
        )

    def on_frame_exit(self, _evt: FrameExit):
        """Stop background refresh work when the frame exits."""
        self.stop_event.set()

    def on_chat(self, chat: Chat):
        """Handle player chat commands when the chatbar menu is unavailable."""
        if self.chatbar_registered:
            return False
        prefix = str(self.cfg["聊天命令前缀"])
        if not chat.msg.startswith(prefix):
            return False
        body = chat.msg[len(prefix) :].strip()
        args = body.split() if body else []
        self._handle_player_command(chat.player, args)
        return True

    def _register_console_commands(self):
        """Register the console entrypoint in the question-mark help menu."""
        if self.console_registered:
            return
        self.frame.add_console_cmd_trigger(
            ["称号"],
            None,
            "输出称号获取菜单",
            self.on_console_command,
        )
        self.console_registered = True

    def on_console_command(self, args: list[str]):
        """Dispatch console subcommands for title administration."""
        reply = self._console_reply()
        if not args:
            self._send_console_help(reply)
            return
        sub = args[0]
        if sub == "新增":
            self._handle_console_add(args[1:], reply)
            return
        if sub == "删除":
            self._handle_console_delete(args[1:], reply)
            return
        if sub == "更改":
            self._handle_console_switch(args[1:], reply)
            return
        if sub == "选择":
            self._handle_console_select(args[1:], reply)
            return
        if sub == "list":
            self._handle_console_list(reply)
            return
        self._send_console_help(reply)

    def _handle_player_command(self, player: Player, args: list[str]):
        """Dispatch player chat commands for title purchase and switching."""
        reply = self._player_reply(player)
        if not args:
            self._send_player_help(reply)
            return
        sub = args[0]
        if sub == "购买称号":
            if len(args) < 2:
                reply("§c用法: .购买称号 称号名字")
                return
            title = " ".join(args[1:]).strip()
            self._buy_title(player, title, reply)
            return
        if sub == "更改称号":
            if len(args) < 2:
                reply("§c用法: .更改称号 称号名字")
                return
            title = " ".join(args[1:]).strip()
            self._switch_own_title(player, title, reply, cost=True)
            return
        if sub == "移除称号":
            self._remove_own_title(player, reply)
            return
        if sub in {"我的称号", "查看称号"}:
            self._show_player_titles(player.name, reply)
            return
        self._send_player_help(reply)

    def _send_player_help(self, reply: Callable[[str], None]):
        """Send the available player title commands to the caller."""
        reply("§a.购买称号 <称号名字> §7- 花费金币购买称号")
        reply("§a.更改称号 <称号名字> §7- 花费金币替换自己当前称号")
        reply("§a.移除称号 §7- 删除自己当前称号")
        reply("§a.我的称号 §7- 查看自己当前使用的称号")

    def _send_console_help(self, reply: Callable[[str], None]):
        """Send the available console title commands to the caller."""
        reply("§a称号 新增 <玩家名> <称号名字> §7- 给玩家新增并设为当前称号")
        reply("§a称号 删除 <玩家名> <称号名字> §7- 删除玩家的指定称号")
        reply("§a称号 更改 <玩家名> <称号名字> §7- 切换玩家当前称号")
        reply("§a称号 选择 <序号> §7- 从模糊匹配候选中选择玩家")
        reply("§a称号 list §7- 查看所有玩家称号")

    def _buy_title(self, player: Player, title: str, reply: Callable[[str], None]):
        """Charge the player, equip the purchased title, and clean up the old one."""
        if not title:
            reply("§c称号名字不能为空")
            return
        self._validate_scoreboard_exists_or_raise()
        self._ensure_player_default_score(player.name)
        pdata = self._get_or_create_player_data(player.name)
        old_title = str(pdata.get("current_title", "") or "")
        if old_title == title:
            reply("§e你已经拥有这个称号了")
            return
        cost = int(self.cfg["购买称号价格"])
        if not self._change_score(player.name, -cost):
            reply(
                f"§c金币不足，购买需要 {cost} {self.cfg['金币计分板名']}。"
            )
            return
        pdata["current_title"] = title
        self._ensure_objective(title)
        self.save_player_data()
        self.refresh_player_later(player.name, 0.2, True)
        if old_title and old_title != title:
            self._cleanup_objective_if_unused(old_title)
        reply(f"§a购买成功，已花费 {cost} 金币并装备称号: §f{title}")

    def _switch_own_title(
        self,
        player: Player,
        title: str,
        reply: Callable[[str], None],
        *,
        cost: bool,
    ):
        """Switch the caller title and optionally charge the configured fee."""
        if not title:
            reply("§c称号名字不能为空")
            return
        self._validate_scoreboard_exists_or_raise()
        self._ensure_player_default_score(player.name)
        pdata = self._get_or_create_player_data(player.name)
        old_title = str(pdata.get("current_title", "") or "")
        if pdata.get("current_title") == title:
            reply("§e你当前已经在使用这个称号")
            return
        switch_cost = int(self.cfg["更改称号价格"])
        if (
            cost
            and switch_cost > 0
            and not self._change_score(player.name, -switch_cost)
        ):
            reply(
                f"§c金币不足，更改需要 {switch_cost} {self.cfg['金币计分板名']}。"
            )
            return
        pdata["current_title"] = title
        self._ensure_objective(title)
        self.save_player_data()
        self.refresh_player_later(player.name, 0.2, True)
        if old_title and old_title != title:
            self._cleanup_objective_if_unused(old_title)
        if cost:
            reply(f"§a更改成功，已扣除 {switch_cost} 金币并切换为: §f{title}")
        else:
            reply(f"§a已切换当前称号为: §f{title}")

    def _remove_own_title(
        self,
        player: Player,
        reply: Callable[[str], None],
    ):
        """Remove the caller's currently equipped title if one exists."""
        title = self._get_or_create_player_data(player.name).get("current_title", "")
        if not isinstance(title, str) or not title.strip():
            reply("§e你当前没有称号可移除")
            return
        self._remove_player_title(player.name, title, reply, actor_label="你")

    def _show_player_titles(self, player_name: str, reply: Callable[[str], None]):
        """Show the current equipped title for the requested player."""
        pdata = self._get_or_create_player_data(player_name)
        current = pdata.get("current_title") or "无"
        reply(f"§a当前称号: §f{current}")

    def _handle_console_add(self, args: list[str], reply: Callable[[str], None]):
        """Validate and dispatch the console add-title request."""
        if len(args) < 2:
            reply("§c用法: 称号 新增 <玩家名> <称号名字>")
            return
        title = " ".join(args[1:]).strip()
        if not title:
            reply("§c称号名字不能为空")
            return
        matched = self._resolve_console_player(args[0], "add", title, reply)
        if matched is None:
            return
        self._execute_console_add(matched, title, reply)

    def _execute_console_add(
        self,
        matched: str,
        title: str,
        reply: Callable[[str], None],
    ):
        """Apply the console add-title request to the resolved player."""
        self._validate_scoreboard_exists_or_raise()
        pdata = self._get_or_create_player_data(matched)
        old_title = str(pdata.get("current_title", "") or "")
        pdata["current_title"] = title
        self._ensure_objective(title)
        self.save_player_data()
        self.refresh_player_later(matched, 0.2, True)
        if old_title and old_title != title:
            self._cleanup_objective_if_unused(old_title)
        reply(f"§a已为玩家 {matched} 新增称号并装备: §f{title}")

    def _handle_console_delete(self, args: list[str], reply: Callable[[str], None]):
        """Validate and dispatch the console delete-title request."""
        if len(args) < 2:
            reply("§c用法: 称号 删除 <玩家名> <称号名字>")
            return
        title = " ".join(args[1:]).strip()
        if not title:
            reply("§c称号名字不能为空")
            return
        matched = self._resolve_console_player(args[0], "delete", title, reply)
        if matched is None:
            return
        self._execute_console_delete(matched, title, reply)

    def _execute_console_delete(
        self,
        matched: str,
        title: str,
        reply: Callable[[str], None],
    ):
        """Apply the console delete-title request to the resolved player."""
        self._remove_player_title(matched, title, reply, actor_label=f"玩家 {matched}")

    def _handle_console_switch(self, args: list[str], reply: Callable[[str], None]):
        """Validate and dispatch the console switch-title request."""
        if len(args) < 2:
            reply("§c用法: 称号 更改 <玩家名> <称号名字>")
            return
        title = " ".join(args[1:]).strip()
        if not title:
            reply("§c称号名字不能为空")
            return
        matched = self._resolve_console_player(args[0], "switch", title, reply)
        if matched is None:
            return
        self._execute_console_switch(matched, title, reply)

    def _execute_console_switch(
        self,
        matched: str,
        title: str,
        reply: Callable[[str], None],
    ):
        """Apply the console switch-title request to the resolved player."""
        pdata = self._get_or_create_player_data(matched)
        old_title = str(pdata.get("current_title", "") or "")
        if old_title == title:
            reply("§e玩家当前已经在使用这个称号")
            return
        if not old_title:
            reply(f"§e玩家 {matched} 当前没有旧称号，将直接设置新称号")
        pdata["current_title"] = title
        self._ensure_objective(title)
        self.save_player_data()
        self.refresh_player_later(matched, 0.2, True)
        if old_title and old_title != title:
            self._cleanup_objective_if_unused(old_title)
        reply(f"§a已将玩家 {matched} 当前称号切换为: §f{title}")

    def _handle_console_select(self, args: list[str], reply: Callable[[str], None]):
        """Handle a numbered selection for pending fuzzy console matches."""
        pending = self.pending_console_selection
        if pending is None:
            reply("§e当前没有待确认的模糊匹配结果")
            return
        if len(args) != 1:
            reply("§c用法: 称号 选择 <序号>")
            return
        try:
            index = int(args[0])
        except ValueError:
            reply("§c序号必须是数字")
            return
        candidates = pending["candidates"]
        if index < 1 or index > len(candidates):
            reply(f"§c序号超出范围，请输入 1 到 {len(candidates)}")
            return
        matched = candidates[index - 1]
        action = pending["action"]
        title = pending["title"]
        self.pending_console_selection = None
        if action == "add":
            self._execute_console_add(matched, title, reply)
            return
        if action == "delete":
            self._execute_console_delete(matched, title, reply)
            return
        if action == "switch":
            self._execute_console_switch(matched, title, reply)
            return
        reply("§c待确认操作已失效，请重新输入命令")

    def _resolve_console_player(
        self,
        keyword: str,
        action: str,
        title: str,
        reply: Callable[[str], None],
    ) -> str | None:
        """Resolve a console player target, falling back to indexed fuzzy selection."""
        self.pending_console_selection = None
        exact = self._find_single_player(keyword, None)
        if exact is not None:
            return exact
        candidates = self._find_player_candidates(keyword)
        if not candidates:
            reply(f"§c未找到玩家: {keyword}")
            return None
        self.pending_console_selection = {
            "action": action,
            "title": title,
            "candidates": candidates,
        }
        reply(f"§e未精确匹配到玩家 {keyword}，请按序号选择：")
        for index, name in enumerate(candidates, start=1):
            reply(f"§f{index}. {name}")
        reply("§e请输入 §f称号 选择 <序号> §e继续")
        return None

    def _find_player_candidates(self, keyword: str) -> list[str]:
        """Return fuzzy player-name matches from online and stored player names."""
        return sorted(
            [
                name
                for name in (set(self._online_names()) | set(self.player_data.keys()))
                if keyword in name
            ],
            key=lambda item: (len(item), item),
        )

    def _handle_console_list(self, reply: Callable[[str], None]):
        """List every stored player and their currently equipped title."""
        if not self.player_data:
            reply("§e当前没有任何称号数据")
            return
        for player_name in sorted(self.player_data):
            pdata = self._get_or_create_player_data(player_name)
            current = pdata.get("current_title") or "无"
            reply(f"§f{player_name} §7-> 当前: §r{current}")

    def _register_chatbar_menu(self):
        """Register player-facing title commands into the chatbar menu plugin."""
        if self.chatbar_registered:
            return
        chatbar = self.GetPluginAPI("聊天栏菜单", force=False)
        if chatbar is None:
            if not self.chatbar_missing_warned:
                self.print_war(
                    "未检测到前置_聊天栏菜单，已尝试自动下载。重载插件后将自动注册到聊天栏菜单。"
                )
                self.chatbar_missing_warned = True
            return

        def buy_trigger(player: Player, args: tuple):
            """Purchase and equip a title from the chatbar menu trigger."""
            title = " ".join(str(item) for item in args).strip()
            self._buy_title(player, title, self._player_reply(player))

        def switch_trigger(player: Player, args: tuple):
            """Switch the caller's title from the chatbar menu trigger."""
            title = " ".join(str(item) for item in args).strip()
            self._switch_own_title(player, title, self._player_reply(player), cost=True)

        def remove_trigger(player: Player, _args: tuple):
            """Remove the caller's current title from the chatbar menu trigger."""
            self._remove_own_title(player, self._player_reply(player))

        def list_trigger(player: Player, _args: tuple):
            """Show the caller's current title from the chatbar menu trigger."""
            self._show_player_titles(player.name, self._player_reply(player))

        chatbar.add_new_trigger(
            ["购买称号"],
            ...,
            "购买一个头顶称号",
            buy_trigger,
            False,
        )
        chatbar.add_new_trigger(
            ["更改称号"],
            ...,
            "替换自己当前使用的称号",
            switch_trigger,
            False,
        )
        chatbar.add_new_trigger(
            ["移除称号"],
            [],
            "删除自己当前称号",
            remove_trigger,
            False,
        )
        chatbar.add_new_trigger(
            ["我的称号", "查看称号"],
            [],
            "查看自己当前称号",
            list_trigger,
            False,
        )
        self.chatbar_registered = True

    def _ensure_chatbar_plugin(self):
        """Download the required chatbar dependency when it is not installed."""
        chatbar = self.GetPluginAPI("聊天栏菜单", force=False)
        if chatbar is not None:
            return
        plugin_dir = TOOLDELTA_CLASSIC_PLUGIN_PATH / self.CHATBAR_PLUGIN_DIRNAME
        if plugin_dir.exists():
            return
        try:
            plugin_market.market.download_plugin(
                PluginRegData(
                    self.CHATBAR_PLUGIN_DIRNAME,
                    {
                        "author": "SuperScript",
                        "version": "0.4.1",
                        "plugin-type": "classic",
                        "description": "前置_聊天栏菜单",
                        "plugin-id": self.CHATBAR_PLUGIN_ID,
                    },
                ),
                with_pres=False,
                is_enabled=True,
            )
            self.print_suc(
                "已自动下载前置_聊天栏菜单插件，请执行 reload 使菜单注册生效。"
            )
        except Exception as err:
            self.print_err(f"自动下载前置_聊天栏菜单失败: {err}")

    def _validate_scoreboard_exists_or_raise(self):
        """Ensure the currency scoreboard exists before title operations run."""
        if self.scoreboard_checked:
            return
        scoreboard_name = str(self.cfg["金币计分板名"])
        try:
            resp = self.game_ctrl.sendcmd_with_resp(
                f"/scoreboard players test @a {scoreboard_name} * *", 5
            )
            if not self._response_has_objective_not_found(resp, scoreboard_name):
                self.scoreboard_checked = True
                return
        except Exception:
            pass

        try:
            resp = self.game_ctrl.sendwscmd_with_resp("/scoreboard objectives list", 5)
        except Exception as err:
            raise RuntimeError(
                f"无法检查计分板 {scoreboard_name} 是否存在: {err}"
            ) from err

        if self._objective_exists_in_response(resp, scoreboard_name):
            self.scoreboard_checked = True
            return
        raise RuntimeError(
            f"缺少计分板: {scoreboard_name}。请先在游戏中创建该计分板后再运行插件。"
        )

    @staticmethod
    def _objective_exists_in_response(resp: Any, scoreboard_name: str) -> bool:
        """Return whether a scoreboard objective name appears in a command response."""
        for msg in getattr(resp, "OutputMessages", []):
            parameters = getattr(msg, "Parameters", [])
            if scoreboard_name in parameters:
                return True
        return False

    @staticmethod
    def _response_has_objective_not_found(resp: Any, scoreboard_name: str) -> bool:
        """Return whether a command response reports a missing scoreboard objective."""
        for msg in getattr(resp, "OutputMessages", []):
            if getattr(msg, "Message", "") == "commands.scoreboard.objectiveNotFound":
                params = getattr(msg, "Parameters", [])
                return not params or scoreboard_name in params
        return False

    def _ensure_player_default_score(self, player_name: str):
        """Create the default currency score for a player when it is missing."""
        self._validate_scoreboard_exists_or_raise()
        scoreboard_name = str(self.cfg["金币计分板名"])
        try:
            self._get_score(player_name, scoreboard_name)
        except Exception:
            default_score = int(self.cfg["????"])
            self.game_ctrl.sendwocmd(
                f"scoreboard players set {self._selector(player_name)} "
                f"{scoreboard_name} {default_score}"
            )

    def _change_score(self, player_name: str, delta: int) -> bool:
        """Apply a currency delta to a player and reject negative overdrafts."""
        scoreboard_name = str(self.cfg["金币计分板名"])
        selector = self._selector(player_name)
        if delta < 0:
            amount = -delta
            try:
                current = self._get_score(player_name, scoreboard_name)
            except Exception:
                return False
            if current < amount:
                return False
            self.game_ctrl.sendwocmd(
                f"scoreboard players remove {selector} {scoreboard_name} {amount}"
            )
            return True
        self.game_ctrl.sendwocmd(
            f"scoreboard players add {selector} {scoreboard_name} {delta}"
        )
        return True

    def _get_score(self, player_name: str, scoreboard_name: str) -> int:
        """Read the current score value for one player from the target scoreboard."""
        selector = self._selector(player_name)
        resp = self.game_ctrl.sendwscmd_with_resp(
            f"/scoreboard players test {selector} {scoreboard_name} * *",
            5,
        )
        if not resp.OutputMessages:
            raise ValueError("未获取到计分板返回")
        params = resp.OutputMessages[0].Parameters
        if not params:
            raise ValueError("计分板参数为空")
        return int(params[0])

    def _read_raw_player_data(self) -> dict[str, Any]:
        """Read the raw persisted title data from disk and validate the root shape."""
        if self.titles_path is None:
            return {}
        if not self.titles_path.exists():
            self.titles_path.write_text("{}", encoding="utf-8")
            return {}
        try:
            raw = json.loads(self.titles_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.print_war("titles.json ?????????????????")
            return {}
        if not isinstance(raw, dict):
            self.print_war("titles.json ????????????????")
            return {}
        return raw

    @staticmethod
    def _extract_current_title(pdata: dict[str, Any]) -> tuple[Any, bool]:
        """Extract the current title, falling back to legacy owned_titles data."""
        current_raw = pdata.get("current_title", "")
        if current_raw or not isinstance(pdata.get("owned_titles"), list):
            return current_raw, False

        for item in pdata["owned_titles"]:
            if isinstance(item, str) and item.strip():
                return item, True
        return current_raw, False

    @staticmethod
    def _migrate_player_entry(
        player_name: Any,
        pdata: Any,
    ) -> tuple[str | None, dict[str, Any] | None, bool]:
        """Convert one raw player entry into the current storage shape."""
        if not isinstance(player_name, str):
            return None, None, True
        if isinstance(pdata, str):
            return player_name, {"current_title": pdata}, True
        if not isinstance(pdata, dict):
            return None, None, True

        current_raw, changed = BelownameTitlePlugin._extract_current_title(pdata)
        current_title = current_raw.strip() if isinstance(current_raw, str) else ""
        changed = changed or current_title != pdata.get("current_title", "")
        return player_name, {"current_title": current_title}, changed

    def _load_player_data(self) -> dict[str, dict[str, Any]]:
        """Load persisted title data and migrate legacy player records in memory."""
        raw = self._read_raw_player_data()

        migrated: dict[str, dict[str, Any]] = {}
        changed = False
        for player_name, pdata in raw.items():
            migrated_name, migrated_data, entry_changed = self._migrate_player_entry(
                player_name,
                pdata,
            )
            changed = changed or entry_changed
            if migrated_name is None or migrated_data is None:
                continue
            migrated[migrated_name] = migrated_data
        self.player_data = migrated
        for player_name in list(self.player_data):
            if self._normalize_player_record(player_name):
                changed = True
        if changed:
            self.save_player_data()
        return migrated

    def save_player_data(self):
        """Persist the normalized player title data back to titles.json."""
        if self.titles_path is None:
            return
        self.titles_path.write_text(
            json.dumps(self.player_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _normalize_player_record(self, player_name: str) -> bool:
        """Trim and normalize one player record, removing empty-title entries."""
        pdata = self.player_data.get(player_name)
        if pdata is None:
            return False
        current_title = pdata.get("current_title", "")
        current_title = current_title.strip() if isinstance(current_title, str) else ""
        changed = current_title != pdata.get("current_title", "")
        if not current_title:
            self.player_data.pop(player_name, None)
            return True
        self.player_data[player_name] = {
            "current_title": current_title,
        }
        return changed

    def _get_or_create_player_data(self, player_name: str) -> dict[str, Any]:
        pdata = self.player_data.get(player_name)
        if pdata is None:
            pdata = {"current_title": ""}
            self.player_data[player_name] = pdata
        self._normalize_player_record(player_name)
        return self.player_data[player_name]

    def _rebuild_objective_cache(self):
        self.managed_objectives = {
            self._objective_name(title)
            for pdata in self.player_data.values()
            for title in [pdata.get("current_title", "")]
            if isinstance(title, str) and title.strip()
        }
        self.managed_objectives.add(self._objective_name(self._blank_title()))

    def _blank_title(self) -> str:
        return str(self.cfg["无称号显示文本"])

    @staticmethod
    def _objective_name(title: str) -> str:
        digest = hashlib.md5(title.encode("utf-8")).hexdigest()[:10]
        return f"tdt_{digest}"

    def _ensure_objective(self, title: str) -> str:
        objective = self._objective_name(title)
        self.managed_objectives.add(objective)
        self.game_ctrl.sendwocmd(
            f"scoreboard objectives add {objective} dummy {self._quote(title)}"
        )
        return objective

    def _cleanup_objective_if_unused(self, title: str):
        if not title.strip():
            return
        for pdata in self.player_data.values():
            current_title = pdata.get("current_title", "")
            if isinstance(current_title, str) and current_title == title:
                return
        objective = self._objective_name(title)
        self.managed_objectives.discard(objective)
        self.game_ctrl.sendwocmd(f"scoreboard objectives remove {objective}")

    def _remove_player_title(
        self,
        player_name: str,
        title: str,
        reply: Callable[[str], None],
        *,
        actor_label: str,
    ):
        if not title:
            reply("§c称号名字不能为空")
            return
        pdata = self._get_or_create_player_data(player_name)
        current_title = str(pdata.get("current_title", "") or "")
        if current_title != title:
            reply(f"§e{actor_label}没有称号: {title}")
            self._cleanup_objective_if_unused(title)
            return
        old_title = current_title
        pdata["current_title"] = ""
        self._normalize_player_record(player_name)
        self.save_player_data()
        self.refresh_player_later(player_name, 0.2, True)
        self._cleanup_objective_if_unused(title)
        reply(f"§a已删除{actor_label}的称号: §f{title}")

    @staticmethod
    def _quote(text: str) -> str:
        return json.dumps(text, ensure_ascii=False)

    def _selector(self, player_name: str) -> str:
        return f"@a[name={self._quote(player_name)}]"

    def _online_names(self) -> list[str]:
        return [player.name for player in self.game_ctrl.players.getAllPlayers()]

    def _refresh_player(self, player_name: str, full_cleanup: bool = False):
        if player_name not in self._online_names():
            return
        pdata = self.player_data.get(player_name)
        if pdata is None or not pdata.get("current_title"):
            if full_cleanup:
                self._reset_player_objectives(player_name)
            self.player_current_objective.pop(player_name, None)
            return

        title = str(pdata["current_title"])
        objective = self._ensure_objective(title)
        selector = self._selector(player_name)

        old_objectives = set()
        cached = self.player_current_objective.get(player_name)
        if cached:
            old_objectives.add(cached)
        if full_cleanup:
            old_objectives |= self.managed_objectives
        for old_objective in old_objectives:
            if old_objective != objective:
                self.game_ctrl.sendwocmd(
                    f"scoreboard players reset {selector} {old_objective}"
                )

        self.game_ctrl.sendwocmd(
            f"scoreboard players set {selector} {objective} {int(self.cfg['默认显示分数'])}"
        )
        self.game_ctrl.sendwocmd(
            f"scoreboard objectives setdisplay belowname {objective}"
        )
        self.game_ctrl.sendwocmd(
            f"scoreboard objectives setdisplay list {objective}"
        )
        wait_seconds = float(self.cfg["切换显示后等待秒"])
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        self.game_ctrl.sendwocmd(
            f"scoreboard players set {selector} {objective} {int(self.cfg['默认显示分数'])}"
        )
        self.game_ctrl.sendwocmd(
            f"scoreboard objectives setdisplay list {objective}"
        )
        self.player_current_objective[player_name] = objective

    def _reset_player_objectives(self, player_name: str):
        selector = self._selector(player_name)
        for objective in self.managed_objectives:
            self.game_ctrl.sendwocmd(
                f"scoreboard players reset {selector} {objective}"
            )

    def _restore_list_objective(self):
        list_objective = str(self.cfg["玩家列表列显示计分板的名字"]).strip()
        if not list_objective:
            return
        self.game_ctrl.sendwocmd(
            f"scoreboard objectives setdisplay list {list_objective}"
        )

    def refresh_player(self, player_name: str, full_cleanup: bool = False):
        with self.refresh_lock:
            self._refresh_player(player_name, full_cleanup)
            self._restore_list_objective()

    def refresh_all(self, full_cleanup: bool = False):
        if not self.refresh_lock.acquire(blocking=False):
            return
        try:
            online_names = self._online_names()
            for player_name in list(self.player_current_objective):
                if player_name not in online_names:
                    self.player_current_objective.pop(player_name, None)

            titled_online_names = [
                player_name
                for player_name in online_names
                if self.player_data.get(player_name, {}).get("current_title")
            ]

            if full_cleanup:
                untitled_online_names = [
                    player_name
                    for player_name in online_names
                    if not self.player_data.get(player_name, {}).get("current_title")
                ]
                for player_name in untitled_online_names:
                    self._reset_player_objectives(player_name)
                    self.player_current_objective.pop(player_name, None)

            for index, player_name in enumerate(titled_online_names):
                self._refresh_player(player_name, full_cleanup)
                interval = float(self.cfg["逐玩家刷新间隔秒"])
                if index != len(titled_online_names) - 1 and interval > 0:
                    time.sleep(interval)
        finally:
            self.refresh_lock.release()

    @utils.thread_func("头顶称号全服刷新")
    def refresh_all_later(self, delay: float = 0.0, full_cleanup: bool = False):
        if delay > 0:
            time.sleep(delay)
        self.refresh_all(full_cleanup)

    @utils.thread_func("头顶称号循环刷新")
    def refresh_loop(self):
        refresh_interval = float(self.cfg["刷新间隔秒"])
        if refresh_interval <= 0:
            return
        while not self.stop_event.wait(refresh_interval):
            self.refresh_all(False)

    @utils.thread_func("头顶称号单人刷新")
    def refresh_player_later(
        self,
        player_name: str,
        delay: float = 0.0,
        full_cleanup: bool = False,
    ):
        if delay > 0:
            time.sleep(delay)
        self.refresh_player(player_name, full_cleanup)

    def _find_single_player(
        self,
        keyword: str,
        reply: Callable[[str], None] | None,
    ) -> str | None:
        candidates = sorted(
            set(self._online_names()) | set(self.player_data.keys()),
            key=lambda item: (item != keyword, len(item), item),
        )
        exact = [name for name in candidates if name == keyword]
        if exact:
            return exact[0]
        fuzzy = self._find_player_candidates(keyword)
        if not fuzzy:
            if reply is not None:
                reply(f"§c未找到玩家: {keyword}")
            return None
        if len(fuzzy) > 1:
            if reply is not None:
                reply("§c匹配到多个玩家: " + ", ".join(fuzzy))
            return None
        if reply is None:
            return None
        return fuzzy[0]

    @staticmethod
    def _player_reply(player: Player):
        def reply(msg: str):
            player.show(msg)

        return reply

    def _console_reply(self):
        def reply(msg: str):
            self.print_inf(msg)

        return reply

    def _config_schema(self) -> dict[str, Any]:
        return {
            "聊天命令前缀": str,
            "购买称号价格": int,
            "更改称号价格": int,
            "金币计分板名": str,
            "玩家列表列显示计分板的名字": str,
            "默认金币": int,
            "默认显示分数": int,
            "无称号显示文本": str,
            "刷新间隔秒": float,
            "逐玩家刷新间隔秒": float,
            "切换显示后等待秒": float,
            "进服后延迟刷新秒": float,
        }

    def _default_config(self) -> dict[str, Any]:
        return {
            "聊天命令前缀": ".",
            "购买称号价格": 500,
            "更改称号价格": 500,
            "金币计分板名": "金币",
            "玩家列表列显示计分板的名字": "金币",
            "默认金币": 1000,
            "默认显示分数": 666,
            "无称号显示文本": " ",
            "刷新间隔秒": 15.0,
            "逐玩家刷新间隔秒": 0.15,
            "切换显示后等待秒": 0.05,
            "进服后延迟刷新秒": 1.0,
        }


entry = plugin_entry(BelownameTitlePlugin)

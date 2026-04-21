import inspect
import json
import os
import re
import time
from typing import Any
from collections.abc import Callable

import websocket

from tooldelta import (
    Plugin,
    cfg,
    utils,
    fmts,
    Chat,
    Player,
    plugin_entry,
    InternalBroadcast,
)

try:
    from tooldelta.utils.mc_translator import translate
except ImportError:
    translate = None


EASTER_EGG_QQIDS = {2528622340: ("SuperScript", "Super")}


class QQMsgTrigger:
    def __init__(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[..., Any],
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only: bool = False,
    ):
        self.triggers = triggers
        self.argument_hint = argument_hint
        self.usage = usage
        self.func = func
        self.args_pd = args_pd
        self.op_only = op_only
        self.accept_group = self._accept_group_arg(func)

    @staticmethod
    def _accept_group_arg(func: Callable[..., Any]) -> bool:
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            return False
        positional_count = 0
        for param in sig.parameters.values():
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                positional_count += 1
            elif param.kind == inspect.Parameter.VAR_POSITIONAL:
                return True
        return positional_count >= 3

    def match(self, msg: str):
        for trigger in self.triggers:
            if msg.startswith(trigger):
                return trigger
        return None


def remove_cq_code(content: str):
    cq_start = content.find("[CQ:")
    while cq_start != -1:
        cq_end = content.find("]", cq_start) + 1
        content = content[:cq_start] + content[cq_end:]
        cq_start = content.find("[CQ:")
    return content


def remove_color(content: str):
    return re.compile(r"§(.)").sub("", content)


CQ_IMAGE_RULE = re.compile(r"\[CQ:image,([^\]])*\]")
CQ_VIDEO_RULE = re.compile(r"\[CQ:video,[^\]]*\]")
CQ_FILE_RULE = re.compile(r"\[CQ:file,[^\]]*\]")
CQ_AT_RULE = re.compile(r"\[CQ:at,[^\]]*\]")
CQ_REPLY_RULE = re.compile(r"\[CQ:reply,[^\]]*\]")
CQ_FACE_RULE = re.compile(r"\[CQ:face,[^\]]*\]")


def replace_cq(content: str):
    for rule, replacement in (
        (CQ_IMAGE_RULE, "[图片]"),
        (CQ_FILE_RULE, "[文件]"),
        (CQ_VIDEO_RULE, "[视频]"),
        (CQ_AT_RULE, "[@]"),
        (CQ_REPLY_RULE, "[回复]"),
        (CQ_FACE_RULE, "[表情]"),
    ):
        content = rule.sub(replacement, content)
    return content


class QQLinker(Plugin):
    version = (0, 2, 15)
    name = "群服互通云链版Ultra版"
    author = "大庆油田 / 小六神"
    description = "提供多群独立管理的群服互通、QQ群管理员体系和 Orion 联动封禁功能"
    QQMsgTrigger = QQMsgTrigger

    def __init__(self, f):
        super().__init__(f)
        self.make_data_path()
        self.group_state_dir = self.format_data_path("群聊权限数据")
        os.makedirs(self.group_state_dir, exist_ok=True)

        self.ws = None
        self.reloaded = False
        self.available = False
        self.triggers: list[QQMsgTrigger] = []
        self.waitmsg_cbs: dict[int | tuple[int, int], Callable[[str], None]] = {}
        self.plugin = []
        self._manual_launch = False
        self._manual_launch_port = -1
        self.tps_calc = None
        self.orion = None
        self.whitelist_checker = None

        raw_cfg, _ = cfg.get_plugin_config_and_version(
            self.name,
            {},
            self.cfg_default(),
            self.version,
        )
        self.cfg = self.migrate_config(raw_cfg)
        cfg.check_auto(self.cfg_std(), self.cfg)
        cfg.upgrade_plugin_config(self.name, self.cfg, self.version)

        self.group_cfgs: dict[int, dict[str, Any]] = {}
        self.group_order: list[int] = []
        self.reload_group_configs()

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)

    # ------------------------ 配置 ------------------------
    @staticmethod
    def group_default(group_id: int = 194838530):
        return {
            "群号": group_id,
            "游戏到群": {
                "是否启用": False,
                "转发格式": "<[玩家名]> [消息]",
                "仅转发以下符号开头的消息(列表为空则全部转发)": ["#"],
                "屏蔽以下字符串开头的消息": [".", "。"],
                "转发玩家进退提示": True,
            },
            "群到游戏": {
                "是否启用": True,
                "转发格式": "群 <[昵称]> [消息]",
                "屏蔽的QQ号": [],
                "替换花里胡哨的昵称": True,
                "替换花里胡哨的消息": True,
            },
            "指令设置": {
                "发送指令前缀": "/",
                "帮助菜单唤醒词": ["help", "帮助"],
                "管理员菜单唤醒词": ["管理员菜单"],
                "是否允许查看玩家列表": True,
                "查看玩家人数的唤醒词": ["list", "玩家列表"],
                "查询背包菜单唤醒词": ["查询背包"],
                "查询背包菜单每页显示的玩家数量": 10,
                "QQ群封禁唤醒词": ["orban", "orion ban", "猎户封禁"],
                "QQ群解封唤醒词": ["orunban", "orion unban", "猎户解封"],
                "QQ群白名单&管理员检测唤醒词": ["白名单&管理员检测", "检测管理"],
                "QQ群封禁/解封菜单每页显示个数": 10,
            },
        }

    @classmethod
    def cfg_default(cls):
        return {
            "云链设置": {"地址": "ws://127.0.0.1:3001", "校验码": ""},
            "群聊设置": [cls.group_default()],
        }

    @classmethod
    def cfg_std(cls):
        group_std = {
            "群号": cfg.PInt,
            "游戏到群": {
                "是否启用": bool,
                "转发格式": str,
                "仅转发以下符号开头的消息(列表为空则全部转发)": cfg.JsonList(str, -1),
                "屏蔽以下字符串开头的消息": cfg.JsonList(str, -1),
                "转发玩家进退提示": bool,
            },
            "群到游戏": {
                "是否启用": bool,
                "转发格式": str,
                "屏蔽的QQ号": cfg.JsonList(cfg.PInt, -1),
                "替换花里胡哨的昵称": bool,
                "替换花里胡哨的消息": bool,
            },
            "指令设置": {
                "发送指令前缀": str,
                "帮助菜单唤醒词": cfg.JsonList(str, -1),
                "管理员菜单唤醒词": cfg.JsonList(str, -1),
                "是否允许查看玩家列表": bool,
                "查看玩家人数的唤醒词": cfg.JsonList(str, -1),
                "查询背包菜单唤醒词": cfg.JsonList(str, -1),
                "查询背包菜单每页显示的玩家数量": cfg.PInt,
                "QQ群封禁唤醒词": cfg.JsonList(str, -1),
                "QQ群解封唤醒词": cfg.JsonList(str, -1),
                "QQ群白名单&管理员检测唤醒词": cfg.JsonList(str, -1),
                "QQ群封禁/解封菜单每页显示个数": cfg.PInt,
            },
        }
        return {
            "云链设置": {"地址": str, "校验码": str},
            "群聊设置": cfg.JsonList(group_std, -1),
        }

    @staticmethod
    def normalize_int_list(values: Any) -> list[int]:
        if not isinstance(values, list):
            return []
        result: list[int] = []
        for value in values:
            try:
                ivalue = int(value)
            except (TypeError, ValueError):
                continue
            if ivalue > 0 and ivalue not in result:
                result.append(ivalue)
        return result

    @classmethod
    def merge_with_default(cls, raw: Any, default: Any):
        if isinstance(default, dict):
            result = {
                key: cls.merge_with_default(None, value)
                for key, value in default.items()
            }
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key in result:
                        result[key] = cls.merge_with_default(value, result[key])
                    else:
                        result[key] = value
            return result
        if isinstance(default, list):
            return list(raw) if isinstance(raw, list) else list(default)
        return raw if raw is not None else default

    def migrate_group_config(self, raw_group: Any):
        if not isinstance(raw_group, dict):
            return None
        try:
            group_id = int(raw_group.get("群号", 0))
        except (TypeError, ValueError):
            return None
        if group_id <= 0:
            return None
        group_cfg = self.group_default(group_id)
        old_g2q = raw_group.get("游戏到群", {})
        old_q2g = raw_group.get("群到游戏", {})
        old_cmd = raw_group.get("指令设置", {})
        if isinstance(old_g2q, dict):
            group_cfg["游戏到群"]["是否启用"] = bool(
                old_g2q.get("是否启用", group_cfg["游戏到群"]["是否启用"])
            )
            group_cfg["游戏到群"]["转发格式"] = str(
                old_g2q.get("转发格式", group_cfg["游戏到群"]["转发格式"])
            )
            group_cfg["游戏到群"]["仅转发以下符号开头的消息(列表为空则全部转发)"] = [
                str(i)
                for i in old_g2q.get(
                    "仅转发以下符号开头的消息(列表为空则全部转发)",
                    group_cfg["游戏到群"]["仅转发以下符号开头的消息(列表为空则全部转发)"],
                )
                if isinstance(i, str)
            ]
            group_cfg["游戏到群"]["屏蔽以下字符串开头的消息"] = [
                str(i)
                for i in old_g2q.get(
                    "屏蔽以下字符串开头的消息",
                    group_cfg["游戏到群"]["屏蔽以下字符串开头的消息"],
                )
                if isinstance(i, str)
            ]
            group_cfg["游戏到群"]["转发玩家进退提示"] = bool(
                old_g2q.get(
                    "转发玩家进退提示",
                    group_cfg["游戏到群"]["转发玩家进退提示"],
                )
            )
        if isinstance(old_q2g, dict):
            group_cfg["群到游戏"]["是否启用"] = bool(
                old_q2g.get("是否启用", group_cfg["群到游戏"]["是否启用"])
            )
            group_cfg["群到游戏"]["转发格式"] = str(
                old_q2g.get("转发格式", group_cfg["群到游戏"]["转发格式"])
            )
            group_cfg["群到游戏"]["屏蔽的QQ号"] = self.normalize_int_list(
                old_q2g.get("屏蔽的QQ号", [])
            )
            group_cfg["群到游戏"]["替换花里胡哨的昵称"] = bool(
                old_q2g.get(
                    "替换花里胡哨的昵称",
                    group_cfg["群到游戏"]["替换花里胡哨的昵称"],
                )
            )
            group_cfg["群到游戏"]["替换花里胡哨的消息"] = bool(
                old_q2g.get(
                    "替换花里胡哨的消息",
                    group_cfg["群到游戏"]["替换花里胡哨的消息"],
                )
            )
        if isinstance(old_cmd, dict):
            group_cfg["指令设置"]["发送指令前缀"] = str(
                old_cmd.get(
                    "发送指令前缀",
                    group_cfg["指令设置"]["发送指令前缀"],
                )
            ).strip() or group_cfg["指令设置"]["发送指令前缀"]
            group_cfg["指令设置"]["管理员菜单唤醒词"] = [
                str(i)
                for i in old_cmd.get(
                    "管理员菜单唤醒词",
                    group_cfg["指令设置"]["管理员菜单唤醒词"],
                )
                if isinstance(i, str)
            ] or group_cfg["指令设置"]["管理员菜单唤醒词"]
            group_cfg["指令设置"]["帮助菜单唤醒词"] = [
                str(i)
                for i in old_cmd.get(
                    "帮助菜单唤醒词",
                    group_cfg["指令设置"]["帮助菜单唤醒词"],
                )
                if isinstance(i, str)
            ] or group_cfg["指令设置"]["帮助菜单唤醒词"]
            group_cfg["指令设置"]["是否允许查看玩家列表"] = bool(
                old_cmd.get(
                    "是否允许查看玩家列表",
                    group_cfg["指令设置"]["是否允许查看玩家列表"],
                )
            )
            group_cfg["指令设置"]["查看玩家人数的唤醒词"] = [
                str(i)
                for i in old_cmd.get(
                    "查看玩家人数的唤醒词",
                    group_cfg["指令设置"]["查看玩家人数的唤醒词"],
                )
                if isinstance(i, str)
            ] or group_cfg["指令设置"]["查看玩家人数的唤醒词"]
            group_cfg["指令设置"]["查询背包菜单唤醒词"] = [
                str(i)
                for i in old_cmd.get(
                    "查询背包菜单唤醒词",
                    group_cfg["指令设置"]["查询背包菜单唤醒词"],
                )
                if isinstance(i, str)
            ] or group_cfg["指令设置"]["查询背包菜单唤醒词"]
            inventory_page_size = old_cmd.get(
                "查询背包菜单每页显示的玩家数量",
                group_cfg["指令设置"]["查询背包菜单每页显示的玩家数量"],
            )
            try:
                inventory_page_size_int = int(inventory_page_size)
            except (TypeError, ValueError):
                inventory_page_size_int = group_cfg["指令设置"]["查询背包菜单每页显示的玩家数量"]
            group_cfg["指令设置"]["查询背包菜单每页显示的玩家数量"] = max(
                1,
                inventory_page_size_int,
            )
            group_cfg["指令设置"]["QQ群封禁唤醒词"] = [
                str(i)
                for i in old_cmd.get(
                    "QQ群封禁唤醒词",
                    group_cfg["指令设置"]["QQ群封禁唤醒词"],
                )
                if isinstance(i, str)
            ] or group_cfg["指令设置"]["QQ群封禁唤醒词"]
            group_cfg["指令设置"]["QQ群解封唤醒词"] = [
                str(i)
                for i in old_cmd.get(
                    "QQ群解封唤醒词",
                    group_cfg["指令设置"]["QQ群解封唤醒词"],
                )
                if isinstance(i, str)
            ] or group_cfg["指令设置"]["QQ群解封唤醒词"]
            group_cfg["指令设置"]["QQ群白名单&管理员检测唤醒词"] = [
                str(i)
                for i in old_cmd.get(
                    "QQ群白名单&管理员检测唤醒词",
                    group_cfg["指令设置"]["QQ群白名单&管理员检测唤醒词"],
                )
                if isinstance(i, str)
            ] or group_cfg["指令设置"]["QQ群白名单&管理员检测唤醒词"]
            page_size = old_cmd.get(
                "QQ群封禁/解封菜单每页显示个数",
                group_cfg["指令设置"]["QQ群封禁/解封菜单每页显示个数"],
            )
            try:
                page_size_int = int(page_size)
            except (TypeError, ValueError):
                page_size_int = group_cfg["指令设置"]["QQ群封禁/解封菜单每页显示个数"]
            group_cfg["指令设置"]["QQ群封禁/解封菜单每页显示个数"] = max(
                1,
                page_size_int,
            )
        return group_cfg

    def migrate_config(self, raw_cfg: Any):
        new_cfg = self.cfg_default()
        if not isinstance(raw_cfg, dict):
            return new_cfg
        raw_cfg = self.merge_with_default(raw_cfg, new_cfg)

        cloud_cfg = raw_cfg.get("云链设置", {})
        if isinstance(cloud_cfg, dict):
            new_cfg["云链设置"]["地址"] = str(
                cloud_cfg.get("地址", new_cfg["云链设置"]["地址"])
            )
            validate_code = cloud_cfg.get("校验码", "")
            new_cfg["云链设置"]["校验码"] = (
                "" if validate_code is None else str(validate_code)
            )

        group_cfgs: list[dict[str, Any]] = []
        if isinstance(raw_cfg.get("群聊设置"), list):
            for raw_group in raw_cfg["群聊设置"]:
                migrated = self.migrate_group_config(raw_group)
                if migrated is not None:
                    group_cfgs.append(migrated)
        elif isinstance(raw_cfg.get("消息转发设置"), dict):
            old_msg_cfg = raw_cfg["消息转发设置"]
            try:
                old_group_id = int(old_msg_cfg.get("链接的群聊", 194838530))
            except (TypeError, ValueError):
                old_group_id = 194838530
            migrated_group = self.group_default(old_group_id)
            if isinstance(old_msg_cfg.get("游戏到群"), dict):
                migrated_group["游戏到群"] = self.migrate_group_config(
                    {
                        "群号": old_group_id,
                        "游戏到群": old_msg_cfg["游戏到群"],
                    }
                )["游戏到群"]
            if isinstance(old_msg_cfg.get("群到游戏"), dict):
                migrated_group["群到游戏"] = self.migrate_group_config(
                    {
                        "群号": old_group_id,
                        "群到游戏": old_msg_cfg["群到游戏"],
                    }
                )["群到游戏"]
            if isinstance(raw_cfg.get("指令设置"), dict):
                migrated_group["指令设置"]["是否允许查看玩家列表"] = bool(
                    raw_cfg["指令设置"].get(
                        "是否允许查看玩家列表",
                        migrated_group["指令设置"]["是否允许查看玩家列表"],
                    )
                )
            group_cfgs.append(migrated_group)

        if group_cfgs:
            dedup: dict[int, dict[str, Any]] = {}
            for group_cfg in group_cfgs:
                dedup[group_cfg["群号"]] = group_cfg
            new_cfg["群聊设置"] = list(dedup.values())

        return new_cfg

    def reload_group_configs(self):
        self.group_cfgs.clear()
        self.group_order.clear()
        for group_cfg in self.cfg["群聊设置"]:
            group_id = int(group_cfg["群号"])
            self.group_cfgs[group_id] = group_cfg
            self.group_order.append(group_id)
        for group_id in self.group_order:
            self.ensure_group_state(group_id)

    # ------------------------ 群权限数据 ------------------------
    def group_state_path(self, group_id: int):
        return os.path.join(self.group_state_dir, f"{group_id}.json")

    def read_group_state(self, group_id: int):
        path = self.group_state_path(group_id)
        if not os.path.isfile(path):
            return {"admins": [], "super_admins": []}
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            data = {}
        return {
            "admins": self.normalize_int_list(data.get("admins", [])),
            "super_admins": self.normalize_int_list(data.get("super_admins", [])),
        }

    def save_group_state(self, group_id: int, state: dict[str, list[int]]):
        path = self.group_state_path(group_id)
        normalized = {
            "admins": self.normalize_int_list(state.get("admins", [])),
            "super_admins": self.normalize_int_list(state.get("super_admins", [])),
        }
        with open(path, "w", encoding="utf-8") as file:
            json.dump(normalized, file, ensure_ascii=False, indent=2)

    def ensure_group_state(self, group_id: int):
        path = self.group_state_path(group_id)
        if os.path.isfile(path):
            state = self.read_group_state(group_id)
            self.save_group_state(group_id, state)
            return
        state = {"admins": [], "super_admins": []}
        self.save_group_state(group_id, state)

    def is_group_super_admin(self, group_id: int, qqid: int):
        return qqid in self.read_group_state(group_id)["super_admins"]

    def is_group_admin(self, group_id: int, qqid: int):
        state = self.read_group_state(group_id)
        return qqid in state["super_admins"] or qqid in state["admins"]

    def is_qq_op(self, qqid: int, group_id: int | None = None):
        if group_id is not None:
            return self.is_group_admin(group_id, qqid)
        return any(self.is_group_admin(gid, qqid) for gid in self.group_order)

    def add_group_role(self, group_id: int, qqid: int, is_super: bool):
        state = self.read_group_state(group_id)
        if is_super:
            if qqid in state["super_admins"]:
                return False, "该 QQ 已经是本群超级管理员"
            if qqid in state["admins"]:
                state["admins"].remove(qqid)
            state["super_admins"].append(qqid)
            self.save_group_state(group_id, state)
            return True, "已添加为本群超级管理员"
        if qqid in state["super_admins"]:
            return False, "该 QQ 已经是本群超级管理员，无需再添加为管理员"
        if qqid in state["admins"]:
            return False, "该 QQ 已经是本群管理员"
        state["admins"].append(qqid)
        self.save_group_state(group_id, state)
        return True, "已添加为本群管理员"

    def remove_group_role(self, group_id: int, qqid: int, is_super: bool):
        state = self.read_group_state(group_id)
        if is_super:
            if qqid not in state["super_admins"]:
                return False, "该 QQ 不是本群超级管理员"
            state["super_admins"].remove(qqid)
            self.save_group_state(group_id, state)
            return True, "已移除本群超级管理员"
        if qqid not in state["admins"]:
            return False, "该 QQ 不是本群普通管理员"
        state["admins"].remove(qqid)
        self.save_group_state(group_id, state)
        return True, "已移除本群普通管理员"

    def get_group_player_list_triggers(self, group_id: int):
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("查看玩家人数的唤醒词", ["list", "玩家列表"])
        return self.normalize_string_triggers(raw, ["list", "玩家列表"])

    def get_group_inventory_menu_triggers(self, group_id: int):
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("查询背包菜单唤醒词", ["查询背包"])
        return self.normalize_string_triggers(raw, ["查询背包"])

    def get_group_inventory_items_per_page(self, group_id: int):
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["查询背包菜单每页显示的玩家数量"]),
                )
            except (KeyError, TypeError, ValueError):
                pass
        return 10

    def get_group_help_triggers(self, group_id: int):
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("帮助菜单唤醒词", ["help", "帮助"])
        return self.normalize_string_triggers(raw, ["help", "帮助"])

    def get_group_admin_menu_triggers(self, group_id: int):
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("管理员菜单唤醒词", ["管理员菜单"])
        return self.normalize_string_triggers(raw, ["管理员菜单"])

    def get_group_cmd_prefix(self, group_id: int):
        group_cfg = self.group_cfgs[group_id]
        prefix = str(group_cfg["指令设置"].get("发送指令前缀", "/")).strip()
        return prefix or "/"

    def get_group_orion_ban_triggers(self, group_id: int):
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get(
            "QQ群封禁唤醒词",
            ["orban", "orion ban", "猎户封禁"],
        )
        return self.normalize_string_triggers(raw, ["orban", "orion ban", "猎户封禁"])

    def get_group_orion_unban_triggers(self, group_id: int):
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get(
            "QQ群解封唤醒词",
            ["orunban", "orion unban", "猎户解封"],
        )
        return self.normalize_string_triggers(raw, ["orunban", "orion unban", "猎户解封"])

    def get_group_checker_menu_triggers(self, group_id: int):
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get(
            "QQ群白名单&管理员检测唤醒词",
            ["白名单&管理员检测", "检测管理"],
        )
        return self.normalize_string_triggers(raw, ["白名单&管理员检测", "检测管理"])

    @staticmethod
    def normalize_string_triggers(raw: Any, fallback: list[str]):
        triggers: list[str] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, str):
                    continue
                text = item.strip()
                if text and text not in triggers:
                    triggers.append(text)
        return triggers or fallback

    # ------------------------ API ------------------------
    def add_trigger(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[..., Any],
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only: bool = False,
    ):
        self.triggers.append(
            QQMsgTrigger(triggers, argument_hint, usage, func, args_pd, op_only)
        )

    def set_manual_launch(self, port: int):
        self._manual_launch = True
        self._manual_launch_port = port

    def manual_launch(self):
        self.connect_to_websocket()

    # ------------------------------------------------------
    def on_def(self):
        self.tps_calc = self.GetPluginAPI("tps计算器", (0, 0, 1), False)
        self.orion = self.GetPluginAPI("Orion_System", force=False)
        self.whitelist_checker = self.GetPluginAPI("白名单&管理员检测云链联动版", force=False)

    def on_inject(self):
        self.print("尝试连接到群服互通云链版Ultra版机器人..")
        if not self._manual_launch:
            self.connect_to_websocket()
        self.init_basic_triggers()

    def init_basic_triggers(self):
        self.frame.add_console_cmd_trigger(
            ["QQ", "发群"], "[群号可选] [消息]", "在群内发消息测试", self.on_sendmsg_test
        )
        self.frame.add_console_cmd_trigger(
            ["OPQQ"],
            None,
            "进入QQ群管理员增删菜单",
            self.on_console_add_qq_op,
        )

    # ------------------------ QQ 触发词回调 ------------------------
    @utils.thread_func("群服执行指令并获取返回")
    def on_qq_execute_cmd(self, group_id: int, qqid: int, cmd: list[str]):
        if not self.is_group_admin(group_id, qqid):
            self.sendmsg(group_id, "你没有权限执行此指令")
            return
        res = self.execute_cmd_and_get_zhcn_cb(" ".join(cmd))
        self.sendmsg(group_id, res)

    def on_qq_help(self, group_id: int, sender: int, _):
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
        online_names = list(self.game_ctrl.allplayers)
        if not online_names:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 当前没有在线玩家", do_remove_cq_code=False)
            return
        page = 1
        per_page = self.get_group_inventory_items_per_page(group_id)
        while True:
            total_pages, start_index, end_index = utils.paginate(
                len(online_names),
                per_page,
                page,
            ) if hasattr(utils, "paginate") else self.simple_paginate(len(online_names), per_page, page)
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
            player_name = online_names[choice - 1]
            self.show_player_inventory(group_id, qqid, player_name)
            return

    @staticmethod
    def simple_paginate(total_len: int, per_page: int, page: int):
        total_pages = max(1, (total_len + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start_index = (page - 1) * per_page + 1
        end_index = min(page * per_page, total_len)
        return total_pages, start_index, end_index

    def show_player_inventory(self, group_id: int, qqid: int, player_name: str):
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
        for attr in ("customName", "custom_name", "name"):
            value = getattr(slot, attr, None)
            if isinstance(value, str) and value.strip() and value.strip() != getattr(slot, "id", ""):
                return value.strip()
        return ""

    @staticmethod
    def get_item_enchantments_text(slot: Any):
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
        if not self.is_group_super_admin(group_id, sender):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 只有本群超级管理员可以添加管理员", do_remove_cq_code=False)
            return
        try:
            qqid = int(args[0])
        except (TypeError, ValueError):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] QQ号格式有误", do_remove_cq_code=False)
            return
        ok, msg = self.add_group_role(group_id, qqid, is_super=False)
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {msg}", do_remove_cq_code=False)

    def qq_admin_menu(self, group_id: int, qqid: int):
        if not self.is_group_super_admin(group_id, qqid):
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] 只有本群超级管理员可以打开管理员菜单",
                do_remove_cq_code=False,
            )
            return
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.plugin_ui_menu(
                "群服互通云链版Ultra版",
                "普通管理员 管理菜单",
                [
                    "添加普通管理员",
                    "删除普通管理员",
                ],
                [
                    "输入 [1-2] 之间的数字以选择 对应功能",
                    "输入 . 退出",
                ],
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
                [
                    f"请输入要{'添加' if choice == '1' else '删除'}的 QQ 号",
                    "输入 . 退出",
                ],
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
        if self.whitelist_checker is None:
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={sender}] 未检测到插件 白名单&管理员检测云链联动版",
                do_remove_cq_code=False,
            )
            return False
        return True

    def on_qq_whitelist_add(self, group_id: int, sender: int, args: list[str]):
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.add_whitelist_player(args[0])
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    def on_qq_whitelist_remove(self, group_id: int, sender: int, args: list[str]):
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.remove_whitelist_player(args[0])
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    def on_qq_server_admin_add(self, group_id: int, sender: int, args: list[str]):
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.add_admin_player(args[0])
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    def on_qq_server_admin_remove(self, group_id: int, sender: int, args: list[str]):
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        ok, msg = self.whitelist_checker.remove_admin_player(args[0])
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    def on_qq_whitelist_toggle(self, group_id: int, sender: int, args: list[str]):
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        action = args[0].strip()
        if action not in ("开启", "关闭", "on", "off"):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 参数错误，格式：白名单检测 [开启/关闭]", do_remove_cq_code=False)
            return
        enabled = action in ("开启", "on")
        ok, msg = self.whitelist_checker.set_whitelist_enabled(enabled)
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    def on_qq_admin_check_toggle(self, group_id: int, sender: int, args: list[str]):
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        action = args[0].strip()
        if action not in ("开启", "关闭", "on", "off"):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 参数错误，格式：管理员检测 [开启/关闭]", do_remove_cq_code=False)
            return
        enabled = action in ("开启", "on")
        ok, msg = self.whitelist_checker.set_admin_check_enabled(enabled)
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    def on_qq_check_interval(self, group_id: int, sender: int, args: list[str]):
        if not self.ensure_whitelist_checker(group_id, sender):
            return
        try:
            seconds = float(args[0])
        except (TypeError, ValueError):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 参数错误，格式：检测周期 [秒数]", do_remove_cq_code=False)
            return
        ok, msg = self.whitelist_checker.set_check_interval(seconds)
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    def on_qq_check_status(self, group_id: int, sender: int, _args: list[str]):
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
        if not self.ensure_whitelist_checker(group_id, qqid):
            return
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
                [
                    "输入 [1-8] 之间的数字以选择 对应功能",
                    "输入 . 退出",
                ],
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

    def on_qq_orion_ban(self, group_id: int, sender: int, args: list[str]):
        if not self.is_group_admin(group_id, sender):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 你没有权限执行此指令", do_remove_cq_code=False)
            return
        if args == []:
            self.qq_orion_ban_menu(group_id, sender)
            return
        target = args[0]
        ban_time_raw = args[1]
        reason = " ".join(args[2:]).strip() or "群聊管理员封禁"
        ok, msg = self.orion_ban_player(target, ban_time_raw, reason)
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    def on_qq_orion_unban(self, group_id: int, sender: int, args: list[str]):
        if not self.is_group_admin(group_id, sender):
            self.sendmsg(group_id, f"[CQ:at,qq={sender}] 你没有权限执行此指令", do_remove_cq_code=False)
            return
        if args == []:
            self.qq_orion_unban_menu(group_id, sender)
            return
        target = args[0]
        ok, msg = self.orion_unban_player(target)
        prefix = "😄" if ok else "😭"
        self.sendmsg(group_id, f"[CQ:at,qq={sender}] {prefix} {msg}", do_remove_cq_code=False)

    # ------------------------ Orion 联动 ------------------------
    def qq_prompt(self, group_id: int, qqid: int, text: str, timeout: int = 60):
        self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {text}", do_remove_cq_code=False)
        resp = self.waitMsg(qqid, timeout=timeout, group_id=group_id)
        if isinstance(resp, str):
            return resp.strip()
        return None

    @staticmethod
    def orion_ui_border():
        return "✧✦〓〓〓〓〓〓〓〓〓〓〓✦✧"

    def orion_ui_menu(self, subtitle: str, options: list[str], hints: list[str]):
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
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["QQ群封禁/解封菜单每页显示个数"]),
                )
            except (KeyError, TypeError, ValueError):
                pass
        return 10

    def orion_xuid_status_text(self, xuid: str):
        assert self.orion is not None
        path = f"{self.orion.data_path}/{self.orion.config_mgr.xuid_dir}/{xuid}.json"
        if not os.path.exists(path):
            return "未封禁"
        try:
            data = self.orion.utils.disk_read_need_exists(path)
        except Exception:
            return "状态异常"
        return f"封禁至: {data.get('ban_end_real_time', '未知')}"

    def orion_device_status_text(self, device_id: str):
        assert self.orion is not None
        path = f"{self.orion.data_path}/{self.orion.config_mgr.device_id_dir}/{device_id}.json"
        if not os.path.exists(path):
            return "未封禁"
        try:
            data = self.orion.utils.disk_read_need_exists(path)
        except Exception:
            return "状态异常"
        return f"封禁至: {data.get('ban_end_real_time', '未知')}"

    @staticmethod
    def format_device_history(player_data: dict[str, list[str]]):
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
        assert self.orion is not None
        result: dict[str, str] = {}
        for player_name in self.game_ctrl.allplayers.copy():
            try:
                xuid = self.orion.xuid_getter.get_xuid_by_name(player_name)
            except Exception:
                continue
            result[xuid] = player_name
        return result

    def build_historical_xuid_data(self):
        path = os.path.join("插件数据文件", "前置-玩家XUID获取", "xuids.json")
        try:
            return self.orion.utils.disk_read_need_exists(path) if self.orion else {}
        except Exception:
            return {}

    def build_device_history_data(self):
        assert self.orion is not None
        path = f"{self.orion.data_path}/{self.orion.config_mgr.player_data_file}"
        try:
            data = self.orion.utils.disk_read_need_exists(path)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def qq_select_orion_xuid(
        self,
        group_id: int,
        qqid: int,
        title: str,
        xuid_data: dict[str, str],
        allow_search: bool = True,
    ):
        if not xuid_data:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 没有可用的玩家记录", do_remove_cq_code=False)
            return None, None
        search = ""
        page = 1
        per_page = self.get_orion_items_per_page(group_id)
        while True:
            matched_items = [
                (xuid, name)
                for xuid, name in xuid_data.items()
                if (search == "" or search in xuid or search in name)
            ]
            if not matched_items:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 找不到您输入的 xuid 或玩家名称", do_remove_cq_code=False)
                return None, None
            total_pages, start_index, end_index = self.orion.utils.paginate(
                len(matched_items),
                per_page,
                page,
            )
            output_lines: list[str] = []
            for i in range(start_index - 1, end_index):
                xuid, name = matched_items[i]
                output_lines.append(
                    f"{xuid} - {name} - {self.orion_xuid_status_text(xuid)}"
                )
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] "
                + self.orion_ui_list(
                    title,
                    output_lines,
                    page,
                    total_pages,
                    f"[{start_index}-{end_index}] 之间的数字以选择 对应玩家",
                    "xuid、玩家名称或玩家部分名称 可尝试搜索",
                ),
                do_remove_cq_code=False,
            )
            user_input = self.waitMsg(qqid, timeout=60, group_id=group_id)
            if user_input is None:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
                return None, None
            user_input = user_input.strip()
            if user_input.lower() in ("q", ".", "。"):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
                return None, None
            if user_input == "+":
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
            if choice is not None and choice in range(start_index, end_index + 1):
                return matched_items[choice - 1]
            if allow_search:
                search = user_input.replace("\\", "")
                page = 1
                continue
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 您的输入有误", do_remove_cq_code=False)

    def qq_select_orion_device(self, group_id: int, qqid: int, title: str, device_data: dict[str, dict[str, list[str]]]):
        if not device_data:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 没有可用的设备号记录", do_remove_cq_code=False)
            return None, None
        search = ""
        page = 1
        per_page = self.get_orion_items_per_page(group_id)
        while True:
            matched_items = []
            for device_id, player_info in device_data.items():
                formatted = self.format_device_history(player_info)
                if search == "" or search in device_id or search in formatted:
                    matched_items.append((device_id, player_info, formatted))
            if not matched_items:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 找不到您输入的设备号或玩家名称", do_remove_cq_code=False)
                return None, None
            total_pages, start_index, end_index = self.orion.utils.paginate(
                len(matched_items),
                per_page,
                page,
            )
            output_lines: list[str] = []
            for i in range(start_index - 1, end_index):
                device_id, player_info, formatted = matched_items[i]
                output_lines.append(
                    f"{device_id} - {formatted} - {self.orion_device_status_text(device_id)}"
                )
            self.sendmsg(
                group_id,
                f"[CQ:at,qq={qqid}] "
                + self.orion_ui_list(
                    title,
                    output_lines,
                    page,
                    total_pages,
                    f"[{start_index}-{end_index}] 之间的数字以选择 对应设备号",
                    "设备号、玩家名称或玩家部分名称 可尝试搜索",
                ),
                do_remove_cq_code=False,
            )
            user_input = self.waitMsg(qqid, timeout=60, group_id=group_id)
            if user_input is None:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
                return None, None
            user_input = user_input.strip()
            if user_input.lower() in ("q", ".", "。"):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
                return None, None
            if user_input == "+":
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
            if choice is not None and choice in range(start_index, end_index + 1):
                device_id, player_info, _formatted = matched_items[choice - 1]
                return device_id, player_info
            search = user_input.replace("\\", "")
            page = 1

    def qq_get_orion_ban_time(self, group_id: int, qqid: int):
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
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
            return None
        if user_input.lower() in ("q", ".", "。"):
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
            return None
        ban_time = self.orion.utils.ban_time_format(user_input) if self.orion else 0
        if ban_time == 0:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 您输入的封禁时间有误", do_remove_cq_code=False)
            return None
        return ban_time

    def qq_get_orion_reason(self, group_id: int, qqid: int):
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
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
            return None
        if user_input.lower() in ("q", ".", "。"):
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
            return None
        return user_input or "群聊管理员封禁"

    def qq_orion_ban_menu(self, group_id: int, qqid: int):
        if self.orion is None:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 未检测到 Orion_System 插件", do_remove_cq_code=False)
            return
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.orion_ui_menu(
                "封禁管理系统",
                [
                    "根据在线玩家名称和xuid封禁",
                    "根据历史玩家名称和xuid封禁",
                    "根据设备号封禁",
                ],
                [
                    "输入 [1-3] 之间的数字以选择 封禁模式",
                    "输入 . 退出",
                ],
            ),
            timeout=120,
        )
        if choice is None:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
            return
        if choice.lower() in ("q", ".", "。"):
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
            return
        if choice == "1":
            xuid_data = self.build_online_xuid_data()
            xuid, player_name = self.qq_select_orion_xuid(group_id, qqid, "在线玩家封禁", xuid_data)
            if not xuid or not player_name:
                return
            ban_time = self.qq_get_orion_ban_time(group_id, qqid)
            if ban_time is None:
                return
            reason = self.qq_get_orion_reason(group_id, qqid)
            if reason is None:
                return
            ok, msg = self.apply_orion_xuid_ban(xuid, player_name, ban_time, reason, online_only=True)
            prefix = "😄" if ok else "😭"
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {prefix} {msg}", do_remove_cq_code=False)
            return
        if choice == "2":
            xuid_data = self.build_historical_xuid_data()
            xuid, player_name = self.qq_select_orion_xuid(group_id, qqid, "历史玩家封禁", xuid_data)
            if not xuid or not player_name:
                return
            ban_time = self.qq_get_orion_ban_time(group_id, qqid)
            if ban_time is None:
                return
            reason = self.qq_get_orion_reason(group_id, qqid)
            if reason is None:
                return
            ok, msg = self.apply_orion_xuid_ban(xuid, player_name, ban_time, reason)
            prefix = "😄" if ok else "😭"
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {prefix} {msg}", do_remove_cq_code=False)
            return
        if choice == "3":
            device_data = self.build_device_history_data()
            device_id, player_info = self.qq_select_orion_device(group_id, qqid, "设备号封禁", device_data)
            if not device_id or not player_info:
                return
            ban_time = self.qq_get_orion_ban_time(group_id, qqid)
            if ban_time is None:
                return
            reason = self.qq_get_orion_reason(group_id, qqid)
            if reason is None:
                return
            ok, msg = self.apply_orion_device_ban(device_id, player_info, ban_time, reason)
            prefix = "😄" if ok else "😭"
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {prefix} {msg}", do_remove_cq_code=False)
            return
        self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 您的输入有误", do_remove_cq_code=False)

    def qq_orion_unban_menu(self, group_id: int, qqid: int):
        if self.orion is None:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 未检测到 Orion_System 插件", do_remove_cq_code=False)
            return
        choice = self.qq_prompt(
            group_id,
            qqid,
            self.orion_ui_menu(
                "解封管理系统",
                [
                    "根据玩家名称和xuid解封",
                    "根据设备号解封",
                ],
                [
                    "输入 [1-2] 之间的数字以选择 解封模式",
                    "输入 . 退出",
                ],
            ),
            timeout=120,
        )
        if choice is None:
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 回复超时！ 已退出菜单", do_remove_cq_code=False)
            return
        if choice.lower() in ("q", ".", "。"):
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 已退出菜单", do_remove_cq_code=False)
            return
        if choice == "1":
            xuid_dir = f"{self.orion.data_path}/{self.orion.config_mgr.xuid_dir}"
            xuid_data: dict[str, str] = {}
            if os.path.isdir(xuid_dir):
                for xuid_json in os.listdir(xuid_dir):
                    xuid = xuid_json.replace(".json", "")
                    try:
                        xuid_data[xuid] = self.orion.xuid_getter.get_name_by_xuid(xuid, True)
                    except Exception:
                        xuid_data[xuid] = xuid
            xuid, player_name = self.qq_select_orion_xuid(group_id, qqid, "xuid 解封", xuid_data, allow_search=True)
            if not xuid or not player_name:
                return
            ok, msg = self.apply_orion_xuid_unban(xuid, player_name)
            prefix = "😄" if ok else "😭"
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {prefix} {msg}", do_remove_cq_code=False)
            return
        if choice == "2":
            device_dir = f"{self.orion.data_path}/{self.orion.config_mgr.device_id_dir}"
            player_data = self.build_device_history_data()
            device_data: dict[str, dict[str, list[str]]] = {}
            if os.path.isdir(device_dir):
                for device_json in os.listdir(device_dir):
                    device_id = device_json.replace(".json", "")
                    device_data[device_id] = player_data.get(device_id, {})
            device_id, player_info = self.qq_select_orion_device(group_id, qqid, "设备号解封", device_data)
            if not device_id or player_info is None:
                return
            ok, msg = self.apply_orion_device_unban(device_id, player_info)
            prefix = "😄" if ok else "😭"
            self.sendmsg(group_id, f"[CQ:at,qq={qqid}] {prefix} {msg}", do_remove_cq_code=False)
            return
        self.sendmsg(group_id, f"[CQ:at,qq={qqid}] ❀ 您的输入有误", do_remove_cq_code=False)

    def resolve_orion_target(self, target: str):
        if self.orion is None:
            return None, None, "未检测到 Orion_System 插件"
        if not hasattr(self.orion, "xuid_getter"):
            return None, None, "Orion 插件尚未完成初始化"

        xuid = None
        player_name = target
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
        xuid, player_name, error = self.resolve_orion_target(target)
        if error:
            return False, error
        assert self.orion is not None
        ban_time = self.orion.utils.ban_time_format(ban_time_raw)
        return self.apply_orion_xuid_ban(xuid, player_name, ban_time, reason)

    def orion_unban_player(self, target: str):
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
        assert self.orion is not None
        if online_only and player_name not in self.game_ctrl.allplayers:
            return False, f"玩家 {player_name} 当前不在线"
        if self.orion.utils.in_whitelist(player_name):
            return False, f"玩家 {player_name} 位于 Orion 反制白名单内"
        timestamp_now, date_now = self.orion.utils.now()
        path = f"{self.orion.data_path}/{self.orion.config_mgr.xuid_dir}/{xuid}.json"
        with self.orion.lock_ban_xuid:
            ban_data = self.orion.utils.disk_read(path)
            timestamp_end, date_end = self.orion.utils.calculate_ban_end_time(
                ban_data,
                ban_time,
                timestamp_now,
            )
            if timestamp_end is False or date_end is False:
                return False, f"玩家 {player_name} 已经是永久封禁"
            self.orion.utils.disk_write(
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
            self.orion.utils.kick(player_name, f"由于{reason}，您被系统封禁至：{date_end}")
        return True, f"已通过 Orion 封禁 {player_name} (xuid:{xuid}) 至 {date_end}"

    def apply_orion_device_ban(
        self,
        device_id: str,
        player_info: dict[str, list[str]],
        ban_time: int | str,
        reason: str,
    ):
        assert self.orion is not None
        timestamp_now, date_now = self.orion.utils.now()
        path = f"{self.orion.data_path}/{self.orion.config_mgr.device_id_dir}/{device_id}.json"
        with self.orion.lock_ban_device_id:
            ban_data = self.orion.utils.disk_read(path)
            timestamp_end, date_end = self.orion.utils.calculate_ban_end_time(
                ban_data,
                ban_time,
                timestamp_now,
            )
            if timestamp_end is False or date_end is False:
                return False, f"设备号 {device_id} 已经是永久封禁"
            self.orion.utils.disk_write(
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
        for xuid, names in player_info.items():
            kick_name = None
            if isinstance(names, list):
                for name in reversed(names):
                    if name in self.game_ctrl.allplayers:
                        kick_name = name
                        break
            if kick_name:
                self.orion.utils.kick(kick_name, f"由于{reason}，您被系统封禁至：{date_end}")
        return True, f"已通过 Orion 封禁设备号 {device_id} 至 {date_end}"

    def apply_orion_xuid_unban(self, xuid: str, player_name: str):
        assert self.orion is not None
        path = f"{self.orion.data_path}/{self.orion.config_mgr.xuid_dir}/{xuid}.json"
        if not os.path.exists(path):
            return False, f"玩家 {player_name} 当前不在 Orion 的 xuid 封禁列表中"
        os.remove(path)
        return True, f"已通过 Orion 解封 {player_name} (xuid:{xuid})"

    def apply_orion_device_unban(self, device_id: str, player_info: dict[str, list[str]]):
        assert self.orion is not None
        path = f"{self.orion.data_path}/{self.orion.config_mgr.device_id_dir}/{device_id}.json"
        if not os.path.exists(path):
            return False, f"设备号 {device_id} 当前不在 Orion 的设备号封禁列表中"
        os.remove(path)
        return True, f"已通过 Orion 解封设备号 {device_id}"

    # ------------------------ 控制台菜单 ------------------------
    def on_console_add_qq_op(self, _args: list[str]):
        if not self.group_order:
            fmts.print_err("当前没有配置任何群聊")
            return
        fmts.print_inf("QQ群管理员增删菜单")
        for index, group_id in enumerate(self.group_order, start=1):
            state = self.read_group_state(group_id)
            fmts.print_inf(
                f"{index}. 群 {group_id} (管理员:{len(state['admins'])} 超级管理员:{len(state['super_admins'])})"
            )
        while True:
            group_input = input("请输入群序号，输入 q 退出: ").strip().lower()
            if group_input == "q":
                fmts.print_inf("已退出QQ群管理员添加菜单")
                return
            group_index = utils.try_int(group_input)
            if group_index is None or group_index not in range(1, len(self.group_order) + 1):
                fmts.print_err("群序号无效")
                continue
            target_group = self.group_order[group_index - 1]
            break
        while True:
            action_input = input("请输入操作类型 (1=添加, 2=删除, q=退出): ").strip().lower()
            if action_input == "q":
                fmts.print_inf("已退出QQ群管理员增删菜单")
                return
            if action_input in ("1", "2"):
                is_remove = action_input == "2"
                break
            fmts.print_err("操作类型无效")
        while True:
            role_input = input("请输入角色类型 (1=普通管理员, 2=超级管理员, q=退出): ").strip().lower()
            if role_input == "q":
                fmts.print_inf("已退出QQ群管理员增删菜单")
                return
            if role_input in ("1", "2"):
                is_super = role_input == "2"
                break
            fmts.print_err("角色类型无效")
        while True:
            qq_input = input(
                f"请输入要{'删除' if is_remove else '添加'}的QQ号，输入 q 退出: "
            ).strip().lower()
            if qq_input == "q":
                fmts.print_inf("已退出QQ群管理员增删菜单")
                return
            qqid = utils.try_int(qq_input)
            if qqid is None or qqid <= 0:
                fmts.print_err("QQ号无效")
                continue
            if is_remove:
                ok, msg = self.remove_group_role(target_group, qqid, is_super=is_super)
            else:
                ok, msg = self.add_group_role(target_group, qqid, is_super=is_super)
            if ok:
                fmts.print_inf(f"群 {target_group}: {msg}")
            else:
                fmts.print_err(f"群 {target_group}: {msg}")
            return

    # ------------------------ 公用执行逻辑 ------------------------
    def execute_cmd_and_get_zhcn_cb(self, cmd: str):
        try:
            result = self.game_ctrl.sendwscmd_with_resp(cmd, 10)
            if len(result.OutputMessages) == 0:
                return ["😅 指令执行失败", "😄 指令执行成功"][bool(result.SuccessCount)]
            if (result.OutputMessages[0].Message == "commands.generic.syntax") or (
                result.OutputMessages[0].Message == "commands.generic.unknown"
            ):
                return f'😅 未知的 MC 指令, 可能是指令格式有误: "{cmd}"'
            if translate is not None:
                output_text = "\n".join(
                    translate(i.Message, i.Parameters) for i in result.OutputMessages
                )
            else:
                output_text = "\n".join(i.Message for i in result.OutputMessages)
            if result.SuccessCount:
                return "😄 指令执行成功，执行结果：\n" + output_text
            return "😭 指令执行失败，原因：\n" + output_text
        except IndexError as exec_err:
            import traceback

            traceback.print_exc()
            return f"执行出现问题: {exec_err}"
        except TimeoutError:
            return "😭 超时：指令获取结果返回超时"

    def iter_game_to_group_targets(self):
        for group_id in self.group_order:
            group_cfg = self.group_cfgs[group_id]
            if group_cfg["游戏到群"]["是否启用"]:
                yield group_id, group_cfg

    def should_forward_game_message(self, msg: str, group_cfg: dict[str, Any]):
        trans_chars = group_cfg["游戏到群"]["仅转发以下符号开头的消息(列表为空则全部转发)"]
        block_prefixs = group_cfg["游戏到群"]["屏蔽以下字符串开头的消息"]
        if trans_chars:
            for prefix in trans_chars:
                if msg.startswith(prefix):
                    return True, msg[len(prefix) :]
            return False, msg
        if block_prefixs:
            for prefix in block_prefixs:
                if msg.startswith(prefix):
                    return False, msg
        return True, msg

    # ------------------------ WebSocket ------------------------
    @utils.thread_func("云链群服连接进程")
    def connect_to_websocket(self):
        header = None
        validate_code = self.cfg["云链设置"]["校验码"].strip()
        if validate_code:
            header = {"Authorization": f"Bearer {validate_code}"}
        self.ws = websocket.WebSocketApp(
            (
                f"ws://127.0.0.1:{self._manual_launch_port}"
                if self._manual_launch
                else self.cfg["云链设置"]["地址"]
            ),
            header,
            on_message=lambda a, b: self.on_ws_message(a, b) and None,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close,
        )
        self.ws.on_open = self.on_ws_open
        self.ws.run_forever()

    @utils.thread_func("云链群服消息广播进程")
    def broadcast(self, data):
        for i in self.plugin:
            self.GetPluginAPI(i).QQLinker_message(data)

    def on_ws_open(self, ws):
        self.available = True
        self.print("§a已成功连接到群服互通云链版Ultra版 =============")

    @utils.thread_func("群服互通消息接收线程")
    def on_ws_message(self, ws, message):
        data = json.loads(message)
        bc_recv = self.BroadcastEvent(InternalBroadcast("群服互通/数据json", data))
        if any(bc_recv):
            return
        if data.get("post_type") != "message" or data.get("message_type") != "group":
            return

        self.broadcast(data)

        group_id = data.get("group_id")
        if group_id not in self.group_cfgs:
            return
        group_cfg = self.group_cfgs[group_id]

        msg = data["message"]
        if isinstance(msg, list):
            msg_rawdict = msg[0]
            msg_type = msg_rawdict["type"]
            msg_data = msg_rawdict["data"]
            if msg_type != "text":
                return
            msg = msg_data["text"]
        elif not isinstance(msg, str):
            raise ValueError(f"键 'message' 值不是字符串类型, 而是 {msg}")

        user_id = int(data["sender"]["user_id"])
        nickname = data["sender"]["card"] or data["sender"]["nickname"]

        wait_key = (group_id, user_id)
        if wait_key in self.waitmsg_cbs:
            self.waitmsg_cbs[wait_key](msg)
            return
        if user_id in self.waitmsg_cbs:
            self.waitmsg_cbs[user_id](msg)
            return

        bc_recv = self.BroadcastEvent(
            InternalBroadcast(
                "群服互通/链接群消息",
                {"群号": group_id, "QQ号": user_id, "昵称": nickname, "消息": msg},
            ),
        )
        if any(bc_recv):
            return

        if self.execute_triggers(group_id, user_id, msg):
            return

        if not group_cfg["群到游戏"]["是否启用"]:
            return
        if user_id in group_cfg["群到游戏"]["屏蔽的QQ号"]:
            return

        if group_cfg["群到游戏"]["替换花里胡哨的昵称"]:
            nickname = remove_color(nickname)
        if group_cfg["群到游戏"]["替换花里胡哨的消息"]:
            msg = remove_color(msg)
        self.game_ctrl.say_to(
            "@a",
            utils.simple_fmt(
                {"[昵称]": nickname, "[消息]": replace_cq(msg)},
                group_cfg["群到游戏"]["转发格式"],
            ),
        )

    def on_ws_error(self, ws, error):
        if not isinstance(error, Exception):
            fmts.print_inf(f"群服互通云链版Ultra版发生错误: {error}, 可能为系统退出, 已关闭")
            self.reloaded = True
            return
        self.available = False
        fmts.print_err(f"群服互通云链版Ultra版发生错误: {error}, 15s后尝试重连")
        time.sleep(15)

    def waitMsg(self, qqid: int, timeout=60, group_id: int | None = None) -> str | None:
        getter, setter = utils.create_result_cb(str)
        key: int | tuple[int, int] = qqid if group_id is None else (group_id, qqid)
        self.waitmsg_cbs[key] = setter
        result = getter(timeout)
        if key in self.waitmsg_cbs:
            del self.waitmsg_cbs[key]
        return result

    def on_ws_close(self, ws, _, _2):
        self.available = False
        if self.reloaded:
            return
        fmts.print_err("群服互通云链版Ultra版被关闭, 10s后尝试重连")
        time.sleep(10)
        self.connect_to_websocket()

    # ------------------------ 游戏到群 ------------------------
    def on_player_join(self, playerf: Player):
        player = playerf.name
        if not self.ws:
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            if group_cfg["游戏到群"]["转发玩家进退提示"]:
                self.sendmsg(group_id, f"{player} 加入了游戏")

    def on_player_leave(self, playerf: Player):
        player = playerf.name
        if not self.ws:
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            if group_cfg["游戏到群"]["转发玩家进退提示"]:
                self.sendmsg(group_id, f"{player} 退出了游戏")

    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg
        if not self.ws:
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            can_send, filtered_msg = self.should_forward_game_message(msg, group_cfg)
            if not can_send:
                continue
            self.sendmsg(
                group_id,
                utils.simple_fmt(
                    {"[玩家名]": player, "[消息]": remove_cq_code(filtered_msg)},
                    group_cfg["游戏到群"]["转发格式"],
                ),
            )

    # ------------------------ Trigger 执行 ------------------------
    def execute_triggers(self, group_id: int, qqid: int, msg: str):
        clean_msg = msg.strip()
        if clean_msg in self.get_group_help_triggers(group_id):
            self.on_qq_help(group_id, qqid, [])
            return True
        if clean_msg in self.get_group_admin_menu_triggers(group_id):
            self.qq_admin_menu(group_id, qqid)
            return True
        cmd_prefix = self.get_group_cmd_prefix(group_id)
        if clean_msg.startswith(cmd_prefix):
            args = clean_msg.removeprefix(cmd_prefix).strip().split()
            if not self.is_group_admin(group_id, qqid):
                self.sendmsg(
                    group_id,
                    f"[CQ:at,qq={qqid}] 你没有权限执行此指令",
                    do_remove_cq_code=False,
                )
                return True
            if len(args) == 0:
                self.sendmsg(
                    group_id,
                    f"[CQ:at,qq={qqid}] 参数错误，格式：{cmd_prefix}[指令]",
                    do_remove_cq_code=False,
                )
                return True
            self.on_qq_execute_cmd(group_id, qqid, args)
            return True
        if clean_msg in self.get_group_player_list_triggers(group_id):
            self.on_qq_player_list(group_id, qqid, [])
            return True
        if clean_msg in self.get_group_inventory_menu_triggers(group_id):
            if not self.is_group_admin(group_id, qqid):
                self.sendmsg(
                    group_id,
                    f"[CQ:at,qq={qqid}] 你没有权限执行此指令",
                    do_remove_cq_code=False,
                )
                return True
            self.qq_inventory_menu(group_id, qqid)
            return True
        if clean_msg in self.get_group_checker_menu_triggers(group_id):
            if not self.is_group_admin(group_id, qqid):
                self.sendmsg(
                    group_id,
                    f"[CQ:at,qq={qqid}] 你没有权限执行此指令",
                    do_remove_cq_code=False,
                )
                return True
            self.qq_checker_menu(group_id, qqid)
            return True
        for trigger in self.get_group_orion_ban_triggers(group_id):
            if clean_msg.startswith(trigger):
                args = clean_msg.removeprefix(trigger).strip().split()
                if not self.is_group_admin(group_id, qqid):
                    self.sendmsg(
                        group_id,
                        f"[CQ:at,qq={qqid}] 你没有权限执行此指令",
                        do_remove_cq_code=False,
                    )
                    return True
                if not (len(args) == 0 or len(args) >= 2):
                    self.sendmsg(
                        group_id,
                        f"[CQ:at,qq={qqid}] 参数错误，格式：{trigger} [玩家名/xuid] [封禁时间] [原因可选]",
                        do_remove_cq_code=False,
                    )
                    return True
                self.on_qq_orion_ban(group_id, qqid, args)
                return True
        for trigger in self.get_group_orion_unban_triggers(group_id):
            if clean_msg.startswith(trigger):
                args = clean_msg.removeprefix(trigger).strip().split()
                if not self.is_group_admin(group_id, qqid):
                    self.sendmsg(
                        group_id,
                        f"[CQ:at,qq={qqid}] 你没有权限执行此指令",
                        do_remove_cq_code=False,
                    )
                    return True
                if len(args) not in (0, 1):
                    self.sendmsg(
                        group_id,
                        f"[CQ:at,qq={qqid}] 参数错误，格式：{trigger} [玩家名/xuid]",
                        do_remove_cq_code=False,
                    )
                    return True
                self.on_qq_orion_unban(group_id, qqid, args)
                return True
        for trigger in self.triggers:
            if t := trigger.match(msg):
                if trigger.op_only and not self.is_group_admin(group_id, qqid):
                    if easter_egg := EASTER_EGG_QQIDS.get(qqid):
                        _name, nickname = easter_egg
                        self.sendmsg(
                            group_id,
                            f"[CQ:at,qq={qqid}] 你没有权限执行此指令，即使你是 {nickname}..",
                            do_remove_cq_code=False,
                        )
                    else:
                        self.sendmsg(
                            group_id,
                            f"[CQ:at,qq={qqid}] 你没有权限执行此指令",
                            do_remove_cq_code=False,
                        )
                    return True

                args = msg.removeprefix(t).strip().split()
                if not trigger.args_pd(len(args)):
                    self.sendmsg(
                        group_id,
                        f"[CQ:at,qq={qqid}] 参数错误，格式：{t}"
                        f"{' ' + trigger.argument_hint if trigger.argument_hint else ''}",
                        do_remove_cq_code=False,
                    )
                    return True
                if trigger.accept_group:
                    trigger.func(group_id, qqid, args)
                else:
                    trigger.func(qqid, args)
                return True
        return False

    # ------------------------ 控制台与发送 ------------------------
    def on_sendmsg_test(self, args: list[str]):
        if not self.ws:
            fmts.print_err("还没有连接到群服互通云链版Ultra版")
            return
        if not args:
            fmts.print_err("请输入要发送的消息")
            return
        target_group = None
        if len(args) >= 2:
            maybe_gid = utils.try_int(args[0])
            if maybe_gid in self.group_cfgs:
                target_group = maybe_gid
                args = args[1:]
        if target_group is not None:
            self.sendmsg(target_group, " ".join(args))
            return
        for group_id in self.group_order:
            self.sendmsg(group_id, " ".join(args))

    def sendmsg(self, group: int, msg: str, do_remove_cq_code=True):
        assert self.ws
        if not self.available:
            self.print(f"§6未连接, 忽略发送至 {group} 的消息 {msg}")
            return
        if msg.startswith("[CQ:at,qq="):
            cq_end = msg.find("]")
            if cq_end != -1:
                head = msg[: cq_end + 1]
                tail = msg[cq_end + 1 :].lstrip()
                msg = head if tail == "" else head + "\n" + tail
        if do_remove_cq_code:
            msg = remove_cq_code(msg)
        jsondat = json.dumps(
            {"action": "send_group_msg", "params": {"group_id": group, "message": msg}}
        )
        self.ws.send(jsondat)


entry = plugin_entry(QQLinker, "群服互通")

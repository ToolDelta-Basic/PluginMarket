"""配置与群权限相关的公共逻辑。

这一层解决两个问题：
1. 把历史配置逐步迁到现在的“多群结构”。
2. 提供群管理员、超级管理员、触发词等基础数据访问能力。
"""

import inspect
import json
import os
from typing import Any
from collections.abc import Callable

from tooldelta import cfg

from .message_utils import QQMsgTrigger


# 配置迁移、群权限状态和触发词读取都收在这一层，避免散到业务逻辑里。
class QQLinkerConfigMixin:
    """配置、群状态和触发词的基础能力集合。"""

    @staticmethod
    def group_default(group_id: int = 194838530):
        """返回单个群聊的默认配置骨架。"""
        # 单个群聊的完整默认结构，老配置迁移时也以它做兜底模板。
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
        """返回插件级默认配置。"""
        return {
            "云链设置": {"地址": "ws://127.0.0.1:3001", "校验码": ""},
            "群聊设置": [cls.group_default()],
        }

    @classmethod
    def cfg_std(cls):
        """返回 ToolDelta 用来校验配置的数据结构定义。"""
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
        """把来源不可信的列表规整成去重后的正整数列表。"""
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
        """递归合并旧配置和默认值。

        这里不会粗暴覆盖未知字段，目的是在升级时尽量保留用户已经写进配置里的内容。
        """
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
        """把单个群聊配置迁到当前结构。

        这个方法主要处理字段补全、类型纠正和历史字段兼容，
        这样业务层就可以假设拿到的 group_cfg 是完整且结构稳定的。
        """
        if not isinstance(raw_group, dict):
            return None
        try:
            group_id = int(raw_group.get("群号", 0))
        except (TypeError, ValueError):
            return None
        if group_id <= 0:
            return None
        group_cfg = self.group_default(group_id)
        # 老版本配置是按几个子区块散开的，这里逐段合并到统一结构里。
        old_g2q = raw_group.get("游戏到群", {})
        old_q2g = raw_group.get("群到游戏", {})
        old_cmd = raw_group.get("指令设置", {})
        self._merge_game_to_group_cfg(group_cfg, old_g2q)
        self._merge_group_to_game_cfg(group_cfg, old_q2g)
        self._merge_command_cfg(group_cfg, old_cmd)
        return group_cfg

    def _merge_game_to_group_cfg(self, group_cfg: dict[str, Any], old_g2q: Any):
        """把旧版“游戏到群”配置段合并进当前群配置。"""
        if not isinstance(old_g2q, dict):
            return
        game_to_group = group_cfg["游戏到群"]
        game_to_group["是否启用"] = bool(old_g2q.get("是否启用", game_to_group["是否启用"]))
        game_to_group["转发格式"] = str(old_g2q.get("转发格式", game_to_group["转发格式"]))
        game_to_group["仅转发以下符号开头的消息(列表为空则全部转发)"] = self._clean_string_list(
            old_g2q.get(
                "仅转发以下符号开头的消息(列表为空则全部转发)",
                game_to_group["仅转发以下符号开头的消息(列表为空则全部转发)"],
            ),
            game_to_group["仅转发以下符号开头的消息(列表为空则全部转发)"],
        )
        game_to_group["屏蔽以下字符串开头的消息"] = self._clean_string_list(
            old_g2q.get(
                "屏蔽以下字符串开头的消息",
                game_to_group["屏蔽以下字符串开头的消息"],
            ),
            game_to_group["屏蔽以下字符串开头的消息"],
        )
        game_to_group["转发玩家进退提示"] = bool(
            old_g2q.get("转发玩家进退提示", game_to_group["转发玩家进退提示"])
        )

    def _merge_group_to_game_cfg(self, group_cfg: dict[str, Any], old_q2g: Any):
        """把旧版“群到游戏”配置段合并进当前群配置。"""
        if not isinstance(old_q2g, dict):
            return
        group_to_game = group_cfg["群到游戏"]
        group_to_game["是否启用"] = bool(old_q2g.get("是否启用", group_to_game["是否启用"]))
        group_to_game["转发格式"] = str(old_q2g.get("转发格式", group_to_game["转发格式"]))
        group_to_game["屏蔽的QQ号"] = self.normalize_int_list(old_q2g.get("屏蔽的QQ号", []))
        group_to_game["替换花里胡哨的昵称"] = bool(
            old_q2g.get("替换花里胡哨的昵称", group_to_game["替换花里胡哨的昵称"])
        )
        group_to_game["替换花里胡哨的消息"] = bool(
            old_q2g.get("替换花里胡哨的消息", group_to_game["替换花里胡哨的消息"])
        )

    def _merge_command_cfg(self, group_cfg: dict[str, Any], old_cmd: Any):
        """把旧版指令相关配置合并进当前群配置。"""
        if not isinstance(old_cmd, dict):
            return
        command_cfg = group_cfg["指令设置"]
        command_cfg["发送指令前缀"] = (
            str(old_cmd.get("发送指令前缀", command_cfg["发送指令前缀"])).strip()
            or command_cfg["发送指令前缀"]
        )
        command_cfg["管理员菜单唤醒词"] = self._clean_string_list(
            old_cmd.get("管理员菜单唤醒词", command_cfg["管理员菜单唤醒词"]),
            command_cfg["管理员菜单唤醒词"],
        )
        command_cfg["帮助菜单唤醒词"] = self._clean_string_list(
            old_cmd.get("帮助菜单唤醒词", command_cfg["帮助菜单唤醒词"]),
            command_cfg["帮助菜单唤醒词"],
        )
        command_cfg["是否允许查看玩家列表"] = bool(
            old_cmd.get("是否允许查看玩家列表", command_cfg["是否允许查看玩家列表"])
        )
        command_cfg["查看玩家人数的唤醒词"] = self._clean_string_list(
            old_cmd.get("查看玩家人数的唤醒词", command_cfg["查看玩家人数的唤醒词"]),
            command_cfg["查看玩家人数的唤醒词"],
        )
        command_cfg["查询背包菜单唤醒词"] = self._clean_string_list(
            old_cmd.get("查询背包菜单唤醒词", command_cfg["查询背包菜单唤醒词"]),
            command_cfg["查询背包菜单唤醒词"],
        )
        command_cfg["查询背包菜单每页显示的玩家数量"] = self._normalize_positive_int(
            old_cmd.get(
                "查询背包菜单每页显示的玩家数量",
                command_cfg["查询背包菜单每页显示的玩家数量"],
            ),
            command_cfg["查询背包菜单每页显示的玩家数量"],
        )
        command_cfg["QQ群封禁唤醒词"] = self._clean_string_list(
            old_cmd.get("QQ群封禁唤醒词", command_cfg["QQ群封禁唤醒词"]),
            command_cfg["QQ群封禁唤醒词"],
        )
        command_cfg["QQ群解封唤醒词"] = self._clean_string_list(
            old_cmd.get("QQ群解封唤醒词", command_cfg["QQ群解封唤醒词"]),
            command_cfg["QQ群解封唤醒词"],
        )
        command_cfg["QQ群白名单&管理员检测唤醒词"] = self._clean_string_list(
            old_cmd.get(
                "QQ群白名单&管理员检测唤醒词",
                command_cfg["QQ群白名单&管理员检测唤醒词"],
            ),
            command_cfg["QQ群白名单&管理员检测唤醒词"],
        )
        command_cfg["QQ群封禁/解封菜单每页显示个数"] = self._normalize_positive_int(
            old_cmd.get(
                "QQ群封禁/解封菜单每页显示个数",
                command_cfg["QQ群封禁/解封菜单每页显示个数"],
            ),
            command_cfg["QQ群封禁/解封菜单每页显示个数"],
        )

    @staticmethod
    def _clean_string_list(raw: Any, fallback: list[str]):
        """清理字符串列表，失败时回退到默认值。"""
        if isinstance(raw, list):
            cleaned = [str(item) for item in raw if isinstance(item, str)]
            if cleaned:
                return cleaned
        return fallback

    @staticmethod
    def _normalize_positive_int(value: Any, fallback: int):
        """把不可信的数字输入规范成正整数。"""
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return fallback

    def migrate_config(self, raw_cfg: Any):
        """把整个插件配置迁到最新版本。

        历史上这个插件经历过“单群结构”和“多群结构”两个阶段，
        所以这里除了常规默认值补齐，还要兼容最早那一版只有 `消息转发设置` 的写法。
        """
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
            # 兼容最早的单群结构，迁完之后统一走“群聊设置”列表。
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
        """把配置中的群信息展开成运行时缓存。

        后续消息分发会频繁按群号查配置，所以这里同时保留：
        - `group_cfgs`: 适合按群号直接读取
        - `group_order`: 适合顺序遍历和显示菜单
        """
        self.group_cfgs.clear()
        self.group_order.clear()
        # 运行时同时保留 dict 和顺序列表，后面做群路由会更直接。
        for group_cfg in self.cfg["群聊设置"]:
            group_id = int(group_cfg["群号"])
            self.group_cfgs[group_id] = group_cfg
            self.group_order.append(group_id)
        for group_id in self.group_order:
            self.ensure_group_state(group_id)

    @property
    def linked_group(self) -> int | None:
        """返回兼容旧插件调用时使用的默认群号。"""
        # 给还按“单群互通”接口调用的旧插件留一个兼容入口。
        return self.group_order[0] if self.group_order else None

    def group_state_path(self, group_id: int):
        """返回某个群的权限状态文件路径。"""
        return os.path.join(self.group_state_dir, f"{group_id}.json")

    def read_group_state(self, group_id: int):
        """读取单个群的管理员状态。

        就算文件损坏，也会兜底回空状态，避免因为单个群配置异常拖垮整个插件。
        """
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
        """保存并顺手归一化群权限状态。"""
        path = self.group_state_path(group_id)
        normalized = {
            "admins": self.normalize_int_list(state.get("admins", [])),
            "super_admins": self.normalize_int_list(state.get("super_admins", [])),
        }
        with open(path, "w", encoding="utf-8") as file:
            json.dump(normalized, file, ensure_ascii=False, indent=2)

    def ensure_group_state(self, group_id: int):
        """确保群权限文件一定存在，而且结构可读。"""
        path = self.group_state_path(group_id)
        if os.path.isfile(path):
            state = self.read_group_state(group_id)
            self.save_group_state(group_id, state)
            return
        self.save_group_state(group_id, {"admins": [], "super_admins": []})

    def is_group_super_admin(self, group_id: int, qqid: int):
        """判断某个 QQ 是否是指定群的超级管理员。"""
        return qqid in self.read_group_state(group_id)["super_admins"]

    def is_group_admin(self, group_id: int, qqid: int):
        """判断某个 QQ 是否拥有群内管理权限。

        普通管理员和超级管理员在大多数执行权限上是并列的，所以这里统一封装成一个入口。
        """
        state = self.read_group_state(group_id)
        return qqid in state["super_admins"] or qqid in state["admins"]

    def is_qq_op(self, qqid: int, group_id: int | None = None):
        """兼容旧命名，判断某个 QQ 是否拥有管理员权限。"""
        if group_id is not None:
            return self.is_group_admin(group_id, qqid)
        return any(self.is_group_admin(gid, qqid) for gid in self.group_order)

    def add_group_role(self, group_id: int, qqid: int, is_super: bool):
        """给群成员授予管理员或超级管理员身份。"""
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
        """移除群成员的管理员或超级管理员身份。"""
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
        """读取某个群的玩家列表触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("查看玩家人数的唤醒词", ["list", "玩家列表"])
        return self.normalize_string_triggers(raw, ["list", "玩家列表"])

    def get_group_inventory_menu_triggers(self, group_id: int):
        """读取某个群的背包查询触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("查询背包菜单唤醒词", ["查询背包"])
        return self.normalize_string_triggers(raw, ["查询背包"])

    def get_group_inventory_items_per_page(self, group_id: int):
        """读取背包查询菜单每页条数。"""
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["查询背包菜单每页显示的玩家数量"]),
                )
            except (KeyError, TypeError, ValueError):
                return 10
        return 10

    def get_group_help_triggers(self, group_id: int):
        """读取某个群的帮助菜单触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("帮助菜单唤醒词", ["help", "帮助"])
        return self.normalize_string_triggers(raw, ["help", "帮助"])

    def get_group_admin_menu_triggers(self, group_id: int):
        """读取某个群的管理员菜单触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("管理员菜单唤醒词", ["管理员菜单"])
        return self.normalize_string_triggers(raw, ["管理员菜单"])

    def get_group_cmd_prefix(self, group_id: int):
        """读取群内执行 MC 指令时使用的命令前缀。"""
        group_cfg = self.group_cfgs[group_id]
        prefix = str(group_cfg["指令设置"].get("发送指令前缀", "/")).strip()
        return prefix or "/"

    def get_group_orion_ban_triggers(self, group_id: int):
        """读取某个群的 Orion 封禁触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get(
            "QQ群封禁唤醒词",
            ["orban", "orion ban", "猎户封禁"],
        )
        return self.normalize_string_triggers(raw, ["orban", "orion ban", "猎户封禁"])

    def get_group_orion_unban_triggers(self, group_id: int):
        """读取某个群的 Orion 解封触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get(
            "QQ群解封唤醒词",
            ["orunban", "orion unban", "猎户解封"],
        )
        return self.normalize_string_triggers(raw, ["orunban", "orion unban", "猎户解封"])

    def get_group_checker_menu_triggers(self, group_id: int):
        """读取某个群的白名单联动菜单触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get(
            "QQ群白名单&管理员检测唤醒词",
            ["白名单&管理员检测", "检测管理"],
        )
        return self.normalize_string_triggers(raw, ["白名单&管理员检测", "检测管理"])

    @staticmethod
    def normalize_string_triggers(raw: Any, fallback: list[str]):
        """把触发词列表清洗成无空值、无重复的稳定序列。"""
        triggers: list[str] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, str):
                    continue
                text = item.strip()
                if text and text not in triggers:
                    triggers.append(text)
        return triggers or fallback

    def add_trigger(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[..., Any],
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only: bool = False,
    ):
        """把外部插件注册的 QQ 触发规则挂入统一分发入口。"""
        # 允许外部插件把自己的 QQ 指令挂进互通插件的统一分发入口。
        if not inspect.isroutine(func) and not callable(func):
            raise TypeError("func 必须是可调用对象")
        self.triggers.append(
            QQMsgTrigger(triggers, argument_hint, usage, func, args_pd, op_only)
        )

    def set_manual_launch(self, port: int):
        """切换到“本地启动器负责拉起云链”的模式。"""
        self._manual_launch = True
        self._manual_launch_port = port

    def manual_launch(self):
        """给本地启动器调用的显式连接入口。"""
        self.connect_to_websocket()

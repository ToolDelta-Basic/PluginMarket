"""配置与群权限相关的公共逻辑。

这一层解决两个问题：
1. 把历史配置逐步迁到现在的“多群结构”。
2. 提供群管理员、超级管理员、触发词等基础数据访问能力。
"""

import inspect
import json
import os
from copy import deepcopy
from typing import Any
from collections.abc import Callable

from tooldelta import cfg

from .message_utils import QQMsgTrigger


# 配置迁移、群权限状态和触发词读取都收在这一层，避免散到业务逻辑里。
class QQLinkerConfigMixin:
    """配置、群状态和触发词的基础能力集合。"""

    MENU_EXIT_TRIGGERS_DEFAULT = [".", "。", "q"]
    MENU_BACK_TRIGGERS_DEFAULT = ["!", "！"]
    CONFIG_FILE_DIR = "插件配置文件"
    RUNTIME_CONFIG_RELOAD_INTERVAL = 5
    DYNAMIC_LOAD_SETTINGS_KEY = "动态载入设置"
    DYNAMIC_LOAD_ENABLED_KEY = "是否启用动态载入配置文件（仅用于本插件）"
    DYNAMIC_LOAD_INTERVAL_KEY = "动态载入检测时间间隔（单位：秒）"
    OWNER_QQ_DEFAULT = 1234567890
    OWNER_QQ_UNSET = 0
    PERMISSION_SETTINGS_KEY = "权限设置"
    LEGACY_GROUP_STATE_DIR_NAME = "群聊权限数据"

    @staticmethod
    def binding_default():
        """返回全局 QQ 与游戏 ID 绑定配置。"""
        return {
            "是否开启QQ号与游戏ID绑定功能": False,
            "是否允许单QQ号可绑定多游戏ID": False,
            "是否允许单游戏ID可绑定多QQ号": False,
            "绑定触发词": ["绑定"],
            "绑定超时时间（单位：分钟）": 10,
            "绑定验证码群聊提示文本": "已将验证码发送至您的私信，请在{time}分钟内在游戏中发送验证码以完成绑定。",
            "绑定验证码私信提示文本": "您的绑定验证码是：{auth_code}。请在{time}分钟内在游戏中发送该验证码已完成绑定。",
            "拒绝绑定提示文本（仅在“是否允许单QQ号可绑定多游戏ID”为否时生效）": "您已有绑定账号，请解绑后再绑定",
            "绑定超时提示文本": "绑定超时，请重新获取验证码绑定",
            "绑定成功提示文本": "恭喜你绑定成功，您的游戏ID为：{player_name}。",
        }

    @classmethod
    def permission_default(cls):
        """返回单个群聊的权限配置。"""
        return {
            "所有者QQ号": cls.OWNER_QQ_DEFAULT,
            "超级管理员QQ号": [cls.OWNER_QQ_DEFAULT],
            "普通管理员QQ号": [cls.OWNER_QQ_DEFAULT],
            "各功能权限设置": {
                "查看玩家人数权限": {
                    "是否允许普通成员使用": True,
                    "是否允许普通管理员使用": True,
                    "是否允许超级管理员使用": True,
                },
                "发送指令权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": True,
                    "是否允许超级管理员使用": True,
                },
                "查询背包权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": True,
                    "是否允许超级管理员使用": True,
                },
                "封禁/解封玩家权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": True,
                    "是否允许超级管理员使用": True,
                },
                "白名单&管理员检测权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": False,
                    "是否允许超级管理员使用": True,
                },
                "领地系统权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": True,
                    "是否允许超级管理员使用": True,
                },
                "公会系统权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": True,
                    "是否允许超级管理员使用": True,
                },
                "任务系统权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": True,
                    "是否允许超级管理员使用": True,
                },
                "配置配置文件权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": False,
                    "是否允许超级管理员使用": True,
                },
                "QQ普通管理员菜单权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": False,
                    "是否允许超级管理员使用": True,
                },
                "QQ超级管理员菜单权限": {
                    "是否允许普通成员使用": False,
                    "是否允许普通管理员使用": False,
                    "是否允许超级管理员使用": False,
                },
            },
        }

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
                "仅转发以下符号开头的消息(列表为空则全部转发)": [],
                "屏蔽的QQ号": [],
                "替换花里胡哨的昵称": True,
                "替换花里胡哨的消息": True,
            },
            QQLinkerConfigMixin.PERMISSION_SETTINGS_KEY: (
                QQLinkerConfigMixin.permission_default()
            ),
            "指令设置": {
                "发送指令前缀": "/",
                "帮助菜单唤醒词": ["help", "帮助"],
                "帮助菜单非管理功能每页显示数量": 10,
                "帮助菜单管理功能每页显示数量": 10,
                "命令触发词帮助菜单每页显示数量": 10,
                "配置文件整文件修改模式每页显示数量": 10,
                "管理员菜单唤醒词": ["管理员菜单"],
                "配置中心唤醒词": ["配置中心", "配置菜单", "群服配置"],
                "退出整个菜单触发词": [".", "。", "q"],
                "返回上一级菜单触发词": ["!", "！"],
                "是否允许查看玩家列表": True,
                "查看玩家人数的唤醒词": ["list", "玩家列表"],
                "查询背包菜单唤醒词": ["查询背包"],
                "查询背包菜单每页显示的玩家数量": 10,
                "QQ群封禁唤醒词": ["orban", "orion ban", "猎户封禁"],
                "QQ群解封唤醒词": ["orunban", "orion unban", "猎户解封"],
                "QQ群白名单&管理员检测唤醒词": ["白名单&管理员检测", "检测管理"],
                "任务系统菜单唤醒词": ["任务系统"],
                "任务系统每页显示玩家数量": 10,
                "任务系统每页显示任务数量": 10,
                "领地系统菜单唤醒词": ["领地系统云链联动版", "领地系统", "领地管理"],
                "领地系统每页显示领地数量": 10,
                "公会系统管理菜单唤醒词": ["公会系统"],
                "QQ群封禁/解封菜单每页显示个数": 10,
            },
        }

    @classmethod
    def cfg_default(cls):
        """返回插件级默认配置。"""
        return {
            cls.DYNAMIC_LOAD_SETTINGS_KEY: {
                cls.DYNAMIC_LOAD_ENABLED_KEY: True,
                cls.DYNAMIC_LOAD_INTERVAL_KEY: cls.RUNTIME_CONFIG_RELOAD_INTERVAL,
            },
            "云链设置": {
                "地址": "ws://127.0.0.1:3001",
                "校验码": ""},
            "绑定设置": cls.binding_default(),
            "群聊设置": [
                cls.group_default()],
        }

    @classmethod
    def cfg_std(cls):
        """返回 ToolDelta 用来校验配置的数据结构定义。"""
        binding_std = {
            "是否开启QQ号与游戏ID绑定功能": bool,
            "是否允许单QQ号可绑定多游戏ID": bool,
            "是否允许单游戏ID可绑定多QQ号": bool,
            "绑定触发词": cfg.JsonList(str, -1),
            "绑定超时时间（单位：分钟）": cfg.PInt,
            "绑定验证码群聊提示文本": str,
            "绑定验证码私信提示文本": str,
            "拒绝绑定提示文本（仅在“是否允许单QQ号可绑定多游戏ID”为否时生效）": str,
            "绑定超时提示文本": str,
            "绑定成功提示文本": str,
        }
        permission_item_std = {
            "是否允许普通成员使用": bool,
            "是否允许普通管理员使用": bool,
            "是否允许超级管理员使用": bool,
        }
        permission_std = {
            "所有者QQ号": int,
            "超级管理员QQ号": cfg.JsonList(cfg.PInt, -1),
            "普通管理员QQ号": cfg.JsonList(cfg.PInt, -1),
            "各功能权限设置": {
                "查看玩家人数权限": permission_item_std,
                "发送指令权限": permission_item_std,
                "查询背包权限": permission_item_std,
                "封禁/解封玩家权限": permission_item_std,
                "白名单&管理员检测权限": permission_item_std,
                "领地系统权限": permission_item_std,
                "公会系统权限": permission_item_std,
                "任务系统权限": permission_item_std,
                "配置配置文件权限": permission_item_std,
                "QQ普通管理员菜单权限": permission_item_std,
                "QQ超级管理员菜单权限": permission_item_std,
            },
        }
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
                "仅转发以下符号开头的消息(列表为空则全部转发)": cfg.JsonList(str, -1),
                "屏蔽的QQ号": cfg.JsonList(cfg.PInt, -1),
                "替换花里胡哨的昵称": bool,
                "替换花里胡哨的消息": bool,
            },
            cls.PERMISSION_SETTINGS_KEY: permission_std,
            "指令设置": {
                "发送指令前缀": str,
                "帮助菜单唤醒词": cfg.JsonList(str, -1),
                "帮助菜单非管理功能每页显示数量": cfg.PInt,
                "帮助菜单管理功能每页显示数量": cfg.PInt,
                "命令触发词帮助菜单每页显示数量": cfg.PInt,
                "配置文件整文件修改模式每页显示数量": cfg.PInt,
                "管理员菜单唤醒词": cfg.JsonList(str, -1),
                "配置中心唤醒词": cfg.JsonList(str, -1),
                "退出整个菜单触发词": cfg.JsonList(str, -1),
                "返回上一级菜单触发词": cfg.JsonList(str, -1),
                "是否允许查看玩家列表": bool,
                "查看玩家人数的唤醒词": cfg.JsonList(str, -1),
                "查询背包菜单唤醒词": cfg.JsonList(str, -1),
                "查询背包菜单每页显示的玩家数量": cfg.PInt,
                "QQ群封禁唤醒词": cfg.JsonList(str, -1),
                "QQ群解封唤醒词": cfg.JsonList(str, -1),
                "QQ群白名单&管理员检测唤醒词": cfg.JsonList(str, -1),
                "任务系统菜单唤醒词": cfg.JsonList(str, -1),
                "任务系统每页显示玩家数量": cfg.PInt,
                "任务系统每页显示任务数量": cfg.PInt,
                "领地系统菜单唤醒词": cfg.JsonList(str, -1),
                "领地系统每页显示领地数量": cfg.PInt,
                "公会系统管理菜单唤醒词": cfg.JsonList(str, -1),
                "QQ群封禁/解封菜单每页显示个数": cfg.PInt,
            },
        }
        return {
            cls.DYNAMIC_LOAD_SETTINGS_KEY: {
                cls.DYNAMIC_LOAD_ENABLED_KEY: bool,
                cls.DYNAMIC_LOAD_INTERVAL_KEY: cfg.PInt,
            },
            "云链设置": {"地址": str, "校验码": str},
            "绑定设置": binding_std,
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
    def normalize_owner_qq(cls, value: Any) -> int:
        """把配置中的所有者 QQ 规整成单个整数 QQ 号。"""
        text = str(value).strip() if value is not None else ""
        if text in ("", "00000000"):
            return cls.OWNER_QQ_DEFAULT
        try:
            qqid = int(text)
        except (TypeError, ValueError):
            return cls.OWNER_QQ_DEFAULT
        if qqid == cls.OWNER_QQ_UNSET:
            return cls.OWNER_QQ_DEFAULT
        return qqid if qqid > 0 else cls.OWNER_QQ_DEFAULT

    @staticmethod
    def _normalize_bool(value: Any, fallback: bool) -> bool:
        """Normalize bool values."""
        if isinstance(value, bool):
            return value
        return fallback

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
                        result[key] = cls.merge_with_default(
                            value, result[key])
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
        old_permissions = raw_group.get(self.PERMISSION_SETTINGS_KEY, {})
        old_cmd = raw_group.get("指令设置", {})
        self._merge_game_to_group_cfg(group_cfg, old_g2q)
        self._merge_group_to_game_cfg(group_cfg, old_q2g)
        self._merge_permission_cfg(group_cfg, old_permissions)
        self._merge_command_cfg(group_cfg, old_cmd)
        return group_cfg

    def _merge_binding_cfg(
            self, binding_cfg: dict[str, Any], old_binding: Any):
        """把 QQ 与游戏 ID 绑定设置合并进全局配置。"""
        if not isinstance(old_binding, dict):
            return
        binding_cfg["是否开启QQ号与游戏ID绑定功能"] = bool(
            old_binding.get(
                "是否开启QQ号与游戏ID绑定功能",
                binding_cfg["是否开启QQ号与游戏ID绑定功能"],
            )
        )
        binding_cfg["是否允许单QQ号可绑定多游戏ID"] = bool(
            old_binding.get(
                "是否允许单QQ号可绑定多游戏ID",
                binding_cfg["是否允许单QQ号可绑定多游戏ID"],
            )
        )
        binding_cfg["是否允许单游戏ID可绑定多QQ号"] = bool(
            old_binding.get(
                "是否允许单游戏ID可绑定多QQ号",
                binding_cfg["是否允许单游戏ID可绑定多QQ号"],
            )
        )
        binding_cfg["绑定触发词"] = self._clean_string_list(
            old_binding.get("绑定触发词", binding_cfg["绑定触发词"]),
            binding_cfg["绑定触发词"],
        )
        binding_cfg["绑定超时时间（单位：分钟）"] = self._normalize_positive_int(
            old_binding.get(
                "绑定超时时间（单位：分钟）",
                binding_cfg["绑定超时时间（单位：分钟）"],
            ),
            binding_cfg["绑定超时时间（单位：分钟）"],
        )
        old_send_text = str(
            old_binding.get(
                "绑定验证码群聊提示文本",
                binding_cfg["绑定验证码群聊提示文本"],
            )
        ).strip()
        if old_send_text:
            binding_cfg["绑定验证码群聊提示文本"] = old_send_text
        binding_cfg["绑定验证码私信提示文本"] = (
            str(
                old_binding.get(
                    "绑定验证码私信提示文本",
                    binding_cfg["绑定验证码私信提示文本"],
                )
            ).strip()
            or binding_cfg["绑定验证码私信提示文本"]
        )
        binding_cfg["拒绝绑定提示文本（仅在“是否允许单QQ号可绑定多游戏ID”为否时生效）"] = (
            str(
                old_binding.get(
                    "拒绝绑定提示文本（仅在“是否允许单QQ号可绑定多游戏ID”为否时生效）",
                    binding_cfg["拒绝绑定提示文本（仅在“是否允许单QQ号可绑定多游戏ID”为否时生效）"],
                )
            ).strip()
            or binding_cfg["拒绝绑定提示文本（仅在“是否允许单QQ号可绑定多游戏ID”为否时生效）"]
        )
        binding_cfg["绑定超时提示文本"] = (
            str(
                old_binding.get(
                    "绑定超时提示文本",
                    binding_cfg["绑定超时提示文本"],
                )
            ).strip()
            or binding_cfg["绑定超时提示文本"]
        )
        binding_cfg["绑定成功提示文本"] = (
            str(old_binding.get("绑定成功提示文本", binding_cfg["绑定成功提示文本"])).strip()
            or binding_cfg["绑定成功提示文本"]
        )

    def _merge_game_to_group_cfg(
            self, group_cfg: dict[str, Any], old_g2q: Any):
        """把旧版“游戏到群”配置段合并进当前群配置。"""
        if not isinstance(old_g2q, dict):
            return
        game_to_group = group_cfg["游戏到群"]
        game_to_group["是否启用"] = bool(
            old_g2q.get("是否启用", game_to_group["是否启用"]))
        game_to_group["转发格式"] = str(old_g2q.get("转发格式", game_to_group["转发格式"]))
        game_to_group["仅转发以下符号开头的消息(列表为空则全部转发)"] = self._clean_string_list(
            old_g2q.get(
                "仅转发以下符号开头的消息(列表为空则全部转发)",
                game_to_group["仅转发以下符号开头的消息(列表为空则全部转发)"],
            ),
            game_to_group["仅转发以下符号开头的消息(列表为空则全部转发)"],
            allow_empty=True,
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

    def _merge_group_to_game_cfg(
            self, group_cfg: dict[str, Any], old_q2g: Any):
        """把旧版“群到游戏”配置段合并进当前群配置。"""
        if not isinstance(old_q2g, dict):
            return
        group_to_game = group_cfg["群到游戏"]
        group_to_game["是否启用"] = bool(
            old_q2g.get("是否启用", group_to_game["是否启用"]))
        group_to_game["转发格式"] = str(old_q2g.get("转发格式", group_to_game["转发格式"]))
        group_to_game["仅转发以下符号开头的消息(列表为空则全部转发)"] = self._clean_string_list(
            old_q2g.get(
                "仅转发以下符号开头的消息(列表为空则全部转发)",
                group_to_game["仅转发以下符号开头的消息(列表为空则全部转发)"],
            ),
            group_to_game["仅转发以下符号开头的消息(列表为空则全部转发)"],
            allow_empty=True,
        )
        group_to_game["屏蔽的QQ号"] = self.normalize_int_list(
            old_q2g.get("屏蔽的QQ号", []))
        group_to_game["替换花里胡哨的昵称"] = bool(
            old_q2g.get("替换花里胡哨的昵称", group_to_game["替换花里胡哨的昵称"])
        )
        group_to_game["替换花里胡哨的消息"] = bool(
            old_q2g.get("替换花里胡哨的消息", group_to_game["替换花里胡哨的消息"])
        )

    def _legacy_group_state_dir(self) -> str:
        """Implement the legacy group state dir operation."""
        return self.format_data_path(self.LEGACY_GROUP_STATE_DIR_NAME)

    def _read_legacy_group_state_file(self, path: str) -> dict[str, list[int]]:
        """Implement the read legacy group state file operation."""
        if not os.path.isfile(path):
            return {"admins": [], "super_admins": []}
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {
            "admins": self.normalize_int_list(
                data.get(
                    "admins", [])), "super_admins": self.normalize_int_list(
                data.get(
                    "super_admins", [])), }

    def _merge_permission_item(
            self, next_item: dict[str, bool], raw_item: Any):
        """Implement the merge permission item operation."""
        if not isinstance(raw_item, dict):
            return
        for key, fallback in list(next_item.items()):
            next_item[key] = self._normalize_bool(raw_item.get(key), fallback)

    def _merge_permission_cfg(
        self,
        group_cfg: dict[str, Any],
        old_permissions: Any,
    ):
        """把权限配置合并进当前群配置。管理员状态只来自配置本身。"""
        permission_cfg = group_cfg[self.PERMISSION_SETTINGS_KEY]

        if isinstance(old_permissions, dict):
            permission_cfg["所有者QQ号"] = self.normalize_owner_qq(
                old_permissions.get("所有者QQ号", permission_cfg["所有者QQ号"])
            )
            permission_cfg["超级管理员QQ号"] = self.normalize_int_list(
                old_permissions.get("超级管理员QQ号", permission_cfg["超级管理员QQ号"])
            )
            permission_cfg["普通管理员QQ号"] = self.normalize_int_list(
                old_permissions.get("普通管理员QQ号", permission_cfg["普通管理员QQ号"])
            )
            feature_permissions = old_permissions.get("各功能权限设置", {})
            if isinstance(feature_permissions, dict):
                for key, next_item in permission_cfg["各功能权限设置"].items():
                    self._merge_permission_item(
                        next_item, feature_permissions.get(key))

        owner_qq = self.normalize_owner_qq(permission_cfg.get("所有者QQ号"))
        permission_cfg["所有者QQ号"] = owner_qq
        permission_cfg["超级管理员QQ号"] = self.normalize_int_list(
            permission_cfg.get("超级管理员QQ号", [])
        )
        permission_cfg["普通管理员QQ号"] = self.normalize_int_list(
            permission_cfg.get("普通管理员QQ号", [])
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
        command_cfg["帮助菜单非管理功能每页显示数量"] = self._normalize_positive_int(
            old_cmd.get(
                "帮助菜单非管理功能每页显示数量",
                command_cfg["帮助菜单非管理功能每页显示数量"],
            ),
            command_cfg["帮助菜单非管理功能每页显示数量"],
        )
        command_cfg["帮助菜单管理功能每页显示数量"] = self._normalize_positive_int(
            old_cmd.get(
                "帮助菜单管理功能每页显示数量",
                command_cfg["帮助菜单管理功能每页显示数量"],
            ),
            command_cfg["帮助菜单管理功能每页显示数量"],
        )
        command_cfg["命令触发词帮助菜单每页显示数量"] = self._normalize_positive_int(
            old_cmd.get(
                "命令触发词帮助菜单每页显示数量",
                command_cfg["命令触发词帮助菜单每页显示数量"],
            ),
            command_cfg["命令触发词帮助菜单每页显示数量"],
        )
        command_cfg["配置文件整文件修改模式每页显示数量"] = self._normalize_positive_int(
            old_cmd.get(
                "配置文件整文件修改模式每页显示数量",
                command_cfg["配置文件整文件修改模式每页显示数量"],
            ),
            command_cfg["配置文件整文件修改模式每页显示数量"],
        )
        command_cfg["配置中心唤醒词"] = self._clean_string_list(
            old_cmd.get("配置中心唤醒词", command_cfg["配置中心唤醒词"]),
            command_cfg["配置中心唤醒词"],
        )
        command_cfg["退出整个菜单触发词"] = self._clean_string_list(
            old_cmd.get("退出整个菜单触发词", command_cfg["退出整个菜单触发词"]),
            command_cfg["退出整个菜单触发词"],
        )
        command_cfg["返回上一级菜单触发词"] = self._clean_string_list(
            old_cmd.get("返回上一级菜单触发词", command_cfg["返回上一级菜单触发词"]),
            command_cfg["返回上一级菜单触发词"],
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
        command_cfg["任务系统菜单唤醒词"] = self._clean_string_list(
            old_cmd.get("任务系统菜单唤醒词", command_cfg["任务系统菜单唤醒词"]),
            command_cfg["任务系统菜单唤醒词"],
        )
        command_cfg["任务系统每页显示玩家数量"] = self._normalize_positive_int(
            old_cmd.get(
                "任务系统每页显示玩家数量",
                command_cfg["任务系统每页显示玩家数量"],
            ),
            command_cfg["任务系统每页显示玩家数量"],
        )
        command_cfg["任务系统每页显示任务数量"] = self._normalize_positive_int(
            old_cmd.get(
                "任务系统每页显示任务数量",
                command_cfg["任务系统每页显示任务数量"],
            ),
            command_cfg["任务系统每页显示任务数量"],
        )
        command_cfg["领地系统菜单唤醒词"] = self._clean_string_list(
            old_cmd.get("领地系统菜单唤醒词", command_cfg["领地系统菜单唤醒词"]),
            command_cfg["领地系统菜单唤醒词"],
        )
        command_cfg["领地系统每页显示领地数量"] = self._normalize_positive_int(
            old_cmd.get(
                "领地系统每页显示领地数量",
                command_cfg["领地系统每页显示领地数量"],
            ),
            command_cfg["领地系统每页显示领地数量"],
        )
        command_cfg["公会系统管理菜单唤醒词"] = self._clean_string_list(
            old_cmd.get(
                "公会系统管理菜单唤醒词",
                command_cfg["公会系统管理菜单唤醒词"],
            ),
            command_cfg["公会系统管理菜单唤醒词"],
        )
        command_cfg["QQ群封禁/解封菜单每页显示个数"] = self._normalize_positive_int(
            old_cmd.get(
                "QQ群封禁/解封菜单每页显示个数",
                command_cfg["QQ群封禁/解封菜单每页显示个数"],
            ),
            command_cfg["QQ群封禁/解封菜单每页显示个数"],
        )

    @staticmethod
    def _clean_string_list(
            raw: Any,
            fallback: list[str],
            allow_empty: bool = False):
        """清理字符串列表，失败时回退到默认值。"""
        if isinstance(raw, list):
            cleaned = [str(item) for item in raw if isinstance(item, str)]
            if cleaned or allow_empty:
                return cleaned
        return fallback

    @staticmethod
    def _normalize_positive_int(value: Any, fallback: int):
        """把不可信的数字输入规范成正整数。"""
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return fallback

    def _legacy_group_state_files(self) -> list[tuple[int, str]]:
        """Implement the legacy group state files operation."""
        legacy_dir = self._legacy_group_state_dir()
        try:
            names = os.listdir(legacy_dir)
        except OSError:
            return []
        files: list[tuple[int, str]] = []
        for name in names:
            stem, ext = os.path.splitext(name)
            if ext.lower() != ".json":
                continue
            try:
                group_id = int(stem)
            except ValueError:
                continue
            if group_id > 0:
                files.append((group_id, os.path.join(legacy_dir, name)))
        return files

    @staticmethod
    def _append_unique_ints(target: list[int], values: list[int]) -> bool:
        """Implement the append unique ints operation."""
        changed = False
        for value in values:
            if value not in target:
                target.append(value)
                changed = True
        return changed

    def migrate_legacy_group_admin_data(self, next_cfg: dict[str, Any]) -> int:
        """把旧插件数据目录里的群管理员状态合并进主配置。"""
        group_list = next_cfg.get("群聊设置")
        if not isinstance(group_list, list):
            group_list = []
            next_cfg["群聊设置"] = group_list

        groups_by_id: dict[int, dict[str, Any]] = {}
        for group_cfg in group_list:
            if not isinstance(group_cfg, dict):
                continue
            try:
                group_id = int(group_cfg.get("群号", 0))
            except (TypeError, ValueError):
                continue
            if group_id > 0:
                groups_by_id[group_id] = group_cfg

        migrated_files = 0
        for group_id, path in self._legacy_group_state_files():
            legacy_state = self._read_legacy_group_state_file(path)
            if not legacy_state["admins"] and not legacy_state["super_admins"]:
                continue
            group_cfg = groups_by_id.get(group_id)
            if group_cfg is None:
                group_cfg = self.group_default(group_id)
                group_list.append(group_cfg)
                groups_by_id[group_id] = group_cfg
            permission_cfg = group_cfg.setdefault(
                self.PERMISSION_SETTINGS_KEY,
                self.permission_default(),
            )
            if not isinstance(permission_cfg, dict):
                permission_cfg = self.permission_default()
                group_cfg[self.PERMISSION_SETTINGS_KEY] = permission_cfg

            owner_qq = self.normalize_owner_qq(permission_cfg.get("所有者QQ号"))
            super_admins = self.normalize_int_list(
                permission_cfg.get("超级管理员QQ号", [])
            )
            admins = self.normalize_int_list(
                permission_cfg.get("普通管理员QQ号", []))
            self._append_unique_ints(
                super_admins, legacy_state["super_admins"])
            self._append_unique_ints(admins, legacy_state["admins"])
            permission_cfg["所有者QQ号"] = owner_qq
            permission_cfg["超级管理员QQ号"] = super_admins
            permission_cfg["普通管理员QQ号"] = admins
            self.delete_migrated_legacy_group_admin_file(path)
            migrated_files += 1

        return migrated_files

    def delete_migrated_legacy_group_admin_file(self, path: str) -> bool:
        """迁移完单个旧群管理员数据文件后立即删除。"""
        try:
            os.remove(path)
        except FileNotFoundError:
            return True
        except OSError as err:
            if hasattr(self, "print_console_warn"):
                self.print_console_warn(f"旧版群管理员数据文件删除失败: {path}: {err}")
            return False
        return True

    def migrate_config(self, raw_cfg: Any):  # skipcq: PY-R1000
        """把整个插件配置迁到最新版本。

        历史上这个插件经历过“单群结构”和“多群结构”两个阶段，
        所以这里除了常规默认值补齐，还要兼容最早那一版只有 `消息转发设置` 的写法。
        """
        new_cfg = self.cfg_default()
        if not isinstance(raw_cfg, dict):
            self.migrate_legacy_group_admin_data(new_cfg)
            return new_cfg
        original_cfg = raw_cfg
        has_top_level_binding = isinstance(original_cfg.get("绑定设置"), dict)
        raw_cfg = self.merge_with_default(raw_cfg, new_cfg)

        dynamic_load_cfg = raw_cfg.get(self.DYNAMIC_LOAD_SETTINGS_KEY, {})
        if isinstance(dynamic_load_cfg, dict):
            dynamic_settings = new_cfg[self.DYNAMIC_LOAD_SETTINGS_KEY]
            dynamic_settings[self.DYNAMIC_LOAD_ENABLED_KEY] = bool(
                dynamic_load_cfg.get(
                    self.DYNAMIC_LOAD_ENABLED_KEY,
                    dynamic_settings[self.DYNAMIC_LOAD_ENABLED_KEY],
                )
            )
            default_interval = dynamic_settings[self.DYNAMIC_LOAD_INTERVAL_KEY]
            dynamic_settings[
                self.DYNAMIC_LOAD_INTERVAL_KEY
            ] = self._normalize_positive_int(
                dynamic_load_cfg.get(
                    self.DYNAMIC_LOAD_INTERVAL_KEY,
                    default_interval,
                ),
                default_interval,
            )

        cloud_cfg = raw_cfg.get("云链设置", {})
        if isinstance(cloud_cfg, dict):
            new_cfg["云链设置"]["地址"] = str(
                cloud_cfg.get("地址", new_cfg["云链设置"]["地址"])
            )
            validate_code = cloud_cfg.get("校验码", "")
            new_cfg["云链设置"]["校验码"] = (
                "" if validate_code is None else str(validate_code)
            )

        if has_top_level_binding:
            self._merge_binding_cfg(new_cfg["绑定设置"], original_cfg["绑定设置"])

        group_cfgs: list[dict[str, Any]] = []
        if isinstance(raw_cfg.get("群聊设置"), list):
            for raw_group in raw_cfg["群聊设置"]:
                if (
                    not has_top_level_binding
                    and isinstance(raw_group, dict)
                    and isinstance(raw_group.get("绑定设置"), dict)
                ):
                    self._merge_binding_cfg(new_cfg["绑定设置"], raw_group["绑定设置"])
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
            self._merge_permission_cfg(migrated_group, {})
            group_cfgs.append(migrated_group)

        if group_cfgs:
            dedup: dict[int, dict[str, Any]] = {}
            for group_cfg in group_cfgs:
                dedup[group_cfg["群号"]] = group_cfg
            new_cfg["群聊设置"] = list(dedup.values())

        self.migrate_legacy_group_admin_data(new_cfg)
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

    def persist_runtime_config(self):
        """把当前 Ultra 配置写回 ToolDelta 配置文件。"""
        cfg.check_auto(self.cfg_std(), self.cfg)
        cfg.upgrade_plugin_config(self.name, self.cfg, self.version)
        self.refresh_runtime_config_file_state()

    def runtime_config_path(self) -> str:
        """返回 ToolDelta 生成的本插件配置文件路径。"""
        return os.path.join(self.CONFIG_FILE_DIR, f"{self.name}.json")

    @staticmethod
    def runtime_config_file_state(path: str) -> tuple[int, int] | None:
        """返回配置文件状态，用于判断外部修改。"""
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def refresh_runtime_config_file_state(self) -> None:
        """记录当前配置文件状态，避免刚启动就重复热载一次。"""
        path = getattr(
            self,
            "_runtime_config_path",
            None) or self.runtime_config_path()
        self._runtime_config_path = path
        self._runtime_config_file_state = self.runtime_config_file_state(path)

    def is_runtime_config_reload_enabled(self) -> bool:
        """返回是否启用本插件配置文件动态载入。"""
        settings = getattr(
            self, "cfg", {}).get(
            self.DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return True
        return bool(settings.get(self.DYNAMIC_LOAD_ENABLED_KEY, True))

    def runtime_config_reload_interval(self) -> int:
        """返回动态载入检测间隔秒数。"""
        settings = getattr(
            self, "cfg", {}).get(
            self.DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return self.RUNTIME_CONFIG_RELOAD_INTERVAL
        return self._normalize_positive_int(
            settings.get(self.DYNAMIC_LOAD_INTERVAL_KEY,
                         self.RUNTIME_CONFIG_RELOAD_INTERVAL),
            self.RUNTIME_CONFIG_RELOAD_INTERVAL,
        )

    def apply_ultra_runtime_config(self, raw_config: Any) -> str:
        """把 Ultra 配置应用到当前运行时，无需重载插件。"""
        old_cloud_cfg = deepcopy(getattr(self, "cfg", {}).get("云链设置", {}))
        migrated = self.migrate_config(raw_config)
        cfg.check_auto(self.cfg_std(), migrated)
        self.cfg = migrated
        self.reload_group_configs()
        self.persist_runtime_config()
        if old_cloud_cfg != self.cfg.get("云链设置", {}):
            self.reload_websocket_connection()
            return "Ultra 配置已动态载入，云链连接正在按新配置重连"
        return "Ultra 配置已动态载入"

    def check_runtime_config_file_update(self) -> bool:
        """检查本插件配置文件是否被修改，变化时立即热应用。"""
        if not self.is_runtime_config_reload_enabled():
            return False

        path = getattr(
            self,
            "_runtime_config_path",
            None) or self.runtime_config_path()
        self._runtime_config_path = path
        current_state = self.runtime_config_file_state(path)
        if current_state is None or current_state == getattr(
            self,
            "_runtime_config_file_state",
            None,
        ):
            return False

        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                full_config = json.load(file)
            raw_config = self._extract_config_items(full_config)
            message = self.apply_ultra_runtime_config(raw_config)
            self.refresh_runtime_config_file_state()
            if hasattr(self, "print_console_success"):
                self.print_console_success(message)
            return True
        except Exception as err:
            self._runtime_config_file_state = current_state
            if hasattr(self, "print_console_error"):
                self.print_console_error(f"Ultra 配置热更新失败: {err}")
            return False

    @staticmethod
    def _extract_config_items(full_config: Any) -> Any:
        """Implement the extract config items operation."""
        if isinstance(
                full_config,
                dict) and isinstance(
                full_config.get("配置项"),
                dict):
            return full_config["配置项"]
        return full_config

    @property
    def linked_group(self) -> int | None:
        """返回兼容旧插件调用时使用的默认群号。"""
        # 给还按“单群互通”接口调用的旧插件留一个兼容入口。
        return self.group_order[0] if self.group_order else None

    def _permission_cfg_for_group(
            self, group_id: int) -> dict[str, Any] | None:
        """Implement the permission cfg for group operation."""
        group_cfg = getattr(self, "group_cfgs", {}).get(group_id)
        if not isinstance(group_cfg, dict):
            return None
        permission_cfg = group_cfg.get(self.PERMISSION_SETTINGS_KEY)
        return permission_cfg if isinstance(permission_cfg, dict) else None

    def read_group_state(self, group_id: int):
        """从主配置读取单个群的管理员状态。"""
        permission_cfg = self._permission_cfg_for_group(group_id)
        if permission_cfg is None:
            return {"admins": [], "super_admins": []}
        return {
            "admins": self.normalize_int_list(
                permission_cfg.get(
                    "普通管理员QQ号", [])), "super_admins": self.normalize_int_list(
                permission_cfg.get(
                    "超级管理员QQ号", [])), }

    def get_group_owner_qq(self, group_id: int) -> int | None:
        """读取群配置中的所有者 QQ。"""
        permission_cfg = self._permission_cfg_for_group(group_id)
        if permission_cfg is None:
            return None
        owner_qq = self.normalize_owner_qq(permission_cfg.get("所有者QQ号"))
        if owner_qq == self.OWNER_QQ_UNSET:
            return None
        return owner_qq

    def save_group_state(self, group_id: int, state: dict[str, list[int]]):
        """把群权限状态保存到主配置文件。"""
        permission_cfg = self._permission_cfg_for_group(group_id)
        if permission_cfg is None:
            return
        normalized = {
            "admins": self.normalize_int_list(
                state.get(
                    "admins", [])), "super_admins": self.normalize_int_list(
                state.get(
                    "super_admins", [])), }
        permission_cfg["普通管理员QQ号"] = normalized["admins"]
        permission_cfg["超级管理员QQ号"] = normalized["super_admins"]
        self.persist_runtime_config()

    def ensure_group_state(self, group_id: int):
        """确保群权限配置结构可读，并移除重复/非法管理员项。"""
        permission_cfg = self._permission_cfg_for_group(group_id)
        if permission_cfg is None:
            return
        state = self.read_group_state(group_id)
        permission_cfg["超级管理员QQ号"] = state["super_admins"]
        permission_cfg["普通管理员QQ号"] = state["admins"]

    def is_group_owner(self, group_id: int, qqid: int):
        """判断某个 QQ 是否是指定群的所有者。"""
        return self.get_group_owner_qq(group_id) == qqid

    def is_group_super_admin(self, group_id: int, qqid: int):
        """判断某个 QQ 是否拥有超级管理员级权限。"""
        if self.is_group_owner(group_id, qqid):
            return True
        return qqid in self.read_group_state(group_id)["super_admins"]

    def is_group_admin(self, group_id: int, qqid: int):
        """判断某个 QQ 是否拥有群内管理权限。

        所有者、超级管理员和普通管理员都可以执行普通管理功能。
        """
        if self.is_group_owner(group_id, qqid):
            return True
        state = self.read_group_state(group_id)
        return qqid in state["super_admins"] or qqid in state["admins"]

    def has_group_permission(
            self,
            group_id: int,
            qqid: int,
            permission_name: str) -> bool:
        """按群配置中的“各功能权限设置”判断某个 QQ 是否可用指定功能。"""
        if self.is_group_owner(group_id, qqid):
            return True
        permission_cfg = self._permission_cfg_for_group(group_id)
        if permission_cfg is None:
            return False
        feature_permissions = permission_cfg.get("各功能权限设置", {})
        if not isinstance(feature_permissions, dict):
            return False
        item = feature_permissions.get(permission_name)
        if not isinstance(item, dict):
            return False
        state = self.read_group_state(group_id)
        if qqid in state["super_admins"]:
            return bool(item.get("是否允许超级管理员使用", False))
        if qqid in state["admins"]:
            return bool(item.get("是否允许普通管理员使用", False))
        return bool(item.get("是否允许普通成员使用", False))

    def is_qq_op(self, qqid: int, group_id: int | None = None):
        """兼容旧命名，判断某个 QQ 是否拥有管理员权限。"""
        if group_id is not None:
            return self.is_group_admin(group_id, qqid)
        return any(self.is_group_admin(gid, qqid) for gid in self.group_order)

    def add_group_role(self, group_id: int, qqid: int, is_super: bool):
        """给群成员授予管理员或超级管理员身份。"""
        if self.is_group_owner(group_id, qqid):
            return False, "该 QQ 是本群所有者，已拥有最高权限"
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
        if self.is_group_owner(group_id, qqid):
            return False, "不能在管理员菜单中移除本群所有者"
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

    @staticmethod
    def _api_int_value(value: Any):
        """Implement the api int value operation."""
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def api_get_linked_groups(self) -> list[int]:
        """Return configured linked QQ group IDs in runtime order."""
        return list(self.group_order)

    def api_get_default_group(self) -> int | None:
        """Return the first configured group ID for old single-group callers."""
        return self.linked_group

    def api_is_group_configured(self, group_id: int | str) -> bool:
        """Return whether a QQ group is configured in Ultra."""
        gid = self._api_int_value(group_id)
        return gid in self.group_cfgs if gid is not None else False

    def api_get_group_config(self, group_id: int |
                             str) -> dict[str, Any] | None:
        """Return a copy of one group's runtime config."""
        gid = self._api_int_value(group_id)
        if gid is None or gid not in self.group_cfgs:
            return None
        return deepcopy(self.group_cfgs[gid])

    def api_get_group_state(self, group_id: int |
                            str) -> dict[str, list[int]] | None:
        """Return a copy of one group's admin state."""
        gid = self._api_int_value(group_id)
        if gid is None or gid not in self.group_cfgs:
            return None
        state = self.read_group_state(gid)
        owner_qq = self.get_group_owner_qq(gid)
        return {
            "admins": list(state["admins"]),
            "super_admins": list(state["super_admins"]),
            "owner": [] if owner_qq is None else [owner_qq],
        }

    def api_get_group_admins(
        self,
        group_id: int | str,
        include_super: bool = True,
    ) -> list[int]:
        """Return normal group admins, optionally including super admins."""
        state = self.api_get_group_state(group_id)
        if state is None:
            return []
        admins = list(state["admins"])
        if include_super:
            for qqid in state["super_admins"]:
                if qqid not in admins:
                    admins.append(qqid)
            for qqid in state.get("owner", []):
                if qqid not in admins:
                    admins.append(qqid)
        return admins

    def api_get_group_super_admins(self, group_id: int | str) -> list[int]:
        """Return super admins for one configured group."""
        state = self.api_get_group_state(group_id)
        return [] if state is None else list(state["super_admins"])

    def api_is_group_admin(self, group_id: int | str, qqid: int | str) -> bool:
        """Return whether a QQ number has admin permission in a group."""
        gid = self._api_int_value(group_id)
        qid = self._api_int_value(qqid)
        if gid is None or qid is None or gid not in self.group_cfgs:
            return False
        return self.is_group_admin(gid, qid)

    def api_is_group_super_admin(
            self,
            group_id: int | str,
            qqid: int | str) -> bool:
        """Return whether a QQ number is a super admin in a group."""
        gid = self._api_int_value(group_id)
        qid = self._api_int_value(qqid)
        if gid is None or qid is None or gid not in self.group_cfgs:
            return False
        return self.is_group_super_admin(gid, qid)

    def api_get_group_owner(self, group_id: int | str) -> int | None:
        """Return the configured owner QQ for one group."""
        gid = self._api_int_value(group_id)
        if gid is None or gid not in self.group_cfgs:
            return None
        return self.get_group_owner_qq(gid)

    def api_is_group_owner(self, group_id: int | str, qqid: int | str) -> bool:
        """Return whether a QQ number is the configured owner in a group."""
        gid = self._api_int_value(group_id)
        qid = self._api_int_value(qqid)
        if gid is None or qid is None or gid not in self.group_cfgs:
            return False
        return self.is_group_owner(gid, qid)

    def api_add_group_admin(
        self,
        group_id: int | str,
        qqid: int | str,
        is_super: bool = False,
    ) -> tuple[bool, str]:
        """Grant normal-admin or super-admin permission to a QQ number."""
        gid = self._api_int_value(group_id)
        qid = self._api_int_value(qqid)
        if gid is None or gid not in self.group_cfgs:
            return False, "群号无效或未配置"
        if qid is None or qid <= 0:
            return False, "QQ号无效"
        return self.add_group_role(gid, qid, bool(is_super))

    def api_remove_group_admin(
        self,
        group_id: int | str,
        qqid: int | str,
        is_super: bool = False,
    ) -> tuple[bool, str]:
        """Remove normal-admin or super-admin permission from a QQ number."""
        gid = self._api_int_value(group_id)
        qid = self._api_int_value(qqid)
        if gid is None or gid not in self.group_cfgs:
            return False, "群号无效或未配置"
        if qid is None or qid <= 0:
            return False, "QQ号无效"
        return self.remove_group_role(gid, qid, bool(is_super))

    def api_get_group_triggers(
            self, group_id: int | str) -> dict[str, Any] | None:
        """Return normalized trigger words and menu controls for one group."""
        gid = self._api_int_value(group_id)
        if gid is None or gid not in self.group_cfgs:
            return None
        triggers = {
            "help": self.get_group_help_triggers(gid),
            "admin_menu": self.get_group_admin_menu_triggers(gid),
            "player_list": self.get_group_player_list_triggers(gid),
            "inventory_menu": self.get_group_inventory_menu_triggers(gid),
            "menu_exit": self.get_group_menu_exit_triggers(gid),
            "menu_back": self.get_group_menu_back_triggers(gid),
            "command_prefix": self.get_group_cmd_prefix(gid),
            "orion_ban": self.get_group_orion_ban_triggers(gid),
            "orion_unban": self.get_group_orion_unban_triggers(gid),
            "checker_menu": self.get_group_checker_menu_triggers(gid),
            "task_menu": self.get_group_task_menu_triggers(gid),
            "land_menu": self.get_group_land_menu_triggers(gid),
            "guild_menu": self.get_group_guild_menu_triggers(gid),
        }
        if hasattr(self, "get_group_binding_triggers"):
            triggers["binding"] = self.get_group_binding_triggers(gid)
        return triggers

    def api_get_registered_triggers(self) -> list[dict[str, Any]]:
        """Return external QQ triggers registered through add_trigger(...)."""
        return [
            {
                "triggers": list(trigger.triggers),
                "argument_hint": trigger.argument_hint,
                "usage": trigger.usage,
                "op_only": bool(trigger.op_only),
                "accept_group": bool(trigger.accept_group),
            }
            for trigger in self.triggers
        ]

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

    def get_group_help_non_admin_items_per_page(self, group_id: int):
        """读取帮助菜单非管理功能每页条数。"""
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["帮助菜单非管理功能每页显示数量"]),
                )
            except (KeyError, TypeError, ValueError):
                return 10
        return 10

    def get_group_help_admin_items_per_page(self, group_id: int):
        """读取帮助菜单管理功能每页条数。"""
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["帮助菜单管理功能每页显示数量"]),
                )
            except (KeyError, TypeError, ValueError):
                return 10
        return 10

    def get_group_command_help_items_per_page(self, group_id: int):
        """读取命令触发词帮助菜单每页条数。"""
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["命令触发词帮助菜单每页显示数量"]),
                )
            except (KeyError, TypeError, ValueError):
                return 10
        return 10

    def get_group_config_file_items_per_page(
            self, group_id: int | None = None):
        """读取配置文件整文件修改模式选择菜单每页条数。"""
        group_cfg = self.group_cfgs.get(
            group_id) if group_id is not None else None
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["配置文件整文件修改模式每页显示数量"]),
                )
            except (KeyError, TypeError, ValueError):
                return 10
        return 10

    def get_group_task_player_items_per_page(self, group_id: int):
        """读取任务系统选择玩家菜单每页条数。"""
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["任务系统每页显示玩家数量"]),
                )
            except (KeyError, TypeError, ValueError):
                return self.get_group_inventory_items_per_page(group_id)
        return 10

    def get_group_task_items_per_page(self, group_id: int):
        """读取任务系统选择任务菜单每页条数。"""
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["任务系统每页显示任务数量"]),
                )
            except (KeyError, TypeError, ValueError):
                return self.get_group_inventory_items_per_page(group_id)
        return 10

    def get_group_land_items_per_page(self, group_id: int):
        """读取领地系统云链联动版菜单每页条数。"""
        group_cfg = self.group_cfgs.get(group_id)
        if group_cfg is not None:
            try:
                return max(
                    1,
                    int(group_cfg["指令设置"]["领地系统每页显示领地数量"]),
                )
            except (KeyError, TypeError, ValueError):
                return self.get_group_inventory_items_per_page(group_id)
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

    def get_group_menu_exit_triggers(self, group_id: int | None = None):
        """读取菜单内“退出整个菜单”的触发词。"""
        if group_id is not None and group_id in self.group_cfgs:
            raw = self.group_cfgs[group_id]["指令设置"].get(
                "退出整个菜单触发词",
                self.MENU_EXIT_TRIGGERS_DEFAULT,
            )
            return self.normalize_string_triggers(
                raw, self.MENU_EXIT_TRIGGERS_DEFAULT)
        return list(self.MENU_EXIT_TRIGGERS_DEFAULT)

    def get_group_menu_back_triggers(self, group_id: int | None = None):
        """读取菜单内“返回上一级”的触发词。"""
        if group_id is not None and group_id in self.group_cfgs:
            raw = self.group_cfgs[group_id]["指令设置"].get(
                "返回上一级菜单触发词",
                self.MENU_BACK_TRIGGERS_DEFAULT,
            )
            return self.normalize_string_triggers(
                raw, self.MENU_BACK_TRIGGERS_DEFAULT)
        return list(self.MENU_BACK_TRIGGERS_DEFAULT)

    def is_menu_exit_input(self, user_input: str, group_id: int | None = None):
        """判断一条输入是否要求退出整个交互菜单。"""
        text = str(user_input).strip()
        return any(
            text.lower() == trigger.lower()
            for trigger in self.get_group_menu_exit_triggers(group_id)
        )

    def is_menu_back_input(self, user_input: str, group_id: int | None = None):
        """判断一条输入是否要求返回上一级菜单。"""
        text = str(user_input).strip()
        return any(
            text.lower() == trigger.lower()
            for trigger in self.get_group_menu_back_triggers(group_id)
        )

    def menu_exit_hint(self, group_id: int | None = None, action: str = "退出"):
        """Implement the menu exit hint operation."""
        return f"输入 {' / '.join(self.get_group_menu_exit_triggers(group_id))} {action}"

    def menu_back_hint(
            self,
            group_id: int | None = None,
            action: str = "返回上级菜单"):
        """Implement the menu back hint operation."""
        return f"输入 {' / '.join(self.get_group_menu_back_triggers(group_id))} {action}"

    def normalize_menu_control_hints(
        self,
        hints: list[str],
        group_id: int | None = None,
    ) -> list[str]:
        """把旧菜单里的硬编码退出/返回提示替换成当前配置中的触发词。"""
        normalized: list[str] = []
        for hint in hints:
            if hint == "输入 . 退出":
                normalized.append(self.menu_exit_hint(group_id))
            elif hint == "输入 . 取消":
                normalized.append(self.menu_back_hint(group_id, "取消"))
            elif hint == "输入 0 返回上级":
                normalized.append(self.menu_back_hint(group_id, "返回上级"))
            elif hint == "输入 0 返回上级菜单":
                normalized.append(self.menu_back_hint(group_id))
            elif hint == "输入 q 退出菜单":
                normalized.append(self.menu_exit_hint(group_id, "退出菜单"))
            else:
                normalized.append(hint)
        return normalized

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
        return self.normalize_string_triggers(
            raw, ["orban", "orion ban", "猎户封禁"])

    def get_group_orion_unban_triggers(self, group_id: int):
        """读取某个群的 Orion 解封触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get(
            "QQ群解封唤醒词",
            ["orunban", "orion unban", "猎户解封"],
        )
        return self.normalize_string_triggers(
            raw, ["orunban", "orion unban", "猎户解封"])

    def get_group_checker_menu_triggers(self, group_id: int):
        """读取某个群的白名单联动菜单触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get(
            "QQ群白名单&管理员检测唤醒词",
            ["白名单&管理员检测", "检测管理"],
        )
        return self.normalize_string_triggers(raw, ["白名单&管理员检测", "检测管理"])

    def get_group_task_menu_triggers(self, group_id: int):
        """读取某个群的任务系统菜单触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("任务系统菜单唤醒词", ["任务系统"])
        return self.normalize_string_triggers(raw, ["任务系统"])

    def get_group_land_menu_triggers(self, group_id: int):
        """读取某个群的领地系统云链联动版菜单触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("领地系统菜单唤醒词", ["领地系统云链联动版", "领地系统", "领地管理"])
        return self.normalize_string_triggers(
            raw, ["领地系统云链联动版", "领地系统", "领地管理"])

    def get_group_guild_menu_triggers(self, group_id: int):
        """读取某个群的公会系统管理菜单触发词。"""
        group_cfg = self.group_cfgs[group_id]
        raw = group_cfg["指令设置"].get("公会系统管理菜单唤醒词", ["公会系统"])
        return self.normalize_string_triggers(raw, ["公会系统"])

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
            QQMsgTrigger(
                triggers,
                argument_hint,
                usage,
                func,
                args_pd,
                op_only))

    def set_manual_launch(self, port: int):
        """切换到“本地启动器负责拉起云链”的模式。"""
        self._manual_launch = True
        self._manual_launch_port = port

    def manual_launch(self):
        """给本地启动器调用的显式连接入口。"""
        self.connect_to_websocket()

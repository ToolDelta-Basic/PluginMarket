"""Public QQ and plugin API operations for guild cloud interop."""

import copy
import json
import os
import re
import shutil
import time
import uuid
from typing import Any, Optional

from tooldelta import fmts

from guild_cloud_interop.config import Config
from guild_cloud_interop.models import (
    GuildBase,
    GuildData,
    GuildMember,
    GuildRank,
    GuildStats,
    GuildTask,
    VaultItem,
)
from guild_cloud_interop.validators import InputValidator


COLOR_CODE_RE = re.compile(r"§.")


def _plain(text: object) -> str:
    return COLOR_CODE_RE.sub("", str(text))


def _now() -> float:
    return time.time()


def _actor(actor: str | None) -> str:
    text = str(actor or "").strip()
    return text or "QQ管理"


def _to_int(value: object, field_name: str, minimum: int |
            None = None) -> tuple[bool, str, int]:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return False, f"{field_name}必须是整数", 0
    if minimum is not None and parsed < minimum:
        return False, f"{field_name}不能小于 {minimum}", 0
    return True, "", parsed


def _to_float(value: object, field_name: str) -> tuple[bool, str, float]:
    try:
        return True, "", float(str(value).strip())
    except (TypeError, ValueError):
        return False, f"{field_name}必须是数字", 0.0


def _ensure_settings(guild: GuildData) -> dict[str, Any]:
    if not isinstance(guild.settings, dict):
        guild.settings = {}
    return guild.settings


def _rebuild_player_cache(self, guilds: dict[str, GuildData]) -> None:
    self.guild_manager.rebuild_player_cache(guilds)


def _save_guilds(self,
                 guilds: dict[str,
                              GuildData],
                 force: bool = True) -> bool:
    _rebuild_player_cache(self, guilds)
    ok = self.guild_manager.save_guilds(guilds, force=force)
    if ok:
        self.guild_manager.load_guilds(force_reload=True)
    return ok


def _load_guilds(self) -> dict[str, GuildData]:
    return self.guild_manager.load_guilds(force_reload=True)


def _find_guild(
    self,
    guild_query: object,
    guilds: Optional[dict[str, GuildData]] = None,
) -> tuple[Optional[GuildData], str]:
    query = str(guild_query or "").strip()
    if not query:
        return None, "公会不能为空"

    guild_map = guilds if guilds is not None else _load_guilds(self)
    if query in guild_map:
        return guild_map[query], ""

    exact = [guild for guild in guild_map.values() if guild.name == query]
    if len(exact) == 1:
        return exact[0], ""
    if len(exact) > 1:
        return None, f"存在多个同名公会：{query}，请使用公会ID"

    query_lower = query.casefold()
    fuzzy = [
        guild
        for guild in guild_map.values()
        if query_lower in guild.name.casefold() or query_lower in guild.guild_id.casefold()
    ]
    if len(fuzzy) == 1:
        return fuzzy[0], ""
    if len(fuzzy) > 1:
        names = "、".join(guild.name for guild in fuzzy[:5])
        if len(fuzzy) > 5:
            names += "……"
        return None, f"匹配到多个公会：{names}"
    return None, f"公会不存在：{query}"


def _find_player_guild(
    self,
    player_name: object,
    guilds: Optional[dict[str, GuildData]] = None,
) -> tuple[Optional[GuildData], str]:
    name = str(player_name or "").strip()
    if not name:
        return None, "玩家名不能为空"

    guild_map = guilds if guilds is not None else _load_guilds(self)
    for guild in guild_map.values():
        if guild.get_member(name):
            return guild, ""
    return None, f"玩家 {name} 不在任何公会"


def _find_player_context(
    self,
    player_name: object,
    guilds: Optional[dict[str, GuildData]] = None,
) -> tuple[str, Optional[GuildData], Optional[GuildMember], str]:
    name = str(player_name or "").strip()
    if not name:
        return "", None, None, "玩家名不能为空"
    guild, err = _find_player_guild(self, name, guilds)
    if guild is None:
        return name, None, None, err
    member = guild.get_member(name)
    if member is None:
        return name, guild, None, "成员数据异常"
    return name, guild, member, ""


def _find_task(guild: GuildData,
               task_query: object) -> tuple[Optional[GuildTask], str]:
    query = str(task_query or "").strip()
    if not query:
        return None, "任务不能为空"
    for task in guild.tasks:
        if query in (task.task_id, task.name):
            return task, ""
    query_lower = query.casefold()
    matched = [
        task
        for task in guild.tasks
        if query_lower in task.task_id.casefold() or query_lower in task.name.casefold()
    ]
    if len(matched) == 1:
        return matched[0], ""
    if len(matched) > 1:
        names = "、".join(
            f"{task.name}({task.task_id})" for task in matched[:5])
        return None, f"匹配到多个任务：{names}"
    return None, f"任务不存在：{query}"


def _member_summary(member: GuildMember) -> dict[str, Any]:
    return {
        "name": member.name,
        "rank": member.rank.value,
        "rank_name": _plain(member.rank.display_name),
        "join_time": member.join_time,
        "contribution": member.contribution,
        "last_online": member.last_online,
    }


def _base_summary(base: GuildBase | None) -> dict[str, Any] | None:
    if base is None:
        return None
    return {
        "dimension": base.dimension,
        "x": base.x,
        "y": base.y,
        "z": base.z,
    }


def _vault_item_summary(item: VaultItem, index: int |
                        None = None) -> dict[str, Any]:
    data = item.to_dict()
    if index is not None:
        data["index"] = index
    return data


def _task_summary(task: GuildTask) -> dict[str, Any]:
    return task.to_dict()


def _guild_summary(guild: GuildData) -> dict[str, Any]:
    settings = _ensure_settings(guild)
    return {
        "guild_id": guild.guild_id,
        "name": guild.name,
        "owner": guild.owner,
        "level": guild.level,
        "exp": guild.exp,
        "create_time": guild.create_time,
        "member_count": len(guild.members),
        "max_members": Config.MAX_GUILD_MEMBERS,
        "base": _base_summary(guild.base),
        "vault_count": len(guild.vault_items),
        "vault_capacity": Config.VAULT_INITIAL_SLOTS,
        "announcement": guild.announcement,
        "purchased_effects": dict(guild.purchased_effects),
        "funds": int(settings.get("funds", 0) or 0),
        "frozen": bool(settings.get("frozen", False)),
        "frozen_reason": str(settings.get("frozen_reason", "")),
        "base_locked": bool(settings.get("base_locked", False)),
        "active_tasks": len([task for task in guild.tasks if not task.completed]),
        "completed_tasks": len([task for task in guild.tasks if task.completed]),
        "total_contribution": guild.stats.total_contribution,
    }


def _apply_level_ups(guild: GuildData) -> list[int]:
    level_ups: list[int] = []
    next_level = guild.level + 1
    required = Config.GUILD_LEVEL_EXP.get(next_level)
    while required and guild.exp >= required:
        guild.exp -= required
        guild.level = next_level
        level_ups.append(next_level)
        guild.add_log(f"公会升级到 {next_level} 级")
        next_level = guild.level + 1
        required = Config.GUILD_LEVEL_EXP.get(next_level)
    return level_ups


def _activity_multiplier(self, key: str) -> float:
    event = getattr(self, "_guild_runtime_events", {}).get(key)
    if not isinstance(event, dict):
        return 1.0
    expires_at = float(event.get("expires_at", 0) or 0)
    if 0 < expires_at <= _now():
        getattr(self, "_guild_runtime_events", {}).pop(key, None)
        return 1.0
    try:
        multiplier = float(event.get("multiplier", 1.0))
    except (TypeError, ValueError):
        return 1.0
    return max(1.0, multiplier)


def guild_get_activity_multiplier(self, key: str) -> float:
    return _activity_multiplier(self, key)


def guild_apply_reward_multipliers(
    self,
    exp: int | float = 0,
    contribution: int | float = 0,
) -> tuple[int, int]:
    exp_out = int(float(exp) * _activity_multiplier(self, "exp"))
    contribution_out = int(float(contribution) *
                           _activity_multiplier(self, "contribution"))
    return max(0, exp_out), max(0, contribution_out)


def guild_is_frozen(self, guild: GuildData | None) -> bool:
    if guild is None:
        return False
    settings = getattr(guild, "settings", {})
    return isinstance(settings, dict) and bool(settings.get("frozen", False))


def guild_frozen_message(self, guild: GuildData | None) -> str:
    if guild is None:
        return "公会已冻结"
    settings = getattr(guild, "settings", {})
    reason = ""
    if isinstance(settings, dict):
        reason = str(settings.get("frozen_reason", "") or "").strip()
    suffix = f"：{reason}" if reason else ""
    return f"公会 {guild.name} 已被冻结{suffix}"


def show_guild_frozen(self, player, guild: GuildData | None) -> None:
    player.show(f"§l§a公会 §d>> §c{self.guild_frozen_message(guild)}")


def api_list_guilds(self) -> tuple[bool, str, list[dict[str, Any]]]:
    guilds = _load_guilds(self)
    data = [_guild_summary(guild) for guild in guilds.values()]
    data.sort(key=lambda item: (-int(item["level"]), -
              int(item["member_count"]), item["name"]))
    return True, f"共 {len(data)} 个公会", data


def api_get_guild(
        self, guild_query: str) -> tuple[bool, str, Optional[dict[str, Any]]]:
    guild, err = _find_guild(self, guild_query)
    if guild is None:
        return False, err, None
    data = _guild_summary(guild)
    data["members"] = [_member_summary(member) for member in guild.members]
    data["tasks"] = [_task_summary(task) for task in guild.tasks]
    return True, "查询成功", data


def api_get_player_record(
        self, player_name: str) -> tuple[bool, str, Optional[dict[str, Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_player_guild(self, player_name, guilds)
    if guild is None:
        return False, err, None
    member = guild.get_member(str(player_name).strip())
    if member is None:
        return False, "成员数据异常", None
    records = [
        log.to_dict()
        for log in guild.audit_logs
        if member.name in (log.actor, log.target)
    ]
    vault_records = [
        log.to_dict()
        for log in guild.vault_trade_logs
        if member.name in (log.actor, log.seller, log.buyer)
    ]
    return True, "查询成功", {
        "guild": _guild_summary(guild),
        "member": _member_summary(member),
        "audit_logs": records[-50:],
        "vault_trade_logs": vault_records[-50:],
    }


def api_get_player_guild_menu_state(
        self, player_name: str) -> tuple[bool, str, dict[str, Any]]:
    """Return safe QQ-side guild menu state for one player identity."""
    guilds = _load_guilds(self)
    name, guild, member, err = _find_player_context(self, player_name, guilds)
    if not name:
        return False, err, {}
    if guild is None:
        return True, f"玩家 {name} 暂未加入公会", {
            "player_name": name,
            "in_guild": False,
            "guild": None,
            "member": None,
            "permissions": [],
            "is_owner": False,
            "is_frozen": False,
        }
    if member is None:
        return False, err, {}
    return True, "查询成功", {
        "player_name": name,
        "in_guild": True,
        "guild": _guild_summary(guild),
        "member": _member_summary(member),
        "permissions": guild.get_member_permissions(name),
        "is_owner": member.rank == GuildRank.OWNER,
        "is_frozen": bool(_ensure_settings(guild).get("frozen", False)),
    }


def api_get_own_guild_logs(self,
                           player_name: str,
                           limit: int = 20) -> tuple[bool,
                                                     str,
                                                     Optional[dict[str,
                                                                   Any]]]:
    """Return logs for the guild that the player belongs to."""
    ok, _err, parsed_limit = _to_int(limit, "日志数量", 1)
    if not ok:
        parsed_limit = 20
    guilds = _load_guilds(self)
    name, guild, member, err = _find_player_context(self, player_name, guilds)
    if guild is None or member is None:
        return False, err, None
    data: dict[str, Any] = {"logs": guild.logs[-parsed_limit:]}
    if guild.has_permission(name, "audit_log"):
        data["audit_logs"] = [log.to_dict()
                              for log in guild.audit_logs[-parsed_limit:]]
        data["vault_trade_logs"] = [log.to_dict()
                                    for log in guild.vault_trade_logs[-parsed_limit:]]
    else:
        data["audit_logs"] = []
        data["vault_trade_logs"] = []
    return True, "查询成功", data


def api_get_own_guild_vault(
        self, player_name: str) -> tuple[bool, str, Optional[list[dict[str, Any]]]]:
    """Return the current player's guild vault after normal guild permission checks."""
    guilds = _load_guilds(self)
    name, guild, member, err = _find_player_context(self, player_name, guilds)
    if guild is None or member is None:
        return False, err, None
    if not guild.has_permission(name, "vault"):
        return False, "你没有使用仓库权限", None
    data = [_vault_item_summary(item, index)
            for index, item in enumerate(guild.vault_items, start=1)]
    return True, f"{guild.name} 仓库共有 {len(data)} 件上架物品", data


def api_get_own_guild_tasks(
        self, player_name: str) -> tuple[bool, str, Optional[list[dict[str, Any]]]]:
    """Return the task list for the guild that the player belongs to."""
    guilds = _load_guilds(self)
    _name, guild, member, err = _find_player_context(self, player_name, guilds)
    if guild is None or member is None:
        return False, err, None
    return True, f"{guild.name} 共有 {len(guild.tasks)} 个任务", [
        _task_summary(task) for task in guild.tasks]


def api_request_join_guild_as_player(
    self,
    player_name: str,
    guild_query: str,
    reason: str = "",
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Submit a normal player join request for a guild."""
    name = str(player_name or "").strip()
    if not name:
        return False, "玩家名不能为空", None
    guilds = _load_guilds(self)
    current_guild, _ = _find_player_guild(self, name, guilds)
    if current_guild is not None:
        return False, f"你已经加入了公会 {
            current_guild.name}", _guild_summary(current_guild)
    target_guild, err = _find_guild(self, guild_query, guilds)
    if target_guild is None:
        return False, err, None
    if _ensure_settings(target_guild).get("frozen", False):
        return False, f"公会 {
            target_guild.name} 已被冻结，暂不能提交申请", _guild_summary(target_guild)
    if len(target_guild.members) >= Config.MAX_GUILD_MEMBERS:
        return False, "该公会已满员", _guild_summary(target_guild)
    if not target_guild.add_join_request(name, reason):
        return False, "申请提交失败，可能已有待处理申请或队列已满", _guild_summary(target_guild)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    notify = getattr(self, "_notify_join_request_admins", None)
    if callable(notify):
        notify(target_guild, name)
    return True, f"申请已提交至 {
        target_guild.name} 的申请队列", _guild_summary(target_guild)


def api_leave_guild_as_player(
        self, player_name: str) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Leave the current guild as a normal member."""
    guilds = _load_guilds(self)
    name, guild, member, err = _find_player_context(self, player_name, guilds)
    if guild is None or member is None:
        return False, err, None
    if member.rank == GuildRank.OWNER:
        return False, "会长不能退出公会，只能解散公会", _guild_summary(guild)
    guild.members = [item for item in guild.members if item.name != name]
    guild.add_log(f"{name} 退出公会")
    guild.add_audit_log("member_leave", name, target=name)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已退出公会 {guild.name}", _guild_summary(guild)


def api_disband_owned_guild_as_player(
        self, player_name: str) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Disband the player's own guild, only when the player is the owner."""
    guilds = _load_guilds(self)
    _, guild, member, err = _find_player_context(self, player_name, guilds)
    if guild is None or member is None:
        return False, err, None
    if member.rank != GuildRank.OWNER:
        return False, "你不是当前公会的会长", _guild_summary(guild)
    summary = _guild_summary(guild)
    guild_name = guild.name
    online_members = [
        item.name
        for item in guild.members
        if item.name in getattr(self.game_ctrl, "allplayers", [])
    ]
    del guilds[guild.guild_id]
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    for member_name in online_members:
        self.game_ctrl.sendcmd(
            f'/tellraw {member_name} {{"rawtext":[{{"text":"§l§a公会 §d>> §r公会 §e{guild_name}§r 已被解散"}}]}}'
        )
    return True, f"已解散公会 {guild_name}", summary


def api_set_announcement_as_player(
    self,
    player_name: str,
    announcement: str,
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Set the current guild announcement through normal guild permission checks."""
    text = str(announcement or "").strip()
    is_valid, error_msg = InputValidator.validate_announcement(text)
    if not is_valid:
        return False, error_msg, None
    guilds = _load_guilds(self)
    name, guild, member, err = _find_player_context(self, player_name, guilds)
    if guild is None or member is None:
        return False, err, None
    if _ensure_settings(guild).get("frozen", False):
        return False, guild_frozen_message(self, guild), _guild_summary(guild)
    if not guild.has_permission(name, "announce"):
        return False, "你没有设置公会公告权限", _guild_summary(guild)
    guild.announcement = text
    guild.add_log(f"{name} 更新了公告")
    guild.add_audit_log("announcement_set", name, detail=text)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    message = "§l§a公会 §d>> §r公告已更新，输入 .公会 公告 查看"
    for member_item in guild.members:
        if member_item.name in getattr(self.game_ctrl, "allplayers", []):
            self.game_ctrl.sendcmd(
                f'/tellraw {member_item.name} {{"rawtext":[{{"text":"{message}"}}]}}'
            )
    return True, "公告已更新", _guild_summary(guild)


def api_join_guild_task_as_player(
    self,
    player_name: str,
    task_query: str,
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Join an active guild task as the current player."""
    guilds = _load_guilds(self)
    name, guild, member, err = _find_player_context(self, player_name, guilds)
    if guild is None or member is None:
        return False, err, None
    if _ensure_settings(guild).get("frozen", False):
        return False, guild_frozen_message(self, guild), None
    task, err = _find_task(guild, task_query)
    if task is None:
        return False, err, None
    if task.completed:
        return False, "该任务已完成", _task_summary(task)
    if name in task.participants:
        return True, f"你已经参与了任务：{task.name}", _task_summary(task)
    task.participants.append(name)
    guild.add_log(f"{name} 参与了任务: {task.name}")
    guild.add_audit_log("task_join", name, detail=task.name)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已参与任务：{task.name}", _task_summary(task)


def api_return_to_guild_base_as_player(
        self, player_name: str) -> tuple[bool, str]:
    """Teleport the player to their guild base after normal permission checks."""
    guilds = _load_guilds(self)
    name, guild, member, err = _find_player_context(self, player_name, guilds)
    if guild is None or member is None:
        return False, err
    if name not in getattr(self.game_ctrl, "allplayers", []):
        return False, f"玩家 {name} 当前不在线，无法传送"
    if _ensure_settings(guild).get("frozen", False):
        return False, guild_frozen_message(self, guild)
    if not guild.has_permission(name, "return_base"):
        return False, "你没有返回公会据点权限"
    if _ensure_settings(guild).get("base_locked", False):
        return False, f"公会 {guild.name} 据点已锁定"
    if not guild.base:
        return False, f"公会 {guild.name} 尚未设置据点"
    base = guild.base
    self.game_ctrl.sendwocmd(
        f"tp {name} {float(base.x)} {float(base.y)} {float(base.z)}")
    return True, f"已传送到公会 {guild.name} 据点"


def api_force_disband_guild(self, guild_query: str,
                            actor: str = "QQ管理") -> tuple[bool, str]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err
    name = guild.name
    del guilds[guild.guild_id]
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败"
    return True, f"已强制解散公会 {name}"


def api_rename_guild(self, guild_query: str, new_name: str,
                     actor: str = "QQ管理") -> tuple[bool, str, Optional[dict[str, Any]]]:
    new_name = str(new_name or "").strip()
    if not new_name:
        return False, "新公会名不能为空", None
    if len(new_name) < 2 or len(new_name) > 20:
        return False, "新公会名长度必须在 2-20 之间", None
    guilds = _load_guilds(self)
    if any(guild.name == new_name for guild in guilds.values()):
        return False, f"公会名已存在：{new_name}", None
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    old_name = guild.name
    guild.name = new_name
    guild.add_log(f"{_actor(actor)} 将公会名从 {old_name} 修改为 {new_name}")
    guild.add_audit_log(
        "guild_rename",
        _actor(actor),
        target=old_name,
        detail=new_name)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已修改公会名称：{old_name} -> {new_name}", _guild_summary(guild)


def api_set_guild_level(self,
                        guild_query: str,
                        level: int,
                        actor: str = "QQ管理") -> tuple[bool,
                                                      str,
                                                      Optional[dict[str,
                                                                    Any]]]:
    ok, err, parsed = _to_int(level, "公会等级", 1)
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    old = guild.level
    guild.level = parsed
    guild.add_log(f"{_actor(actor)} 将公会等级从 {old} 修改为 {parsed}")
    guild.add_audit_log(
        "guild_set_level",
        _actor(actor),
        detail=f"{old}->{parsed}")
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已设置 {guild.name} 等级为 {parsed}", _guild_summary(guild)


def api_set_guild_exp(self, guild_query: str, exp: int,
                      actor: str = "QQ管理") -> tuple[bool, str, Optional[dict[str, Any]]]:
    ok, err, parsed = _to_int(exp, "公会经验", 0)
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    old = guild.exp
    guild.exp = parsed
    level_ups = _apply_level_ups(guild)
    guild.add_log(f"{_actor(actor)} 将公会经验从 {old} 修改为 {parsed}")
    guild.add_audit_log(
        "guild_set_exp",
        _actor(actor),
        detail=f"{old}->{parsed}")
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    suffix = f"，触发升级到 {level_ups[-1]} 级" if level_ups else ""
    return True, f"已设置 {
        guild.name} 经验为 {
        guild.exp}{suffix}", _guild_summary(guild)


def api_transfer_guild_owner(self,
                             guild_query: str,
                             new_owner: str,
                             actor: str = "QQ管理") -> tuple[bool,
                                                           str,
                                                           Optional[dict[str,
                                                                         Any]]]:
    target_name = str(new_owner or "").strip()
    if not target_name:
        return False, "新会长不能为空", None
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    target = guild.get_member(target_name)
    if target is None:
        target = GuildMember(
            name=target_name,
            rank=GuildRank.MEMBER,
            join_time=_now())
        guild.members.append(target)
    for member in guild.members:
        if member.rank == GuildRank.OWNER and member.name != target_name:
            member.rank = GuildRank.DEPUTY
    target.rank = GuildRank.OWNER
    old_owner = guild.owner
    guild.owner = target.name
    guild.add_log(f"{_actor(actor)} 强制将会长从 {old_owner} 转让给 {target.name}")
    guild.add_audit_log("guild_force_transfer_owner", _actor(actor),
                        target=target.name, detail=old_owner)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已将 {guild.name} 会长转让给 {target.name}", _guild_summary(guild)


def api_force_join_guild(self,
                         guild_query: str,
                         player_name: str,
                         actor: str = "QQ管理") -> tuple[bool,
                                                       str,
                                                       Optional[dict[str,
                                                                     Any]]]:
    name = str(player_name or "").strip()
    if not name:
        return False, "玩家名不能为空", None
    guilds = _load_guilds(self)
    target_guild, err = _find_guild(self, guild_query, guilds)
    if target_guild is None:
        return False, err, None
    old_guild, _ = _find_player_guild(self, name, guilds)
    if old_guild and old_guild.guild_id == target_guild.guild_id:
        return True, f"{name} 已在公会 {
            target_guild.name}", _guild_summary(target_guild)
    if old_guild:
        old_guild.members = [
            member for member in old_guild.members if member.name != name]
        old_guild.add_log(f"{_actor(actor)} 强制移出 {name}")
        old_guild.add_audit_log("guild_force_leave", _actor(
            actor), target=name, detail=target_guild.name)
    target_guild.members.append(GuildMember(
        name=name, rank=GuildRank.MEMBER, join_time=_now()))
    target_guild.add_log(f"{_actor(actor)} 强制加入成员 {name}")
    target_guild.add_audit_log("guild_force_join", _actor(actor), target=name)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已将 {name} 加入公会 {
        target_guild.name}", _guild_summary(target_guild)


def api_force_leave_guild(self,
                          player_name: str,
                          actor: str = "QQ管理") -> tuple[bool,
                                                        str,
                                                        Optional[dict[str,
                                                                      Any]]]:
    name = str(player_name or "").strip()
    if not name:
        return False, "玩家名不能为空", None
    guilds = _load_guilds(self)
    guild, err = _find_player_guild(self, name, guilds)
    if guild is None:
        return False, err, None
    guild.members = [member for member in guild.members if member.name != name]
    if not guild.members:
        old_name = guild.name
        del guilds[guild.guild_id]
        if not _save_guilds(self, guilds):
            return False, "保存公会数据失败", None
        return True, f"已移除 {name}，公会 {old_name} 已无成员并被解散", None
    if guild.owner == name or not any(
            member.rank == GuildRank.OWNER for member in guild.members):
        new_owner = guild.members[0]
        new_owner.rank = GuildRank.OWNER
        guild.owner = new_owner.name
    guild.add_log(f"{_actor(actor)} 强制移出成员 {name}")
    guild.add_audit_log("guild_force_leave", _actor(actor), target=name)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已将 {name} 移出公会 {guild.name}", _guild_summary(guild)


def api_force_kick_member(self,
                          player_name: str,
                          actor: str = "QQ管理") -> tuple[bool,
                                                        str,
                                                        Optional[dict[str,
                                                                      Any]]]:
    return api_force_leave_guild(self, player_name, actor)


def api_set_guild_frozen(self,
                         guild_query: str,
                         frozen: bool,
                         reason: str = "",
                         actor: str = "QQ管理") -> tuple[bool,
                                                       str,
                                                       Optional[dict[str,
                                                                     Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    settings = _ensure_settings(guild)
    settings["frozen"] = bool(frozen)
    settings["frozen_reason"] = str(reason or "")
    settings["frozen_at"] = _now() if frozen else 0
    action = "冻结" if frozen else "解冻"
    guild.add_log(f"{_actor(actor)} {action}了公会")
    guild.add_audit_log("guild_freeze" if frozen else "guild_unfreeze",
                        _actor(actor), detail=str(reason or ""))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已{action}公会 {guild.name}", _guild_summary(guild)


def api_get_guild_vault(
        self, guild_query: str) -> tuple[bool, str, Optional[list[dict[str, Any]]]]:
    guild, err = _find_guild(self, guild_query)
    if guild is None:
        return False, err, None
    data = [_vault_item_summary(item, index)
            for index, item in enumerate(guild.vault_items, start=1)]
    return True, f"{guild.name} 仓库共有 {len(data)} 件上架物品", data


def api_backup_guild_vault(self,
                           guild_query: str,
                           label: str = "",
                           actor: str = "QQ管理") -> tuple[bool,
                                                         str,
                                                         Optional[dict[str,
                                                                       Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    settings = _ensure_settings(guild)
    backups = settings.setdefault("vault_backups", [])
    if not isinstance(backups, list):
        backups = []
        settings["vault_backups"] = backups
    backup = {
        "label": str(label or ""),
        "actor": _actor(actor),
        "created_at": _now(),
        "items": [item.to_dict() for item in guild.vault_items],
    }
    backups.insert(0, backup)
    settings["vault_backups"] = backups[:10]
    guild.add_audit_log("vault_backup", _actor(actor), detail=str(label or ""))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已备份 {
        guild.name} 仓库，当前保留 {
        len(
            settings['vault_backups'])} 份", backup


def api_clear_guild_vault(self,
                          guild_query: str,
                          actor: str = "QQ管理") -> tuple[bool,
                                                        str,
                                                        Optional[dict[str,
                                                                      Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    api_backup_guild_vault(self, guild.guild_id, "clear-before", actor)
    guilds = _load_guilds(self)
    guild = guilds[guild.guild_id]
    removed = len(guild.vault_items)
    guild.vault_items = []
    guild.add_log(f"{_actor(actor)} 清空了公会仓库")
    guild.add_audit_log(
        "vault_clear",
        _actor(actor),
        detail=f"removed={removed}")
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已清空 {
        guild.name} 仓库，共删除 {removed} 件物品", _guild_summary(guild)


def api_delete_guild_vault_item(self,
                                guild_query: str,
                                index: int,
                                actor: str = "QQ管理") -> tuple[bool,
                                                              str,
                                                              Optional[dict[str,
                                                                            Any]]]:
    ok, err, parsed = _to_int(index, "仓库序号", 1)
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    zero_index = parsed - 1
    if zero_index >= len(guild.vault_items):
        return False, f"仓库序号超出范围：{parsed}", None
    item = guild.vault_items.pop(zero_index)
    guild.add_vault_trade_log(
        "admin_delete",
        item,
        _actor(actor),
        detail="管理员删除")
    guild.add_audit_log("vault_item_delete", _actor(
        actor), target=item.seller, detail=item.item_id)
    guild.add_log(f"{_actor(actor)} 删除了仓库物品 {item.item_id} x{item.count}")
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已删除 {
        guild.name} 仓库第 {parsed} 件物品", _vault_item_summary(
        item, parsed)


def api_rollback_guild_vault(self,
                             guild_query: str,
                             backup_index: int = 1,
                             actor: str = "QQ管理") -> tuple[bool,
                                                           str,
                                                           Optional[dict[str,
                                                                         Any]]]:
    ok, err, parsed = _to_int(backup_index, "备份序号", 1)
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    backups = _ensure_settings(guild).get("vault_backups", [])
    if not isinstance(backups, list) or parsed > len(backups):
        return False, f"仓库备份不存在：{parsed}", None
    selected_backup = copy.deepcopy(backups[parsed - 1])
    api_backup_guild_vault(self, guild.guild_id, "rollback-before", actor)
    guilds = _load_guilds(self)
    guild = guilds[guild.guild_id]
    guild.vault_items = [
        VaultItem.from_dict(item)
        for item in selected_backup.get("items", [])
        if isinstance(item, dict)
    ]
    guild.add_log(f"{_actor(actor)} 回滚了公会仓库")
    guild.add_audit_log("vault_rollback", _actor(actor), detail=str(parsed))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已回滚 {guild.name} 仓库到备份 {parsed}", {
        "guild": _guild_summary(guild),
        "backup": selected_backup,
    }


def api_export_guild_vault(
        self, guild_query: str) -> tuple[bool, str, Optional[dict[str, Any]]]:
    guild, err = _find_guild(self, guild_query)
    if guild is None:
        return False, err, None
    data = {
        "guild": _guild_summary(guild), "vault_items": [
            _vault_item_summary(
                item, index) for index, item in enumerate(
                guild.vault_items, start=1)], "vault_trade_logs": [
                    log.to_dict() for log in guild.vault_trade_logs], }
    data["json"] = json.dumps(data, ensure_ascii=False, indent=2)
    return True, f"已导出 {guild.name} 仓库数据", data


def _make_task_from_template(
        template: dict[str, Any], prefix: str = "auto") -> GuildTask:
    now = _now()
    deadline_seconds = int(getattr(Config, "GUILD_TASK_CONFIG",
                           {}).get("自动任务默认有效期秒", 172800))
    return GuildTask(
        task_id=f"{prefix} -{uuid.uuid4().hex[: 8]} ",
        name=str(template.get("name", "公会任务"))[: 20],
        description=str(template.get("description", ""))[: 100],
        task_type=str(template.get("task_type", "trade")),
        target=str(template.get("target", "trade_count")),
        target_count=max(1, int(template.get("target_count", 1))),
        current_count=max(0, int(template.get("current_count", 0))),
        reward_exp=max(0, int(template.get("reward_exp", 0))),
        reward_contribution=max(
            0, int(template.get("reward_contribution", 0))),
        create_time=now, deadline=now + deadline_seconds
        if deadline_seconds > 0 else 0,)


def api_refresh_guild_tasks(
        self, guild_query: str, actor: str = "QQ管理") -> tuple[bool, str, list[dict[str, Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, []
    templates = getattr(Config, "GUILD_TASK_CONFIG", {}).get("自动任务模板列表", [])
    if not templates:
        return False, "没有配置自动任务模板", []
    active_keys = {(task.name, task.task_type, task.target)
                   for task in guild.tasks if not task.completed}
    created: list[GuildTask] = []
    for template in templates:
        key = (
            template.get("name"),
            template.get("task_type"),
            template.get("target"))
        if key in active_keys:
            continue
        task = _make_task_from_template(template)
        guild.tasks.append(task)
        created.append(task)
    guild.add_log(f"{_actor(actor)} 刷新了公会任务，新增 {len(created)} 个")
    guild.add_audit_log(
        "task_refresh",
        _actor(actor),
        detail=str(
            len(created)))
    if created and not _save_guilds(self, guilds):
        return False, "保存公会数据失败", []
    return True, f"已为 {
        guild.name} 刷新任务，新增 {
        len(created)} 个", [
            _task_summary(task) for task in created]


def api_create_global_task(
    self,
    name: str,
    task_type: str,
    target: str,
    target_count: int,
    reward_exp: int = 0,
    reward_contribution: int = 0,
    description: str = "",
    deadline_seconds: int = 0,
    actor: str = "QQ管理",
) -> tuple[bool, str, list[dict[str, Any]]]:
    task_name = str(name or "").strip()
    if not task_name:
        return False, "任务名称不能为空", []
    ok, err, count = _to_int(target_count, "目标数量", 1)
    if not ok:
        return False, err, []
    _, _, exp = _to_int(reward_exp, "经验奖励", 0)
    _, _, contribution = _to_int(reward_contribution, "贡献奖励", 0)
    _, _, seconds = _to_int(deadline_seconds, "截止秒数", 0)
    guilds = _load_guilds(self)
    now = _now()
    created: list[dict[str, Any]] = []
    for guild in guilds.values():
        task = GuildTask(
            task_id=f"global-{uuid.uuid4().hex[:8]}",
            name=task_name[:20],
            description=str(description or task_name)[:100],
            task_type=str(task_type or "trade"),
            target=str(target or "trade_count"),
            target_count=count,
            reward_exp=exp,
            reward_contribution=contribution,
            create_time=now,
            deadline=now + seconds if seconds > 0 else 0,
        )
        guild.tasks.append(task)
        guild.add_log(f"{_actor(actor)} 创建了全服任务 {task.name}")
        created.append({"guild_id": guild.guild_id,
                       "guild_name": guild.name, "task": _task_summary(task)})
    if created and not _save_guilds(self, guilds):
        return False, "保存公会数据失败", []
    return True, f"已向 {len(created)} 个公会创建全服任务", created


def api_delete_guild_task(self,
                          guild_query: str,
                          task_query: str,
                          actor: str = "QQ管理") -> tuple[bool,
                                                        str,
                                                        Optional[dict[str,
                                                                      Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    task, err = _find_task(guild, task_query)
    if task is None:
        return False, err, None
    guild.tasks = [
        item for item in guild.tasks if item.task_id != task.task_id]
    guild.add_log(f"{_actor(actor)} 删除了任务 {task.name}")
    guild.add_audit_log("task_delete", _actor(actor), detail=task.name)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已删除任务 {task.name}", _task_summary(task)


def api_reset_guild_task_progress(self,
                                  guild_query: str,
                                  task_query: str,
                                  actor: str = "QQ管理") -> tuple[bool,
                                                                str,
                                                                Optional[dict[str,
                                                                              Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    task, err = _find_task(guild, task_query)
    if task is None:
        return False, err, None
    task.current_count = 0
    task.completed = False
    task.participants = []
    guild.add_log(f"{_actor(actor)} 重置了任务 {task.name}")
    guild.add_audit_log("task_reset", _actor(actor), detail=task.name)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已重置任务 {task.name}", _task_summary(task)


def api_force_complete_guild_task(self,
                                  guild_query: str,
                                  task_query: str,
                                  actor: str = "QQ管理") -> tuple[bool,
                                                                str,
                                                                Optional[dict[str,
                                                                              Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    task, err = _find_task(guild, task_query)
    if task is None:
        return False, err, None
    task.current_count = task.target_count
    task.completed = True
    guild.add_log(f"{_actor(actor)} 强制完成了任务 {task.name}")
    guild.add_audit_log("task_force_complete", _actor(actor), detail=task.name)
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已强制完成任务 {task.name}", _task_summary(task)


def api_teleport_player_to_guild_base(
        self, player_name: str, guild_query: str | None = None) -> tuple[bool, str]:
    name = str(player_name or "").strip()
    if not name:
        return False, "玩家名不能为空"
    guilds = _load_guilds(self)
    if guild_query:
        guild, err = _find_guild(self, guild_query, guilds)
    else:
        guild, err = _find_player_guild(self, name, guilds)
    if guild is None:
        return False, err
    if _ensure_settings(guild).get("base_locked", False):
        return False, f"公会 {guild.name} 据点已锁定"
    if not guild.base:
        return False, f"公会 {guild.name} 尚未设置据点"
    base = guild.base
    self.game_ctrl.sendwocmd(
        f"tp {name} {float(base.x)} {float(base.y)} {float(base.z)}")
    return True, f"已传送 {name} 到公会 {guild.name} 据点"


def api_delete_guild_base(self,
                          guild_query: str,
                          actor: str = "QQ管理") -> tuple[bool,
                                                        str,
                                                        Optional[dict[str,
                                                                      Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    guild.base = None
    guild.add_log(f"{_actor(actor)} 删除了公会据点")
    guild.add_audit_log("base_delete", _actor(actor))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已删除 {guild.name} 据点", _guild_summary(guild)


def api_set_guild_base(self,
                       guild_query: str,
                       dimension: int,
                       x: float,
                       y: float,
                       z: float,
                       actor: str = "QQ管理") -> tuple[bool,
                                                     str,
                                                     Optional[dict[str,
                                                                   Any]]]:
    ok, err, dim = _to_int(dimension, "维度")
    if not ok:
        return False, err, None
    coord_values = []
    for field_name, value in (("x", x), ("y", y), ("z", z)):
        ok, err, parsed = _to_float(value, field_name)
        if not ok:
            return False, err, None
        coord_values.append(parsed)
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    guild.base = GuildBase(
        dim,
        coord_values[0],
        coord_values[1],
        coord_values[2])
    guild.add_log(f"{_actor(actor)} 修改了公会据点")
    guild.add_audit_log("base_set", _actor(
        actor), detail=f"{dim},{coord_values}")
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已设置 {guild.name} 据点", _guild_summary(guild)


def api_set_guild_base_locked(self,
                              guild_query: str,
                              locked: bool,
                              actor: str = "QQ管理") -> tuple[bool,
                                                            str,
                                                            Optional[dict[str,
                                                                          Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    _ensure_settings(guild)["base_locked"] = bool(locked)
    action = "锁定" if locked else "解锁"
    guild.add_log(f"{_actor(actor)} {action}了公会据点")
    guild.add_audit_log(
        "base_lock" if locked else "base_unlock",
        _actor(actor))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已{action} {guild.name} 据点", _guild_summary(guild)


def api_clear_guild_effects(self,
                            guild_query: str,
                            actor: str = "QQ管理") -> tuple[bool,
                                                          str,
                                                          Optional[dict[str,
                                                                        Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    guild.purchased_effects = {}
    guild.add_log(f"{_actor(actor)} 清空了公会效果")
    guild.add_audit_log("effect_clear", _actor(actor))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已清空 {guild.name} 效果", _guild_summary(guild)


def api_set_guild_effect(self,
                         guild_query: str,
                         effect_key: str,
                         level: int,
                         actor: str = "QQ管理") -> tuple[bool,
                                                       str,
                                                       Optional[dict[str,
                                                                     Any]]]:
    key = str(effect_key or "").strip()
    if key not in Config.EFFECTS_CONFIG:
        names = {
            str(value.get("name", "")): effect_id
            for effect_id, value in Config.EFFECTS_CONFIG.items()
            if isinstance(value, dict)
        }
        key = names.get(key, key)
    if key not in Config.EFFECTS_CONFIG:
        return False, f"效果不存在：{effect_key}", None
    ok, err, parsed_level = _to_int(level, "效果等级", 0)
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    if parsed_level <= 0:
        guild.purchased_effects.pop(key, None)
    else:
        guild.purchased_effects[key] = parsed_level
    guild.add_log(f"{_actor(actor)} 设置效果 {key} 为 {parsed_level} 级")
    guild.add_audit_log(
        "effect_set",
        _actor(actor),
        detail=f"{key}={parsed_level}")
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已设置 {
        guild.name} 效果 {key} 为 {parsed_level} 级", _guild_summary(guild)


def api_add_guild_funds(self,
                        guild_query: str,
                        amount: int,
                        actor: str = "QQ管理") -> tuple[bool,
                                                      str,
                                                      Optional[dict[str,
                                                                    Any]]]:
    ok, err, parsed = _to_int(amount, "资金数量")
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    settings = _ensure_settings(guild)
    settings["funds"] = int(settings.get("funds", 0) or 0) + parsed
    guild.add_log(f"{_actor(actor)} 调整公会资金 {parsed:+d}")
    guild.add_audit_log("funds_add", _actor(actor), detail=str(parsed))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已调整 {
        guild.name} 资金，当前 {
        settings['funds']}", _guild_summary(guild)


def api_set_guild_funds(self,
                        guild_query: str,
                        amount: int,
                        actor: str = "QQ管理") -> tuple[bool,
                                                      str,
                                                      Optional[dict[str,
                                                                    Any]]]:
    ok, err, parsed = _to_int(amount, "资金余额", 0)
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    _ensure_settings(guild)["funds"] = parsed
    guild.add_log(f"{_actor(actor)} 设置公会资金为 {parsed}")
    guild.add_audit_log("funds_set", _actor(actor), detail=str(parsed))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已设置 {guild.name} 资金为 {parsed}", _guild_summary(guild)


def api_add_member_contribution(self,
                                player_name: str,
                                amount: int,
                                actor: str = "QQ管理") -> tuple[bool,
                                                              str,
                                                              Optional[dict[str,
                                                                            Any]]]:
    ok, err, parsed = _to_int(amount, "贡献值")
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_player_guild(self, player_name, guilds)
    if guild is None:
        return False, err, None
    member = guild.get_member(str(player_name).strip())
    if member is None:
        return False, "成员数据异常", None
    member.contribution += parsed
    guild.stats.total_contribution += max(0, parsed)
    guild.add_log(f"{_actor(actor)} 调整 {member.name} 贡献 {parsed:+d}")
    guild.add_audit_log("member_contribution_add", _actor(actor),
                        target=member.name, detail=str(parsed))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已调整 {
        member.name} 贡献，当前 {
        member.contribution}", _member_summary(member)


def api_set_member_contribution(self,
                                player_name: str,
                                amount: int,
                                actor: str = "QQ管理") -> tuple[bool,
                                                              str,
                                                              Optional[dict[str,
                                                                            Any]]]:
    ok, err, parsed = _to_int(amount, "贡献值", 0)
    if not ok:
        return False, err, None
    guilds = _load_guilds(self)
    guild, err = _find_player_guild(self, player_name, guilds)
    if guild is None:
        return False, err, None
    member = guild.get_member(str(player_name).strip())
    if member is None:
        return False, "成员数据异常", None
    old = member.contribution
    member.contribution = parsed
    guild.add_log(f"{_actor(actor)} 将 {member.name} 贡献从 {old} 设置为 {parsed}")
    guild.add_audit_log("member_contribution_set", _actor(
        actor), target=member.name, detail=f"{old}->{parsed}")
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已设置 {member.name} 贡献为 {parsed}", _member_summary(member)


def api_reset_guild_contributions(self,
                                  guild_query: str,
                                  actor: str = "QQ管理") -> tuple[bool,
                                                                str,
                                                                Optional[dict[str,
                                                                              Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    for member in guild.members:
        member.contribution = 0
    guild.stats.total_contribution = 0
    guild.add_log(f"{_actor(actor)} 重置了所有成员贡献")
    guild.add_audit_log("member_contribution_reset_all", _actor(actor))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已重置 {guild.name} 所有成员贡献", _guild_summary(guild)


def api_reset_market_prices(self,
                            guild_query: str,
                            actor: str = "QQ管理") -> tuple[bool,
                                                          str,
                                                          Optional[dict[str,
                                                                        Any]]]:
    guilds = _load_guilds(self)
    guild, err = _find_guild(self, guild_query, guilds)
    if guild is None:
        return False, err, None
    removed = len(guild.custom_item_values)
    guild.custom_item_values = {}
    guild.add_log(f"{_actor(actor)} 重置了市场价格")
    guild.add_audit_log(
        "market_price_reset",
        _actor(actor),
        detail=str(removed))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", None
    return True, f"已重置 {
        guild.name} 市场价格，删除 {removed} 条自定义价格", _guild_summary(guild)


def api_get_guild_logs(self, guild_query: str,
                       limit: int = 20) -> tuple[bool, str, Optional[dict[str, Any]]]:
    ok, _err, parsed_limit = _to_int(limit, "日志数量", 1)
    if not ok:
        parsed_limit = 20
    guild, err = _find_guild(self, guild_query)
    if guild is None:
        return False, err, None
    return True, "查询成功", {
        "logs": guild.logs[-parsed_limit:],
        "audit_logs": [log.to_dict() for log in guild.audit_logs[-parsed_limit:]],
        "vault_trade_logs": [log.to_dict() for log in guild.vault_trade_logs[-parsed_limit:]],
    }


def api_get_abnormal_trades(self,
                            guild_query: str | None = None,
                            ratio: float = 3.0) -> tuple[bool,
                                                         str,
                                                         list[dict[str,
                                                                   Any]]]:
    try:
        threshold = float(ratio)
    except (TypeError, ValueError):
        threshold = 3.0
    guilds = _load_guilds(self)
    target_guilds: list[GuildData]
    if guild_query:
        guild, err = _find_guild(self, guild_query, guilds)
        if guild is None:
            return False, err, []
        target_guilds = [guild]
    else:
        target_guilds = list(guilds.values())
    results = []
    for guild in target_guilds:
        for log in guild.vault_trade_logs:
            suggested = guild.get_item_value(
                log.item_id) * max(1, int(log.count or 1))
            if suggested > 0 and log.price >= suggested * threshold:
                data = log.to_dict()
                data["guild_id"] = guild.guild_id
                data["guild_name"] = guild.name
                data["suggested_price"] = suggested
                data["ratio"] = round(log.price / suggested, 2)
                results.append(data)
    results.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
    return True, f"共 {len(results)} 条异常交易记录", results


def api_get_donation_rankings(self,
                              guild_query: str | None = None,
                              limit: int = 10) -> tuple[bool,
                                                        str,
                                                        list[dict[str,
                                                                  Any]]]:
    ok, _err, parsed_limit = _to_int(limit, "排行数量", 1)
    if not ok:
        parsed_limit = 10
    guilds = _load_guilds(self)
    records = []
    for guild in guilds.values():
        if guild_query and guild.name != guild_query and guild.guild_id != guild_query:
            continue
        for member in guild.members:
            records.append({
                "guild_id": guild.guild_id,
                "guild_name": guild.name,
                "player_name": member.name,
                "rank": member.rank.value,
                "contribution": member.contribution,
            })
    records.sort(key=lambda item: int(item["contribution"]), reverse=True)
    return True, f"贡献排行前 {min(parsed_limit, len(records))} 名", records[:parsed_limit]


def api_get_guild_rankings(self, sort_by: str = "level",
                           limit: int = 10) -> tuple[bool, str, list[dict[str, Any]]]:
    """返回适合外部插件消费的公会排行榜数据。"""
    raw_sort_by = str(sort_by or "level").strip()
    sort_key = {
        "等级": "level",
        "level": "level",
        "成员": "members",
        "members": "members",
        "贡献": "contribution",
        "contribution": "contribution",
        "活跃": "activity",
        "activity": "activity",
    }.get(raw_sort_by, raw_sort_by)
    ok, _err, parsed_limit = _to_int(limit, "排行数量", 1)
    if not ok:
        parsed_limit = 10
    rankings = _get_guild_rankings(self, sort_key)[:parsed_limit]
    data: list[dict[str, Any]] = []
    for index, (guild, score) in enumerate(rankings, start=1):
        item = _guild_summary(guild)
        item["rank"] = index
        item["score"] = score
        item["sort_by"] = sort_key
        data.append(item)
    return True, f"公会排行前 {len(data)} 名", data


def api_reload_guild_config(self) -> tuple[bool, str, dict[str, Any]]:
    self.config = Config.load(self.name, self.version)
    return True, "公会系统配置已重新加载", copy.deepcopy(self.config)


def api_save_guild_data(self) -> tuple[bool, str]:
    guilds = _load_guilds(self)
    if not _save_guilds(self, guilds, force=True):
        return False, "保存公会数据失败"
    return True, "公会数据已强制保存"


def api_backup_guild_data(self) -> tuple[bool, str, Optional[str]]:
    if not os.path.exists(self.guilds_file):
        return False, "公会数据文件不存在", None
    data_dir = os.path.dirname(self.guilds_file)
    backup_dir = os.path.join(data_dir, "公会数据备份")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(
        backup_dir, f"公会数据文件-api-{time.strftime('%Y%m%d-%H%M%S')}.json")
    shutil.copy2(self.guilds_file, backup_path)
    return True, "公会数据备份已创建", backup_path


def api_repair_guild_data(
        self, actor: str = "QQ管理") -> tuple[bool, str, dict[str, Any]]:
    guilds = _load_guilds(self)
    fixed = {"guild_id": 0, "level": 0, "exp": 0,
             "owner": 0, "vault": 0, "removed_empty": 0}
    for outer_id in list(guilds.keys()):
        guild = guilds[outer_id]
        if not guild.members:
            del guilds[outer_id]
            fixed["removed_empty"] += 1
            continue
        if guild.guild_id != outer_id:
            guild.guild_id = outer_id
            fixed["guild_id"] += 1
        if not isinstance(guild.level, int) or guild.level < 1:
            guild.level = 1
            fixed["level"] += 1
        if not isinstance(guild.exp, (int, float)) or guild.exp < 0:
            guild.exp = 0
            fixed["exp"] += 1
        owners = [member for member in guild.members
                  if member.rank == GuildRank.OWNER]
        if len(owners) != 1:
            preferred = guild.get_member(guild.owner) or guild.members[0]
            for member in guild.members:
                member.rank = GuildRank.MEMBER
            preferred.rank = GuildRank.OWNER
            guild.owner = preferred.name
            fixed["owner"] += 1
        if len(guild.vault_items) > Config.VAULT_INITIAL_SLOTS:
            guild.vault_items = guild.vault_items[:Config.VAULT_INITIAL_SLOTS]
            fixed["vault"] += 1
        if not isinstance(guild.stats, GuildStats):
            guild.stats = GuildStats()
        guild.add_audit_log("data_repair", _actor(
            actor), detail=json.dumps(fixed, ensure_ascii=False))
    if not _save_guilds(self, guilds):
        return False, "保存公会数据失败", fixed
    return True, "公会数据修复完成", fixed


def api_get_guild_statistics(self) -> tuple[bool, str, dict[str, Any]]:
    guilds = _load_guilds(self)
    total_members = sum(len(guild.members) for guild in guilds.values())
    total_vault_items = sum(len(guild.vault_items)
                            for guild in guilds.values())
    total_tasks = sum(len(guild.tasks) for guild in guilds.values())
    active_tasks = sum(
        len([task for task in guild.tasks if not task.completed])
        for guild in guilds.values())
    frozen_count = sum(1 for guild in guilds.values()
                       if _ensure_settings(guild).get("frozen", False))
    data = {
        "guild_count": len(guilds),
        "member_count": total_members,
        "vault_item_count": total_vault_items,
        "task_count": total_tasks,
        "active_task_count": active_tasks,
        "frozen_guild_count": frozen_count,
        "activity_status": api_get_guild_activity_status(self)[2],
    }
    return True, "查询成功", data


def api_start_guild_activity(
    self,
    activity: str,
    duration_seconds: int = 3600,
    multiplier: float = 2.0,
    actor: str = "QQ管理",
) -> tuple[bool, str, dict[str, Any]]:
    activity_key = str(activity or "").strip().lower()
    aliases = {
        "双倍经验": "exp",
        "经验": "exp",
        "exp": "exp",
        "双倍贡献": "contribution",
        "贡献": "contribution",
        "contribution": "contribution",
        "公会争霸": "contest",
        "争霸": "contest",
        "contest": "contest",
    }
    activity_key = aliases.get(activity_key, activity_key)
    if activity_key not in ("exp", "contribution", "contest"):
        return False, f"未知活动类型：{activity}", {}
    ok, err, seconds = _to_int(duration_seconds, "活动时长秒", 1)
    if not ok:
        return False, err, {}
    try:
        parsed_multiplier = max(1.0, float(multiplier))
    except (TypeError, ValueError):
        parsed_multiplier = 2.0
    if not hasattr(self, "_guild_runtime_events"):
        self._guild_runtime_events = {}
    event = {
        "activity": activity_key,
        "multiplier": parsed_multiplier,
        "started_at": _now(),
        "expires_at": _now() + seconds,
        "actor": _actor(actor),
    }
    self._guild_runtime_events[activity_key] = event
    return True, f"已开启 {activity_key} 活动 {seconds} 秒，倍率 {parsed_multiplier}", copy.deepcopy(
        event)


def api_stop_guild_activity(self, activity: str) -> tuple[bool, str]:
    activity_key = str(activity or "").strip().lower()
    aliases = {"经验": "exp", "双倍经验": "exp", "贡献": "contribution",
               "双倍贡献": "contribution", "争霸": "contest", "公会争霸": "contest"}
    activity_key = aliases.get(activity_key, activity_key)
    removed = getattr(
        self,
        "_guild_runtime_events",
        {}).pop(
        activity_key,
        None)
    if removed is None:
        return False, f"活动未开启：{activity}"
    return True, f"已停止活动 {activity_key}"


def api_get_guild_activity_status(self) -> tuple[bool, str, dict[str, Any]]:
    events = getattr(self, "_guild_runtime_events", {})
    now = _now()
    active = {}
    for key, event in list(events.items()):
        expires_at = float(event.get("expires_at", 0) or 0)
        if 0 < expires_at <= now:
            events.pop(key, None)
            continue
        active[key] = copy.deepcopy(event)
        active[key]["remaining_seconds"] = max(
            0, int(expires_at - now)) if expires_at > 0 else 0
    return True, f"当前 {len(active)} 个活动运行中", active


def api_settle_guild_ranking_rewards(
    self,
    sort_by: str = "level",
    top: int = 3,
    reward_exp: int = 0,
    reward_funds: int = 0,
    actor: str = "QQ管理",
) -> tuple[bool, str, list[dict[str, Any]]]:
    ok, err, parsed_top = _to_int(top, "排行数量", 1)
    if not ok:
        return False, err, []
    _, _, exp = _to_int(reward_exp, "经验奖励", 0)
    _, _, funds = _to_int(reward_funds, "资金奖励", 0)
    guilds = _load_guilds(self)
    ranking = _get_guild_rankings(self, sort_by)
    rewarded = []
    for guild, score in ranking[:parsed_top]:
        latest = guilds.get(guild.guild_id)
        if latest is None:
            continue
        latest.exp += exp
        _apply_level_ups(latest)
        settings = _ensure_settings(latest)
        settings["funds"] = int(settings.get("funds", 0) or 0) + funds
        latest.add_log(f"{_actor(actor)} 发放排行榜奖励：经验 {exp}，资金 {funds}")
        latest.add_audit_log("ranking_reward", _actor(actor),
                             detail=f"{sort_by}:{score}")
        rewarded.append({"guild_id": latest.guild_id,
                        "guild_name": latest.name, "score": score})
    if rewarded and not _save_guilds(self, guilds):
        return False, "保存公会数据失败", []
    return True, f"已结算 {len(rewarded)} 个公会的排行榜奖励", rewarded


def api_broadcast_guild_announcement(
        self, message: str, actor: str = "QQ管理") -> tuple[bool, str]:
    text = str(message or "").strip()
    if not text:
        return False, "公告内容不能为空"
    payload = json.dumps(
        {"rawtext": [{"text": f"§l§a公会公告 §d>> §r{text}"}]}, ensure_ascii=False)
    self.game_ctrl.sendcmd(f"/tellraw @a {payload}")
    fmts.print_inf(f"{_actor(actor)} 发布公会全服公告：{text}")
    return True, "全服公告已发送"


def _get_guild_rankings(
        self, sort_by: str = "level") -> list[tuple[GuildData, Any]]:
    return self.get_guild_rankings(sort_by)


guild_api_functions = {
    "guild_get_activity_multiplier": guild_get_activity_multiplier,
    "guild_apply_reward_multipliers": guild_apply_reward_multipliers,
    "guild_is_frozen": guild_is_frozen,
    "guild_frozen_message": guild_frozen_message,
    "show_guild_frozen": show_guild_frozen,
    "api_list_guilds": api_list_guilds,
    "api_get_guild": api_get_guild,
    "api_get_player_record": api_get_player_record,
    "api_get_player_guild_menu_state": api_get_player_guild_menu_state,
    "api_get_own_guild_logs": api_get_own_guild_logs,
    "api_get_own_guild_vault": api_get_own_guild_vault,
    "api_get_own_guild_tasks": api_get_own_guild_tasks,
    "api_request_join_guild_as_player": api_request_join_guild_as_player,
    "api_leave_guild_as_player": api_leave_guild_as_player,
    "api_disband_owned_guild_as_player": api_disband_owned_guild_as_player,
    "api_set_announcement_as_player": api_set_announcement_as_player,
    "api_join_guild_task_as_player": api_join_guild_task_as_player,
    "api_return_to_guild_base_as_player": api_return_to_guild_base_as_player,
    "api_force_disband_guild": api_force_disband_guild,
    "api_rename_guild": api_rename_guild,
    "api_set_guild_level": api_set_guild_level,
    "api_set_guild_exp": api_set_guild_exp,
    "api_transfer_guild_owner": api_transfer_guild_owner,
    "api_force_join_guild": api_force_join_guild,
    "api_force_leave_guild": api_force_leave_guild,
    "api_force_kick_member": api_force_kick_member,
    "api_set_guild_frozen": api_set_guild_frozen,
    "api_get_guild_vault": api_get_guild_vault,
    "api_backup_guild_vault": api_backup_guild_vault,
    "api_clear_guild_vault": api_clear_guild_vault,
    "api_delete_guild_vault_item": api_delete_guild_vault_item,
    "api_rollback_guild_vault": api_rollback_guild_vault,
    "api_export_guild_vault": api_export_guild_vault,
    "api_refresh_guild_tasks": api_refresh_guild_tasks,
    "api_create_global_task": api_create_global_task,
    "api_delete_guild_task": api_delete_guild_task,
    "api_reset_guild_task_progress": api_reset_guild_task_progress,
    "api_force_complete_guild_task": api_force_complete_guild_task,
    "api_teleport_player_to_guild_base": api_teleport_player_to_guild_base,
    "api_delete_guild_base": api_delete_guild_base,
    "api_set_guild_base": api_set_guild_base,
    "api_set_guild_base_locked": api_set_guild_base_locked,
    "api_clear_guild_effects": api_clear_guild_effects,
    "api_set_guild_effect": api_set_guild_effect,
    "api_add_guild_funds": api_add_guild_funds,
    "api_set_guild_funds": api_set_guild_funds,
    "api_add_member_contribution": api_add_member_contribution,
    "api_set_member_contribution": api_set_member_contribution,
    "api_reset_guild_contributions": api_reset_guild_contributions,
    "api_reset_market_prices": api_reset_market_prices,
    "api_get_guild_logs": api_get_guild_logs,
    "api_get_abnormal_trades": api_get_abnormal_trades,
    "api_get_donation_rankings": api_get_donation_rankings,
    "api_get_guild_rankings": api_get_guild_rankings,
    "api_reload_guild_config": api_reload_guild_config,
    "api_save_guild_data": api_save_guild_data,
    "api_backup_guild_data": api_backup_guild_data,
    "api_repair_guild_data": api_repair_guild_data,
    "api_get_guild_statistics": api_get_guild_statistics,
    "api_start_guild_activity": api_start_guild_activity,
    "api_stop_guild_activity": api_stop_guild_activity,
    "api_get_guild_activity_status": api_get_guild_activity_status,
    "api_settle_guild_ranking_rewards": api_settle_guild_ranking_rewards,
    "api_broadcast_guild_announcement": api_broadcast_guild_announcement,
}

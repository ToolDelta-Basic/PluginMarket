"""Libra 的纯函数核心：校验、命令生成、权限差异和玩家搜索。"""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable

XUID_RE = re.compile(r"^[0-9a-fA-F]{8,32}$")
FLAGS_RE = re.compile(r"^[01]{8}$")
PERMISSION_NAMES = ("build", "mine", "doors", "containers", "attack_players", "attack_mobs", "commands", "teleport")
CONSOLE_ROOT_TRIGGER = "权限"
CONSOLE_TRIGGERS = {"help": (CONSOLE_ROOT_TRIGGER, "打开权限管理总菜单")}
_CONSOLE_SUBCOMMANDS: dict[str, str] = {}
MENU_DEFINITIONS = {
    "main": {"1": "status", "2": "list", "3": "set_menu", "4": "snapshot_menu", "5": "realtime_menu", "q": "close", "Q": "close"},
    "set": {"1": "set_admin", "2": "set_member", "3": "set_guest", "4": "set_custom", "!": "back", "！": "back", "q": "close", "Q": "close"},
    "snapshots": {"1": "snapshot_create", "2": "snapshot_restore", "3": "snapshot_delete", "!": "back", "！": "back", "q": "close", "Q": "close"},
    "snapshot_list": {"!": "back", "！": "back", "q": "close", "Q": "close"},
    # 旧 API/第三方单步调用兼容；控制台总菜单不再暴露此菜单。
    "revoke": {"1": "revoke_target", "!": "back", "！": "back", "q": "close", "Q": "close"},
    "confirm": {"y": "confirm", "Y": "confirm", "q": "cancel", "Q": "cancel", "!": "back", "！": "back"},
}

def menu_action(menu: str, choice: str) -> tuple[str, str | None]:
    action = MENU_DEFINITIONS.get(menu, {}).get(str(choice or "").strip(), "invalid")
    if action in {"set_admin", "set_member", "set_guest"}:
        return action, {"set_admin": "11111111", "set_member": "11111100", "set_guest": "00000000"}[action]
    if action == "confirm":
        return action, "y"
    return action, None

def parse_console_args(args: list[str]) -> tuple[str, list[str]]:
    values = list(args or [])
    if values and values[0] == CONSOLE_ROOT_TRIGGER:
        values.pop(0)
    return (_CONSOLE_SUBCOMMANDS.get(values[0], "help"), values[1:]) if values else ("help", [])

@dataclass(frozen=True)
class ParsedFlags:
    raw: str
    mask: int
    permissions: tuple[bool, ...]


@dataclass(frozen=True)
class AdminDiff:
    """权限差异结果，供第三方 API 调用方使用。"""

    to_set: list[tuple[str, str]]
    to_delete: list[str]


def normalize_xuid(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("XUID 必须是字符串")
    value = value.strip()
    if not XUID_RE.fullmatch(value):
        raise ValueError("XUID 必须是 8-32 位十六进制字符串")
    return value.lower()

def parse_flags(value: str) -> ParsedFlags:
    if not isinstance(value, str) or not FLAGS_RE.fullmatch(value):
        raise ValueError("权限标志必须是恰好 8 位的 0/1 字符串")
    mask = sum(1 << i for i, char in enumerate(value) if char == "1")
    return ParsedFlags(value, mask, tuple(char == "1" for char in value))

def format_flags(mask: int) -> str:
    if not isinstance(mask, int) or isinstance(mask, bool) or not 0 <= mask <= 0xFF:
        raise ValueError("权限掩码必须是 0-255 的整数")
    return "".join("1" if mask & (1 << i) else "0" for i in range(8))

def build_set_command(xuid: str, flags: str) -> str:
    return f"/permission setbyxuid .{normalize_xuid(xuid)} .{parse_flags(flags).raw}"

def build_delete_command(xuid: str) -> str:
    return f"/permission del .{normalize_xuid(xuid)}"

def build_list_command() -> str:
    return "/permission list"


def plan_admin_diff(desired: dict[str, str], observed_admins: Iterable[str]) -> AdminDiff:
    expected = {normalize_xuid(x): parse_flags(f).raw for x, f in desired.items()}
    observed = {normalize_xuid(x) for x in observed_admins}
    return AdminDiff(
        sorted((x, f) for x, f in expected.items() if x not in observed),
        sorted(observed - set(expected)),
    )


def parse_admin_xuids(text: str) -> list[str]:
    if not isinstance(text, str):
        return []
    found: list[str] = []
    for token in re.findall(r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{8,32})(?![0-9A-Fa-f])", text):
        token = token.lower()
        if token not in found:
            found.append(token)
    return found

def permission_descriptions(flags: str) -> dict[str, bool]:
    return dict(zip(PERMISSION_NAMES, parse_flags(flags).permissions))

def load_xuid_map(path: str | Path) -> dict[str, str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for xuid, name in raw.items():
        if isinstance(xuid, str) and isinstance(name, str):
            try:
                result[normalize_xuid(xuid)] = name.strip()
            except ValueError:
                continue
    return {x: n for x, n in result.items() if n}

def search_player_records(records: dict[str, str], query: str, limit: int = 8) -> list[dict[str, str]]:
    q = str(query or "").strip().casefold()
    if not q or limit <= 0:
        return []
    ranked = []
    for xuid, name in records.items():
        folded = name.casefold()
        rank = 0 if folded == q else 1 if folded.startswith(q) else 2 if q in folded else 99
        if rank < 99:
            ranked.append((rank, folded, xuid))
    ranked.sort()
    return [{"xuid": x, "name": records[x]} for _, _, x in ranked[:limit]]

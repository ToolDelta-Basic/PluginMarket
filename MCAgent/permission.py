from enum import Enum
from typing import TYPE_CHECKING, ClassVar
from tooldelta import Player
if TYPE_CHECKING:
    from . import MCAgent

class PermissionLevel(Enum):
    """Permission level enumeration"""
    NONE = 0
    CREATIVE = 1
    OP = 2
    FULL = 3

class PermissionManager:
    """Permission manager for tool access control"""
    # 若想添加新的tool 需在此处进行注册并划分权限
    TOOL_PERMISSIONS: ClassVar[dict[str, PermissionLevel]] = {
        "execute_command": PermissionLevel.OP,
        "get_game_rule": PermissionLevel.OP,
        "place_command_block": PermissionLevel.OP,

        "teleport_player": PermissionLevel.CREATIVE,
        "give_item": PermissionLevel.CREATIVE,
        "set_block": PermissionLevel.CREATIVE,
        "fill_blocks": PermissionLevel.CREATIVE,
        "broadcast_message": PermissionLevel.CREATIVE,
        "get_player_info": PermissionLevel.CREATIVE,
        "get_online_players": PermissionLevel.CREATIVE,
        "get_player_position": PermissionLevel.CREATIVE,
        "get_player_inventory": PermissionLevel.CREATIVE,
        "get_player_tags": PermissionLevel.CREATIVE,
        "get_player_score": PermissionLevel.CREATIVE,
        "send_message": PermissionLevel.CREATIVE,
        "get_chatbar_menu_triggers": PermissionLevel.CREATIVE,
        "interact_with_menu": PermissionLevel.CREATIVE,
    }

    def __init__(self, plugin: "MCAgent"):
        self.plugin = plugin
        self.full_permission_whitelist = plugin.full_permission_whitelist
        self.level1_permission_whitelist = plugin.level1_permission_whitelist
        self.dangerous_commands = plugin.dangerous_commands

    def get_player_permission_level(self, player: Player) -> PermissionLevel:
        if player.name in self.full_permission_whitelist:
            return PermissionLevel.FULL

        if player.name in self.plugin.whitelist:
            return PermissionLevel.OP

        try:
            if player.is_op():
                return PermissionLevel.OP
        except Exception:
            pass

        # 一级权限白名单和创造模式拥有相同的权限等级
        if player.name in self.level1_permission_whitelist:
            return PermissionLevel.CREATIVE

        if self._is_creative_mode(player):
            return PermissionLevel.CREATIVE

        return PermissionLevel.NONE

    def _is_creative_mode(self, player: Player) -> bool:
        try:
            command = f"/testfor @a[name={player.name},m=creative]"
            result = self.plugin.game_ctrl.sendwscmd_with_resp(command, timeout=3)
            if result.SuccessCount > 0:
                return True

            command2 = f"/testfor @a[name={player.name},m=1]"
            result2 = self.plugin.game_ctrl.sendwscmd_with_resp(command2, timeout=3)
            if result2.SuccessCount > 0:
                return True

            return False
        except Exception:
            return False

    def check_tool_permission(self, player: Player, tool_name: str) -> tuple[bool, str | None]:
        player_level = self.get_player_permission_level(player)

        if player_level == PermissionLevel.FULL:
            return True, None

        required_level = self.TOOL_PERMISSIONS.get(tool_name, PermissionLevel.CREATIVE)

        if player_level.value < required_level.value:
            error_msg = self._get_permission_error_message(player_level, required_level, tool_name)
            return False, error_msg

        return True, None

    def check_command_safety(self, player: Player, command: str) -> tuple[bool, str | None]:
        player_level = self.get_player_permission_level(player)
        if player_level == PermissionLevel.FULL:
            return True, None

        command_lower = command.lower().strip()
        for dangerous_cmd in self.dangerous_commands:
            if dangerous_cmd.lower() in command_lower:
                error_msg = f"§c§l拦截: 命令 '{command}' 包含危险操作 '{dangerous_cmd}'，已被阻止执行"
                return False, error_msg

        return True, None

    def _get_permission_error_message(self, player_level: PermissionLevel, required_level: PermissionLevel, tool_name: str) -> str:
        level_names = {
            PermissionLevel.NONE: "普通玩家",
            PermissionLevel.CREATIVE: "创造模式",
            PermissionLevel.OP: "OP权限",
            PermissionLevel.FULL: "完全权限"
        }

        current = level_names.get(player_level, "未知")
        required = level_names.get(required_level, "未知")

        return f"§c§l权限不足: 工具 '{tool_name}' 需要 {required} 权限，您当前为 {current}"

    def get_available_tools_for_player(self, player: Player) -> list[str]:
        player_level = self.get_player_permission_level(player)

        if player_level == PermissionLevel.FULL:
            return list(self.TOOL_PERMISSIONS.keys())

        available_tools = []
        for tool_name, required_level in self.TOOL_PERMISSIONS.items():
            if player_level.value >= required_level.value:
                available_tools.append(tool_name)

        return available_tools

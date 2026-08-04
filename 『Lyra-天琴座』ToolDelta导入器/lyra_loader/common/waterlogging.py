"""Java 含水方块的 Bedrock secondary 水层放置"""

from collections.abc import Callable

from tooldelta.internal.types import Packet_CommandOutput

from .parse_command import parse_command

WATER_COMMAND = 'minecraft:water ["liquid_depth"=0]'


def place_water_layer(
    sendaicmd: Callable[[str], object],
    sendaicmd_with_resp: Callable[[str], Packet_CommandOutput],
    position: tuple[int, int, int],
    verified_commands: set[str],
    rejected_commands: dict[str, str],
) -> tuple[bool, bool, str]:
    """放置静态水层, 返回 (是否发送成功、是否首次确认、错误详情)"""
    if WATER_COMMAND in rejected_commands:
        return False, False, rejected_commands[WATER_COMMAND]
    setblock = f"/setblock {position[0]} {position[1]} {position[2]} {WATER_COMMAND}"
    if WATER_COMMAND in verified_commands:
        sendaicmd(setblock)
        return True, False, ""
    ok, error = parse_command(sendaicmd_with_resp(setblock))
    if not ok:
        rejected_commands[WATER_COMMAND] = error
        return False, False, error
    verified_commands.add(WATER_COMMAND)
    return True, True, ""

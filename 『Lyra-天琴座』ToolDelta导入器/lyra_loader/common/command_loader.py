"""各基岩版格式共用的命令方块更新流程"""

import time
from typing import TYPE_CHECKING, Any

from tooldelta import fmts
from tooldelta.constants import PacketIDS

from .chunk_loading import chunk_preload
from .dimensions import COMMAND_MODE_NAMES

if TYPE_CHECKING:
    from ...__init__ import LyraSystem
    from .dimensions import Dimension


def load_command_blocks(
    plugin: "LyraSystem",
    command_data: list[dict[str, Any]],
    dimension: "Dimension",
    offset: tuple[int, int, int] = (0, 0, 0),
) -> None:
    """关闭命令方块后, 将更新包写入已放置的命令方块"""
    game_ctrl = plugin.game_ctrl
    started = time.perf_counter()
    sleep_time = 1 / plugin.config_mgr.CMD_LOAD_SPEED
    sent = 0
    fmts.print_inf("\n§e开始导入命令方块数据")
    fmts.print_inf("§c❀ 警告: 即将关闭 commandblocksenabled")
    game_ctrl.sendaicmd("/gamerule commandblocksenabled false")
    try:
        for original in command_data:
            packet = dict(original)
            relative = packet["Position"]
            x = int(relative[0]) + offset[0]
            y = int(relative[1]) + offset[1]
            z = int(relative[2]) + offset[2]
            packet["Position"] = [x, y, z]
            chunk_preload(
                game_ctrl.sendaicmd,
                game_ctrl.sendaicmd_with_resp,
                game_ctrl.bot_name,
                dimension.command_id,
                x,
                y,
                z,
            )
            game_ctrl.sendPacket(PacketIDS.IDCommandBlockUpdate, packet)
            fmts.print_inf(
                f"§a命令更新包已发送 - 坐标: ({x},{y},{z}), "
                f"命令: {packet['Command']}, "
                f"类型: {COMMAND_MODE_NAMES.get(int(packet['Mode']), '未知')}, "
                f"条件: {packet['Conditional']}"
            )
            sent += 1
            time.sleep(sleep_time)
    finally:
        elapsed = time.perf_counter() - started
        fmts.print_inf(f"\n§a命令方块更新包已发送 {sent} 个, 共耗时 {elapsed:.6f} 秒")
        fmts.print_inf(
            "§c❀ 安全提示: commandblocksenabled 已保持关闭; "
            "请检查所有命令后再自行决定是否启用"
        )

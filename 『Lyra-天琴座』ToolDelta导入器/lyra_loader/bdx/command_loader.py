"""写入命令方块"""

import time
from typing import TYPE_CHECKING, Any

from tooldelta import fmts
from tooldelta.constants import PacketIDS

from ..common.dimensions import COMMAND_MODE_NAMES

if TYPE_CHECKING:
    from ...__init__ import LyraSystem
    from ..common.dimensions import Dimension


class CommandLoader:
    def __init__(self, plugin: "LyraSystem") -> None:
        self.game_ctrl = plugin.game_ctrl
        self.cfg = plugin.config_mgr
        self.sendaicmd = plugin.game_ctrl.sendaicmd
        self.sendaicmd_with_resp = plugin.game_ctrl.sendaicmd_with_resp

    def load_commands(
        self, command_data: list[dict[str, Any]], dimension: "Dimension"
    ) -> None:
        started = time.perf_counter()
        sleep_time = 1 / self.cfg.CMD_LOAD_SPEED
        sent = 0
        fmts.print_inf("\n§e开始导入命令方块数据")
        fmts.print_inf(
            "§c❀ 警告: 即将关闭 commandblocksenabled"
        )
        self.sendaicmd("/gamerule commandblocksenabled false")
        try:
            for original in command_data:
                packet = dict(original)
                x, y, z = (int(value) for value in packet["Position"])
                self.sendaicmd(
                    f'/execute in {dimension.command_id} run tp @a[name="{self.game_ctrl.bot_name}"] {x} {y} {z}'
                )
                self.sendaicmd_with_resp(f"/testforblock {x} {y} {z} air")
                self.game_ctrl.sendPacket(PacketIDS.IDCommandBlockUpdate, packet)
                fmts.print_inf(
                    f"§a命令更新包已发送 - 坐标: ({x},{y},{z}), "
                    f"命令: {packet['Command']}, 类型: {COMMAND_MODE_NAMES.get(int(packet['Mode']), '未知')}, "
                    f"条件: {packet['Conditional']}"
                )
                sent += 1
                time.sleep(sleep_time)
        finally:
            elapsed = time.perf_counter() - started
            fmts.print_inf(
                f"\n§a命令方块更新包已发送 {sent} 个, 共耗时 {elapsed:.6f} 秒"
            )
            fmts.print_inf(
                "§c❀ 安全提示: commandblocksenabled 已保持关闭; 请检查所有命令后再自行决定是否启用"
            )

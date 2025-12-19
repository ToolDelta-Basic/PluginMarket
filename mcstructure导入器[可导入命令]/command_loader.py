"""命令导入器"""

from tooldelta import fmts, TYPE_CHECKING
from tooldelta.constants import PacketIDS
import time

if TYPE_CHECKING:
    from .__init__ import MCStructureLoader


class CommandLoader:
    def __init__(self, plugin: "MCStructureLoader") -> None:
        self.game_ctrl = plugin.game_ctrl
        self.cfg = plugin.config_mgr
        self.sendanycmd = plugin.core.sendanycmd

    def load_command(
        self,
        command_data: list,
        dim: str,
        start_x: int,
        start_y: int,
        start_z: int,
    ) -> None:
        start_time = time.perf_counter()
        sleep_time = 1 / self.cfg.CMD_LOAD_SPEED
        set_count = 0
        fmts.print_inf("\n§e开始导入命令")
        fmts.print_inf("§c警告: 导入命令时需要关闭 启用命令方块")
        self.sendanycmd("/gamerule commandblocksenabled false")
        for packet in command_data:
            position = packet["Position"]
            x = position[0] + start_x
            y = position[1] + start_y
            z = position[2] + start_z
            packet["Position"] = [x, y, z]
            self.sendanycmd(
                f'/execute in {dim} run tp @a[name="{self.game_ctrl.bot_name}"] {x} {y} {z}'
            )
            OutputMessages = self.game_ctrl.sendwscmd_with_resp(
                f"/testforblock {x} {y} {z} air"
            ).as_dict["OutputMessages"][0]
            Success = OutputMessages["Success"]
            Parameters = OutputMessages["Parameters"]
            if Success:
                continue
            if not (isinstance(Parameters, list) and len(Parameters) >= 4):
                continue
            tile_name = Parameters[3]
            if tile_name == "%tile.command_block.name":
                cb_mode = 0
            elif tile_name == "%tile.repeating_command_block.name":
                cb_mode = 1
            elif tile_name == "%tile.chain_command_block.name":
                cb_mode = 2
            else:
                continue
            packet["Mode"] = cb_mode
            self.game_ctrl.sendPacket(PacketIDS.IDCommandBlockUpdate, packet)
            fmts.print_inf(
                f"\n§a导入命令 - 坐标: ({x},{y},{z}), 命令: {packet['Command']}, 类型: {tile_name}, 条件: {packet['Conditional']}"
            )
            set_count += 1
            time.sleep(sleep_time)

        elapsed = time.perf_counter() - start_time
        fmts.print_inf(
            f"\n§a已完成命令导入, 导入了 {set_count} 条命令, 共耗时 {elapsed:.6f} 秒"
        )

"""放置方块"""

import math
import time
from collections import Counter
from typing import TYPE_CHECKING, cast

from tooldelta import fmts
from ..common.parse_command import parse_command
from ..common.chunk_loading import chunk_preload
from ..common.chunk_clear import chunk_clear

if TYPE_CHECKING:
    from ...__init__ import LyraSystem
    from ..common.dimensions import Dimension
    from .command_loader import CommandLoader
    from .nbt_parser import MCStructureData

CHUNK_SIZE = 16


class ChunkPainter:
    def __init__(self, plugin: "LyraSystem") -> None:
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl
        self.cfg = plugin.config_mgr
        self.sendaicmd = plugin.game_ctrl.sendaicmd
        self.sendaicmd_with_resp = plugin.game_ctrl.sendaicmd_with_resp

    def paint(
        self,
        structure: "MCStructureData",
        dim: "Dimension",
        start_x: int,
        start_y: int,
        start_z: int,
    ) -> None:
        size_x, size_y, size_z = structure.size_x, structure.size_y, structure.size_z
        chunks_x = math.ceil(size_x / CHUNK_SIZE)
        chunks_z = math.ceil(size_z / CHUNK_SIZE)
        total_chunks = chunks_x * chunks_z
        palette_size = len(structure.block_palette)
        sleep_time = 1 / self.cfg.BLOCK_LOAD_SPEED
        verified: set[str] = set()
        rejected: dict[str, str] = {}
        rejected_counts: Counter[str] = Counter()
        rejected_examples: dict[str, tuple[int, int, int]] = {}
        invalid_indexes: Counter[int] = Counter()
        invalid_examples: dict[int, tuple[int, int, int]] = {}
        confirmed_success = 0
        async_sent = 0
        started = time.perf_counter()

        fmts.print_inf(
            f"§emcstructure建筑大小: {size_x} x {size_y} x {size_z}, "
            f"区块数: {chunks_x} x {chunks_z} = {total_chunks}"
        )
        chunk_number = 0
        for cx in range(chunks_x):
            cz_values = range(chunks_z) if cx % 2 == 0 else range(chunks_z - 1, -1, -1)
            for cz in cz_values:
                chunk_number += 1
                x0, z0 = cx * CHUNK_SIZE, cz * CHUNK_SIZE
                x_size = min(CHUNK_SIZE, size_x - x0)
                z_size = min(CHUNK_SIZE, size_z - z0)
                tp_x, tp_z = start_x + x0, start_z + z0
                fmts.print_inf(
                    f"§e当前区块 ({cx},{cz}) ({chunk_number}/{total_chunks})"
                )
                chunk_preload(
                    self.sendaicmd,
                    self.sendaicmd_with_resp,
                    self.game_ctrl.bot_name,
                    dim.command_id,
                    tp_x,
                    start_y,
                    tp_z,
                )
                if self.cfg.INCLUDE_AIR:
                    chunk_clear(
                        self.sendaicmd,
                        (start_x + x0, start_y, start_z + z0),
                        (
                            start_x + x0 + x_size - 1,
                            start_y + size_y - 1,
                            start_z + z0 + z_size - 1,
                        ),
                    )
                    fmts.print_inf(f"§a区块 ({cx},{cz}) 清理已完成")

                chunk_success = 0
                for y in range(size_y):
                    for local_x in range(x_size):
                        for local_z in range(z_size):
                            x, z = x0 + local_x, z0 + local_z
                            position = (x, y, z)
                            # Bedrock 双层方块必须先放 secondary, 再放 primary
                            for layer in (1, 0):
                                palette_index = structure.palette_index(layer, x, y, z)
                                if (
                                    palette_index == -1
                                    or palette_index in structure.air_indexes
                                ):
                                    continue
                                if not 0 <= palette_index < palette_size:
                                    invalid_indexes[palette_index] += 1
                                    invalid_examples.setdefault(palette_index, position)
                                    continue
                                command = structure.block_palette[palette_index]
                                if command in rejected:
                                    rejected_counts[command] += 1
                                    rejected_examples.setdefault(command, position)
                                    continue
                                setblock = (
                                    f"/setblock {start_x + x} {start_y + y} "
                                    f"{start_z + z} {command}"
                                )
                                if command not in verified:
                                    ok, error = parse_command(
                                        self.sendaicmd_with_resp(setblock)
                                    )
                                    if not ok:
                                        rejected[command] = error
                                        rejected_counts[command] += 1
                                        rejected_examples.setdefault(command, position)
                                        continue
                                    verified.add(command)
                                    confirmed_success += 1
                                else:
                                    self.sendaicmd(setblock)
                                    async_sent += 1
                                chunk_success += 1
                                time.sleep(sleep_time)
                fmts.print_inf(
                    f"§a区块 ({cx},{cz}) 导入已完成: 已成功处理区块内 {chunk_success} 方块, "
                    f"当前区块进度: {chunk_number}/{total_chunks} "
                    f"({(chunk_number / total_chunks) * 100:.1f}%)"
                )

        elapsed = time.perf_counter() - started
        fmts.print_inf(
            f"\n§a已完成方块导入, 首次确认成功 {confirmed_success} 方块, "
            f"异步发送 {async_sent} 方块, 非法Palette索引 "
            f"{sum(invalid_indexes.values())} 方块, 服务器拒绝 "
            f"{sum(rejected_counts.values())} 方块, 共耗时 {elapsed:.6f} 秒"
        )
        if invalid_indexes:
            fmts.print_inf("§6❀ 警告: 以下非法Palette索引已跳过:")
            for index, count in invalid_indexes.most_common():
                fmts.print_inf(
                    f"§6- {index}: {count} 个, 示例相对坐标 {invalid_examples[index]}"
                )
        if rejected_counts:
            fmts.print_inf("§c❀ 警告: 以下方块状态被服务器拒绝:")
            for command, count in rejected_counts.most_common():
                fmts.print_inf(
                    f"§c- {command}: {count} 个, 示例相对坐标 "
                    f"{rejected_examples[command]}, 返回: {rejected[command]}"
                )
        if self.cfg.INCLUDE_CMD and structure.command_data:
            command_loader = cast("CommandLoader", self.plugin.command_loader)
            command_loader.load_commands(
                structure.command_data, dim, start_x, start_y, start_z
            )

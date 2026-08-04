"""放置方块"""

import math
import time
from collections import Counter
from typing import TYPE_CHECKING

from tooldelta import fmts
from ..common.parse_command import parse_command
from ..common.waterlogging import WATER_COMMAND, place_water_layer
from ..common.chunk_loading import chunk_preload
from ..common.chunk_clear import chunk_clear

if TYPE_CHECKING:
    from ...__init__ import LyraSystem
    from ..common.dimensions import Dimension
    from .schem_parser import SchemData

CHUNK_SIZE = 16


class ChunkPainter:
    def __init__(self, plugin: "LyraSystem") -> None:
        self.game_ctrl = plugin.game_ctrl
        self.cfg = plugin.config_mgr
        self.converter = plugin.converter
        self.sendaicmd = plugin.game_ctrl.sendaicmd
        self.sendaicmd_with_resp = plugin.game_ctrl.sendaicmd_with_resp

    def paint(
        self,
        schem: "SchemData",
        dim: "Dimension",
        start_x: int,
        start_y: int,
        start_z: int,
    ) -> None:
        width, height, length = schem.width, schem.height, schem.length
        chunks_x = math.ceil(width / CHUNK_SIZE)
        chunks_z = math.ceil(length / CHUNK_SIZE)
        total_chunks = chunks_x * chunks_z
        converted_palette = [self.converter.convert(state) for state in schem.palette]
        conversion_missing: Counter[str] = Counter()
        missing_examples: dict[str, tuple[int, int, int]] = {}
        water_layers = 0
        verified_commands: set[str] = set()
        rejected_commands: dict[str, str] = {}
        server_rejected: Counter[str] = Counter()
        rejected_examples: dict[str, tuple[int, int, int]] = {}
        confirmed_success = 0
        async_sent = 0
        started = time.perf_counter()
        sleep_time = 1 / self.cfg.LOAD_SPEED

        fmts.print_inf(
            f"§eschem建筑大小: {width} x {height} x {length}, "
            f"区块数: {chunks_x} x {chunks_z} = {total_chunks}"
        )
        chunk_number = 0
        for cz in range(chunks_z):
            cx_values = range(chunks_x) if cz % 2 == 0 else range(chunks_x - 1, -1, -1)
            for cx in cx_values:
                chunk_number += 1
                x0, z0 = cx * CHUNK_SIZE, cz * CHUNK_SIZE
                x_size = min(CHUNK_SIZE, width - x0)
                z_size = min(CHUNK_SIZE, length - z0)
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
                            start_y + height - 1,
                            start_z + z0 + z_size - 1,
                        ),
                    )
                    fmts.print_inf(f"§a区块 ({cx},{cz}) 清理已完成")

                chunk_success = 0
                for local_y in range(height):
                    for local_z in range(z0, z0 + z_size):
                        for local_x in range(x0, x0 + x_size):
                            palette_id = schem.palette_id(local_y, local_z, local_x)
                            java_state = schem.palette[palette_id]
                            converted = converted_palette[palette_id]
                            if converted is None:
                                conversion_missing[java_state] += 1
                                missing_examples.setdefault(
                                    java_state, (local_x, local_y, local_z)
                                )
                                continue
                            if converted.command == "minecraft:air":
                                continue
                            gx, gy, gz = (
                                start_x + local_x,
                                start_y + local_y,
                                start_z + local_z,
                            )
                            command = converted.command
                            if command in rejected_commands:
                                server_rejected[java_state] += 1
                                rejected_examples.setdefault(
                                    java_state, (local_x, local_y, local_z)
                                )
                                continue
                            if converted.waterlogged:
                                water_ok, water_confirmed, _ = place_water_layer(
                                    self.sendaicmd,
                                    self.sendaicmd_with_resp,
                                    (gx, gy, gz),
                                    verified_commands,
                                    rejected_commands,
                                )
                                if water_ok:
                                    water_layers += 1
                                    if water_confirmed:
                                        confirmed_success += 1
                                    else:
                                        async_sent += 1
                                    time.sleep(sleep_time)
                                else:
                                    server_rejected[java_state] += 1
                                    rejected_examples.setdefault(
                                        java_state, (local_x, local_y, local_z)
                                    )
                            setblock = f"/setblock {gx} {gy} {gz} {command}"
                            if command not in verified_commands:
                                response = self.sendaicmd_with_resp(setblock)
                                command_ok, error = parse_command(response)
                                if not command_ok:
                                    rejected_commands[command] = error
                                    server_rejected[java_state] += 1
                                    rejected_examples.setdefault(
                                        java_state, (local_x, local_y, local_z)
                                    )
                                    continue
                                verified_commands.add(command)
                                confirmed_success += 1
                            else:
                                self.sendaicmd(setblock)
                                async_sent += 1
                            chunk_success += 1
                            time.sleep(sleep_time)
                fmts.print_inf(
                    f"§a区块 ({cx},{cz}) 导入已完成: 已成功处理区块内 "
                    f"{chunk_success} 方块, 当前区块进度: "
                    f"{chunk_number}/{total_chunks} "
                    f"({(chunk_number / total_chunks) * 100:.1f}%)"
                )

        elapsed = time.perf_counter() - started
        fmts.print_inf(
            f"\n§a已完成方块导入, 首次确认成功 {confirmed_success} 方块, "
            f"异步发送 {async_sent} 方块, 转换缺失 "
            f"{sum(conversion_missing.values())} 方块, 服务器拒绝 "
            f"{sum(server_rejected.values())} 方块, 恢复含水层 "
            f"{water_layers} 个, 共耗时 {elapsed:.6f} 秒"
        )
        if conversion_missing:
            fmts.print_inf("§6❀ 警告: 以下Java方块状态没有可用转换:")
            for state, count in conversion_missing.most_common():
                pos = missing_examples[state]
                fmts.print_inf(f"§6- {state}: {count} 个, 示例相对坐标 {pos}")
        if server_rejected:
            fmts.print_inf("§c❀ 警告: 以下转换结果被服务器拒绝:")
            for state, count in server_rejected.most_common():
                converted = self.converter.convert(state)
                command = converted.command if converted is not None else ""
                error = rejected_commands.get(
                    command, rejected_commands.get(WATER_COMMAND, "未知错误")
                )
                pos = rejected_examples[state]
                fmts.print_inf(
                    f"§c- {state}: {count} 个, 示例相对坐标 {pos}, 返回: {error}"
                )

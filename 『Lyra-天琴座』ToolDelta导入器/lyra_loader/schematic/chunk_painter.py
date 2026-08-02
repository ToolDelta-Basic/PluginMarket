"""放置方块"""

import math
import time
from collections import Counter
from typing import TYPE_CHECKING

from tooldelta import fmts
from tooldelta.internal.types import Packet_CommandOutput

if TYPE_CHECKING:
    from ...__init__ import LyraSystem
    from ..common.dimensions import Dimension
    from .nbt_parser import SchematicData

CHUNK_SIZE = 16


class ChunkPainter:
    def __init__(self, plugin: "LyraSystem") -> None:
        self.game_ctrl = plugin.game_ctrl
        self.cfg = plugin.config_mgr
        self.sendaicmd = plugin.game_ctrl.sendaicmd
        self.sendaicmd_with_resp = plugin.game_ctrl.sendaicmd_with_resp

    def paint(
        self,
        schematic: "SchematicData",
        block_mapping: dict[int, dict[int, str | None]],
        dim: "Dimension",
        start_x: int,
        start_y: int,
        start_z: int,
    ) -> None:
        width, height, length = schematic.width, schematic.height, schematic.length
        chunks_x = math.ceil(width / CHUNK_SIZE)
        chunks_z = math.ceil(length / CHUNK_SIZE)
        total_chunks = chunks_x * chunks_z
        conversion_missing: Counter[tuple[int, int]] = Counter()
        missing_examples: dict[tuple[int, int], tuple[int, int, int]] = {}
        explicit_skips: Counter[tuple[int, int]] = Counter()
        skip_examples: dict[tuple[int, int], tuple[int, int, int]] = {}
        verified_commands: set[str] = set()
        rejected_commands: dict[str, str] = {}
        server_rejected: Counter[str] = Counter()
        rejected_examples: dict[str, tuple[int, int, int]] = {}
        confirmed_success = 0
        async_sent = 0
        sleep_time = 1 / self.cfg.LOAD_SPEED
        started = time.perf_counter()

        fmts.print_inf(
            f"§eSchematic建筑大小: {width} x {height} x {length}, "
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
                self.sendaicmd(
                    f'/execute in {dim.command_id} run tp @a[name="{self.game_ctrl.bot_name}"] {tp_x} {start_y} {tp_z}'
                )
                self.sendaicmd_with_resp(f"/testforblock {tp_x} {start_y} {tp_z} air")
                if self.cfg.INCLUDE_AIR:
                    self._clear_chunk(
                        start_x, start_y, start_z, x0, z0, x_size, z_size, height
                    )
                    fmts.print_inf(f"§a区块 ({cx},{cz}) 清理已完成")

                chunk_success = 0
                for local_y in range(height):
                    for local_z in range(z0, z0 + z_size):
                        for local_x in range(x0, x0 + x_size):
                            block_id = schematic.block_id(local_y, local_z, local_x)
                            if block_id == 0:
                                continue
                            metadata = int(schematic.data[local_y, local_z, local_x])
                            key = (block_id, metadata)
                            command = block_mapping.get(block_id, {}).get(metadata)
                            pos = (local_x, local_y, local_z)
                            if command is None:
                                if (
                                    block_id in block_mapping
                                    and metadata in block_mapping[block_id]
                                ):
                                    explicit_skips[key] += 1
                                    skip_examples.setdefault(key, pos)
                                else:
                                    conversion_missing[key] += 1
                                    missing_examples.setdefault(key, pos)
                                continue
                            if command in rejected_commands:
                                server_rejected[command] += 1
                                rejected_examples.setdefault(command, pos)
                                continue
                            setblock = f"/setblock {start_x + local_x} {start_y + local_y} {start_z + local_z} {command}"
                            if command not in verified_commands:
                                ok, error = _command_success(
                                    self.sendaicmd_with_resp(setblock)
                                )
                                if not ok:
                                    rejected_commands[command] = error
                                    server_rejected[command] += 1
                                    rejected_examples.setdefault(command, pos)
                                    continue
                                verified_commands.add(command)
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
            f"异步发送 {async_sent} 方块, 转换缺失 {sum(conversion_missing.values())} 方块, "
            f"明确跳过 {sum(explicit_skips.values())} 方块, 服务器拒绝 "
            f"{sum(server_rejected.values())} 方块, 共耗时 {elapsed:.6f} 秒"
        )
        if conversion_missing:
            fmts.print_inf("§6❀ 警告: 以下Java 1.12方块 ID/Data 没有可用转换:")
            for key, count in conversion_missing.most_common():
                fmts.print_inf(
                    f"§6- {key[0]}:{key[1]}: {count} 个, 示例相对坐标 {missing_examples[key]}"
                )
        if explicit_skips:
            fmts.print_inf("§6❀ 警告: 以下方块无法安全放置，已明确跳过:")
            for key, count in explicit_skips.most_common():
                fmts.print_inf(
                    f"§6- {key[0]}:{key[1]}: {count} 个, 示例相对坐标 {skip_examples[key]}"
                )
        if server_rejected:
            fmts.print_inf("§c❀ 警告: 以下转换结果被服务器拒绝:")
            for command, count in server_rejected.most_common():
                fmts.print_inf(
                    f"§c- {command}: {count} 个, 示例相对坐标 {rejected_examples[command]}, "
                    f"返回: {rejected_commands[command]}"
                )

    def _clear_chunk(
        self,
        start_x: int,
        start_y: int,
        start_z: int,
        x0: int,
        z0: int,
        x_size: int,
        z_size: int,
        height: int,
    ) -> None:
        x1, z1 = start_x + x0, start_z + z0
        x2, z2 = x1 + x_size - 1, z1 + z_size - 1
        for y0 in range(0, height, CHUNK_SIZE):
            y2 = start_y + min(height - 1, y0 + CHUNK_SIZE - 1)
            self.sendaicmd(f"/fill {x1} {start_y + y0} {z1} {x2} {y2} {z2} air")


def _command_success(response: Packet_CommandOutput) -> tuple[bool, str]:
    try:
        messages = response.as_dict.get("OutputMessages", [])
        if not messages:
            return False, "命令响应没有 OutputMessages"
        message = messages[0]
        if bool(message.get("Success")):
            return True, ""
        detail = str(
            message.get("Message") or message.get("MessageId") or "命令执行失败"
        )
        if parameters := message.get("Parameters"):
            detail += f"; Parameters={parameters}"
        return False, detail
    except Exception as error:
        return False, f"无法解析命令响应: {error}"

"""放置方块"""

import time
from collections import Counter
from typing import TYPE_CHECKING

from tooldelta import fmts
from ..common.command_loader import load_command_blocks
from ..common.parse_command import parse_command
from ..common.chunk_loading import chunk_preload
from ..common.chunk_clear import chunk_clear
from .world_reader import COMMAND_MODES, command_packet

if TYPE_CHECKING:
    from ...__init__ import LyraSystem
    from ..common.dimensions import Dimension
    from .world_reader import MCWorldData

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
        world: "MCWorldData",
        dimension: "Dimension",
        target_x: int,
        target_y: int,
        target_z: int,
    ) -> None:
        source_min, source_max = world.source_min, world.source_max
        min_cx, max_cx = source_min[0] >> 4, source_max[0] >> 4
        min_cz, max_cz = source_min[2] >> 4, source_max[2] >> 4
        total_chunks = (max_cx - min_cx + 1) * (max_cz - min_cz + 1)
        offset = (
            target_x - source_min[0],
            target_y - source_min[1],
            target_z - source_min[2],
        )
        verified: set[str] = set()
        rejected: dict[str, str] = {}
        rejected_counts: Counter[str] = Counter()
        rejected_examples: dict[str, tuple[int, int, int]] = {}
        decode_errors: Counter[str] = Counter()
        extra_layers = 0
        confirmed_success = 0
        async_sent = 0
        ignored_block_entities = 0
        invalid_commands = 0
        entity_count = 0
        command_data: list[dict] = []
        sleep_time = 1 / self.cfg.BLOCK_LOAD_SPEED
        started = time.perf_counter()

        size = world.size
        fmts.print_inf(
            f"§emcworld选区大小: {size[0]} x {size[1]} x {size[2]}, 区块数: {total_chunks}"
        )
        chunk_number = 0
        for row, cz in enumerate(range(min_cz, max_cz + 1)):
            cx_values = (
                range(min_cx, max_cx + 1)
                if row % 2 == 0
                else range(max_cx, min_cx - 1, -1)
            )
            for cx in cx_values:
                chunk_number += 1
                x1 = max(source_min[0], cx << 4)
                x2 = min(source_max[0], (cx << 4) + 15)
                z1 = max(source_min[2], cz << 4)
                z2 = min(source_max[2], (cz << 4) + 15)
                tx, tz = x1 + offset[0], z1 + offset[2]
                fmts.print_inf(
                    f"§e当前源区块 ({cx},{cz}) ({chunk_number}/{total_chunks})"
                )
                chunk_preload(
                    self.sendaicmd,
                    self.sendaicmd_with_resp,
                    self.game_ctrl.bot_name,
                    dimension.command_id,
                    tx,
                    target_y,
                    tz,
                )
                chunk_success = 0
                command_modes: dict[tuple[int, int, int], int] = {}
                for cy in range(source_min[1] >> 4, (source_max[1] >> 4) + 1):
                    sy1 = max(source_min[1], cy << 4)
                    sy2 = min(source_max[1], (cy << 4) + 15)
                    try:
                        subchunk = world.read_subchunk(cx, cy, cz)
                    except ValueError as error:
                        decode_errors[str(error)] += 1
                        continue
                    # 缺失 SubChunk 才能确定为空气, 损坏或未知版本不会清理目标区域
                    if self.cfg.INCLUDE_AIR:
                        chunk_clear(
                            self.sendaicmd,
                            (x1 + offset[0], sy1 + offset[1], z1 + offset[2]),
                            (x2 + offset[0], sy2 + offset[1], z2 + offset[2]),
                        )
                    if subchunk is None:
                        continue
                    extra_layers += subchunk.extra_layers
                    for sy in range(sy1, sy2 + 1):
                        local_y = sy & 15
                        for sz in range(z1, z2 + 1):
                            local_z = sz & 15
                            for sx in range(x1, x2 + 1):
                                local_x = sx & 15
                                position = (sx, sy, sz)
                                relative = (
                                    position[0] - source_min[0],
                                    position[1] - source_min[1],
                                    position[2] - source_min[2],
                                )
                                for layer in (1, 0):
                                    entry = subchunk.palette_entry(
                                        layer, local_x, local_y, local_z
                                    )
                                    if entry is None or entry.air:
                                        continue
                                    command = entry.command
                                    if command in rejected:
                                        rejected_counts[command] += 1
                                        rejected_examples.setdefault(command, relative)
                                        continue
                                    target = (
                                        position[0] + offset[0],
                                        position[1] + offset[1],
                                        position[2] + offset[2],
                                    )
                                    setblock = f"/setblock {target[0]} {target[1]} {target[2]} {command}"
                                    if command not in verified:
                                        ok, error = parse_command(
                                            self.sendaicmd_with_resp(setblock)
                                        )
                                        if not ok:
                                            rejected[command] = error
                                            rejected_counts[command] += 1
                                            rejected_examples.setdefault(
                                                command, relative
                                            )
                                            continue
                                        verified.add(command)
                                        confirmed_success += 1
                                    else:
                                        self.sendaicmd(setblock)
                                        async_sent += 1
                                    if layer == 0 and entry.name in COMMAND_MODES:
                                        command_modes[position] = COMMAND_MODES[
                                            entry.name
                                        ]
                                    chunk_success += 1
                                    time.sleep(sleep_time)
                if self.cfg.INCLUDE_AIR:
                    fmts.print_inf(f"§a源区块 ({cx},{cz}) 对应目标空气区域处理已完成")

                if self.cfg.INCLUDE_CMD:
                    for entity in world.read_block_entities(cx, cz):
                        position = _entity_position(entity)
                        if position is None or not _inside(
                            position, source_min, source_max
                        ):
                            continue
                        if str(entity.get("id", "")) != "CommandBlock":
                            ignored_block_entities += 1
                            continue
                        mode = command_modes.get(position)
                        if mode is None:
                            invalid_commands += 1
                            continue
                        target = (
                            position[0] + offset[0],
                            position[1] + offset[1],
                            position[2] + offset[2],
                        )
                        command_data.append(command_packet(entity, mode, target))
                else:
                    for entity in world.read_block_entities(cx, cz):
                        position = _entity_position(entity)
                        if position is not None and _inside(
                            position, source_min, source_max
                        ):
                            ignored_block_entities += 1
                entity_count += world.count_entities(cx, cz)
                fmts.print_inf(
                    f"§a源区块 ({cx},{cz}) 导入已完成: 已成功处理区块内 {chunk_success} 方块, "
                    f"当前区块进度: {chunk_number}/{total_chunks} "
                    f"({chunk_number / total_chunks * 100:.1f}%)"
                )

        elapsed = time.perf_counter() - started
        fmts.print_inf(
            f"\n§a已完成方块导入, 首次确认成功 {confirmed_success} 方块, "
            f"异步发送 {async_sent} 方块, 服务器拒绝 {sum(rejected_counts.values())} 方块, "
            f"共耗时 {elapsed:.6f} 秒"
        )
        if rejected_counts:
            fmts.print_inf("§c❀ 警告: 以下方块状态被服务器拒绝:")
            for command, count in rejected_counts.most_common():
                fmts.print_inf(
                    f"§c- {command}: {count} 个, 示例相对坐标 {rejected_examples[command]}, "
                    f"返回: {rejected[command]}"
                )
        if decode_errors:
            fmts.print_inf("§6❀ 警告: 以下 SubChunk 无法解析并已跳过:")
            for error, count in decode_errors.most_common():
                fmts.print_inf(f"§6- {error}: {count} 个")
        if extra_layers:
            fmts.print_inf(
                f"§6❀ 警告: 已忽略 {extra_layers} 个超过 secondary 的额外方块层"
            )
        if ignored_block_entities or entity_count:
            fmts.print_inf(
                f"§6❀ 警告: 已忽略非命令方块实体 {ignored_block_entities} 个、实体 {entity_count} 个"
            )
        if invalid_commands:
            fmts.print_inf(
                f"§6❀ 警告: 已跳过 {invalid_commands} 条无法与命令方块Palette对应的数据"
            )
        if self.cfg.INCLUDE_CMD and command_data:
            load_command_blocks(self.plugin, command_data, dimension)


def _inside(
    position: tuple[int, int, int],
    minimum: tuple[int, int, int],
    maximum: tuple[int, int, int],
) -> bool:
    return all(minimum[i] <= position[i] <= maximum[i] for i in range(3))


def _entity_position(entity: dict) -> tuple[int, int, int] | None:
    try:
        return tuple(int(entity[axis]) for axis in ("x", "y", "z"))  # type: ignore[return-value]
    except (KeyError, TypeError, ValueError):
        return None

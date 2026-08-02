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
    from .litematic_parser import LitematicData, LitematicRegion

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
        structure: "LitematicData",
        dim: "Dimension",
        start_x: int,
        start_y: int,
        start_z: int,
    ) -> None:
        dimensions = structure.dimensions
        total_chunks = sum(
            math.ceil(region.dimensions[0] / CHUNK_SIZE)
            * math.ceil(region.dimensions[2] / CHUNK_SIZE)
            for region in structure.regions
        )
        offset = (
            start_x - structure.minimum[0],
            start_y - structure.minimum[1],
            start_z - structure.minimum[2],
        )
        conversion_missing: Counter[str] = Counter()
        missing_examples: dict[str, tuple[int, int, int]] = {}
        degraded: Counter[str] = Counter()
        verified_commands: set[str] = set()
        rejected_commands: dict[str, str] = {}
        server_rejected: Counter[str] = Counter()
        rejected_examples: dict[str, tuple[int, int, int]] = {}
        confirmed_success = 0
        async_sent = 0
        chunk_number = 0
        started = time.perf_counter()
        sleep_time = 1 / self.cfg.LOAD_SPEED

        fmts.print_inf(
            f"§elitematic建筑大小: {dimensions[0]} x {dimensions[1]} x {dimensions[2]}, "
            f"Region数: {len(structure.regions)}, 区块数: {total_chunks}"
        )
        for region_number, region in enumerate(structure.regions, 1):
            sx, sy, sz = region.dimensions
            chunks_x, chunks_z = math.ceil(sx / CHUNK_SIZE), math.ceil(sz / CHUNK_SIZE)
            converted_palette = [
                self.converter.convert(state) for state in region.palette
            ]
            fmts.print_inf(
                f"§e正在导入 Region {region_number}/{len(structure.regions)}: {region.name} "
                f"({sx} x {sy} x {sz})"
            )
            for cz in range(chunks_z):
                cx_values = (
                    range(chunks_x) if cz % 2 == 0 else range(chunks_x - 1, -1, -1)
                )
                for cx in cx_values:
                    chunk_number += 1
                    x0, z0 = cx * CHUNK_SIZE, cz * CHUNK_SIZE
                    x_size, z_size = min(CHUNK_SIZE, sx - x0), min(CHUNK_SIZE, sz - z0)
                    first = region.relative_position(x0, 0, z0)
                    tp = (
                        first[0] + offset[0],
                        first[1] + offset[1],
                        first[2] + offset[2],
                    )
                    fmts.print_inf(
                        f"§e当前区块 ({cx},{cz}) ({chunk_number}/{total_chunks})"
                    )
                    self.sendaicmd(
                        f'/execute in {dim.command_id} run tp @a[name="{self.game_ctrl.bot_name}"] {tp[0]} {tp[1]} {tp[2]}'
                    )
                    self.sendaicmd_with_resp(
                        f"/testforblock {tp[0]} {tp[1]} {tp[2]} air"
                    )
                    if self.cfg.INCLUDE_AIR:
                        self._clear_chunk(region, offset, x0, z0, x_size, z_size)
                        fmts.print_inf(f"§a区块 ({cx},{cz}) 清理已完成")

                    chunk_success = 0
                    for local_y in range(sy):
                        for local_z in range(z0, z0 + z_size):
                            for local_x in range(x0, x0 + x_size):
                                palette_id = region.palette_id(
                                    local_x, local_y, local_z
                                )
                                java_state = region.palette[palette_id]
                                converted = converted_palette[palette_id]
                                relative = region.relative_position(
                                    local_x, local_y, local_z
                                )
                                example = (
                                    relative[0] - structure.minimum[0],
                                    relative[1] - structure.minimum[1],
                                    relative[2] - structure.minimum[2],
                                )
                                if converted is None:
                                    conversion_missing[java_state] += 1
                                    missing_examples.setdefault(java_state, example)
                                    continue
                                if converted.command == "minecraft:air":
                                    continue
                                target = (
                                    relative[0] + offset[0],
                                    relative[1] + offset[1],
                                    relative[2] + offset[2],
                                )
                                command = converted.command
                                if command in rejected_commands:
                                    server_rejected[java_state] += 1
                                    rejected_examples.setdefault(java_state, example)
                                    continue
                                setblock = f"/setblock {target[0]} {target[1]} {target[2]} {command}"
                                if command not in verified_commands:
                                    response = self.sendaicmd_with_resp(setblock)
                                    ok, error = _command_success(response)
                                    if not ok:
                                        rejected_commands[command] = error
                                        server_rejected[java_state] += 1
                                        rejected_examples.setdefault(
                                            java_state, example
                                        )
                                        continue
                                    verified_commands.add(command)
                                    confirmed_success += 1
                                else:
                                    self.sendaicmd(setblock)
                                    async_sent += 1
                                if converted.waterlogged:
                                    degraded[java_state] += 1
                                chunk_success += 1
                                time.sleep(sleep_time)
                    fmts.print_inf(
                        f"§a区块 ({cx},{cz}) 导入已完成: 已成功处理区块内 {chunk_success} 方块, "
                        f"当前区块进度: {chunk_number}/{total_chunks} "
                        f"({chunk_number / total_chunks * 100:.1f}%)"
                    )

        elapsed = time.perf_counter() - started
        fmts.print_inf(
            f"\n§a已完成方块导入, 首次确认成功 {confirmed_success} 方块, "
            f"异步发送 {async_sent} 方块, 转换缺失 {sum(conversion_missing.values())} 方块, "
            f"服务器拒绝 {sum(server_rejected.values())} 方块, 共耗时 {elapsed:.6f} 秒"
        )
        if conversion_missing:
            fmts.print_inf("§6❀ 警告: 以下Java方块状态没有可用转换:")
            for state, count in conversion_missing.most_common():
                fmts.print_inf(
                    f"§6- {state}: {count} 个, 示例相对坐标 {missing_examples[state]}"
                )
        if server_rejected:
            fmts.print_inf("§c❀ 警告: 以下转换结果被服务器拒绝:")
            for state, count in server_rejected.most_common():
                converted = self.converter.convert(state)
                command = converted.command if converted else ""
                fmts.print_inf(
                    f"§c- {state}: {count} 个, 示例相对坐标 {rejected_examples[state]}, "
                    f"返回: {rejected_commands.get(command, '未知错误')}"
                )
        if degraded:
            fmts.print_inf(
                f"§6❀ 警告: 另有 {sum(degraded.values())} 个含水方块仅导入了主方块,未恢复含水层"
            )
        ignored = {
            key: value for key, value in structure.ignored_counts.items() if value
        }
        if ignored:
            detail = ", ".join(f"{key} {value} 条" for key, value in ignored.items())
            fmts.print_inf(f"§6❀ 警告: 首版未导入以下 NBT 数据: {detail}")

    def _clear_chunk(
        self,
        region: "LitematicRegion",
        offset: tuple[int, int, int],
        x0: int,
        z0: int,
        x_size: int,
        z_size: int,
    ) -> None:
        _, sy, _ = region.dimensions
        for y0 in range(0, sy, CHUNK_SIZE):
            a = region.relative_position(x0, y0, z0)
            b = region.relative_position(
                x0 + x_size - 1,
                min(sy - 1, y0 + CHUNK_SIZE - 1),
                z0 + z_size - 1,
            )
            p1 = tuple(a[axis] + offset[axis] for axis in range(3))
            p2 = tuple(b[axis] + offset[axis] for axis in range(3))
            self.sendaicmd(f"/fill {p1[0]} {p1[1]} {p1[2]} {p2[0]} {p2[1]} {p2[2]} air")


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

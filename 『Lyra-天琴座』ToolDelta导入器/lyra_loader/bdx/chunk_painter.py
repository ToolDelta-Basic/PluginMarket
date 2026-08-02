"""放置方块"""

import time
from collections import Counter
from typing import TYPE_CHECKING, Any, cast

from tooldelta import fmts
from tooldelta.internal.types import Packet_CommandOutput

if TYPE_CHECKING:
    from ...__init__ import LyraSystem
    from ..common.dimensions import Dimension
    from .bdx_parser import BDXData
    from .command_loader import CommandLoader

COMMAND_BLOCKS = {
    0: "minecraft:command_block",
    1: "minecraft:repeating_command_block",
    2: "minecraft:chain_command_block",
}


class ChunkPainter:
    def __init__(self, plugin: "LyraSystem") -> None:
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl
        self.cfg = plugin.config_mgr
        self.sendaicmd = plugin.game_ctrl.sendaicmd
        self.sendaicmd_with_resp = plugin.game_ctrl.sendaicmd_with_resp

    def paint(
        self,
        bdx: "BDXData",
        dimension: "Dimension",
        base_x: int,
        base_y: int,
        base_z: int,
    ) -> None:
        strings: list[str] = []
        relative = [0, 0, 0]
        bot_position = [0, 0, 0]
        runtime_pool = 0
        verified: set[str] = set()
        rejected: dict[str, str] = {}
        rejected_counts: Counter[str] = Counter()
        rejected_examples: dict[str, tuple[int, int, int]] = {}
        runtime_missing: Counter[tuple[int, int]] = Counter()
        ignored_chest_slots = 0
        command_data: list[dict[str, Any]] = []
        invalid_commands = 0
        confirmed_success = 0
        async_sent = 0
        block_operations = 0
        operation_count = 0
        started = time.perf_counter()
        sleep_time = 1 / self.cfg.BLOCK_LOAD_SPEED

        fmts.print_inf(f"§e开始流式导入 BDX, 作者: {bdx.author or '未知'}")
        self._preload(dimension, base_x, base_y, base_z)
        for operation in bdx.operations():
            operation_count += 1
            opcode = int(operation["id"])
            if opcode == 1:
                strings.append(str(operation["value"]))
                if len(strings) > 65536:
                    raise ValueError("BDX 常量字符串池超过 65536 项")
                continue
            if opcode in (6, 8, 12):
                relative[0] = 0
                relative[2] += 1 if opcode == 8 else int(operation["value"])
                continue
            if opcode in (14, 15, 16, 17, 18, 19):
                axis = {14: 0, 15: 0, 16: 1, 17: 1, 18: 2, 19: 2}[opcode]
                relative[axis] += 1 if opcode in (14, 16, 18) else -1
                continue
            if opcode in (20, 21, 28):
                relative[0] += int(operation["value"])
                continue
            if opcode in (22, 23, 29):
                relative[1] += int(operation["value"])
                continue
            if opcode in (24, 25, 30):
                relative[2] += int(operation["value"])
                continue
            if opcode in (9, 39):
                continue
            if opcode == 31:
                runtime_pool = int(operation["pool"])
                continue

            target = (base_x + relative[0], base_y + relative[1], base_z + relative[2])
            if sum(abs(relative[i] - bot_position[i]) for i in range(3)) > 16:
                self._preload(dimension, *target)
                bot_position[:] = relative

            command: str | None = None
            command_operation = opcode in (26, 27, 34, 35, 36)
            if opcode in (5, 7, 13, 27, 40):
                name = _constant(strings, int(operation["block"]))
                if opcode == 5:
                    states = _constant(strings, int(operation["states"]))
                    command = f"{name} {states}" if states else name
                elif opcode == 13:
                    states = str(operation["states_text"])
                    command = f"{name} {states}" if states else name
                else:
                    command = f"{name} {int(operation['data'])}"
                if opcode == 40:
                    ignored_chest_slots += int(operation["slots"])
            elif opcode in (32, 33, 37, 38):
                runtime_missing[(runtime_pool, int(operation["runtime_id"]))] += 1
                if opcode in (37, 38):
                    ignored_chest_slots += int(operation["slots"])
            elif opcode in (34, 35, 36):
                mode = int(operation["mode"])
                command = COMMAND_BLOCKS.get(mode)
                if command is None:
                    invalid_commands += 1
                elif opcode == 36:
                    # Opcode 36 携带旧版方块 data, 其中包含命令方块朝向
                    command = f"{command} {int(operation['data'])}"

            placed = False
            if command is not None:
                if _is_air(command) and not self.cfg.INCLUDE_AIR:
                    placed = True
                elif command in rejected:
                    rejected_counts[command] += 1
                    rejected_examples.setdefault(
                        command, (relative[0], relative[1], relative[2])
                    )
                else:
                    setblock = (
                        f"/setblock {target[0]} {target[1]} {target[2]} {command}"
                    )
                    if command not in verified:
                        ok, error = _command_success(self.sendaicmd_with_resp(setblock))
                        if not ok:
                            rejected[command] = error
                            rejected_counts[command] += 1
                            rejected_examples.setdefault(
                                command, (relative[0], relative[1], relative[2])
                            )
                        else:
                            verified.add(command)
                            confirmed_success += 1
                            placed = True
                    else:
                        self.sendaicmd(setblock)
                        async_sent += 1
                        placed = True
                    if placed:
                        time.sleep(sleep_time)
                block_operations += 1

            if command_operation and self.cfg.INCLUDE_CMD:
                # opcode 26 仅更新当前位置；其余操作必须先成功放置命令方块
                if opcode == 26 or placed:
                    packet = _command_packet(operation, target)
                    if packet is None:
                        invalid_commands += 1
                    else:
                        command_data.append(packet)
                else:
                    invalid_commands += 1
            if operation_count % 10_000 == 0:
                fmts.print_inf(
                    f"§e已解析 {operation_count} 条 BDX 操作, 已处理 {block_operations} 个方块操作"
                )

        elapsed = time.perf_counter() - started
        fmts.print_inf(
            f"\n§a已完成BDX方块导入, 首次确认成功 {confirmed_success} 方块, "
            f"异步发送 {async_sent} 方块, 服务器拒绝 {sum(rejected_counts.values())} 方块, "
            f"共解析 {operation_count} 条操作, 共耗时 {elapsed:.6f} 秒"
        )
        if rejected_counts:
            fmts.print_inf("§c❀ 警告: 以下方块状态被服务器拒绝:")
            for state, count in rejected_counts.most_common():
                fmts.print_inf(
                    f"§c- {state}: {count} 个, 示例相对坐标 {rejected_examples[state]}, "
                    f"返回: {rejected[state]}"
                )
        if runtime_missing:
            fmts.print_inf("§6❀ 警告: 以下 Runtime-ID 无离线映射, 相关普通方块已跳过:")
            for (pool, runtime_id), count in runtime_missing.most_common():
                fmts.print_inf(f"§6- Pool {pool}, Runtime-ID {runtime_id}: {count} 个")
        if ignored_chest_slots:
            fmts.print_inf(f"§6❀ 警告: 已忽略箱子物品槽 {ignored_chest_slots} 条")
        if invalid_commands:
            fmts.print_inf(f"§6❀ 警告: 已跳过 {invalid_commands} 条无效命令方块操作")
        if self.cfg.INCLUDE_CMD and command_data:
            command_loader = cast("CommandLoader", self.plugin.command_loader)
            command_loader.load_commands(command_data, dimension)

    def _preload(self, dimension: "Dimension", x: int, y: int, z: int) -> None:
        self.sendaicmd(
            f'/execute in {dimension.command_id} run tp @a[name="{self.game_ctrl.bot_name}"] {x} {y} {z}'
        )
        self.sendaicmd_with_resp(f"/testforblock {x} {y} {z} air")


def _constant(strings: list[str], index: int) -> str:
    if not 0 <= index < len(strings):
        raise ValueError(f"BDX 常量字符串索引越界: {index} >= {len(strings)}")
    return strings[index]


def _is_air(command: str) -> bool:
    name = command.split(" ", 1)[0].lower()
    return name in ("air", "minecraft:air")


def _command_packet(
    operation: dict[str, Any], position: tuple[int, int, int]
) -> dict[str, Any] | None:
    mode = int(operation["mode"])
    if mode not in COMMAND_BLOCKS:
        return None
    return {
        "Block": True,
        "Position": list(position),
        "Mode": mode,
        "NeedsRedstone": bool(operation["needs_redstone"]),
        "Conditional": bool(operation["conditional"]),
        "MinecartEntityRuntimeID": 0,
        "Command": str(operation["command"]),
        "LastOutput": "",
        "Name": str(operation["custom_name"]),
        "ShouldTrackOutput": bool(operation["track_output"]),
        "TickDelay": int(operation["tick_delay"]),
        "ExecuteOnFirstTick": bool(operation["execute_on_first_tick"]),
    }


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

import numpy
from .define import (
    Facing,
    ScannerType,
    GO_POSITION,
    GO_POSITION_OPPOSITE,
    GO_POSITION__OPPOSITE_PAIRS,
)
from .file import CommandBlock

if 0:
    from . import Structure, Block


def GetBlock(block: "Block"):
    if block.foreground is None:
        raise ValueError("此方块没有前景层")
    return block.foreground


class ScanError(Exception):
    def __init__(self, pos: tuple[int, int, int], exc: str):
        self.pos = pos
        self.exc = exc

    def __repr__(self):
        return f"{self.pos}: {self.exc}"


def to_matrix(orig_structure: "Structure"):
    sizex, sizey, sizez = orig_structure.size
    matrix = numpy.zeros(
        (sizex, sizey, sizez),
        dtype=numpy.uint8,
    )
    for x in range(sizex):
        for y in range(sizey):
            for z in range(sizez):
                block = orig_structure.get_block((x, y, z))
                if block.foreground is not None:
                    bname = block.foreground.name.removeprefix("minecraft:")
                else:
                    bname = "structure_void"
                if (
                    bname == "command_block"
                    or bname == "repeating_command_block"
                    or bname == "chain_command_block"
                ):
                    matrix[x, y, z] = ScannerType.COMMAND_BLOCK_NOT_SCANNED
                else:
                    matrix[x, y, z] = ScannerType.OTHER_BLOCK
    return matrix


def scan_all(orig_structure: "Structure", matrix: numpy.ndarray):
    size_x, size_y, size_z = matrix.shape
    chains: dict[tuple[int, int, int], list[CommandBlock]] = {}
    for x in range(size_x):
        for y in range(size_y):
            for z in range(size_z):
                if matrix[x, y, z] == ScannerType.COMMAND_BLOCK_NOT_SCANNED.value:
                    chain, start_point = scan_cb_chain(orig_structure, matrix, x, y, z)
                    chains[start_point] = chain
    return chains


def scan_cb_chain(
    orig_structure: "Structure", matrix: numpy.ndarray, x: int, y: int, z: int
):
    def record(x: int, y: int, z: int, cb_block: "Block"):
        block_data = cb_block.entity_data
        block_states = GetBlock(cb_block).states
        assert block_data is not None, "Block has not nbt data"
        assert cb_block.foreground, "Block has no foreground"
        chain.append(
            CommandBlock(
                str(block_data["Command"]),
                int(block_states["facing_direction"]),
                (
                    "minecraft:command_block",
                    "minecraft:repeating_command_block",
                    "minecraft:chain_command_block",
                ).index(str(cb_block.foreground.name)),
                bool(block_data["conditionalMode"]),
                bool(block_data["LPRedstoneMode"]),
                int(block_data["TickDelay"]),
                bool(block_data["TrackOutput"]),
                bool(block_data["ExecuteOnFirstTick"]),
            )
        )
        matrix[x, y, z] = ScannerType.COMMAND_BLOCK_SCANNED

    def record_cutoff(x: int, y: int, z: int):
        chain.append(CommandBlock("断链", 0, 0, False, False, 0, False, False))
        matrix[x, y, z] = ScannerType.COMMAND_BLOCK_SCANNED

    chain: list[CommandBlock] = []
    # 先寻找起点
    # 一般来说起点是脉冲命令方块或循环命令方块
    err_str = ""
    while True:
        if not in_range(x, y, z, orig_structure):
            err_str = "命令链在扫描范围内断开"
            break
        elif matrix[x, y, z] == ScannerType.COMMAND_BLOCK_SCANNING:
            err_str = "扫描时遇到自闭链"
            break
        matrix[x, y, z] = ScannerType.COMMAND_BLOCK_SCANNING
        block = orig_structure.get_block((x, y, z))
        if block.foreground is not None:
            bname = block.foreground.name.removeprefix("minecraft:")
        else:
            bname = "structure_void"
        # 是脉冲命令方块或循环命令方块
        if bname == "command_block" or bname == "repeating_command_block":
            # 到命令方块链的起点了
            break
        # 是连锁命令方块
        # 在此命令方块周围搜寻朝向自己的命令方块
        current_facing = GetBlock(block).states["facing_direction"]
        fnd = get_prev_cb(x, y, z, orig_structure, current_facing)
        if fnd:
            x, y, z = fnd
        else:
            # 未找到断链
            # 有可能是断链
            opposite_facing = GO_POSITION_OPPOSITE[current_facing]
            # 相反方向走两步
            x1, y1, z1 = go(x, y, z, *GO_POSITION[opposite_facing])
            if not in_range(x1, y1, z1, orig_structure):
                err_str = f"在识别断链时命令链异常断开::1:: {x1, y1, z1} 不在范围内"
                break
            x1, y1, z1 = go(x1, y1, z1, *GO_POSITION[opposite_facing])
            if not in_range(x1, y1, z1, orig_structure):
                err_str = f"在识别断链时命令链异常断开::2:: {x1, y1, z1} 不在范围内"
                break
            block = orig_structure.get_block((x1, y1, z1))
            if (
                GetBlock(block).name.endswith("command_block")
                and GetBlock(block).states["facing_direction"] == current_facing
            ):
                # 确实是断链
                x, y, z = x1, y1, z1
            else:
                err_str = "命令链异常断开"
                break
    if err_str:
        raise ScanError((x, y, z), err_str)
    start_point = (x, y, z)
    # 开始读取命令链
    # 第一个命令方块
    block = orig_structure.get_block((x, y, z))
    record(x, y, z, block)
    current_facing = GetBlock(block).states["facing_direction"]
    x, y, z = go(x, y, z, *GO_POSITION[current_facing])
    # 之后的命令方块
    while True:
        if (
            not in_range(x, y, z, orig_structure)
            or matrix[x, y, z] is ScannerType.COMMAND_BLOCK_SCANNED
        ):
            break
        block = orig_structure.get_block((x, y, z))
        bname = GetBlock(block).name.removeprefix("minecraft:")
        if (
            bname == "chain_command_block"
            and GetBlock(block).states["facing_direction"]
            != GO_POSITION_OPPOSITE[current_facing]
        ):
            record(x, y, z, block)
            current_facing = GetBlock(block).states["facing_direction"]
            x, y, z = go(x, y, z, *GO_POSITION[current_facing])
        else:
            # 有可能是断链
            # 多向前一步
            x1, y1, z1 = go(x, y, z, *GO_POSITION[current_facing])
            if not in_range(x1, y1, z1, orig_structure):
                break
            block = orig_structure.get_block((x1, y1, z1))
            if (
                GetBlock(block).name == "minecraft:chain_command_block"
                and GetBlock(block).states["facing_direction"] == current_facing
            ):
                # 确实是断链
                record_cutoff(x, y, z)
                x, y, z = x1, y1, z1
            else:
                break
    return chain, start_point


def make_description(cb: CommandBlock):
    descs = []
    if cb.type == 0:
        descs.append("脉冲")
    elif cb.type == 1:
        descs.append("循环")
    else:
        descs.append("连锁")
    if cb.conditional:
        descs.append("有条件")
    if cb.need_redstone:
        descs.append("红石控制")
    if cb.tick_delay > 0:
        descs.append(f"延迟 {cb.tick_delay} t")
    return ", ".join(descs)


def in_range(x: int, y: int, z: int, structure: "Structure"):
    sizex, sizey, sizez = structure.size
    return x >= 0 and x < sizex and y >= 0 and y < sizey and z >= 0 and z < sizez


def go(x: int, y: int, z: int, dx: int, dy: int, dz: int):
    return x + dx, y + dy, z + dz


def get_prev_cb(x: int, y: int, z: int, structure: "Structure", current_facing: Facing):
    not_scan = GO_POSITION[current_facing][:3]
    for dx, dy, dz, match_facing in GO_POSITION__OPPOSITE_PAIRS:
        if (dx, dy, dz) == not_scan:
            continue
        nx, ny, nz = go(x, y, z, dx, dy, dz)
        if in_range(nx, ny, nz, structure):
            block = structure.get_block((nx, ny, nz))
            if GetBlock(block).name.endswith("command_block"):
                facing = int(GetBlock(block).states["facing_direction"])
                if facing == match_facing.value:
                    # 保证其的朝向是朝向此命令方块的
                    return nx, ny, nz
    return None

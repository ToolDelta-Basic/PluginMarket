import math
from tooldelta import fmts


def snake_folding_xz(size_x: int, size_z: int):
    x = 0
    z = 0
    dx = 1
    while z < size_z:
        yield x, z
        x += dx
        if x >= size_x or x < 0:
            dx *= -1
            x += dx
            z += 1


def yield_chunks(startx: int, startz: int, endx: int, endz: int):
    # 枚举区域内每个 2x2 区块的起点
    dx = endx - startx
    dz = endz - startz
    f_chunk_x_count = math.ceil(dx / 16)
    f_chunk_z_count = math.ceil(dz / 16)
    for x, z in snake_folding_xz(f_chunk_x_count, f_chunk_z_count):
        yield startx + x * 16, startz + z * 16, x * 16, z * 16

def get_chunks_num(startx: int, startz: int, endx: int, endz: int):
    # 获取总区块数
    dx = endx - startx
    dz = endz - startz
    f_chunk_x_count = math.ceil(dx / 16)
    f_chunk_z_count = math.ceil(dz / 16)
    return f_chunk_x_count * f_chunk_z_count


def progress_bar(
    current: float,
    total: float,
    length: float = 20,
    color1: str = "§f",
    color2: str = "§b",
) -> str:
    """执行进度条

    Args:
        current (float | int): 当前进度值
        total (float | int): 总进度值
        length (int): 进度条长度.
        color1 (str): 进度条颜色 1.
        color2 (str): 进度条颜色 2.

    Returns:
        str: 格式化后的进度条字符串
    """
    pc = round(min(1, current / total) * length)
    return fmts.colormode_replace(
        color1 + " " * pc + color2 + " " * (20 - pc) + f"§r {current}/{total}", 7
    )

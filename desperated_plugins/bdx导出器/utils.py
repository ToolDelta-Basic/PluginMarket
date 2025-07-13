import math


def snake_folding(size_x: int, size_y: int, size_z: int):
    x = 0
    y = 0
    z = 0
    dx = 1
    dz = 1
    while y < size_y:
        yield x, y, z
        x += dx
        if x >= size_x or x < 0:
            dx *= -1
            x += dx
            z += dz
            if z >= size_z or z < 0:
                dz *= -1
                z += dz
                y += 1


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


def yield_4chunks(startx: int, startz: int, endx: int, endz: int):
    # 枚举区域内每个 2x2 区块的起点
    dx = endx - startx
    dz = endz - startz
    f_chunk_x_count = math.ceil(dx / 64)
    f_chunk_z_count = math.ceil(dz / 64)
    for x, z in snake_folding_xz(f_chunk_x_count, f_chunk_z_count):
        yield startx + x * 64, startz + z * 64, x * 64, z * 64

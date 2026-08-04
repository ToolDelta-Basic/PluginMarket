"""清理目标区块"""

from collections.abc import Callable

FILL_HEIGHT = 16

def chunk_clear(
    sendaicmd: Callable[[str], object],
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> None:
    """将闭区间长方体按 16 格高度分段清理为空气"""
    min_x, min_y, min_z = (min(first[i], second[i]) for i in range(3))
    max_x, max_y, max_z = (max(first[i], second[i]) for i in range(3))
    for y1 in range(min_y, max_y + 1, FILL_HEIGHT):
        y2 = min(max_y, y1 + FILL_HEIGHT - 1)
        sendaicmd(f"/fill {min_x} {y1} {min_z} {max_x} {y2} {max_z} air")

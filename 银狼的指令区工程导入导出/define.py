from enum import IntEnum


class Facing(IntEnum):
    DOWN = 0
    UP = 1
    NORTH = 2
    SOUTH = 3
    WEST = 4
    EAST = 5


class ScannerType(IntEnum):
    OTHER_BLOCK = 0
    COMMAND_BLOCK_NOT_SCANNED = 1
    COMMAND_BLOCK_SCANNING = 2
    COMMAND_BLOCK_SCANNED = 3


class CommandBlockType(IntEnum):
    COMMAND_BLOCK = 0
    REPEATING_COMMAND_BLOCK = 1
    CHAIN_COMMAND_BLOCK = 2


GO_POSITION = {
    Facing.UP: (0, 1, 0),
    Facing.DOWN: (0, -1, 0),
    Facing.SOUTH: (0, 0, 1),
    Facing.NORTH: (0, 0, -1),
    Facing.EAST: (1, 0, 0),
    Facing.WEST: (-1, 0, 0),
}

GO_POSITION__OPPOSITE_PAIRS = (
    (0, -1, 0, Facing.UP),
    (0, 1, 0, Facing.DOWN),
    (0, 0, -1, Facing.SOUTH),
    (0, 0, 1, Facing.NORTH),
    (-1, 0, 0, Facing.EAST),
    (1, 0, 0, Facing.WEST),
)

GO_POSITION_OPPOSITE = {
    Facing.DOWN: Facing.UP,
    Facing.UP: Facing.DOWN,
    Facing.SOUTH: Facing.NORTH,
    Facing.NORTH: Facing.SOUTH,
    Facing.EAST: Facing.WEST,
    Facing.WEST: Facing.EAST,
}

FACING_STR = ("y-", "y+", "z-", "z+", "x-", "x+")
CBTYPE_STR = ("脉冲", "循环", "连锁")

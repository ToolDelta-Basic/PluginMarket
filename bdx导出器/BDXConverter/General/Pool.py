from .GeneralClass import GeneralClass
from .Operation import *


def GetBDXCommandPool() -> dict[int, GeneralClass]:
    """
    Return dict[commandId(operationId):int, PythonClass:GeneralClass]
    """
    return {
        1: CreateConstantString(),
        5: PlaceBlockWithBlockStates(),
        6: AddInt16ZValue0(),
        7: PlaceBlock(),
        8: AddZValue0(),
        9: NOP(),
        12: AddInt32ZValue0(),
        13: PlaceBlockWithBlockStatesDeprecated(),
        14: AddXValue(),
        15: SubtractXValue(),
        16: AddYValue(),
        17: SubtractYValue(),
        18: AddZValue(),
        19: SubtractZValue(),
        20: AddInt16XValue(),
        21: AddInt32XValue(),
        22: AddInt16YValue(),
        23: AddInt32YValue(),
        24: AddInt16ZValue(),
        25: AddInt32ZValue(),
        26: SetCommandBlockData(),
        27: PlaceBlockWithCommandBlockData(),
        28: AddInt8XValue(),
        29: AddInt8YValue(),
        30: AddInt8ZValue(),
        31: UseRuntimeIDPool(),
        32: PlaceRuntimeBlock(),
        33: PlaceBlockWithRuntimeId(),
        34: PlaceRuntimeBlockWithCommandBlockData(),
        35: PlaceRuntimeBlockWithCommandBlockDataAndUint32RuntimeID(),
        36: PlaceCommandBlockWithCommandBlockData(),
        37: PlaceRuntimeBlockWithChestData(),
        38: PlaceRuntimeBlockWithChestDataAndUint32RuntimeID(),
        39: AssignDebugData(),
        40: PlaceBlockWithChestData(),
        41: PlaceBlockWithNBTData()
    }

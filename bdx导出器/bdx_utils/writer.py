from io import BytesIO
from struct import pack

from .structs import ChestData


class BDXContentWriter(BytesIO):
    def __init__(self):
        super().__init__()

    def write_op(self, op: int):
        self.write(op.to_bytes())

    def AddXValue(self):
        self.write_op(14)

    def SubtractXValue(self):
        self.write_op(15)

    def AddYValue(self):
        self.write_op(16)

    def SubtractYValue(self):
        self.write_op(17)

    def AddZValue(self):
        self.write_op(18)

    def SubtractZValue(self):
        self.write_op(19)

    def AddInt8XValue(self, x: int):
        self.write_op(28)
        self.write(x.to_bytes(signed=True))

    def AddInt8YValue(self, y: int):
        self.write_op(29)
        self.write(y.to_bytes(signed=True))

    def AddInt8ZValue(self, z: int):
        self.write_op(30)
        self.write(z.to_bytes(signed=True))

    def AddInt16XValue(self, x: int):
        self.write_op(20)
        self.write(pack(">h", x))

    def AddInt16YValue(self, y: int):
        self.write_op(22)
        self.write(pack(">h", y))

    def AddInt16ZValue(self, z: int):
        self.write_op(24)
        self.write(pack(">h", z))

    def AddInt32XValue(self, x: int):
        self.write_op(21)
        self.write(pack(">i", x))

    def AddInt32YValue(self, y: int):
        self.write_op(23)
        self.write(pack(">i", y))

    def AddInt32ZValue(self, z: int):
        self.write_op(25)
        self.write(pack(">i", z))

    def CreateConstantString(self, string: str):
        self.write_op(1)
        self.write(string.encode("utf-8") + b"\x00")

    def PlaceBlock(self, blockConstantStringID: int, blockData: int):
        self.write_op(7)
        self.write(pack(">H", blockConstantStringID))
        self.write(pack(">H", blockData))

    def PlaceBlockWithBlockStates(
        self,
        blockConstantStringID: int,
        blockStatesConstantStringID: int = 0,
    ):
        self.write_op(5)
        self.write(
            pack(">H", blockConstantStringID) + pack(">H", blockStatesConstantStringID)
        )

    def PlaceCommandBlockWithCommandBlockData(
        self,
        data: int,
        mode: int,
        command: str,
        customName: str,
        lastOutput: str,
        tickDelay: int,
        executeOnFirstTick: bool,
        trackOutput: bool,
        conditional: bool,
        needsRedstone: bool,
    ):
        self.write_op(36)
        self.write(
            pack(">H", data)
            + pack(">I", mode)
            + command.encode(encoding="utf-8")
            + b"\x00"
            + customName.encode(encoding="utf-8")
            + b"\x00"
            + lastOutput.encode(encoding="utf-8")
            + b"\x00"
            + pack(">I", tickDelay)
            + executeOnFirstTick.to_bytes()
            + trackOutput.to_bytes()
            + conditional.to_bytes()
            + needsRedstone.to_bytes()
        )

    def PlaceBlockWithChestData(
        self,
        blockConstantStringID: int,
        blockData: int,
        slotCount: int,
        data: ChestData,
    ):
        self.write_op(40)
        self.write(
            pack(">H", blockConstantStringID)
            + pack(">H", blockData)
            + slotCount.to_bytes()
        )
        data.marshal(self)

from io import BytesIO
from struct import pack, unpack
from ..General.GeneralClass import GeneralClass
from ..utils.getString import getByte, getString


class ChestSlot(GeneralClass):
    """
    Note: `ChestSlot` is not a operation
    """

    def __init__(self) -> None:
        super().__init__()
        self.itemName: str = ''
        self.count: int = 0
        self.data: int = 0
        self.slotID: int = 0

    def Marshal(self, writer: BytesIO) -> None:
        writer.write(self.itemName.encode(encoding='utf-8') + b'\x00' + self.count.to_bytes(length=1, byteorder='big',
                     signed=False) + pack('>H', self.data) + self.slotID.to_bytes(length=1, byteorder='big', signed=False))

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.itemName = getString(buffer)
        self.count = getByte(buffer, 1)[0]
        self.data = unpack('>H', getByte(buffer, 2))[0]
        self.slotID = getByte(buffer, 1)[0]


class ChestData(GeneralClass):
    """
    Note: `ChestData` is not a operation
    """

    def __init__(self) -> None:
        self.slotCount: int = 0
        self.chestData: list[ChestSlot] = []

    def Marshal(self, writer: BytesIO) -> None:
        for i in self.chestData:
            i.Marshal(writer)

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.chestData = []
        for _ in range(self.slotCount):
            newSlot = ChestSlot()
            newSlot.UnMarshal(buffer)
            self.chestData.append(newSlot)

    def Loads(self, jsonList: list[dict]) -> None:
        self.slotCount = len(jsonList)
        self.chestData = []
        for i in jsonList:
            newSlot = ChestSlot()
            newSlot.Loads(i)
            self.chestData.append(newSlot)
        self.slotCount = len(self.chestData)

    def Dumps(self) -> list[dict]:
        result: list[dict] = []
        for i in self.chestData:
            result.append(i.Dumps())
        return result

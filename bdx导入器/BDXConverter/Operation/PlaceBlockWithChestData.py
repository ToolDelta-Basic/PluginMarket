from io import BytesIO
from struct import pack, unpack
from .structOfChest import ChestData
from ..General.GeneralClass import GeneralClass
from ..utils.getByte import getByte


class PlaceBlockWithChestData(GeneralClass):
    def __init__(self) -> None:
        super().__init__()
        self.operationName: str = 'PlaceBlockWithChestData'
        self.operationNumber: int = 40
        self.blockConstantStringID: int = 0
        self.blockData: int = 0
        self.slotCount: int = 0
        self.data: ChestData = ChestData()

    def Marshal(self, writer: BytesIO) -> None:
        self.slotCount = len(self.data.chestData)
        writer.write(pack('>H', self.blockConstantStringID) + pack('>H', self.blockData) +
                     self.slotCount.to_bytes(length=1, byteorder='big', signed=False))
        self.data.Marshal(writer)

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.blockConstantStringID = unpack('>H', getByte(buffer, 2))[0]
        self.blockData = unpack('>H', getByte(buffer, 2))[0]
        self.slotCount = getByte(buffer, 1)[0]
        self.data.slotCount = self.slotCount
        self.data.UnMarshal(buffer)

    def Loads(self, jsonDict: dict) -> None:
        if 'operationData' in jsonDict:
            jsonDict = jsonDict['operationData']
            self.blockConstantStringID = jsonDict['blockConstantStringID'] if 'blockConstantStringID' in jsonDict else 0
            self.blockData = jsonDict['blockData'] if 'blockData' in jsonDict else 0
            newChestData = ChestData()
            if 'data' in jsonDict:
                newChestData.Loads(jsonDict['data'])
            self.slotCount = self.data.slotCount
            self.data = newChestData

    def Dumps(self) -> dict:
        return {
            'operationName': self.operationName,
            'operationNumber': self.operationNumber,
            'operationData': {
                'blockConstantStringID': self.blockConstantStringID,
                'blockData': self.blockData,
                'slotCount': len(self.data.chestData),
                'data': self.data.Dumps()
            }
        }

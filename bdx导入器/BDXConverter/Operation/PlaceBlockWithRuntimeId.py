from io import BytesIO
from struct import pack, unpack
from ..General.GeneralClass import GeneralClass
from ..utils.getByte import getByte


class PlaceBlockWithRuntimeId(GeneralClass):
    def __init__(self) -> None:
        super().__init__()
        self.operationName: str = 'placeBlockWithRuntimeId'
        self.operationNumber: int = 33
        self.runtimeId: int = 0

    def Marshal(self, writer: BytesIO) -> None:
        writer.write(pack('>I', self.runtimeId))

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.runtimeId = unpack('>I', getByte(buffer, 4))[0]

from io import BytesIO
from struct import pack, unpack
from ..General.GeneralClass import GeneralClass
from ..utils.getByte import getByte


class AddInt16ZValue(GeneralClass):
    def __init__(self) -> None:
        super().__init__()
        self.operationName: str = 'AddInt16ZValue'
        self.operationNumber: int = 24
        self.value: int = 0

    def Marshal(self, writer: BytesIO) -> None:
        writer.write(pack('>h', self.value))

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.value = unpack('>h', getByte(buffer, 2))[0]

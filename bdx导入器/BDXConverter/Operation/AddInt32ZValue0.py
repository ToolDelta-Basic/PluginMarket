from io import BytesIO
from struct import pack, unpack
from ..General.GeneralClass import GeneralClass
from ..utils.getByte import getByte


class AddInt32ZValue0(GeneralClass):
    def __init__(self) -> None:
        super().__init__()
        self.operationName: str = 'AddInt32ZValue0'
        self.operationNumber: int = 12
        self.value: int = 0

    def Marshal(self, writer: BytesIO) -> None:
        writer.write(pack('>I', self.value))

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.value = unpack('>I', getByte(buffer, 4))[0]

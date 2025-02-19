from io import BytesIO
from struct import pack, unpack
from ..General.GeneralClass import GeneralClass
from ..utils.getByte import getByte


class AddInt32XValue(GeneralClass):
    def __init__(self) -> None:
        super().__init__()
        self.operationName: str = 'AddInt32XValue'
        self.operationNumber: int = 21
        self.value: int = 0

    def Marshal(self, writer: BytesIO) -> None:
        writer.write(pack('>i', self.value))

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.value = unpack('>i', getByte(buffer, 4))[0]

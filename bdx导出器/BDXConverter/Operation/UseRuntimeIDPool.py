from io import BytesIO
from ..General.GeneralClass import GeneralClass
from ..utils.getByte import getByte


class UseRuntimeIDPool(GeneralClass):
    def __init__(self) -> None:
        super().__init__()
        self.operationName: str = 'UseRuntimeIDPool'
        self.operationNumber: int = 31
        self.poolId: int = 0

    def Marshal(self, writer: BytesIO) -> None:
        writer.write(self.poolId.to_bytes(
            length=1, byteorder='big', signed=False))

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.poolId = getByte(buffer, 1)[0]

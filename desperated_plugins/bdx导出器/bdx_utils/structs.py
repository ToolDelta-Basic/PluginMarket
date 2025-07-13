from io import BytesIO
from struct import pack


class ChestSlot:
    def __init__(
        self,
        itemName: str,
        count: int,
        data: int,
        slotID: int,
    ):
        self.itemName = itemName
        self.count = count
        self.data = data
        self.slotID = slotID

    def marshal(
        self,
        writer: BytesIO,
    ):
        writer.write(
            self.itemName.encode(encoding="utf-8")
            + b"\x00"
            + self.count.to_bytes(length=1, byteorder="big")
            + pack(">H", self.data)
            + self.slotID.to_bytes(length=1, byteorder="big")
        )


class ChestData:
    def __init__(self, chestData: list[ChestSlot]):
        self.chestData = chestData

    def marshal(self, writer: BytesIO):
        for i in self.chestData:
            i.marshal(writer)

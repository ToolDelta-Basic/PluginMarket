import nbtlib
import sys
from io import BytesIO
from struct import pack, unpack
from ..General.GeneralClass import GeneralClass
from ..utils.getByte import getByte


if sys.version_info.major >= 3 and sys.version_info.minor >= 10:
    from ..utils.marshalNBT import MarshalPythonNBTObjectToWriter
    from ..utils.unmarshalNBT import UnMarshalBufferToPythonNBTObject
else:
    from ..utils.marshalNBT_OldVersion import MarshalPythonNBTObjectToWriter
    from ..utils.unmarshalNBT_OldVersion import UnMarshalBufferToPythonNBTObject


class PlaceBlockWithNBTData(GeneralClass):
    def __init__(self) -> None:
        super().__init__()
        self.operationName: str = 'PlaceBlockWithNBTData'
        self.operationNumber: int = 41
        self.blockConstantStringID: int = 0
        self.blockStatesConstantStringID: int = 0
        self.blockNBT: nbtlib.tag.Compound = nbtlib.tag.Compound(
            {})  # type: ignore

    def Marshal(self, writer: BytesIO) -> None:
        writer.write(pack('>H', self.blockConstantStringID) + pack('>H',
                     self.blockStatesConstantStringID) + pack('>H', self.blockStatesConstantStringID))
        MarshalPythonNBTObjectToWriter(writer, self.blockNBT, '')

    def UnMarshal(self, buffer: BytesIO) -> None:
        self.blockConstantStringID = unpack('>H', getByte(buffer, 2))[0]
        self.blockStatesConstantStringID = unpack('>H', getByte(buffer, 2))[0]
        getByte(buffer, 2)  # do not delete this line because it is correct
        self.blockNBT, _ = UnMarshalBufferToPythonNBTObject(  # type: ignore
            buffer)

    def Loads(self, jsonDict: dict) -> None:
        if 'operationData' in jsonDict:
            jsonDict = jsonDict['operationData']
            self.blockConstantStringID = jsonDict['blockConstantStringID'] if 'blockConstantStringID' in jsonDict else 0
            self.blockStatesConstantStringID = jsonDict[
                'blockStatesConstantStringID'] if 'blockStatesConstantStringID' in jsonDict else 0
            self.blockNBT = nbtlib.parse_nbt(
                jsonDict['blockNBT']) if 'blockNBT' in jsonDict else nbtlib.tag.Compound({})

    def Dumps(self) -> dict:
        return {
            'operationName': self.operationName,
            'operationNumber': self.operationNumber,
            'operationData': {
                'blockConstantStringID': self.blockConstantStringID,
                'blockStatesConstantStringID': self.blockStatesConstantStringID,
                'blockNBT': nbtlib.serialize_tag(self.blockNBT)
            }
        }

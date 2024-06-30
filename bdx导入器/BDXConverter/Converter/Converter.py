from brotli import compress, decompress
from io import BytesIO
from copy import deepcopy
from .ErrorClassDefine import HeaderError
from .ErrorClassDefine import ReadError, UnknownOperationError
from ..General.GeneralClass import GeneralClass
from ..General.Pool import GetBDXCommandPool
from ..utils.getString import getByte, getString


class BDX(GeneralClass):
    def __init__(self) -> None:
        """
        `AuthorName: str`
            The author of this BDX file
                Note: The default value is "TriM-Organization/BDXConverter"
        `BDXContents: list[GeneralClass]`
            The valid contents of the BDX file
        `Signature: Signature`
            The signature data of the BDX file
        """
        super().__init__()
        self.AuthorName: str = 'TriM-Organization/BDXConverter'
        self.BDXContents: list[GeneralClass] = []

    def Marshal(self, writer: BytesIO) -> None:
        newWriter = BytesIO(
            b'BDX\x00' + self.AuthorName.encode(encoding='utf-8') + b'\x00')
        newWriter.seek(0, 2)
        # inside header with author's name
        for i in self.BDXContents:
            if 'operationNumber' in i.__dict__:
                newWriter.write(i.__dict__['operationNumber'].to_bytes(
                    length=1, byteorder='big', signed=False))
                i.Marshal(newWriter)
        # valid contents
        #if not self.Signature.isLegacy and self.Signature.signedOrNeedToSign:
        #    self.Signature.fileHash = new(newWriter.getvalue())
        #    self.Signature.Marshal(newWriter)
        #else:
        newWriter.write(b'XE')
        # signature
        writer.write(b'BD@' + compress(newWriter.getvalue()))
        # write BDX data

    def UnMarshal(self, binaryData: bytes) -> None:
        if binaryData[0:3] != b'BD@':
            raise HeaderError(binaryData[:3])
        # check outside header
        reader = BytesIO(decompress(binaryData[3:]))
        # get reader to read valid contents
        insideHeader = getByte(reader, 3)
        if insideHeader != b'BDX':
            raise HeaderError(insideHeader)
        # check inside header
        firstOperation = getByte(reader, 1)
        if firstOperation != b'\x00':
            raise UnknownOperationError(firstOperation[0], reader.seek(-1, 1))
        self.AuthorName = getString(reader)
        # get author's name
        BDXCommandPool: dict[int, GeneralClass] = GetBDXCommandPool()
        # get bdx command(operation) pool
        while True:
            commandId = getByte(reader, 1)[0]
            if commandId == 88:
                break
            elif commandId in BDXCommandPool:
                struct: GeneralClass = deepcopy(BDXCommandPool[commandId])
                # get struct(operation) from the pool
                errorType = 0
                # prepare
                try:
                    struct.UnMarshal(reader)
                except EOFError:
                    errorType = 1
                except:
                    errorType = 2
                # unmarshal bytes into the struct
                if errorType == 1:
                    raise EOFError
                elif errorType == 2:
                    raise ReadError(reader.seek(0, 1))
                # if meet error
                self.BDXContents.append(struct)
                # submit single data
        # read data from reader
        # signature

    def Loads(self, jsonDict: dict) -> None:
        BDXCommandPool: dict[int, GeneralClass] = GetBDXCommandPool()

        self.AuthorName = jsonDict['AuthorName'] if 'AuthorName' in jsonDict else ''
        if 'Signature' in jsonDict:
            self.Signature.Loads(jsonDict['Signature'])
        if 'BDXContents' in jsonDict:
            tmp: list[dict] = jsonDict['BDXContents']
            for i in tmp:
                if not ('operationNumber' in i):
                    continue
                if not ('operationData' in i):
                    continue
                commandId: int = i['operationNumber']
                struct: GeneralClass = deepcopy(BDXCommandPool[commandId])
                struct.Loads(i['operationData'])
                self.BDXContents.append(struct)

    def Dumps(self) -> dict:
        return {
            'AuthorName': self.AuthorName,
            'BDXContents': [i.Dumps() for i in self.BDXContents],
            'Signature': self.Signature.Dumps()
        }

class BDX_2(GeneralClass):
    def __init__(self) -> None:
        """
        `AuthorName: str`
            The author of this BDX file
                Note: The default value is "TriM-Organization/BDXConverter"
        `BDXContents: list[GeneralClass]`
            The valid contents of the BDX file
        `Signature: Signature`
            The signature data of the BDX file
        """
        super().__init__()
        self.AuthorName: str = 'TriM-Organization/BDXConverter'

    def Marshal(self, writer: BytesIO) -> None:
        newWriter = BytesIO(
            b'BDX\x00' + self.AuthorName.encode(encoding='utf-8') + b'\x00')
        newWriter.seek(0, 2)
        # inside header with author's name
        for i in self.BDXContents:
            if 'operationNumber' in i.__dict__:
                newWriter.write(i.__dict__['operationNumber'].to_bytes(
                    length=1, byteorder='big', signed=False))
                i.Marshal(newWriter)
        # valid contents
        #if not self.Signature.isLegacy and self.Signature.signedOrNeedToSign:
        #    self.Signature.fileHash = new(newWriter.getvalue())
        #    self.Signature.Marshal(newWriter)
        #else:
        newWriter.write(b'XE')
        # signature
        writer.write(b'BD@' + compress(newWriter.getvalue()))
        # write BDX data

    @property
    def BDXContents(self):
        reader = self._reader
        reader.seek(4, 0)
        BDXCommandPool = GetBDXCommandPool()
        # get bdx command(operation) pool
        while True:
            commandId = getByte(reader, 1)[0]
            if commandId == 88:
                break
            elif commandId in BDXCommandPool:
                struct: GeneralClass = deepcopy(BDXCommandPool[commandId])
                # get struct(operation) from the pool
                errorType = 0
                # prepare
                try:
                    struct.UnMarshal(reader)
                except EOFError:
                    errorType = 1
                except:
                    errorType = 2
                # unmarshal bytes into the struct
                if errorType == 1:
                    raise EOFError
                elif errorType == 2:
                    raise ReadError(reader.seek(0, 1))
                # if meet error
                yield struct
                # submit single data

    def UnMarshal(self, binaryData: bytes) -> None:
        if binaryData[0:3] != b'BD@':
            raise HeaderError(binaryData[:3])
        # check outside header
        reader = BytesIO(decompress(binaryData[3:]))
        # get reader to read valid contents
        insideHeader = getByte(reader, 3)
        if insideHeader != b'BDX':
            raise HeaderError(insideHeader)
        # check inside header
        firstOperation = getByte(reader, 1)
        if firstOperation != b'\x00':
            raise UnknownOperationError(firstOperation[0], reader.seek(-1, 1))
        self.AuthorName = getString(reader)
        # get author's name
        self._reader = reader
from .Converter import BDX, BDX_2
from json import loads, dumps
from io import BytesIO
from typing import TypeVar

BDX_TYPE = TypeVar("BDX_TYPE", BDX, BDX_2)

def ReadBDXFile(path: str, bdx_cls: type[BDX_TYPE] = BDX) -> BDX_TYPE:
    """
    Convert BDX file into class BDX
    """
    with open(path, "r+b") as file:
        fileContext: bytes = file.read()
    # get the content of this bdx file
    result = bdx_cls()
    # request a new class object
    result.UnMarshal(fileContext)
    # unmarshal
    return result
    # return


def DumpStructs(BDXObj: BDX, outputPath: str) -> None:
    """
    Convert BDXObj:BDX into bytes and write it into a bdx file(outputPath:str)
    """
    writer: BytesIO = BytesIO(b'')
    # request a new writer
    BDXObj.Marshal(writer)
    # marshal
    with open(outputPath, 'w+b') as file:
        file.write(writer.getvalue())
    # write bytes into a bdx file


def VisualStructs(BDXObj: BDX, outputPath: str) -> None:
    """
    Convert BDXObj:BDX into json data and write it into outputPath:str
    """
    with open(outputPath, 'w+', encoding='utf-8') as file:
        file.write(
            dumps(
                BDXObj.Dumps(),
                sort_keys=True,
                indent=4,
                separators=(', ', ': '),
                ensure_ascii=False
            )
        )
    # write json data


def ConvertJSONFileIntoStructs(path: str) -> BDX:
    """
    Read json data from path:str and convert it into class BDX
    """
    with open(path, 'r+', encoding='utf-8') as file:
        fileContext: str = file.read()
    jsonData: dict = loads(fileContext)
    # load json data from file
    result = BDX()
    # request a new class object
    result.Loads(jsonData)
    # loads
    return result
    # return

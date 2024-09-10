from io import BytesIO
from struct import unpack
from .getByte import getByte
import nbtlib

endian: str = '<'


class GetValueError(Exception):
    def __init__(self, errorOccurredPosition: int):
        Exception.__init__(
            self, f'failed to parse value, and the error occurred at position {errorOccurredPosition}')


class UnexpectedError(Exception):
    def __init__(self, value: int):
        Exception.__init__(self, f'unexpected number {value}')


def getName(buffer: BytesIO) -> str:
    keyLength = unpack(f'{endian}H', getByte(buffer, 2))[0]
    return getByte(buffer, keyLength).decode(encoding='utf-8', errors='replace')


def getValue(buffer: BytesIO, valueType: int) -> ...:
    if valueType == 1:
        return nbtlib.tag.Byte(unpack(f'{endian}b', getByte(buffer, 1))[0])
    elif valueType == 2:
        return nbtlib.tag.Short(unpack(f'{endian}h', getByte(buffer, 2))[0])
    elif valueType == 3:
        return nbtlib.tag.Int(unpack(f'{endian}i', getByte(buffer, 4))[0])
    elif valueType == 4:
        return nbtlib.tag.Long(unpack(f'{endian}q', getByte(buffer, 8))[0])
    elif valueType == 5:
        return nbtlib.tag.Float(unpack(f'{endian}f', getByte(buffer, 4))[0])
    elif valueType == 6:
        return nbtlib.tag.Double(unpack(f'{endian}d', getByte(buffer, 8))[0])
    elif valueType == 7 or valueType == 11 or valueType == 12:
        return getArray(buffer, valueType)
    elif valueType == 8:
        return nbtlib.tag.String(getName(buffer))
    elif valueType == 9:
        return getList(buffer)
    elif valueType == 10:
        return getCompound(buffer)
    else:
        raise GetValueError(buffer.seek(0, 1))


def getArray(buffer: BytesIO, valueType: int) -> ...:
    arrayLength = unpack(f'{endian}i', getByte(buffer, 4))[0]
    if valueType == 7:
        return nbtlib.tag.ByteArray([unpack(f'{endian}b', getByte(buffer, 1))[0] for _ in range(arrayLength)])
    elif valueType == 11:
        return nbtlib.tag.IntArray([unpack(f'{endian}i', getByte(buffer, 4))[0] for _ in range(arrayLength)])
    elif valueType == 12:
        return nbtlib.tag.LongArray([unpack(f'{endian}q', getByte(buffer, 8))[0] for _ in range(arrayLength)])
    else:
        raise UnexpectedError(valueType)


def getList(buffer: BytesIO) -> nbtlib.tag.List:
    valueType = getByte(buffer, 1)[0]
    listLength = unpack(f'{endian}i', getByte(buffer, 4))[0]
    return nbtlib.tag.List([getValue(buffer, valueType) for _ in range(listLength)])


def getCompound(buffer: BytesIO) -> nbtlib.tag.Compound:
    result: dict = {}
    while True:
        nextBuffer = getByte(buffer, 1)
        if nextBuffer == b'\x00':
            return nbtlib.tag.Compound(result)
        # if meet TAG_End
        buffer.seek(-1, 1)
        # correct the pointer
        valueType = getByte(buffer, 1)[0]
        name = getName(buffer)
        result[name] = getValue(buffer, valueType)
        # set values


def UnMarshalBufferToPythonNBTObject(buffer: BytesIO) -> ...:
    valueType = getByte(buffer, 1)[0]
    name = getName(buffer)
    return getValue(buffer, valueType), name

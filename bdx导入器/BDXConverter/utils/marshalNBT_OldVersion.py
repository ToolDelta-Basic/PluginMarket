from io import BytesIO
from struct import pack
import nbtlib

endian: str = '<'
endianWord: str = 'little'


def getValueType(value) -> bytes:
    if type(value) == nbtlib.tag.Byte:
        return b'\x01'
    elif type(value) == nbtlib.tag.Short:
        return b'\x02'
    elif type(value) == nbtlib.tag.Int:
        return b'\x03'
    elif type(value) == nbtlib.tag.Long:
        return b'\x04'
    elif type(value) == nbtlib.tag.Float:
        return b'\x05'
    elif type(value) == nbtlib.tag.Double:
        return b'\x06'
    elif type(value) == nbtlib.tag.ByteArray:
        return b'\x07'
    elif type(value) == nbtlib.tag.String:
        return b'\x08'
    elif type(value) == nbtlib.tag.Compound:
        return b'\x0a'
    elif type(value) == nbtlib.tag.IntArray:
        return b'\x0b'
    elif type(value) == nbtlib.tag.LongArray:
        return b'\x0c'
    else:
        return b'\x09'


def marshalToName(writer: BytesIO, name: str) -> None:
    encodeResult = name.encode(encoding='utf-8')
    writer.write(pack(f'{endian}H', len(encodeResult)) + encodeResult)


def marshalToValue(writer: BytesIO, value, valueType: int) -> None:
    if valueType == 1:
        writer.write(value.to_bytes(
            length=1, byteorder=endianWord, signed=True))
    elif valueType == 2:
        writer.write(pack(f'{endian}h', value))
    elif valueType == 3:
        writer.write(pack(f'{endian}i', value))
    elif valueType == 4:
        writer.write(pack(f'{endian}q', value))
    elif valueType == 5:
        writer.write(pack(f'{endian}f', value))
    elif valueType == 6:
        writer.write(pack(f'{endian}d', value))
    elif valueType == 7 or valueType == 11 or valueType == 12:
        marshalToArray(writer, value, valueType)
    elif valueType == 8:
        marshalToName(writer, str(value))
    elif valueType == 9:
        marshalToList(writer, value)
    elif valueType == 10:
        marshalToCompound(writer, value)


def marshalToArray(writer: BytesIO, value, valueType: int) -> None:
    writer.write(pack(f'{endian}i', len(value)))
    if valueType == 7:
        writer.write(b''.join([pack(f'{endian}b', i) for i in value]))
    elif valueType == 11:
        writer.write(b''.join([pack(f'{endian}i', i) for i in value]))
    elif valueType == 12:
        writer.write(b''.join([pack(f'{endian}q', i) for i in value]))
    else:
        raise TypeError


def marshalToList(writer: BytesIO, value) -> None:
    if len(value) > 0:
        subValueType = getValueType(value[0])
        writer.write(subValueType+pack(f'{endian}i', len(value)))
        for i in value:
            marshalToValue(writer, i, subValueType[0])
    else:
        writer.write(b'\x00' * 5)


def marshalToCompound(writer: BytesIO, value: nbtlib.tag.Compound) -> None:
    for i in value:
        valueType = getValueType(value[i])
        writer.write(valueType)
        marshalToName(writer, i)
        marshalToValue(writer, value[i], valueType[0])
    writer.write(b'\x00')


def MarshalPythonNBTObjectToWriter(writer: BytesIO, value, name: str) -> None:
    valueType = getValueType(value)
    writer.write(valueType)
    marshalToName(writer, name)
    marshalToValue(writer, value, valueType[0])

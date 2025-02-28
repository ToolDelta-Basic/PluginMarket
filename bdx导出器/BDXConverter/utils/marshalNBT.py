from io import BytesIO
from struct import pack
import nbtlib

endian: str = '<'
endianWord: str = 'little'


def getValueType(value) -> bytes:
    match type(value):
        case nbtlib.tag.Byte:
            return b'\x01'
        case nbtlib.tag.Short:
            return b'\x02'
        case nbtlib.tag.Int:
            return b'\x03'
        case nbtlib.tag.Long:
            return b'\x04'
        case nbtlib.tag.Float:
            return b'\x05'
        case nbtlib.tag.Double:
            return b'\x06'
        case nbtlib.tag.ByteArray:
            return b'\x07'
        case nbtlib.tag.String:
            return b'\x08'
        case nbtlib.tag.Compound:
            return b'\x0a'
        case nbtlib.tag.IntArray:
            return b'\x0b'
        case nbtlib.tag.LongArray:
            return b'\x0c'
        case _:
            return b'\x09'


def marshalToName(writer: BytesIO, name: str) -> None:
    encodeResult = name.encode(encoding='utf-8')
    writer.write(pack(f'{endian}H', len(encodeResult)) + encodeResult)


def marshalToValue(writer: BytesIO, value, valueType: int) -> None:
    match valueType:
        case 1:
            writer.write(value.to_bytes(length=1, byteorder=endianWord, signed=True))
        case 2:
            writer.write(pack(f'{endian}h', value))
        case 3:
            writer.write(pack(f'{endian}i', value))
        case 4:
            writer.write(pack(f'{endian}q', value))
        case 5:
            writer.write(pack(f'{endian}f', value))
        case 6:
            writer.write(pack(f'{endian}d', value))
        case 7 | 11 | 12:
            marshalToArray(writer, value, valueType)
        case 8:
            marshalToName(writer, str(value))
        case 9:
            marshalToList(writer, value)
        case 10:
            marshalToCompound(writer, value)


def marshalToArray(
        writer: BytesIO,
        value: nbtlib.tag.ByteArray | nbtlib.tag.IntArray | nbtlib.tag.LongArray,
        valueType: int
) -> None:
    writer.write(pack(f'{endian}i', len(value)))
    match valueType:
        case 7:
            writer.write(b''.join([pack(f'{endian}b', i) for i in value]))
        case 11:
            writer.write(b''.join([pack(f'{endian}i', i) for i in value]))
        case 12:
            writer.write(b''.join([pack(f'{endian}q', i) for i in value]))
        case _:
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

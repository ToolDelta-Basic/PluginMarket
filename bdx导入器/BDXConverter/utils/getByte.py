from io import BytesIO


def getByte(buffer: BytesIO, readSize: int) -> bytes:
    result = buffer.read(readSize)
    if len(result) < readSize:
        raise EOFError
    return result

"""NBT解析器"""

import gzip
import struct
import numpy as np

# ----------------------------------------------------------------------------------

# NBT tag   NBT标签

TAG_END = 0  # hex: 00    表示复合标签(TAG_COMPOUND)的结束
TAG_BYTE = 1  # hex: 01    1个byte的有符号整数  范围: -128 ~ 127
TAG_SHORT = 2  # hex: 02    2个byte的有符号整数  范围: -32768 ~ 32767
TAG_INT = 3  # hex: 03    4个byte的有符号整数  范围: -2147483648 ~ 2147483647
TAG_LONG = 4  # hex: 04    8个byte的有符号整数  范围: -9223372036854775808 ~ 9223372036854775807
TAG_FLOAT = 5  # hex: 05    4个byte的单精度浮点数(IEEE 754)
TAG_DOUBLE = 6  # hex: 06    8个byte的双精度浮点数(IEEE 754)
TAG_BYTE_ARRAY = 7  # hex: 07    1个byte数组
TAG_STRING = 8  # hex: 08    1个字符串
TAG_LIST = 9  # hex: 09    1个同类型标签的列表
TAG_COMPOUND = 10  # hex: 0A    1个复合标签
TAG_INT_ARRAY = 11  # hex: 0B    1个INT数组
TAG_LONG_ARRAY = 12  # hex: 0C    1个LONG数组

# ----------------------------------------------------------------------------------

# low-level NBT readers (big-endian)   NBT低级二进制读取函数 (大端序)


def read_byte(f):
    b = f.read(1)
    if not b:
        raise EOFError("读取 BYTE 时意外遇到文件结束符")
    return b[0]


def read_signed_byte(f):
    return struct.unpack(">b", f.read(1))[0]


def read_short(f):
    data = f.read(2)
    if len(data) < 2:
        raise EOFError("读取 有符号SHORT 时意外遇到文件结束符")
    return struct.unpack(">h", data)[0]


def read_ushort(f):
    data = f.read(2)
    if len(data) < 2:
        raise EOFError("读取 无符号SHORT 时意外遇到文件结束符")
    return struct.unpack(">H", data)[0]


def read_int(f):
    data = f.read(4)
    if len(data) < 4:
        raise EOFError("读取 有符号INT 时意外遇到文件结束符")
    return struct.unpack(">i", data)[0]


def read_long(f):
    data = f.read(8)
    if len(data) < 8:
        raise EOFError("读取 有符号LONG 时意外遇到文件结束符")
    return struct.unpack(">q", data)[0]


def read_float(f):
    return struct.unpack(">f", f.read(4))[0]


def read_double(f):
    return struct.unpack(">d", f.read(8))[0]


def read_byte_array(f):
    length = read_int(f)
    if length == 0:
        return bytearray()
    data = f.read(length)
    if len(data) < length:
        raise EOFError("读取 BYTE_ARRAY 时意外遇到文件结束符")
    return bytearray(data)


def read_string(f):
    length = read_ushort(f)
    if length == 0:
        return ""
    data = f.read(length)
    if len(data) < length:
        raise EOFError("读取 STRING 时意外遇到文件结束符")
    return data.decode("utf-8", errors="replace")


# ----------------------------------------------------------------------------------

# NBT tag payload reader   NBT标签解析器


def read_tag_payload(f, tag_type):
    if tag_type == TAG_BYTE:
        return read_signed_byte(f)
    if tag_type == TAG_SHORT:
        return read_short(f)
    if tag_type == TAG_INT:
        return read_int(f)
    if tag_type == TAG_LONG:
        return read_long(f)
    if tag_type == TAG_FLOAT:
        return read_float(f)
    if tag_type == TAG_DOUBLE:
        return read_double(f)
    if tag_type == TAG_BYTE_ARRAY:
        return read_byte_array(f)
    if tag_type == TAG_STRING:
        return read_string(f)
    if tag_type == TAG_LIST:
        child_type = read_byte(f)
        length = read_int(f)
        lst = []
        for _ in range(length):
            lst.append(read_tag_payload(f, child_type))
        return lst
    if tag_type == TAG_COMPOUND:
        comp = {}
        while True:
            t = read_byte(f)
            if t == TAG_END:
                break
            name = read_string(f).lower()
            comp[name] = read_tag_payload(f, t)
        return comp
    if tag_type == TAG_INT_ARRAY:
        length = read_int(f)
        arr = []
        for _ in range(length):
            arr.append(read_int(f))
        return arr
    if tag_type == TAG_LONG_ARRAY:
        length = read_int(f)
        arr = []
        for _ in range(length):
            arr.append(read_long(f))
        return arr
    raise NotImplementedError(f"标签类型 {tag_type} 未实现")


# ----------------------------------------------------------------------------------

# read and prepare data structures   读取和准备数据结构体


def load_blocks_from_root(root):
    def get_tag(root, name):
        if name in root:
            return root[name]
        raise KeyError(f"文件缺少必须的 {name} 字段")

    width = int(get_tag(root, "width"))
    height = int(get_tag(root, "height"))
    length = int(get_tag(root, "length"))
    blocks_raw = get_tag(root, "blocks")
    data_raw = root.get("data", bytearray([0]) * len(blocks_raw))

    try:
        blocks_np = np.frombuffer(memoryview(blocks_raw), dtype=np.uint8).copy()
    except Exception:
        blocks_np = np.array(list(blocks_raw), dtype=np.uint8)

    if len(data_raw) < blocks_np.size:
        data_np = np.zeros(blocks_np.size, dtype=np.uint8)
        if len(data_raw) > 0:
            data_np[: len(data_raw)] = np.frombuffer(
                memoryview(data_raw), dtype=np.uint8
            )
    else:
        try:
            data_np = np.frombuffer(memoryview(data_raw), dtype=np.uint8).copy()
        except Exception:
            data_np = np.array(list(data_raw), dtype=np.uint8)

    expected = width * height * length
    if blocks_np.size != expected:
        raise ValueError(
            f"发现 blocks 数量与 width * height * length 不匹配: {blocks_np.size} != {expected}"
        )

    blocks_np = blocks_np.reshape((height, length, width))
    data_np = data_np.reshape((height, length, width))

    return {
        "width": width,
        "height": height,
        "length": length,
        "blocks": blocks_np,
        "data": data_np,
    }


# ----------------------------------------------------------------------------------

# gzip NBT parser   GZIP解压器


def parse_nbt_gzip(path):
    with gzip.open(path, "rb") as gz:
        tag_type = read_byte(gz)
        if tag_type != TAG_COMPOUND:
            raise ValueError(f"发现文件头不是 TAG_Compound(10) ,而是 {tag_type}")
        root_name = read_string(gz)
        root_payload = read_tag_payload(gz, TAG_COMPOUND)
    return root_name, root_payload


# ----------------------------------------------------------------------------------

"""NBT解析器"""

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

# low-level NBT readers (little-endian)   NBT低级二进制读取函数 (小端序)


def read_byte(f):
    data = f.read(1)
    if len(data) < 1:
        raise EOFError("读取 无符号BYTE 时意外遇到文件结束符")
    return struct.unpack("<B", data)[0]


def read_signed_byte(f):
    data = f.read(1)
    if len(data) < 1:
        raise EOFError("读取 有符号BYTE 时意外遇到文件结束符")
    return struct.unpack("<b", data)[0]


def read_short(f):
    data = f.read(2)
    if len(data) < 2:
        raise EOFError("读取 有符号SHORT 时意外遇到文件结束符")
    return struct.unpack("<h", data)[0]


def read_ushort(f):
    data = f.read(2)
    if len(data) < 2:
        raise EOFError("读取 无符号SHORT 时意外遇到文件结束符")
    return struct.unpack("<H", data)[0]


def read_int(f):
    data = f.read(4)
    if len(data) < 4:
        raise EOFError("读取 有符号INT 时意外遇到文件结束符")
    return struct.unpack("<i", data)[0]


def read_long(f):
    data = f.read(8)
    if len(data) < 8:
        raise EOFError("读取 有符号LONG 时意外遇到文件结束符")
    return struct.unpack("<q", data)[0]


def read_float(f):
    data = f.read(4)
    if len(data) < 4:
        raise EOFError("读取 单精度浮点数 时意外遇到文件结束符")
    return struct.unpack("<f", data)[0]


def read_double(f):
    data = f.read(8)
    if len(data) < 8:
        raise EOFError("读取 双精度浮点数 时意外遇到文件结束符")
    return struct.unpack("<d", data)[0]


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


def read_tag_payload(f, tag_type, preserve_child_tag=False):
    # 由于 Python 在 struct.unpack 时会合并 bool 和 int 类型, 故需要使用 tag 来保存 block_states 中的数据类型
    # preserve_child_tag: 如果为 True, 则对原子类型的返回值用 (value, tag_type) 包装
    # preserve_child_tag: 如果为 False, 直接返回原生 Python 值
    if tag_type == TAG_BYTE:
        v = read_signed_byte(f)
        return (v, TAG_BYTE) if preserve_child_tag else v
    if tag_type == TAG_SHORT:
        v = read_short(f)
        return (v, TAG_SHORT) if preserve_child_tag else v
    if tag_type == TAG_INT:
        v = read_int(f)
        return (v, TAG_INT) if preserve_child_tag else v
    if tag_type == TAG_LONG:
        v = read_long(f)
        return (v, TAG_LONG) if preserve_child_tag else v
    if tag_type == TAG_FLOAT:
        v = read_float(f)
        return (v, TAG_FLOAT) if preserve_child_tag else v
    if tag_type == TAG_DOUBLE:
        v = read_double(f)
        return (v, TAG_DOUBLE) if preserve_child_tag else v
    if tag_type == TAG_BYTE_ARRAY:
        v = read_byte_array(f)
        return (v, TAG_BYTE_ARRAY) if preserve_child_tag else v
    if tag_type == TAG_STRING:
        v = read_string(f)
        return (v, TAG_STRING) if preserve_child_tag else v
    if tag_type == TAG_LIST:
        child_type = read_byte(f)
        length = read_int(f)
        lst = []
        for _ in range(length):
            lst.append(read_tag_payload(f, child_type, preserve_child_tag))
        return lst
    if tag_type == TAG_COMPOUND:
        comp = {}
        while True:
            t = read_byte(f)
            if t == TAG_END:
                break
            name = read_string(f)
            if name == "states":
                comp[name] = read_tag_payload(f, t, preserve_child_tag=True)
            else:
                comp[name] = read_tag_payload(f, t, preserve_child_tag)
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


def parse_data_from_root(root, INCLUDE_CMD):
    size = get_tag(root, "size")
    if not (isinstance(size, list) and len(size) >= 3):
        raise ValueError("无法解析 size 字段")
    sizeX = int(size[0])
    sizeY = int(size[1])
    sizeZ = int(size[2])

    structure = get_tag(root, "structure")
    if not isinstance(structure, dict):
        raise ValueError("无法解析 structure 字段")
    block_indices = get_tag(structure, "block_indices")
    palette = get_tag(structure, "palette")

    if not (
        isinstance(block_indices, list)
        and all(isinstance(item, list) for item in block_indices)
    ):
        raise ValueError("无法解析 block_indices 字段")
    block_primary = list(block_indices[0]) if len(block_indices) > 0 else []
    block_secondary = list(block_indices[1]) if len(block_indices) > 1 else []
    block_secondary = block_secondary[: len(block_primary)] + [-1] * max(
        0, len(block_primary) - len(block_secondary)
    )
    if block_primary == []:
        raise ValueError(
            "发现 block_indices 字段的第一项是空表, 说明建筑文件中没有任何方块"
        )
    size_value = sizeX * sizeY * sizeZ
    if len(block_primary) != size_value:
        raise ValueError(
            f"发现 block_indices 数量与 sizeX * sizeY * sizeZ 不匹配: {len(block_primary)} != {size_value}"
        )

    primary_np = np.array(block_primary, dtype=int)
    primary_np = primary_np.reshape((sizeX, sizeY, sizeZ))
    secondary_np = np.array(block_secondary, dtype=int)
    secondary_np = secondary_np.reshape((sizeX, sizeY, sizeZ))

    if not isinstance(palette, dict):
        raise ValueError("无法解析 palette 字段")
    block_position_data = {}
    if "default" in palette:
        default = palette["default"]
        if not isinstance(default, dict):
            raise ValueError("无法解析 palette_default 字段")
        block_palette = get_tag(default, "block_palette")
        if INCLUDE_CMD:
            block_position_data = get_tag(default, "block_position_data", True, {})
    else:
        for v in palette.values():
            if isinstance(v, dict) and "block_palette" in v:
                block_palette = v["block_palette"]
                if INCLUDE_CMD:
                    block_position_data = get_tag(v, "block_position_data", True, {})
                break
        else:
            raise ValueError("无法在 palette 字段中找到 block_palette")

    if not (
        isinstance(block_palette, list)
        and all(isinstance(item, dict) for item in block_palette)
    ):
        raise ValueError("无法解析 block_palette 字段")
    name_states_palette, AIR_INDEX = process_palette(block_palette)

    cmd_update_data = []
    if INCLUDE_CMD:
        structure_world_origin = get_tag(root, "structure_world_origin", True, [])
        if not (
            isinstance(structure_world_origin, list)
            and len(structure_world_origin) >= 3
        ):
            structure_world_origin = []
        if structure_world_origin:
            worldX = int(structure_world_origin[0])
            worldY = int(structure_world_origin[1])
            worldZ = int(structure_world_origin[2])
            if not isinstance(block_position_data, dict):
                raise ValueError("无法解析 block_position_data 字段")
            cmd_update_data = process_cmd(block_position_data, worldX, worldY, worldZ)

    return {
        "size": {"X": sizeX, "Y": sizeY, "Z": sizeZ},
        "block_primary": primary_np,
        "block_secondary": secondary_np,
        "block_palette": name_states_palette,
        "command_data": cmd_update_data,
        "air_index": AIR_INDEX,
    }


def get_tag(data, name, allow_not_exist=False, default=None):
    if name in data:
        return data[name]
    if allow_not_exist:
        return default
    raise KeyError(f"文件缺少必须的 {name} 字段")


# ----------------------------------------------------------------------------------

# read file   读取文件


def read_file(path):
    with open(path, "rb") as f:
        tag_type = read_byte(f)
        if tag_type != TAG_COMPOUND:
            raise ValueError(f"发现文件头不是 TAG_Compound(10) ,而是 {tag_type}")
        _ = read_string(f)
        root_payload = read_tag_payload(f, TAG_COMPOUND)
    return root_payload


# ----------------------------------------------------------------------------------

# process block names and block states   处理方块名称和方块状态


def process_palette(block_palette):
    result = []
    AIR_INDEX = None
    for idx, block in enumerate(block_palette):
        name = str(get_tag(block, "name"))
        states = get_tag(block, "states", True, {})
        if name in ("minecraft:air", "air"):
            AIR_INDEX = idx
        if not states or not isinstance(states, dict):
            result.append(name)
            continue

        states_list = []
        for k, v in states.items():
            if not (isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], int)):
                raise ValueError("无法解析 block_states 的类型信息")
            val, tag = v[0], v[1]

            if tag == TAG_BYTE:
                if val == 0:
                    states_list.append(f'"{k}"=false')
                elif val == 1:
                    states_list.append(f'"{k}"=true')
                else:
                    states_list.append(f'"{k}"={int(val)}')
            elif tag in (TAG_SHORT, TAG_INT, TAG_LONG):
                states_list.append(f'"{k}"={int(val)}')
            elif tag == TAG_STRING:
                states_list.append(f'"{k}"="{val}"')

        states_str = ",".join(states_list)
        result.append(f"{name} [{states_str}]")
    return result, AIR_INDEX


# ----------------------------------------------------------------------------------


# process command block update packet   处理命令导入


def process_cmd(block_position_data, worldX, worldY, worldZ):
    result = []
    for v in block_position_data.values():
        if not (isinstance(v, dict) and "block_entity_data" in v):
            continue
        block_entity_data = v["block_entity_data"]
        if not (isinstance(block_entity_data, dict) and "id" in block_entity_data):
            continue
        block_id = block_entity_data["id"]
        if block_id != "CommandBlock":
            continue
        x = get_tag(block_entity_data, "x", True, None)
        y = get_tag(block_entity_data, "y", True, None)
        z = get_tag(block_entity_data, "z", True, None)
        if x is None or y is None or z is None:
            continue
        position = [int(x) - int(worldX), int(y) - int(worldY), int(z) - int(worldZ)]
        need_redstone = not bool(get_tag(block_entity_data, "auto", True, 0))
        conditional = bool(get_tag(block_entity_data, "conditionalMode", True, 0))
        command = str(get_tag(block_entity_data, "Command", True, ""))
        name = str(get_tag(block_entity_data, "CustomName", True, ""))
        should_track_output = bool(get_tag(block_entity_data, "TrackOutput", True, 0))
        tick_delay = int(get_tag(block_entity_data, "TickDelay", True, 0))
        execute_on_first_tick = bool(
            get_tag(block_entity_data, "ExecuteOnFirstTick", True, 0)
        )
        command_block_update_packet = {
            "Block": True,
            "Position": position,
            "Mode": 0,
            "NeedsRedstone": need_redstone,
            "Conditional": conditional,
            "MinecartEntityRuntimeID": 0,
            "Command": command,
            "LastOutput": "",
            "Name": name,
            "ShouldTrackOutput": should_track_output,
            "TickDelay": tick_delay,
            "ExecuteOnFirstTick": execute_on_first_tick,
        }
        result.append(command_block_update_packet)
    return result

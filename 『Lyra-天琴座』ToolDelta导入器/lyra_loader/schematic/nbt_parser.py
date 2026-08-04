"""schematic文件解析器"""

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
from ..common.streaming_nbt import NBTStreamScanner, close_memmap


@dataclass
class SchematicData:
    root_name: str
    width: int
    height: int
    length: int
    blocks: np.ndarray
    data: np.ndarray
    we_origin: tuple[int, int, int] | None
    we_offset: tuple[int, int, int] | None
    tile_entities: int
    entities: int
    add_blocks: np.ndarray | None = None
    temporary_directory: Path | None = None
    closed: bool = False

    def block_id(self, y: int, z: int, x: int) -> int:
        if self.closed:
            raise RuntimeError("SchematicData 已关闭")
        index = x + z * self.width + y * self.width * self.length
        value = int(self.blocks[y, z, x])
        if self.add_blocks is not None:
            packed = int(self.add_blocks[index // 2])
            value |= ((packed >> 4) if index % 2 == 0 else (packed & 0x0F)) << 8
        return value

    def close(self) -> str | None:
        if self.closed:
            return None
        self.closed = True
        close_memmap(self.blocks)
        close_memmap(self.data)
        close_memmap(self.add_blocks)
        if self.temporary_directory is not None:
            try:
                shutil.rmtree(self.temporary_directory)
            except OSError as error:
                return str(error)
        return None

    def __enter__(self) -> "SchematicData":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def read_file(path: str) -> SchematicData:
    """流式读取经典 Alpha Schematic, 方块数组保存在临时 memmap"""
    temporary_directory = Path(tempfile.mkdtemp(prefix="tooldelta-schematic-"))
    scalar_names = {
        "Materials",
        "Width",
        "Height",
        "Length",
        "WEOriginX",
        "WEOriginY",
        "WEOriginZ",
        "WEOffsetX",
        "WEOffsetY",
        "WEOffsetZ",
    }
    scalar_paths = {(name,) for name in scalar_names}
    array_paths = {(name,) for name in ("Blocks", "Data", "AddBlocks")}
    try:
        result = NBTStreamScanner(
            scalar_paths,
            set(),
            array_paths,
            {("TileEntities",), ("Entities",)},
            temporary_directory,
        ).scan_gzip(path)
        root = {key[0]: value for key, value in result.values.items()}
        root_name = result.root_name
        if root_name.lower() != "schematic":
            raise ValueError(
                f"NBT 根标签名称不是 Schematic, 而是 {root_name or '<空>'}"
            )
        materials = str(_required(root, "Materials"))
        if materials.lower() != "alpha":
            raise ValueError(f"仅支持 Materials=Alpha, 实际为 {materials}")
        width = _positive_int(root, "Width")
        height = _positive_int(root, "Height")
        length = _positive_int(root, "Length")
        volume = width * height * length
        blocks_file = _extracted(result.arrays, ("Blocks",), volume)
        data_file = _extracted(result.arrays, ("Data",), volume)
        add_entry = result.arrays.get(("AddBlocks",))
        if add_entry is not None and add_entry.length != (volume + 1) // 2:
            raise ValueError(
                f"AddBlocks 长度错误: {add_entry.length} != {(volume + 1) // 2}"
            )
        shape = (height, length, width)
        blocks = np.memmap(blocks_file, dtype=np.uint8, mode="r", shape=shape)
        data = np.memmap(data_file, dtype=np.uint8, mode="r", shape=shape)
        add_blocks = (
            np.memmap(
                add_entry.path, dtype=np.uint8, mode="r", shape=(add_entry.length,)
            )
            if add_entry is not None
            else None
        )
        return SchematicData(
            root_name,
            width,
            height,
            length,
            blocks,
            data,
            _vector(root, "WEOrigin"),
            _vector(root, "WEOffset"),
            result.list_lengths.get(("TileEntities",), 0),
            result.list_lengths.get(("Entities",), 0),
            add_blocks,
            temporary_directory,
        )
    except Exception as error:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"无法读取 gzip/NBT 数据: {error}") from error


def _extracted(arrays, path: tuple[str, ...], expected: int) -> Path:
    entry = arrays.get(path)
    if entry is None:
        raise KeyError(f"文件缺少必需的 {path[-1]} 字段")
    if entry.length != expected:
        raise ValueError(
            f"{path[-1]} 数量与建筑体积不匹配: {entry.length} != {expected}"
        )
    return entry.path


def parse_root(root: dict[str, Any], root_name: str = "Schematic") -> SchematicData:
    if root_name.lower() != "schematic":
        raise ValueError(f"NBT 根标签名称不是 Schematic, 而是 {root_name or '<空>'}")
    materials = str(_required(root, "Materials"))
    if materials.lower() != "alpha":
        raise ValueError(f"仅支持 Materials=Alpha, 实际为 {materials}")

    width = _positive_int(root, "Width")
    height = _positive_int(root, "Height")
    length = _positive_int(root, "Length")
    volume = width * height * length

    blocks_raw = _byte_array(_required(root, "Blocks"), "Blocks")
    data_raw = _byte_array(_required(root, "Data"), "Data")
    if len(blocks_raw) != volume:
        raise ValueError(
            f"Blocks 数量与 Width*Height*Length 不匹配: {len(blocks_raw)} != {volume}"
        )
    if len(data_raw) != volume:
        raise ValueError(
            f"Data 数量与 Width*Height*Length 不匹配: {len(data_raw)} != {volume}"
        )

    block_ids = np.frombuffer(blocks_raw, dtype=np.uint8).astype(np.uint16)
    add_raw = root.get("AddBlocks")
    if add_raw is not None:
        add = _byte_array(add_raw, "AddBlocks")
        expected_add = (volume + 1) // 2
        if len(add) != expected_add:
            raise ValueError(f"AddBlocks 长度错误: {len(add)} != {expected_add}")
        packed = np.frombuffer(add, dtype=np.uint8)
        high = np.empty(volume, dtype=np.uint16)
        # MCEdit 格式：偶数方块使用高半字节, 奇数方块使用低半字节
        high[0::2] = packed[: len(high[0::2])] >> 4
        high[1::2] = packed[: len(high[1::2])] & 0x0F
        block_ids |= high << 8

    metadata = np.frombuffer(data_raw, dtype=np.uint8).copy()
    shape = (height, length, width)
    return SchematicData(
        root_name=root_name,
        width=width,
        height=height,
        length=length,
        blocks=block_ids.reshape(shape),
        data=metadata.reshape(shape),
        we_origin=_vector(root, "WEOrigin"),
        we_offset=_vector(root, "WEOffset"),
        tile_entities=_list_length(root.get("TileEntities")),
        entities=_list_length(root.get("Entities")),
    )


def _required(root: dict[str, Any], name: str) -> Any:
    if name not in root:
        raise KeyError(f"文件缺少必需的 {name} 字段")
    return root[name]


def _positive_int(root: dict[str, Any], name: str) -> int:
    value = int(_required(root, name))
    if value <= 0:
        raise ValueError(f"{name} 必须为正整数, 实际为 {value}")
    return value


def _byte_array(value: Any, name: str) -> bytes:
    try:
        return bytes(int(item) & 0xFF for item in value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} 必须是 ByteArray") from error


def _vector(root: dict[str, Any], prefix: str) -> tuple[int, int, int] | None:
    names = tuple(prefix + axis for axis in ("X", "Y", "Z"))
    present = tuple(name in root for name in names)
    if not any(present):
        return None
    if not all(present):
        raise ValueError(f"{prefix}X/Y/Z 必须同时存在")
    return tuple(int(root[name]) for name in names)  # type: ignore[return-value]


def _list_length(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError as error:
        raise ValueError("TileEntities/Entities 必须是 List") from error

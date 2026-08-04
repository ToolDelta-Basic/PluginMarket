"""SchemV2/V3解析器"""

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
from ..common.streaming_nbt import NBTStreamScanner, close_memmap


@dataclass
class SchemData:
    version: int
    data_version: int | None
    width: int
    height: int
    length: int
    offset: tuple[int, int, int]
    palette: tuple[str, ...]
    blocks: np.ndarray
    temporary_directory: Path | None = None
    closed: bool = False

    def palette_id(self, y: int, z: int, x: int) -> int:
        if self.closed:
            raise RuntimeError("SchemData 已关闭")
        return int(self.blocks[y, z, x])

    def close(self) -> str | None:
        if self.closed:
            return None
        self.closed = True
        close_memmap(self.blocks)
        if self.temporary_directory is not None:
            try:
                shutil.rmtree(self.temporary_directory)
            except OSError as error:
                return str(error)
        return None

    def __enter__(self) -> "SchemData":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _plain(value: Any) -> Any:
    return value.unpack() if hasattr(value, "unpack") else value


def read_file(path: str) -> SchemData:
    """流式读取 Sponge Schematic, 方块索引保存在临时 memmap"""
    temporary_directory = Path(tempfile.mkdtemp(prefix="tooldelta-schem-"))
    prefixes = ((), ("Schematic",))
    scalar_names = ("Version", "DataVersion", "Width", "Height", "Length", "Offset")
    scalar_paths = {(*prefix, name) for prefix in prefixes for name in scalar_names}
    compound_paths = {
        (*prefix, *suffix)
        for prefix in prefixes
        for suffix in (("Palette",), ("Blocks", "Palette"))
    }
    byte_paths = {
        (*prefix, *suffix)
        for prefix in prefixes
        for suffix in (("BlockData",), ("Blocks", "Data"))
    }
    try:
        result = NBTStreamScanner(
            scalar_paths,
            compound_paths,
            byte_paths,
            set(),
            temporary_directory,
        ).scan_gzip(path)
        prefix = ("Schematic",) if ("Schematic", "Version") in result.values else ()
        root = {
            name: result.values[(*prefix, name)]
            for name in scalar_names
            if (*prefix, name) in result.values
        }
        version = _positive_int(root, "Version")
        if version not in (2, 3):
            raise ValueError(f"仅支持 Sponge Schematic v2/v3, 当前 Version={version}")
        width = _positive_int(root, "Width")
        height = _positive_int(root, "Height")
        length = _positive_int(root, "Length")
        volume = width * height * length
        palette_path = (
            *prefix,
            *(("Blocks", "Palette") if version == 3 else ("Palette",)),
        )
        data_path = (*prefix, *(("Blocks", "Data") if version == 3 else ("BlockData",)))
        if palette_path not in result.values:
            raise KeyError("文件缺少必需的 Palette Compound")
        palette = _decode_palette(result.values[palette_path])
        data_entry = result.arrays.get(data_path)
        if data_entry is None:
            raise KeyError("文件缺少方块数据字段")
        blocks = _decode_varints_to_memmap(
            data_entry.path,
            temporary_directory / "palette_indexes.bin",
            volume,
            len(palette),
            (height, length, width),
        )
        offset_raw = root.get("Offset", (0, 0, 0))
        offset_values = [int(value) for value in offset_raw]
        if len(offset_values) != 3:
            raise ValueError("Offset 必须包含三个整数")
        data_version = root.get("DataVersion")
        return SchemData(
            version,
            int(data_version) if data_version is not None else None,
            width,
            height,
            length,
            tuple(offset_values),  # type: ignore[arg-type]
            palette,
            blocks,
            temporary_directory,
        )
    except Exception as error:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        if isinstance(error, ValueError | KeyError):
            raise
        raise ValueError(f"无法读取 gzip/NBT 数据: {error}") from error


def _decode_varints_to_memmap(
    source: Path,
    destination: Path,
    expected_count: int,
    palette_size: int,
    shape: tuple[int, int, int],
) -> np.memmap:
    if palette_size <= 0x100:
        dtype = np.uint8
    elif palette_size <= 0x10000:
        dtype = np.uint16
    else:
        dtype = np.uint32
    output = np.memmap(destination, dtype=dtype, mode="w+", shape=shape)
    flat = output.reshape(-1)
    count = 0
    value = 0
    shift = 0
    try:
        with source.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                for byte in chunk:
                    value |= (byte & 0x7F) << shift
                    if byte & 0x80:
                        shift += 7
                        if shift >= 35:
                            raise ValueError("BlockData 中存在超过 5 字节的 VarInt")
                        continue
                    if count >= expected_count:
                        raise ValueError("BlockData 包含多余的方块索引")
                    if value >= palette_size:
                        raise ValueError(
                            f"BlockData 包含越界调色板索引 {value}, Palette 大小为 {palette_size}"
                        )
                    flat[count] = value
                    count += 1
                    value = 0
                    shift = 0
        if shift:
            raise ValueError("BlockData 以不完整的 VarInt 结束")
        if count != expected_count:
            raise ValueError(
                f"BlockData 数量与 Width*Height*Length 不匹配: {count} != {expected_count}"
            )
        output.flush()
        return output
    except Exception:
        close_memmap(output)
        raise


def parse_root(root: dict[str, Any]) -> SchemData:
    version = _positive_int(root, "Version")
    if version not in (2, 3):
        raise ValueError(f"仅支持 Sponge Schematic v2/v3, 当前 Version={version}")
    width = _positive_int(root, "Width")
    height = _positive_int(root, "Height")
    length = _positive_int(root, "Length")
    volume = width * height * length

    if version == 3:
        blocks_root = root.get("Blocks")
        if not isinstance(blocks_root, dict):
            raise KeyError("文件缺少必须的 Blocks Compound")
        palette_raw = blocks_root.get("Palette")
        data_raw = blocks_root.get("Data")
    else:
        palette_raw = root.get("Palette")
        data_raw = root.get("BlockData")

    palette = _decode_palette(palette_raw)
    indexes = decode_varints(data_raw, volume)
    if indexes and max(indexes) >= len(palette):
        raise ValueError(
            f"BlockData 包含越界调色板索引 {max(indexes)}, Palette 大小为 {len(palette)}"
        )
    # Sponge 顺序: x + z * Width + y * Width * Length
    blocks = np.asarray(indexes, dtype=np.int32).reshape((height, length, width))
    offset_raw = root.get("Offset", (0, 0, 0))
    offset_values = [int(v) for v in offset_raw]
    if len(offset_values) != 3:
        raise ValueError("Offset 必须包含三个整数")
    data_version = root.get("DataVersion")
    return SchemData(
        version=version,
        data_version=int(data_version) if data_version is not None else None,
        width=width,
        height=height,
        length=length,
        offset=tuple(offset_values),  # type: ignore
        palette=palette,
        blocks=blocks,
    )


def _positive_int(root: dict[str, Any], name: str) -> int:
    if name not in root:
        raise KeyError(f"文件缺少必须的 {name} 字段")
    value = int(root[name])
    if value <= 0:
        raise ValueError(f"{name} 必须为正整数, 实际为 {value}")
    return value


def _decode_palette(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Palette 必须是非空 Compound")
    by_id: dict[int, str] = {}
    for state, palette_id in raw.items():
        index = int(palette_id)
        if index < 0 or index in by_id:
            raise ValueError(f"Palette ID 非法或重复: {index}")
        by_id[index] = str(state)
    expected = set(range(len(by_id)))
    if set(by_id) != expected:
        raise ValueError("Palette ID 必须从 0 开始连续排列")
    return tuple(by_id[index] for index in range(len(by_id)))


def decode_varints(raw: Any, expected_count: int) -> list[int]:
    if raw is None:
        raise KeyError("文件缺少方块数据字段")
    data = bytes(int(value) & 0xFF for value in raw)
    result: list[int] = []
    value = 0
    shift = 0
    for byte in data:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            if shift >= 35:
                raise ValueError("BlockData 中存在超过 5 字节的 VarInt")
            continue
        result.append(value)
        value = 0
        shift = 0
    if shift:
        raise ValueError("BlockData 以不完整的 VarInt 结束")
    if len(result) != expected_count:
        raise ValueError(
            f"BlockData 数量与 Width*Height*Length 不匹配: {len(result)} != {expected_count}"
        )
    return result

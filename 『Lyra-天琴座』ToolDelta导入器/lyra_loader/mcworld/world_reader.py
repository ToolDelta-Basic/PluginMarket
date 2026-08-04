"""MCWorld, LevelDB, SubChunk解析器"""

from __future__ import annotations

import io
import json
import math
import shutil
import struct
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import nbtlib
import numpy as np

MAX_EXTRACTED_BYTES = 32 << 30
MAX_ARCHIVE_ENTRIES = 100_000
ALLOWED_BITS = {0, 1, 2, 3, 4, 5, 6, 8, 16}
COMMAND_MODES = {
    "minecraft:command_block": 0,
    "minecraft:repeating_command_block": 1,
    "minecraft:chain_command_block": 2,
}


@dataclass(frozen=True)
class PaletteEntry:
    name: str
    command: str
    air: bool


@dataclass
class DecodedSubChunk:
    source_y: int
    layers: tuple[np.ndarray, ...]
    palettes: tuple[tuple[PaletteEntry, ...], ...]
    extra_layers: int = 0

    def palette_entry(self, layer: int, x: int, y: int, z: int) -> PaletteEntry | None:
        if layer >= len(self.layers):
            return None
        palette_id = int(self.layers[layer][x, y, z])
        palette = self.palettes[layer]
        if not 0 <= palette_id < len(palette):
            raise ValueError(
                f"SubChunk Palette 索引越界: {palette_id} >= {len(palette)}"
            )
        return palette[palette_id]


@dataclass
class MCWorldData:
    database: Any
    temporary_directory: Path
    source_dimension: int
    source_min: tuple[int, int, int]
    source_max: tuple[int, int, int]
    world_version: str | None
    closed: bool = False

    @property
    def size(self) -> tuple[int, int, int]:
        return tuple(
            high - low + 1 for low, high in zip(self.source_min, self.source_max)
        )  # type: ignore[return-value]

    def chunk_prefix(self, cx: int, cz: int) -> bytes:
        if self.source_dimension == 0:
            return struct.pack("<ii", cx, cz)
        return struct.pack("<iii", cx, cz, self.source_dimension)

    def read_subchunk(self, cx: int, cy: int, cz: int) -> DecodedSubChunk | None:
        if not -128 <= cy <= 127:
            raise ValueError(f"SubChunk Y 超出键格式范围: {cy}")
        key = self.chunk_prefix(cx, cz) + b"\x2f" + struct.pack("b", cy)
        try:
            payload = self.database.get(key)
        except KeyError:
            return None
        return decode_subchunk(payload, cy)

    def read_block_entities(self, cx: int, cz: int) -> list[dict[str, Any]]:
        key = self.chunk_prefix(cx, cz) + b"\x31"
        try:
            payload = self.database.get(key)
        except KeyError:
            return []
        return parse_nbt_sequence(payload)

    def count_entities(self, cx: int, cz: int) -> int:
        prefix = self.chunk_prefix(cx, cz)
        try:
            legacy = len(parse_nbt_sequence(self.database.get(prefix + b"\x32")))
        except KeyError:
            legacy = 0
        try:
            actors = len(self.database.get(b"digp" + prefix)) // 8
        except KeyError:
            actors = 0
        return max(legacy, actors)

    def close(self) -> str | None:
        if self.closed:
            return None
        self.closed = True
        try:
            self.database.close()
        except Exception:
            pass
        try:
            shutil.rmtree(self.temporary_directory)
        except OSError as error:
            return str(error)
        return None

    def __enter__(self) -> "MCWorldData":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def open_world(
    path: str,
    source_dimension: int,
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> MCWorldData:
    source_min = tuple(min(a, b) for a, b in zip(first, second))
    source_max = tuple(max(a, b) for a, b in zip(first, second))
    temporary_directory = Path(tempfile.mkdtemp(prefix="tooldelta-mcworld-"))
    try:
        _extract_world(path, temporary_directory)
        db_path = temporary_directory / "db"
        if not (db_path / "CURRENT").is_file():
            raise ValueError("mcworld 中缺少有效的 db/CURRENT")
        import leveldb

        database_type: Any = getattr(leveldb, "LevelDB")
        database = database_type(str(db_path), False)
        version = _read_level_version(temporary_directory / "level.dat")
        return MCWorldData(
            database,
            temporary_directory,
            source_dimension,
            source_min,  # type: ignore[arg-type]
            source_max,  # type: ignore[arg-type]
            version,
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise


def _extract_world(path: str, destination: Path) -> None:
    seen: set[str] = set()
    selected: list[zipfile.ZipInfo] = []
    total = 0
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError(
                    f"ZIP 条目过多: {len(entries)} > {MAX_ARCHIVE_ENTRIES}"
                )
            for entry in entries:
                normalized = entry.filename.replace("\\", "/")
                parts = PurePosixPath(normalized).parts
                if normalized.startswith("/") or ".." in parts:
                    raise ValueError(f"ZIP 包含不安全路径: {entry.filename}")
                key = normalized.rstrip("/").casefold()
                if key in seen:
                    raise ValueError(f"ZIP 包含重复路径: {entry.filename}")
                seen.add(key)
                if entry.flag_bits & 1:
                    raise ValueError(f"ZIP 包含加密条目: {entry.filename}")
                if normalized == "level.dat" or normalized.startswith("db/"):
                    selected.append(entry)
                    total += entry.file_size
                    if total > MAX_EXTRACTED_BYTES:
                        raise ValueError(
                            f"LevelDB 解压大小超过限制: {total} > {MAX_EXTRACTED_BYTES}"
                        )
            if not selected:
                raise ValueError("mcworld 中没有 level.dat 或 db/ 数据")
            free = shutil.disk_usage(destination).free
            if free < total + (64 << 20):
                raise OSError(
                    f"临时目录磁盘空间不足: 需要至少 {total + (64 << 20)} 字节"
                )
            for entry in selected:
                target = destination.joinpath(*PurePosixPath(entry.filename).parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, 1 << 20)
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError(f"无法解压 mcworld: {error}") from error


def _read_level_version(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        with path.open("rb") as stream:
            header = stream.read(8)
            if len(header) != 8:
                return None
            _, length = struct.unpack("<II", header)
            payload = stream.read(length)
        root = nbtlib.File.parse(io.BytesIO(payload), byteorder="little")
        version = root.get("lastOpenedWithVersion")
        if isinstance(version, list):
            return ".".join(str(int(item)) for item in version)
        value = root.get("LastPlayed")
        return f"LastPlayed={int(value)}" if value is not None else None
    except Exception:
        return None


def decode_subchunk(payload: bytes, expected_y: int) -> DecodedSubChunk:
    if not payload:
        raise ValueError("SubChunk 数据为空")
    version = payload[0]
    if version == 8:
        if len(payload) < 2:
            raise ValueError("SubChunk v8 头部被截断")
        storage_count, offset = payload[1], 2
    elif version == 9:
        if len(payload) < 3:
            raise ValueError("SubChunk v9 头部被截断")
        storage_count, stored_y, offset = (
            payload[1],
            struct.unpack("b", payload[2:3])[0],
            3,
        )
        if stored_y != expected_y:
            raise ValueError(f"SubChunk v9 Y 不一致: 键={expected_y}, 数据={stored_y}")
    else:
        raise ValueError(f"不支持的 SubChunk 版本: {version}")
    layers: list[np.ndarray] = []
    palettes: list[tuple[PaletteEntry, ...]] = []
    for _ in range(storage_count):
        indexes, palette, consumed = decode_storage(payload[offset:])
        offset += consumed
        if len(layers) < 2:
            layers.append(indexes)
            palettes.append(palette)
    if offset != len(payload):
        raise ValueError(f"SubChunk 尾部存在 {len(payload) - offset} 字节多余数据")
    return DecodedSubChunk(
        expected_y,
        tuple(layers),
        tuple(palettes),
        max(0, storage_count - 2),
    )


def decode_storage(payload: bytes) -> tuple[np.ndarray, tuple[PaletteEntry, ...], int]:
    if not payload:
        raise ValueError("Storage 头部被截断")
    bits = payload[0] >> 1
    if bits not in ALLOWED_BITS:
        raise ValueError(f"Storage 位宽不受支持: {bits}")
    offset = 1
    if bits:
        values_per_word = 32 // bits
        word_count = math.ceil(4096 / values_per_word)
        byte_count = word_count * 4
        if len(payload) < offset + byte_count:
            raise ValueError("Storage 位数组被截断")
        words = np.frombuffer(payload, dtype="<u4", count=word_count, offset=offset)
        positions = np.arange(4096, dtype=np.uint32)
        indexes = (
            words[positions // values_per_word]
            >> ((positions % values_per_word) * bits)
        ) & ((1 << bits) - 1)
        indexes = indexes.astype(np.uint16).reshape((16, 16, 16)).swapaxes(1, 2)
        offset += byte_count
    else:
        indexes = np.zeros((16, 16, 16), dtype=np.uint16)
    if len(payload) < offset + 4:
        raise ValueError("Storage 缺少 Palette 长度")
    palette_size = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    if palette_size == 0 or palette_size > 65536:
        raise ValueError(f"Storage Palette 大小非法: {palette_size}")
    stream = io.BytesIO(payload)
    stream.seek(offset)
    palette: list[PaletteEntry] = []
    for _ in range(palette_size):
        try:
            root = nbtlib.File.parse(stream, byteorder="little")
        except Exception as error:
            raise ValueError(f"无法解析 Storage Palette NBT: {error}") from error
        palette.append(_palette_entry(root))
    offset = stream.tell()
    maximum = int(indexes.max())
    if maximum >= palette_size:
        raise ValueError(f"Storage Palette 索引越界: {maximum} >= {palette_size}")
    return indexes, tuple(palette), offset


def _palette_entry(root: Any) -> PaletteEntry:
    if "name" not in root:
        raise ValueError("Palette 方块缺少 name")
    name = str(root["name"])
    states = root.get("states", {})
    if not isinstance(states, dict):
        raise ValueError(f"方块 {name} 的 states 不是 Compound")
    rendered: list[str] = []
    for state_name in sorted(states):
        value = states[state_name]
        if isinstance(value, nbtlib.Byte):
            number = int(value)
            if number not in (0, 1):
                raise ValueError(f"Byte 布尔状态 {state_name} 不是 0/1")
            output = "true" if number else "false"
        elif isinstance(value, nbtlib.Short | nbtlib.Int | nbtlib.Long):
            output = str(int(value))
        elif isinstance(value, nbtlib.String):
            output = json.dumps(str(value), ensure_ascii=False)
        else:
            raise ValueError(
                f"方块状态 {state_name} 使用不支持的 NBT 类型 {type(value).__name__}"
            )
        rendered.append(f"{json.dumps(str(state_name), ensure_ascii=False)}={output}")
    command = name if not rendered else f"{name} [{','.join(rendered)}]"
    return PaletteEntry(name, command, name in ("air", "minecraft:air"))


def parse_nbt_sequence(payload: bytes) -> list[dict[str, Any]]:
    stream = io.BytesIO(payload)
    result: list[dict[str, Any]] = []
    while stream.tell() < len(payload):
        before = stream.tell()
        try:
            root = nbtlib.File.parse(stream, byteorder="little")
        except Exception as error:
            raise ValueError(f"无法解析方块实体 NBT, 偏移 {before}: {error}") from error
        if stream.tell() <= before:
            raise ValueError("方块实体 NBT 解析器没有前进")
        result.append(dict(root))
    return result


def command_packet(
    entity: dict[str, Any],
    mode: int,
    target: tuple[int, int, int],
) -> dict[str, Any]:
    return {
        "Block": True,
        "Position": list(target),
        "Mode": mode,
        "NeedsRedstone": not bool(int(entity.get("auto", 0))),
        "Conditional": bool(int(entity.get("conditionalMode", 0))),
        "MinecartEntityRuntimeID": 0,
        "Command": str(entity.get("Command", "")),
        "LastOutput": "",
        "Name": str(entity.get("CustomName", "")),
        "ShouldTrackOutput": bool(int(entity.get("TrackOutput", 0))),
        "TickDelay": int(entity.get("TickDelay", 0)),
        "ExecuteOnFirstTick": bool(int(entity.get("ExecuteOnFirstTick", 0))),
    }

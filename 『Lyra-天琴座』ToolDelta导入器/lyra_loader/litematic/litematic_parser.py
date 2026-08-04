"""LitematicaV5/V6的流式解析器"""

from __future__ import annotations

import math
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..common.streaming_nbt import NBTStreamScanner, TaggedValue, close_memmap


@dataclass
class LitematicRegion:
    name: str
    position: tuple[int, int, int]
    size: tuple[int, int, int]
    palette: tuple[str, ...]
    block_states: np.memmap
    bits_per_entry: int

    @property
    def dimensions(self) -> tuple[int, int, int]:
        return tuple(abs(value) for value in self.size)  # type: ignore[return-value]

    @property
    def volume(self) -> int:
        x, y, z = self.dimensions
        return x * y * z

    def palette_id(self, x: int, y: int, z: int) -> int:
        sx, sy, sz = self.dimensions
        index = x + z * sx + y * sx * sz
        bit_index = index * self.bits_per_entry
        word_index, offset = divmod(bit_index, 64)
        value = int(self.block_states[word_index]) >> offset
        remaining = 64 - offset
        if remaining < self.bits_per_entry:
            value |= int(self.block_states[word_index + 1]) << remaining
        result = value & ((1 << self.bits_per_entry) - 1)
        if result >= len(self.palette):
            raise ValueError(
                f"Region {self.name} 的 BlockStates 包含越界 Palette 索引 {result}"
            )
        return result

    def relative_position(self, x: int, y: int, z: int) -> tuple[int, int, int]:
        return tuple(
            origin + local * (1 if size > 0 else -1)
            for origin, size, local in zip(self.position, self.size, (x, y, z))
        )  # type: ignore[return-value]


@dataclass
class LitematicData:
    version: int
    data_version: int
    regions: tuple[LitematicRegion, ...]
    minimum: tuple[int, int, int]
    maximum: tuple[int, int, int]
    ignored_counts: dict[str, int]
    temporary_directory: Path
    closed: bool = False

    @property
    def dimensions(self) -> tuple[int, int, int]:
        return tuple(b - a + 1 for a, b in zip(self.minimum, self.maximum))  # type: ignore[return-value]

    def close(self) -> str | None:
        if self.closed:
            return None
        self.closed = True
        for region in self.regions:
            close_memmap(region.block_states)
        try:
            shutil.rmtree(self.temporary_directory)
        except OSError as error:
            return str(error)
        return None

    def __enter__(self) -> "LitematicData":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def read_file(path: str) -> LitematicData:
    temporary_directory = Path(tempfile.mkdtemp(prefix="tooldelta-litematic-"))
    try:
        first = NBTStreamScanner(
            {("Version",), ("MinecraftDataVersion",)},
            set(),
            set(),
            set(),
            temporary_directory,
            compound_name_paths={("Regions",)},
        ).scan_gzip(path)
        version = _required_int(first.values, ("Version",))
        if version not in (5, 6):
            raise ValueError(f"仅支持 Litematica v5/v6, 当前 Version={version}")
        data_version = _required_int(first.values, ("MinecraftDataVersion",))
        names = first.compound_children.get(("Regions",), ())
        if not names:
            raise ValueError("Litematic 文件不包含任何 Region")

        compound_paths: set[tuple[str, ...]] = set()
        palette_paths: set[tuple[str, ...]] = set()
        long_paths: set[tuple[str, ...]] = set()
        ignored_paths: set[tuple[str, ...]] = set()
        for name in names:
            base = ("Regions", name)
            compound_paths.update({(*base, "Position"), (*base, "Size")})
            palette_paths.add((*base, "BlockStatePalette"))
            long_paths.add((*base, "BlockStates"))
            ignored_paths.update(
                {
                    (*base, "Entities"),
                    (*base, "TileEntities"),
                    (*base, "PendingBlockTicks"),
                    (*base, "PendingFluidTicks"),
                }
            )
        second = NBTStreamScanner(
            set(),
            compound_paths | palette_paths,
            set(),
            ignored_paths,
            temporary_directory,
            typed_paths=palette_paths,
            long_array_paths=long_paths,
        ).scan_gzip(path)

        regions: list[LitematicRegion] = []
        minimum = [2**63 - 1] * 3
        maximum = [-(2**63)] * 3
        ignored = {
            "Entities": 0,
            "TileEntities": 0,
            "PendingBlockTicks": 0,
            "PendingFluidTicks": 0,
        }
        for name in names:
            base = ("Regions", name)
            position = _vector(
                second.values.get((*base, "Position")), "Position", False
            )
            size = _vector(second.values.get((*base, "Size")), "Size", True)
            dimensions = tuple(abs(value) for value in size)
            volume = math.prod(dimensions)
            palette = _decode_palette(second.values.get((*base, "BlockStatePalette")))
            bits = max(2, (len(palette) - 1).bit_length())
            expected_longs = math.ceil(volume * bits / 64)
            entry = second.arrays.get((*base, "BlockStates"))
            if entry is None:
                raise KeyError(f"Region {name} 缺少 BlockStates")
            if entry.length != expected_longs:
                raise ValueError(
                    f"Region {name} 的 BlockStates 长度错误: {entry.length} != {expected_longs}"
                )
            words = np.memmap(entry.path, dtype=">u8", mode="r", shape=(entry.length,))
            region = LitematicRegion(name, position, size, palette, words, bits)
            _validate_palette_indexes(region)
            regions.append(region)
            for axis, (origin, signed_size) in enumerate(zip(position, size)):
                endpoint = origin + signed_size - (1 if signed_size > 0 else -1)
                minimum[axis] = min(minimum[axis], origin, endpoint)
                maximum[axis] = max(maximum[axis], origin, endpoint)
            for key in ignored:
                ignored[key] += second.list_lengths.get((*base, key), 0)
        return LitematicData(
            version,
            data_version,
            tuple(regions),
            tuple(minimum),  # type: ignore[arg-type]
            tuple(maximum),  # type: ignore[arg-type]
            ignored,
            temporary_directory,
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise


def _required_int(values: dict[tuple[str, ...], Any], path: tuple[str, ...]) -> int:
    if path not in values:
        raise KeyError(f"文件缺少必需字段 {'/'.join(path)}")
    return int(values[path])


def _vector(value: Any, name: str, nonzero: bool) -> tuple[int, int, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必须是 Compound")
    try:
        result = tuple(int(value[axis]) for axis in ("x", "y", "z"))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{name} 必须包含整数 x/y/z") from error
    if nonzero and any(item == 0 for item in result):
        raise ValueError(f"{name} 的三个轴长度都不能为 0")
    return result  # type: ignore[return-value]


def _decode_palette(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("BlockStatePalette 必须是非空 List")
    result: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict) or "Name" not in entry:
            raise ValueError("BlockStatePalette 项缺少 Name")
        name = str(_plain(entry["Name"]))
        properties = entry.get("Properties", {})
        if not isinstance(properties, dict):
            raise ValueError(f"Palette {name} 的 Properties 不是 Compound")
        pairs = sorted((key, str(_plain(value))) for key, value in properties.items())
        state = (
            name if not pairs else f"{name}[{','.join(f'{k}={v}' for k, v in pairs)}]"
        )
        result.append(_compatibility_state(state))
    return tuple(result)


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, TaggedValue) else value


def _compatibility_state(state: str) -> str:
    if state.startswith("minecraft:cauldron[") and "level=0" not in state:
        return state.replace("minecraft:cauldron", "minecraft:water_cauldron", 1)
    if state.startswith("minecraft:rail[") and "waterlogged=" not in state:
        return state[:-1] + ",waterlogged=false]"
    if state.startswith("minecraft:player_head[") and "powered=" not in state:
        return state[:-1] + ",powered=false]"
    return state


def _validate_palette_indexes(region: LitematicRegion) -> None:
    """分批矢量校验位流, 不保留完整 Palette 索引副本"""
    mask = np.uint64((1 << region.bits_per_entry) - 1)
    for start in range(0, region.volume, 1 << 20):
        stop = min(region.volume, start + (1 << 20))
        indexes = np.arange(start, stop, dtype=np.uint64)
        bit_indexes = indexes * np.uint64(region.bits_per_entry)
        word_indexes = bit_indexes >> np.uint64(6)
        offsets = bit_indexes & np.uint64(63)
        values = region.block_states[word_indexes] >> offsets
        crossing = offsets + region.bits_per_entry > 64
        if np.any(crossing):
            selected_words = word_indexes[crossing]
            selected_offsets = offsets[crossing]
            values[crossing] |= region.block_states[selected_words + 1] << (
                np.uint64(64) - selected_offsets
            )
        values &= mask
        invalid = np.flatnonzero(values >= len(region.palette))
        if invalid.size:
            absolute_index = start + int(invalid[0])
            raise ValueError(
                f"Region {region.name} 的 BlockStates 在索引 {absolute_index} "
                f"包含越界 Palette 索引 {int(values[invalid[0]])}"
            )

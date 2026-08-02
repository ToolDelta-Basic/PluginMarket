"""MCStructure小端NBT流式解析器"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..common.streaming_nbt import (
    NBTStreamScanner,
    TAG_BYTE,
    TAG_INT,
    TAG_LONG,
    TAG_SHORT,
    TAG_STRING,
    TaggedValue,
    close_memmap,
)

MAX_VOLUME = 134_217_728
COMMAND_MODES = {
    "minecraft:command_block": 0,
    "minecraft:repeating_command_block": 1,
    "minecraft:chain_command_block": 2,
}


@dataclass
class MCStructureData:
    size_x: int
    size_y: int
    size_z: int
    block_primary: np.ndarray
    block_secondary: np.ndarray
    block_palette: tuple[str, ...]
    palette_names: tuple[str, ...]
    air_indexes: frozenset[int]
    command_data: list[dict[str, Any]]
    ignored_block_entities: int
    invalid_command_records: int
    entities: int
    temporary_directory: Path | None = None
    closed: bool = False

    @property
    def volume(self) -> int:
        return self.size_x * self.size_y * self.size_z

    def palette_index(self, layer: int, x: int, y: int, z: int) -> int:
        if self.closed:
            raise RuntimeError("MCStructureData 已关闭")
        array = self.block_primary if layer == 0 else self.block_secondary
        return int(array[x, y, z])

    def close(self) -> str | None:
        if self.closed:
            return None
        self.closed = True
        close_memmap(self.block_primary)
        close_memmap(self.block_secondary)
        if self.temporary_directory is not None:
            try:
                shutil.rmtree(self.temporary_directory)
            except OSError as error:
                return str(error)
        return None

    def __enter__(self) -> "MCStructureData":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def read_file(path: str, include_commands: bool) -> MCStructureData:
    """顺序扫描未压缩小端 NBT，并将两层方块索引映射到磁盘。"""
    temporary_directory = Path(tempfile.mkdtemp(prefix="tooldelta-mcstructure-"))
    primary = secondary = None
    materialize_paths = {
        ("size",),
        ("structure_world_origin",),
        ("structure", "palette", "default", "block_palette"),
    }
    raw_command_records: dict[str, Any] = {}
    ignored_stream_records = 0

    def capture_position_record(name: str, record: Any) -> None:
        nonlocal ignored_stream_records
        if not include_commands or not isinstance(record, dict):
            ignored_stream_records += 1
            return
        entity = record.get("block_entity_data")
        if (
            not isinstance(entity, dict)
            or str(_unbox(entity.get("id", ""))) != "CommandBlock"
        ):
            ignored_stream_records += 1
            return
        raw_command_records[name] = record

    try:
        result = NBTStreamScanner(
            {("format_version",)},
            materialize_paths,
            set(),
            {("structure", "entities")},
            temporary_directory,
            numeric_list_paths={
                ("structure", "block_indices", "0"),
                ("structure", "block_indices", "1"),
            },
            typed_paths={("structure", "palette")},
            record_callbacks={
                (
                    "structure",
                    "palette",
                    "default",
                    "block_position_data",
                ): capture_position_record
            },
        ).scan(path, gzipped=False, byteorder="little")

        version = int(_required_value(result.values, ("format_version",)))
        if version != 1:
            raise ValueError(f"仅支持 format_version=1，实际为 {version}")
        size = _required_value(result.values, ("size",))
        if not isinstance(size, list) or len(size) != 3:
            raise ValueError("size 必须是恰好包含三个整数的 List")
        size_x, size_y, size_z = (int(value) for value in size)
        if min(size_x, size_y, size_z) <= 0:
            raise ValueError(f"建筑尺寸必须为正整数: {size_x} x {size_y} x {size_z}")
        volume = size_x * size_y * size_z
        if volume > MAX_VOLUME:
            raise ValueError(f"建筑体积过大: {volume} > {MAX_VOLUME}")

        numeric = result.numeric_lists
        primary_entry = numeric.get(("structure", "block_indices", "0"))
        secondary_entry = numeric.get(("structure", "block_indices", "1"))
        for name, entry in (("primary", primary_entry), ("secondary", secondary_entry)):
            if entry is None:
                raise KeyError(f"block_indices 缺少 {name} 层")
            if entry.tag_type != TAG_INT:
                raise ValueError(f"block_indices {name} 层必须是 TAG_Int List")
            if entry.length != volume:
                raise ValueError(
                    f"block_indices {name} 层长度错误: {entry.length} != {volume}"
                )
        shape = (size_x, size_y, size_z)
        assert primary_entry is not None
        assert secondary_entry is not None
        primary = np.memmap(primary_entry.path, dtype="<i4", mode="r", shape=shape)
        secondary = np.memmap(secondary_entry.path, dtype="<i4", mode="r", shape=shape)

        raw_palette = _required_value(
            result.values,
            ("structure", "palette", "default", "block_palette"),
        )
        palette_commands, palette_names, air_indexes = _process_palette(raw_palette)
        _validate_indexes(primary, secondary, len(palette_commands))

        command_data: list[dict[str, Any]] = []
        ignored_block_entities = 0
        invalid_command_records = 0
        if include_commands:
            origin_raw = result.values.get(("structure_world_origin",))
            origin = _origin(origin_raw)
            (
                command_data,
                ignored_block_entities,
                invalid_command_records,
            ) = _process_command_data(
                raw_command_records,
                primary,
                palette_names,
                size_x,
                size_y,
                size_z,
                origin,
            )
            ignored_block_entities += ignored_stream_records

        return MCStructureData(
            size_x,
            size_y,
            size_z,
            primary,
            secondary,
            palette_commands,
            palette_names,
            air_indexes,
            command_data,
            ignored_block_entities,
            invalid_command_records,
            result.list_lengths.get(("structure", "entities"), 0),
            temporary_directory,
        )
    except Exception as error:
        close_memmap(primary)
        close_memmap(secondary)
        shutil.rmtree(temporary_directory, ignore_errors=True)
        if isinstance(error, ValueError | KeyError):
            raise
        raise ValueError(f"无法读取小端 NBT 数据: {error}") from error


def _required_value(values: dict[tuple[str, ...], Any], path: tuple[str, ...]) -> Any:
    if path not in values:
        raise KeyError(f"文件缺少必需的 {'/'.join(path)} 字段")
    return values[path]


def _required(data: dict[str, Any], name: str) -> Any:
    if name not in data:
        raise KeyError(f"文件缺少必需的 {name} 字段")
    return data[name]


def _unbox(value: Any) -> Any:
    return value.value if isinstance(value, TaggedValue) else value


def _process_palette(
    raw_palette: Any,
) -> tuple[tuple[str, ...], tuple[str, ...], frozenset[int]]:
    if not isinstance(raw_palette, list) or not raw_palette:
        raise ValueError("block_palette 必须是非空 List")
    commands: list[str] = []
    names: list[str] = []
    air_indexes: set[int] = set()
    for index, block in enumerate(raw_palette):
        if not isinstance(block, dict):
            raise ValueError(f"block_palette[{index}] 不是 Compound")
        name = str(_unbox(_required(block, "name")))
        if not name:
            raise ValueError(f"block_palette[{index}] 方块名称为空")
        states = block.get("states", {})
        if not isinstance(states, dict):
            raise ValueError(f"block_palette[{index}].states 不是 Compound")
        rendered = []
        for state_name in sorted(states):
            tagged = states[state_name]
            if not isinstance(tagged, TaggedValue):
                raise ValueError(f"方块状态 {state_name} 缺少 NBT 类型信息")
            if tagged.tag_type == TAG_BYTE:
                if int(tagged.value) not in (0, 1):
                    raise ValueError(f"Byte 布尔状态 {state_name} 不是 0/1")
                state_value = "true" if int(tagged.value) else "false"
            elif tagged.tag_type in (TAG_SHORT, TAG_INT, TAG_LONG):
                state_value = str(int(tagged.value))
            elif tagged.tag_type == TAG_STRING:
                state_value = json.dumps(str(tagged.value), ensure_ascii=False)
            else:
                raise ValueError(
                    f"方块状态 {state_name} 使用不支持的 NBT 类型 {tagged.tag_type}"
                )
            rendered_name = json.dumps(str(state_name), ensure_ascii=False)
            rendered.append(f"{rendered_name}={state_value}")
        command = name if not rendered else f"{name} [{','.join(rendered)}]"
        commands.append(command)
        names.append(name)
        if name in ("air", "minecraft:air"):
            air_indexes.add(index)
    return tuple(commands), tuple(names), frozenset(air_indexes)


def _validate_indexes(
    primary: np.ndarray, secondary: np.ndarray, palette_size: int
) -> None:
    for name, layer in (("primary", primary), ("secondary", secondary)):
        invalid = np.logical_or(layer < -1, layer >= palette_size)
        if bool(np.any(invalid)):
            first = int(layer.reshape(-1)[int(np.flatnonzero(invalid)[0])])
            raise ValueError(f"block_indices {name} 层包含非法 Palette 索引: {first}")


def _origin(raw: Any) -> tuple[int, int, int] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError("structure_world_origin 必须包含三个整数")
    return tuple(int(value) for value in raw)  # type: ignore[return-value]


def _process_command_data(
    position_data: dict[str, Any],
    primary: np.ndarray,
    palette_names: tuple[str, ...],
    size_x: int,
    size_y: int,
    size_z: int,
    origin: tuple[int, int, int] | None,
) -> tuple[list[dict[str, Any]], int, int]:
    commands: list[dict[str, Any]] = []
    ignored = 0
    invalid = 0
    volume = size_x * size_y * size_z
    for raw_index, record in position_data.items():
        if not isinstance(record, dict):
            invalid += 1
            continue
        entity = record.get("block_entity_data")
        if not isinstance(entity, dict):
            ignored += 1
            continue
        if str(_unbox(entity.get("id", ""))) != "CommandBlock":
            ignored += 1
            continue
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            invalid += 1
            continue
        if not 0 <= index < volume:
            invalid += 1
            continue
        x = index // (size_y * size_z)
        remainder = index % (size_y * size_z)
        y, z = divmod(remainder, size_z)
        palette_index = int(primary[x, y, z])
        if not 0 <= palette_index < len(palette_names):
            invalid += 1
            continue
        mode = COMMAND_MODES.get(palette_names[palette_index])
        if mode is None:
            invalid += 1
            continue
        if origin is not None and all(axis in entity for axis in ("x", "y", "z")):
            actual = tuple(int(_unbox(entity[axis])) for axis in ("x", "y", "z"))
            expected = (origin[0] + x, origin[1] + y, origin[2] + z)
            if actual != expected:
                invalid += 1
                continue
        commands.append(
            {
                "Block": True,
                "Position": [x, y, z],
                "Mode": mode,
                "NeedsRedstone": not bool(int(_unbox(entity.get("auto", 0)))),
                "Conditional": bool(int(_unbox(entity.get("conditionalMode", 0)))),
                "MinecartEntityRuntimeID": 0,
                "Command": str(_unbox(entity.get("Command", ""))),
                "LastOutput": "",
                "Name": str(_unbox(entity.get("CustomName", ""))),
                "ShouldTrackOutput": bool(int(_unbox(entity.get("TrackOutput", 0)))),
                "TickDelay": int(_unbox(entity.get("TickDelay", 0))),
                "ExecuteOnFirstTick": bool(
                    int(_unbox(entity.get("ExecuteOnFirstTick", 0)))
                ),
            }
        )
    return commands, ignored, invalid

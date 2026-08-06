"""『Lyra-天琴座』生命周期适配层"""

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tooldelta import fmts

from .lyra_loader.bdx import bdx_parser, chunk_painter as bdx_painter
from .lyra_loader.common.dimensions import Dimension
from .lyra_loader.litematic import chunk_painter as litematic_painter
from .lyra_loader.litematic import litematic_parser
from .lyra_loader.mcstructure import chunk_painter as mcstructure_painter
from .lyra_loader.mcstructure import nbt_parser as mcstructure_parser
from .lyra_loader.mcworld import chunk_painter as mcworld_painter
from .lyra_loader.mcworld import world_reader
from .lyra_loader.schem import chunk_painter as schem_painter
from .lyra_loader.schem import schem_parser
from .lyra_loader.schematic import chunk_painter as schematic_painter
from .lyra_loader.schematic import nbt_parser as schematic_parser

if TYPE_CHECKING:
    from .__init__ import LyraSystem


@dataclass(frozen=True)
class MCWorldSelection:
    dimension_id: int
    start: tuple[int, int, int]
    end: tuple[int, int, int]


def run(
    plugin: "LyraSystem",
    path: str,
    extension: str,
    target: tuple[Dimension, tuple[int, int, int]],
    source: MCWorldSelection | None,
) -> None:
    dimension, position = target
    fmts.print_inf(f"§e正在解析 {os.path.basename(path)} ...")
    if extension == ".bdx":
        _run_bdx(plugin, path, dimension, position)
    elif extension == ".litematic":
        _run_litematic(plugin, path, dimension, position)
    elif extension == ".mcstructure":
        _run_mcstructure(plugin, path, dimension, position)
    elif extension == ".mcworld":
        if source is None:
            raise ValueError("MCWorld导入缺少源选区")
        _run_mcworld(plugin, path, source, dimension, position)
    elif extension == ".schem":
        _run_schem(plugin, path, dimension, position)
    elif extension == ".schematic":
        _run_schematic(plugin, path, dimension, position)
    else:
        raise ValueError(f"不支持的文件扩展名: {extension}")


def _cleanup(data: Any) -> None:
    if cleanup_error := data.close():
        fmts.print_inf(f"§6❀ 警告: 无法清理导入临时文件: {cleanup_error}")


def _run_bdx(plugin: "LyraSystem", path: str, dimension: Dimension, position) -> None:
    data = bdx_parser.read_file(path)
    try:
        fmts.print_inf(f"§a❀ 文件格式: Brotli BDX, 作者: {data.author or '未知'}")
        bdx_painter.ChunkPainter(plugin).paint(data, dimension, *position)
    finally:
        _cleanup(data)


def _run_litematic(
    plugin: "LyraSystem", path: str, dimension: Dimension, position
) -> None:
    data = litematic_parser.read_file(path)
    try:
        target = plugin.converter.meta.get("bedrock_version", "未知")
        fmts.print_inf(
            f"§a❀ 文件格式: Litematica v{data.version}, "
            f"MinecraftDataVersion={data.data_version}; 转换基线: Bedrock {target}"
        )
        litematic_painter.ChunkPainter(plugin).paint(data, dimension, *position)
    finally:
        _cleanup(data)


def _run_mcstructure(
    plugin: "LyraSystem", path: str, dimension: Dimension, position
) -> None:
    data = mcstructure_parser.read_file(path, plugin.config_mgr.INCLUDE_CMD)
    try:
        fmts.print_inf("§a❀ 文件格式: Bedrock MCStructure v1")
        if data.ignored_block_entities or data.entities:
            fmts.print_inf(
                f"§6❀ 警告: 已忽略非命令方块实体 {data.ignored_block_entities} 个、"
                f"实体 {data.entities} 个"
            )
        mcstructure_painter.ChunkPainter(plugin).paint(data, dimension, *position)
    finally:
        _cleanup(data)


def _run_mcworld(
    plugin: "LyraSystem",
    path: str,
    source: MCWorldSelection,
    dimension: Dimension,
    position,
) -> None:
    plugin.ensure_mcworld_dependency()
    data = world_reader.open_world(path, source.dimension_id, source.start, source.end)
    try:
        fmts.print_inf(
            f"§a❀ 文件格式: Bedrock MCWorld, 存档版本: {data.world_version or '未知'}, "
            f"选区大小: {data.size[0]} x {data.size[1]} x {data.size[2]}"
        )
        mcworld_painter.ChunkPainter(plugin).paint(data, dimension, *position)
    finally:
        _cleanup(data)


def _run_schem(plugin: "LyraSystem", path: str, dimension: Dimension, position) -> None:
    data = schem_parser.read_file(path)
    try:
        source = (
            f"DataVersion={data.data_version}"
            if data.data_version is not None
            else "无DataVersion"
        )
        target = plugin.converter.meta.get("bedrock_version", "未知")
        fmts.print_inf(
            f"§a❀ 文件格式: Sponge Schematic v{data.version}, {source}; "
            f"转换基线: Bedrock {target}"
        )
        schem_painter.ChunkPainter(plugin).paint(data, dimension, *position)
    finally:
        _cleanup(data)


def _run_schematic(
    plugin: "LyraSystem", path: str, dimension: Dimension, position
) -> None:
    data = schematic_parser.read_file(path)
    try:
        fmts.print_inf("§a❀ 文件格式: MCEdit Schematic (Alpha)")
        if data.tile_entities or data.entities:
            fmts.print_inf(
                f"§6❀ 警告: 已忽略 TileEntities {data.tile_entities} 个、"
                f"Entities {data.entities} 个"
            )
        mapping = _load_schematic_mapping(plugin.name)
        schematic_painter.ChunkPainter(plugin).paint(
            data, mapping, dimension, *position
        )
    finally:
        _cleanup(data)


def _load_schematic_mapping(plugin_name: str) -> dict[int, dict[int, str | None]]:
    path = os.path.join(
        "插件文件", "ToolDelta类式插件", plugin_name, "java_ids_to_bedrock_names.json"
    )
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    mappings = raw.get("mappings", raw)
    return {
        int(block_id): {int(data): command for data, command in values.items()}
        for block_id, values in mappings.items()
        if isinstance(values, dict)
    }

"""从 Geyser mappings-generator 的 blocks_debug.json 生成运行时静态映射

用法:
    python generate_mapping.py <blocks_debug.json> <block_palette.nbt> <输出json>
"""

import json
import gzip
import sys
from pathlib import Path
from typing import Any

import nbtlib

SOURCE_COMMIT = "29ea7df5cee9de843fa8c0a1ccc1b82577b7b341"
GENERATOR_RELEASE = "2.0.0-build.1"


def normalize(value: str) -> str:
    if "[" not in value:
        return value
    name, raw = value[:-1].split("[", 1)
    return name + "[" + ",".join(sorted(raw.split(","))) + "]"


def load_state_types(palette_path: Path) -> dict[tuple[str, str], str]:
    """读取 Bedrock palette, 保留 JSON 映射中丢失的 NBT 数字类型"""
    with gzip.open(palette_path, "rb") as stream:
        palette = nbtlib.File.from_fileobj(stream)
    result: dict[tuple[str, str], str] = {}
    for block in palette["blocks"]:
        name = str(block["name"])
        for state_name, state_value in block["states"].items():
            key = (name, str(state_name))
            value_type = type(state_value).__name__
            previous = result.setdefault(key, value_type)
            if previous != value_type:
                raise ValueError(f"同一 Bedrock 状态存在不同 NBT 类型: {key}")
    return result


def format_command(
    java_state: str,
    entry: dict[str, Any],
    state_types: dict[tuple[str, str], str],
) -> str:
    java_name = java_state.split("[", 1)[0]
    identifier = str(entry.get("bedrock_identifier", java_name))
    if ":" not in identifier:
        identifier = "minecraft:" + identifier
    states = entry.get("state", {})
    if not states:
        return identifier
    rendered = []
    for key, value in states.items():
        value_type = state_types.get((identifier, key))
        if value_type == "Byte":
            if int(value) not in (0, 1):
                raise ValueError(f"Byte 布尔状态不是 0/1: {identifier}[{key}={value}]")
            state_value = "true" if int(value) else "false"
        elif value_type in ("Int", "Short", "Long"):
            state_value = str(value)
        elif value_type == "String":
            state_value = json.dumps(value, ensure_ascii=False)
        else:
            raise ValueError(f"无法确定 Bedrock 状态类型: {identifier}[{key}]")
        rendered.append(f'"{key}"={state_value}')
    return f"{identifier} [{','.join(rendered)}]"


def generate(source: Path, palette: Path, destination: Path) -> None:
    raw = json.loads(source.read_text(encoding="utf-8"))
    state_types = load_state_types(palette)
    exact = {
        normalize(java_state): format_command(java_state, entry, state_types)
        for java_state, entry in raw.items()
    }
    output = {
        "meta": {
            "source": "GeyserMC/mappings-generator blocks_debug.json",
            "source_commit": SOURCE_COMMIT,
            "generator_release": GENERATOR_RELEASE,
            "java_version": "26.2",
            "bedrock_version": "1.26.30.5",
            "license": "MIT",
            "entries": len(exact),
        },
        "identifiers": {},
        "exact": exact,
    }
    destination.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "用法: python generate_mapping.py <blocks_debug.json> <block_palette.nbt> <输出json>"
        )
    generate(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))

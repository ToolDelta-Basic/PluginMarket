"""生成经典 Java 1.12 ID/Data 到 Bedrock 的离线静态映射

用法:
    python generate_mapping.py <minecraft-data/legacy.json> \
        <schem导入器/java_to_bedrock.json> <Minecraft_BE_block_id.json>

目标文件中已有、但无法通过最新 Geyser 精确匹配的条目会作为显式覆盖保留
"""

import json
import sys
from pathlib import Path
from typing import Any

PRISMARINE_COMMIT = "e426427e0b3c0456654e646c2291d2fd9e91ee1c"
GEYSER_COMMIT = "29ea7df5cee9de843fa8c0a1ccc1b82577b7b341"


def normalize(state: str) -> str:
    if "[" not in state:
        return state
    name, raw = state[:-1].split("[", 1)
    return name + "[" + ",".join(sorted(raw.split(","))) + "]"


def _existing_mappings(raw: Any) -> dict[str, dict[str, str | None]]:
    if not isinstance(raw, dict):
        return {}
    source = raw.get("mappings", raw)
    return {
        str(block_id): {str(data): command for data, command in values.items()}
        for block_id, values in source.items()
        if str(block_id).isdigit() and isinstance(values, dict)
    }


def generate(legacy_path: Path, geyser_path: Path, destination: Path) -> None:
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))["blocks"]
    geyser_raw = json.loads(geyser_path.read_text(encoding="utf-8"))
    geyser = geyser_raw["exact"]
    old_raw = (
        json.loads(destination.read_text(encoding="utf-8"))
        if destination.exists()
        else {}
    )
    old = _existing_mappings(old_raw)

    mappings: dict[str, dict[str, str | None]] = {}
    generated = 0
    overrides = 0
    for legacy_key, java_state in legacy.items():
        block_id, metadata = legacy_key.split(":", 1)
        command = geyser.get(normalize(java_state))
        if command is not None:
            generated += 1
        else:
            command = old.get(block_id, {}).get(metadata)
            if command is not None:
                overrides += 1
        if command is not None:
            mappings.setdefault(block_id, {})[metadata] = command

    # 保留 Prismarine 未列出的合法历史 metadata 覆盖；不进行 metadata=0 回退
    for block_id, values in old.items():
        for metadata, command in values.items():
            if metadata not in mappings.setdefault(block_id, {}):
                mappings[block_id][metadata] = command
                if command is not None:
                    overrides += 1

    # moving_piston 是运行时占位方块，不能通过 /setblock 安全恢复
    mappings["36"] = {str(metadata): None for metadata in range(16)}
    output = {
        "meta": {
            "java_source": "PrismarineJS/minecraft-data pc/common/legacy.json",
            "java_source_commit": PRISMARINE_COMMIT,
            "java_source_license": "MIT",
            "bedrock_source": "GeyserMC mappings-generator blocks_debug.json + Bedrock palette",
            "bedrock_source_commit": GEYSER_COMMIT,
            "bedrock_source_license": "MIT",
            "java_version": "1.12.2 legacy ID/Data",
            "bedrock_version": geyser_raw.get("meta", {}).get(
                "bedrock_version", "1.26.30.5"
            ),
            "generated_entries": generated,
            "explicit_override_entries": overrides,
            "entries": sum(len(values) for values in mappings.values()),
        },
        "mappings": mappings,
    }
    destination.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "用法: generate_mapping.py <minecraft-data legacy.json> "
            "<java_to_bedrock.json> <输出json>"
        )
    generate(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))

"""Java方块状态到Bedrock的离线转换"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol


class PluginWithName(Protocol):
    name: str


STATE_RE = re.compile(r"^([a-z0-9_.-]+:[a-z0-9_./-]+)(?:\[(.*)\])?$")
FACING_DIRECTION = {"down": 0, "up": 1, "north": 2, "south": 3, "west": 4, "east": 5}
DIRECTION = {"east": 0, "south": 1, "west": 2, "north": 3}
STAIR_DIRECTION = {"east": 0, "west": 1, "south": 2, "north": 3}


@dataclass(frozen=True)
class ConvertedBlock:
    command: str
    waterlogged: bool = False
    note: str | None = None


class BlockConverter:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self.meta = mapping.get("meta", {})
        self.identifiers: dict[str, str] = mapping.get("identifiers", {})
        self.exact: dict[str, str] = mapping.get("exact", {})

    @classmethod
    def from_plugin(cls, plugin: PluginWithName) -> "BlockConverter":
        path = os.path.join(
            "插件文件", "ToolDelta类式插件", plugin.name, "java_names_to_bedrock_names.json"
        )
        with open(path, encoding="utf-8") as file:
            return cls(json.load(file))

    def convert(self, java_state: str) -> ConvertedBlock | None:
        name, props, normalized = parse_java_state(java_state)
        if normalized in self.exact:
            return ConvertedBlock(
                self.exact[normalized], props.get("waterlogged") == "true"
            )
        bedrock_name = self.identifiers.get(name, name)
        if name.startswith("minecraft:") is False:
            return None
        waterlogged = props.pop("waterlogged", "false") == "true"
        states: dict[str, str | int | bool] = {}

        if not props:
            return ConvertedBlock(_format_command(bedrock_name, states), waterlogged)
        base = name.split(":", 1)[1]

        if base.endswith(("_log", "_wood", "_stem", "_hyphae")) and set(props) <= {
            "axis"
        }:
            states["pillar_axis"] = props["axis"]
        elif base.endswith("_slab") and set(props) <= {"type"}:
            slab_type = props["type"]
            if slab_type == "double":
                bedrock_name = self.identifiers.get(
                    name + "#double", bedrock_name.replace("_slab", "_double_slab")
                )
            else:
                states["minecraft:vertical_half"] = (
                    "top" if slab_type == "top" else "bottom"
                )
        elif base.endswith("_stairs") and set(props) <= {"facing", "half", "shape"}:
            if (
                props.get("shape", "straight") != "straight"
                or props.get("facing") not in STAIR_DIRECTION
            ):
                return None
            states["weirdo_direction"] = STAIR_DIRECTION[props["facing"]]
            states["upside_down_bit"] = props.get("half") == "top"
        elif base.endswith("_door") and set(props) <= {
            "facing",
            "half",
            "hinge",
            "open",
            "powered",
        }:
            if props.get("facing") not in DIRECTION:
                return None
            states["direction"] = DIRECTION[props["facing"]]
            states["upper_block_bit"] = props.get("half") == "upper"
            states["door_hinge_bit"] = props.get("hinge") == "right"
            states["open_bit"] = props.get("open") == "true"
        elif base.endswith("_trapdoor") and set(props) <= {
            "facing",
            "half",
            "open",
            "powered",
        }:
            if props.get("facing") not in DIRECTION:
                return None
            states["direction"] = DIRECTION[props["facing"]]
            states["upside_down_bit"] = props.get("half") == "top"
            states["open_bit"] = props.get("open") == "true"
        elif base.endswith(("_fence", "_wall", "_pane")):
            # Bedrock 会根据相邻方块自动计算连接状态
            pass
        elif base.endswith("_leaves") and set(props) <= {"distance", "persistent"}:
            states["persistent_bit"] = props.get("persistent") == "true"
            states["update_bit"] = False
        elif set(props) == {"facing"}:
            if props["facing"] not in FACING_DIRECTION:
                return None
            states["facing_direction"] = FACING_DIRECTION[props["facing"]]
        else:
            return None
        return ConvertedBlock(_format_command(bedrock_name, states), waterlogged)


def parse_java_state(value: str) -> tuple[str, dict[str, str], str]:
    value = value.strip().lower()
    if ":" not in value:
        value = "minecraft:" + value
    match = STATE_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"非法 Java 方块状态: {value}")
    name = match.group(1)
    props: dict[str, str] = {}
    raw_props = match.group(2)
    if raw_props:
        for item in raw_props.split(","):
            if "=" not in item:
                raise ValueError(f"非法 Java 方块属性: {item}")
            key, prop_value = item.split("=", 1)
            if not key or not prop_value or key in props:
                raise ValueError(f"非法或重复的 Java 方块属性: {item}")
            props[key] = prop_value
    normalized_props = ",".join(f"{key}={props[key]}" for key in sorted(props))
    normalized = name + (f"[{normalized_props}]" if normalized_props else "")
    return name, props, normalized


def _format_command(name: str, states: dict[str, str | int | bool]) -> str:
    if not states:
        return name
    values = []
    for key, value in states.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, int):
            rendered = str(value)
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        values.append(f'"{key}"={rendered}')
    return f"{name} [{','.join(values)}]"

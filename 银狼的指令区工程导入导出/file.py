from dataclasses import dataclass
from .define import FACING_STR, CBTYPE_STR

def marshal_version(version: tuple[int, int, int]) -> str:
    return ".".join(map(str, version))


def unmarshal_version(version: str) -> tuple[int, int, int]:
    a, b, c = map(int, version.split("."))
    return a, b, c


def marshal_properties(dic: dict[str, str]) -> str:
    return " ".join(f"{key}={value}" for key, value in dic.items() if value is not None)


def unmarshal_properties(properties: str) -> dict[str, str]:
    return dict(pair.split("=") for pair in properties.split(" "))


def dump_facing(facing: int):
    return FACING_STR[facing]


def load_facing(facing: str):
    return FACING_STR.index(facing)


def dump_delay(delay: int):
    return str(delay)


def load_delay(delay: str):
    return int(delay)


def dump_type(type: int):
    return CBTYPE_STR[type]


def load_type(type: str):
    return CBTYPE_STR.index(type)


@dataclass
class CommandBlock:
    command: str
    facing: int
    type: int
    conditional: bool
    need_redstone: bool
    tick_delay: int
    should_track_output: bool
    execute_on_first_tick: bool


class MCFProjectFile:
    my_format = "ToolDelta/SWExport"
    my_format_version = (0, 0, 1)

    def __init__(self, cbs: list[CommandBlock]):
        self.cbs = cbs

    def dump(self) -> str:
        file_contents = [
            f"# format: {self.my_format} {marshal_version(self.my_format_version)}"
        ]
        last_facing = -1
        for cb in self.cbs:
            properties: dict[str, str] = {}
            if cb.facing != last_facing:
                properties["朝向"] = dump_facing(cb.facing)
                last_facing = cb.facing
            if cb.need_redstone:
                properties["红石控制"] = "是"
            if cb.tick_delay != 0:
                properties["延迟"] = dump_delay(cb.tick_delay)
            if cb.execute_on_first_tick:
                properties["首次执行"] = "是"
            if cb.conditional:
                properties["有条件"] = "是"
            properties["类型"] = dump_type(cb.type)
            file_contents.append(f"# {marshal_properties(properties)}")
            file_contents.append(cb.command)
        return "\n".join(file_contents)

    @classmethod
    def load(cls, content: str):
        cbs: list[CommandBlock] = []
        contents = content.split("\n")
        format_line = contents.pop(0)
        if not format_line.startswith("# format:"):
            raise ValueError("不合法的文件格式头")
        format, version = format_line[len("# format: ") :].split(" ")
        if format != cls.my_format:
            raise ValueError("不支持的格式")
        version = unmarshal_version(version)
        last_facing = -1
        line = 1
        try:
            while contents:
                line += 1
                properties_line = contents.pop(0)
                if not properties_line.startswith("# "):
                    raise ValueError("缺失注释行")
                properties = unmarshal_properties(properties_line[len("# ") :])
                if (facing := properties.get("朝向")) is not None:
                    last_facing = load_facing(facing)
                command = contents.pop(0)
                cbs.append(
                    CommandBlock(
                        command=command,
                        facing=last_facing,
                        type=load_type(properties.get("类型", "脉冲")),
                        conditional=properties.get("有条件", "否") == "是",
                        need_redstone=properties.get("红石控制", "否") == "是",
                        tick_delay=load_delay(properties.get("延迟", "0")),
                        execute_on_first_tick=properties.get("首次执行", "否") == "是",
                        should_track_output=False,
                    )
                )
        except Exception as err:
            raise ValueError(f"第 {line} 行出错: {err}") from err
        return cls(cbs)


def dump_command_blocks(cbs: list[CommandBlock]): ...

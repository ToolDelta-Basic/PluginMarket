"""统一维度的显示名、存档ID与Minecraft命令标识"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    number: int
    display_name: str
    command_id: str


def target_dimension(number: int) -> Dimension:
    if not 0 <= number <= 20:
        raise ValueError(f"目标维度编号越界: {number}")
    names = {0: ("主世界", "overworld"), 1: ("下界", "nether"), 2: ("末地", "the_end")}
    display, command = names.get(number, (f"dm{number}", f"dm{number}"))
    return Dimension(number, display, command)


def source_dimension(number: int) -> Dimension:
    if not 0 <= number <= 2:
        raise ValueError(f"MCWorld源维度只能是0、1或2: {number}")
    return target_dimension(number)


COMMAND_MODE_NAMES = {0: "脉冲", 1: "循环", 2: "连锁"}

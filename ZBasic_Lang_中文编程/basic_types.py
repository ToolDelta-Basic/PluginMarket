# 定义了 ZBasic 的基本类型

from typing import Any, Callable


class Pattern: ...


class BasicType:
    def __init__(self, name: str, extra1: "BasicType | Any" = None):
        self.name = name
        self.extra1 = extra1

    @property
    def type(self):
        if not self.extra1:
            return BasicType(self.name)
        else:
            return BasicType(self.name, self.extra1)

    def __repr__(self):
        if not self.extra1:
            return get_typename_zhcn(self.type)
        else:
            return (
                f"{get_typename_zhcn(self.type)}[{get_typename_zhcn(self.extra1.type)}]"
            )

    def __getitem__(self, v: "ANY_TYPE"):
        return BasicType(self.name, v)


class OptionalType:
    def __init__(self, t: BasicType):
        self.type = t


class _Signal:
    GLOBAL = 0
    IF = 1
    ELIF = 2
    ELSE = 3
    WHILE = 4
    LOOP_UNTIL = 5


Signal = _Signal


def get_code_block_zhcn(bid: int):
    match bid:
        case Signal.IF:
            return "如果"
        case Signal.ELSE:
            return "否则"
        case Signal.ELIF:
            return "又或者"
        case Signal.LOOP_UNTIL:
            return "循环直到"


class SkipScript(Exception): ...


ANY = BasicType("任意值")
NUMBER = BasicType("数值")
STRING = BasicType("字符串")
BOOLEAN = BasicType("是或否")
NULL = BasicType("空值")
LIST = BasicType("列表")
POSITION = BasicType("坐标")


zhcn_type = {
    "数值": NUMBER,
    "字符串": STRING,
    "是或否": BOOLEAN,
    "空值": NULL,
    "坐标": POSITION,
    "任意值": ANY,
    "列表": LIST,
}

ANY_TYPE = BasicType | OptionalType
REGISTER = dict[str, ANY_TYPE]
VAR_MAP = dict[str, Any]
RES_TYPE = ANY_TYPE | Callable[[tuple[ANY_TYPE, ...]], ANY_TYPE]


def get_typename_zhcn(t: ANY_TYPE):
    optional = False
    if isinstance(t, OptionalType):
        t = t.type
        optional = True
    res = t.name
    if res is None:
        raise ValueError(f"类型 {t} 不存在")
    else:
        if optional:
            return "可空变量[" + t.type.name + "]"
        else:
            return t.type.name


def get_zhcn_type(t: str):
    res = zhcn_type.get(t)
    if res is None:
        raise ValueError(f"类型 {t} 不存在")
    else:
        return zhcn_type[t]


def de_optional(t: OptionalType):
    return t.type

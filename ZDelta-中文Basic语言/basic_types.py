class BasicType:
    def __init__(self, name: str):
        self.name = name
        self.type = self

class OptionalType:
    def __init__(self, t: BasicType):
        self.type = t

class SkipScript(Exception):...

ANY = BasicType("ANY")
NUMBER = BasicType("NUMBER")
STRING = BasicType("STRING")
NULL = BasicType("NULL")
POSITION = BasicType("POSITION")

types_zhcn = {
    NUMBER: "数值",
    STRING: "字符串",
    NULL: "空值",
    POSITION: "列表",
    ANY: "任意值"
}

zhcn_type = {v:k for k,v in types_zhcn.items()}

def get_typename_zhcn(t: BasicType | OptionalType):
    optional = False
    if isinstance(t, OptionalType):
        t = t.type
        optional = True
    res = types_zhcn.get(t)
    if res is None:
        raise ValueError(f"类型 {t} 不存在")
    else:
        if optional:
            return "(" + types_zhcn[t] + "或空变量)"
        else:
            return types_zhcn[t]

def get_zhcn_type(t: str):
    res = zhcn_type.get(t)
    if res is None:
        raise ValueError(f"类型 {t} 不存在")
    else:
        return zhcn_type[t]

def de_optional(t: OptionalType):
    return t.type
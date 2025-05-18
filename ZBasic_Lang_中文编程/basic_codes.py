from typing import Any
from basic_types import REGISTER


class OPs:
    END = 1
    SET = 2
    ENDIF = 5
    ENDLOOP = 7
    PRINT = 8
    EXECMD = 9
    SAYTO = 10
    IGNORE_NULL = 11
    SLEEP = 12


class CodeUnit:
    # 代码单元
    def __init__(self, cid: int, *args):
        self.id = cid
        self.args = args


class CustomCodeUnit(CodeUnit):
    def __init__(self, *args):
        super().__init__(-1, *args)


class CompiledCode:
    # 代码块
    def __init__(self, code_seq: list[CodeUnit], out_namespace: REGISTER | None = None, at_line: int = -1):
        self.out_namespace = out_namespace or {}
        self.code_seq = code_seq
        self.cache1: Any = None
        self.cache2: Any = None
        self.cache3: Any = None
        self.at_ln = at_line

    def add_code(self, op: CodeUnit):
        self.code_seq.append(op)

    def add_namespace(self, ns: REGISTER):
        self.out_namespace.update(ns)

    def clear_cache(self):
        self.cache1 = self.cache2 = self.cache3 = None

    def __repr__(self):
        return f"<CompileCode at ln {self.at_ln}>"


class CodeSyntaxError(SyntaxError):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg

    def __repr__(self):
        return self.msg

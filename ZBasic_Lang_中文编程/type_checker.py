from typing import Callable  # noqa: UP035
import err_str
from syntax_lib import (
    OpPtr,
    VarPtr,
    ConstPtr,
    FuncPtr,
)
from syntax_lib import (
    AddPtr,
    SubPtr,
    MulPtr,
    DivPtr,
    PowPtr,
    EqPtr,
    AndPtr,
    OrPtr,
    LtPtr,
    GtPtr
)
from basic_types import (
    BasicType,
    OptionalType,
    ANY,
    ANY_TYPE,
    RES_TYPE,
    REGISTER,
)
from basic_types import (
    STRING,
    NUMBER,
    BOOLEAN,
)
from basic_types import get_typename_zhcn


class ReallyNone: ...


class FuncRegDatas:
    res_types: dict[str, RES_TYPE] = {}  # noqa: RUF012
    input_type_checkers: dict[str, Callable[[list[ANY_TYPE]], str | None]] = {}  # noqa: RUF012
    func_cbs = {}  # noqa: RUF012

    @classmethod
    def add_type_checker(
        cls,
        func_name: str,
        checker: Callable[[list[ANY_TYPE]], str | None] | tuple[ANY_TYPE, ...],
    ):
        if isinstance(checker, tuple):
            types_zhcn = ", ".join(
                f"可空[{t.type.name}]" if isinstance(t, OptionalType) else t.name
                for t in checker
            )

            def _checker(args: list[ANY_TYPE]):
                if len(args) != len(checker):
                    return types_zhcn
                for i, j in zip(args, checker):
                    if not cls_isinstance(i, j):
                        return types_zhcn

            cls.input_type_checkers[func_name] = _checker
        else:
            cls.input_type_checkers[func_name] = checker

    @classmethod
    def add_func_restype(cls, func_name: str, res_type):
        cls.res_types[func_name] = res_type


def cls_isinstance(type_c: ANY_TYPE, checker: ANY_TYPE):
    if type_c.type.name != checker.type.name:
        return False
    elif checker.type.extra1 != ANY:
        checker = checker.type
        type_c = type_c.type
        return checker.name == type_c.name and checker.extra1 == type_c.extra1
    else:
        return True


def get_final_type(syntax):
    if isinstance(syntax, BasicType):
        raise SyntaxError(f"Input can't be {syntax}")
    return _type_checker_recr(syntax)


def _type_checker_recr(syntax):
    "对表达式进行类型检查"
    if isinstance(syntax, OpPtr):
        arg1type = _type_checker_recr(syntax.arg1)
        arg2type = _type_checker_recr(syntax.arg2)
        if not _is_op_valid(arg1type, type(syntax), arg2type):
            notice = ""
            if isinstance(arg1type, OptionalType) or isinstance(arg2type, OptionalType):
                notice += "\n似乎是遇到了可能为空的变量, 你可以用 §e忽略空变量 <变量名> §c这条指令以跳过空变量(如果你清楚后果的话)"
            raise SyntaxError(
                err_str.OP_NOT_SUPPORTED
                % (
                    get_typename_zhcn(arg1type),
                    syntax.name,
                    get_typename_zhcn(arg2type),
                )
                + notice
            )
        if isinstance(syntax, EqPtr):
            return BOOLEAN
        else:
            return _valid_op_type(type(syntax))[(arg1type, arg2type)]
    elif isinstance(syntax, FuncPtr):
        input_type_checker = FuncRegDatas.input_type_checkers[syntax.name]
        try:
            input_argstypes = []
            for i in syntax.args:
                typec = _type_checker_recr(i)
                if typec is None:
                    raise Exception("传入 None 类型 不支持")
                input_argstypes.append(typec)
            if err := input_type_checker(input_argstypes):
                raise SyntaxError(
                    err_str.FUNC_ARGS_TYPE_INVALID
                    % (
                        syntax.name,
                        ", ".join(get_typename_zhcn(j) for j in input_argstypes),
                        err,
                    )
                )
        except IndexError:
            raise SyntaxError(
                err_str.FUNC_ARGS_LEN_WRONG % (syntax.name, len(input_argstypes))
            )
        arg_types = tuple(_type_checker_recr(arg) for arg in syntax.args)
        restype = FuncRegDatas.res_types[syntax.name]
        if callable(restype):
            return restype(arg_types)
        else:
            return restype

    elif isinstance(syntax, VarPtr):
        return syntax.type
    elif isinstance(syntax, ConstPtr):
        if syntax.type in (int, float):
            return NUMBER
        elif syntax.type is str:
            return STRING
        elif syntax.type is bool:
            return BOOLEAN
        else:
            raise SyntaxError(err_str.UNKNOWN_TYPE % str(syntax))
    else:
        raise SyntaxError(err_str.UNKNOWN_TYPE % str(syntax))


def _is_op_valid(arg1, op: type[OpPtr], arg2):
    if op == EqPtr:
        return True
    ops = _valid_op_type(op)
    return any((arg1, arg2) == sop for sop in ops.keys())


def _valid_op_type(op: type[OpPtr]):
    # 给出该运算可用的运算项与结果类型
    if op == AddPtr:
        return {
            (STRING, STRING): STRING,
            (NUMBER, NUMBER): NUMBER,
            (STRING, NUMBER): STRING,
            (NUMBER, STRING): STRING,
        }
    elif op == MulPtr:
        return {(NUMBER, NUMBER): NUMBER, (STRING, NUMBER): STRING}
    elif op in (SubPtr, DivPtr, PowPtr):
        return {(NUMBER, NUMBER): NUMBER}
    elif op in (AndPtr, OrPtr):
        return {(NUMBER, NUMBER): BOOLEAN, (BOOLEAN, BOOLEAN): BOOLEAN}
    elif op in (LtPtr, GtPtr):
        return {(NUMBER, NUMBER): BOOLEAN, (STRING, STRING): BOOLEAN}
    elif op == EqPtr:
        raise Exception("无法在此使用 EqPtr 作为参数")
    else:
        raise Exception(err_str.UNKNOWN_OP % str(op))


def find_pairs(regs: list[REGISTER]) -> REGISTER:
    # 寻找在所有代码分支里都存在且变量类型相同的变量命名
    output = {}
    std = regs[0]
    for k, v in std.items():
        join_ok = True
        for reg in regs[1:]:
            if reg.get(k) != v:
                join_ok = False
                break
        if join_ok:
            output[k] = v
    return output

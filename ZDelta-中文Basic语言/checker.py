from syntax_lib import *
from basic_types import *

fun_restype = {}
fun_inputypechk = {}
typelst = ("数", "字符串", "空变量", "坐标")

def get_final_type(syntax):
    return _type_checker_recr(syntax)

def _type_checker_recr(syntax):
    if isinstance(syntax, OpPtr):
        arg1type = _type_checker_recr(syntax.arg1)
        arg2type = _type_checker_recr(syntax.arg2)
        if not _is_op_valid(arg1type, type(syntax), arg2type):
            raise SyntaxError(f"不支持这么运算: {typelst[arg1type]} {syntax.name} {typelst[arg2type]}")
        return _valid_op_type(type(syntax))[(arg1type,arg2type)]
    elif isinstance(syntax, FuncPtr):
        input_type_checker = fun_inputypechk[syntax.name]
        try:
            input_argstypes = []
            for i in syntax.args:
                typec = _type_checker_recr(i)
                if typec is None:
                    raise Exception("传入 None 类型 不支持")
                input_argstypes.append(typec)
            if not input_type_checker(input_argstypes):
                raise SyntaxError(f"函数 {syntax.name} 传入的参数类型不正确: " + ", ".join(typelst[j] for j in input_argstypes))
        except IndexError:
            raise SyntaxError(f"函数 {syntax.name} 传入的参数长度不正确, 传入了{len(input_argstypes)}个")
        for arg in syntax.args:
            _type_checker_recr(arg)
        return fun_restype[syntax.name]
    elif isinstance(syntax, VarPtr):
        return syntax.type
    else:
        if isinstance(syntax, (int, float)):
            return NUMBER
        elif isinstance(syntax, str):
            return STRING
        else:
            raise ValueError(f"未知类型: {syntax}")

def _is_op_valid(arg1, op: type[OpPtr], arg2):
    ops = _valid_op_type(op)
    return any((arg1, arg2) == sop for sop in ops.keys())

def _valid_op_type(op: type[OpPtr]):
    if op == AddPtr:
        return {(STRING, STRING):STRING,(NUMBER, NUMBER):NUMBER, (STRING, NUMBER):STRING, (NUMBER, STRING):STRING}
    elif op == MulPtr:
        return {(NUMBER, NUMBER):NUMBER, (STRING, NUMBER):STRING}
    elif op in (SubPtr, DivPtr, PowPtr):
        return {(NUMBER, NUMBER):NUMBER}
    else:
        raise Exception("未知的操作类型")
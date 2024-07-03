# 本模块功能: 解析并编译表达式
# 编写耗时最久的一块
# 编译的结果的最外层类往往是运算符/函数/变量/常量类实例
# 可以直接通过 eval() 属性方法传入本地变量表来计算结果
# 当然在这之前要先去判定类型是否正确
# 因为这是强类型的静态语言

from typing import Callable
import err_str
from syntax_lib import *

from type_checker import FuncRegDatas, get_final_type
from basic_types import *

# 调试器开关, 会显示详细的表达式编译信息
DEBUG_CHECK = False
if DEBUG_CHECK:
    from tooldelta import Print

func_names: list[str] = []
func_cbs: dict = {}


def register_func_syntax(func_name: str, restype, input_type_checker, func: Callable):
    """注册一个函数功能

    Args:
        func_name (str): 函数名
        restype (BasicType | OptionalType): 返回类型
        input_type_checker (Callable, optional): 参数类型检查器, 检查不通过则返回所需参数类型的提示, 如 "字符串, 数值"
    """
    func_names.append(func_name)
    func_cbs[func_name] = func
    FuncRegDatas.add_func_restype(func_name, restype)
    FuncRegDatas.add_type_checker(func_name, input_type_checker)


def parse_as_chunks(pat: str, types_register: REGISTER | None = None, level=0) -> list:
    """
    解析表达式字符串作为表达式序列
    传入:
        pat: 表达式组
    返回:
        表达式列表
    """
    if not pat.strip():
        raise SyntaxError("需要表达式, 此处不能为空")
    opseq = []
    txt_cache = ""
    cma_num = 0
    cma_txt = ""
    is_str = False
    str_cache = ""
    is_fun = False
    fun_name = ""
    fun_cache: Any = None
    funseq = []
    if types_register is None:
        types_register = {}
    if DEBUG_CHECK:
        Print.clean_print(f"[§b{level}§r] Start parsing §d{pat}")
    for c in pat + "?":
        if c == '"':
            if is_str:
                # 双引号打开
                is_str = False
                if cma_num:
                    # 在括号
                    cma_txt += f'"' + str_cache + f'"'
                elif is_fun:
                    # 在函数接收模式
                    fun_cache = ConstPtr(str_cache)
                else:
                    # 普通的模式
                    txt_cache += f'"' + str_cache + f'"'
                str_cache = ""
                continue
            else:
                is_str = True
        elif is_str:
            str_cache += c
        elif c == "(":
            # 括号递进
            if txt_cache.strip():
                raise SyntaxError(err_str.NOT_OP_BEFORE_COMMA % txt_cache)
            cma_num += 1
            if cma_num == 1:
                # 不需要理会第一次的出现的左括号
                continue
            else:
                # 肯定是第二次括号或者以上的括号扩增
                cma_txt += "("
        elif c == ")":
            # 括号回缩
            cma_num -= 1
            if cma_num < 0:
                raise SyntaxError(err_str.BRACKET_NOT_CLOSED)
            if cma_num == 0:
                # 到了括号最外层
                if not cma_txt:
                    raise SyntaxError(err_str.BRACKET_CANT_BE_EMPTY)
                if is_fun:
                    # 解析并添加为函数参数项 (缓存, 在遇到括号或结束符后再存进参数)
                    fun_cache = parse(cma_txt, types_register, level=level + 1)
                else:
                    # 对括号内表达式进行解析
                    opseq.append(parse(cma_txt, types_register, level=level + 1))
                cma_txt = ""
                continue
            else:
                # 肯定是第二次括号或者以上的括号回缩
                cma_txt += ")"
        elif cma_num:
            # 在括号内的表达式, 直接无脑加入括号缓存
            cma_txt += c
        elif is_fun:
            # 正在接受函数参数
            if c in OP_CHARS + ",?":
                # 终止了当前参数接收
                if c in SPEC_OP_CHARS:
                    # 特殊符号, 前面可以没有操作项: +, - 表示正负数
                    txt_cache += "0" + c
                    continue
                elif fun_cache:
                    # 如果参数缓存区有内容
                    # 那么这可能是常量变量之类
                    funseq.append(fun_cache)
                    fun_cache = None
                elif txt_cache.strip():
                    # 如果接收到了参数, 在普通的字符串缓存区
                    funseq.append(parse(txt_cache, types_register, level=level + 1))
                    txt_cache = ""
                else:
                    raise SyntaxError(err_str.NOT_SYNTAX_BRFORE_BRACKET)
            if c in OP_CHARS + "?":
                # 为操作符, 终止参数接收
                # 不是为什么非得tuple啊
                # 有病吧, 没tuple 输出的函数就没参
                syntax_grp = tuple(funseq)
                opseq.append(deal_funptr(fun_name, syntax_grp))
                if c != "?":
                    # 非结束运算符
                    opseq.append(opmap.get(c))
                txt_cache = ""
                is_fun = False
                funseq.clear()
                txt_cache = ""
            elif c == " ":
                if txt_cache.strip() in func_names:
                    # 不允许再次调用函数, 除非使用括号 (此时正处于函数参数接收时刻)
                    raise SyntaxError(err_str.FUNC_ARGS_NOT_FUNC)
            elif c != ",":
                txt_cache += c
        elif c in " " + OP_CHARS + "?":
            # 空格 或 操作符 或 结束 标志着一个函数名/变量名/常量的结束
            # 其他则忽略不管
            if txt_cache in func_names:
                # 是函数调用
                if c == "?":
                    # 一开始就结束了
                    opseq.append(deal_funptr(txt_cache, ()))
                    is_fun = False
                else:
                    if is_fun:
                        # 不可以在函数模式下再次调用函数, 除非使用括号
                        raise SyntaxError(err_str.FUNC_ARGS_NOT_FUNC)
                    is_fun = True
                    fun_name = txt_cache
            elif txt_cache in types_register.keys():
                # 是已注册变量
                opseq.append(VarPtr(txt_cache, types_register[txt_cache]))
            elif txt_cache:
                # 不是函数调用 不是已知变量 则可能为变量等?
                if txt_cache.endswith(",") and not is_fun:
                    raise SyntaxError(err_str.USE_COMMA_OUTSIDE_FUNC % txt_cache)
                # 到底是什么样的数据? 常量或者命名表里的变量?
                opseq.append(num3var(txt_cache, types_register))
            # 以上都是对目前处理的字符之前的工作进行收尾
            if c in OP_CHARS + "?":
                # 是操作运算符或者结束符
                # (这时候已经退出接收函数参数模式了)
                if c != "?":
                    opc = opmap.get(c)
                    if opc is None:
                        raise SyntaxError(err_str.OP_NOT_VALID % c)
                    opseq.append(opc)
            txt_cache = ""
        else:
            # 连续的文本
            txt_cache += c
    if cma_num:
        raise SyntaxError("括号没有正确闭合")
    if is_str:
        raise SyntaxError("字符串未正确闭合")
    if DEBUG_CHECK:
        Print.clean_print(
            f"[§9{level}§r] Parsing §2{pat}, §rok, as §d{' §6|§9 '.join(str(i) for i in opseq)}"
        )
    return opseq


def deal_funptr(func_name: str, fun_args: tuple):
    """
    生成一个函数实例

    Args:
        fun_name (str): 函数ID
        fun_args (tuple): 参数

    Returns:
        FuncPtr (FuncPtr): 返回
    """
    if not isinstance(func_name, str):
        raise SyntaxError("需要函数名")
    return FuncPtr(
        func_name, fun_args, FuncRegDatas.res_types[func_name], func_cbs[func_name]
    )


def deal_syntaxgrp(grp: list):
    """
    对表达式组进行优先分级

    Args:
        grp: 传入表达式组

    Returns:
        表达式
    """
    if len(grp) > 256:
        raise OverflowError("Syntax sequence overflow")
    if not grp:
        raise SyntaxError("Empty syntax")
    opmode = -1
    if len(grp) > 1 and subcls(grp[0], OpPtr):
        # 可能遇到 -1 这样的负数了
        grp.insert(0, ConstPtr(0))
    for s in grp:
        if subcls(s, OpPtr):
            if opmode == 1:
                raise SyntaxError(err_str.MULTI_OP_STRING)
            opmode = 1
        else:
            if opmode == 0:
                raise SyntaxError(err_str.MULTI_ARGS_WITHOUT_OP)
            else:
                opmode = 0
    if subcls(grp[-1], OpPtr):
        raise SyntaxError(err_str.END_WITH_OP)
    prior_table = grp.copy()
    for p in range(max_priority, 0, -1):
        # 遍历所有优先级, 从大到小
        now_prior_table = []
        # 操作符两侧的项
        arg1 = None
        arg2 = None
        lastop = OpPtr
        for s in prior_table + [OpPtr]:
            if subcls(s, OpPtr):
                # 是操作符
                if op_prior(s) == p:
                    # 当前的优先级应当被处理
                    if op_prior(lastop) == p:
                        # 上一个优先级也和当前一样
                        # 那么就直接合并当前的
                        arg1 = lastop(arg1, arg2)
                        arg2 = None
                elif op_prior(s) < p:
                    # 当前的优先级大于目前操作符的优先级
                    if op_prior(lastop) == p:
                        # 上一个优先级和目前优先级相同
                        # 那么就把上一个合并
                        now_prior_table.append(lastop(arg1, arg2))
                        arg1 = arg2 = None
                    elif op_prior(lastop) < p:
                        # 上一个优先级和小于目前优先级
                        now_prior_table.append(arg1)
                    if arg2:
                        raise Exception("what?!", arg1, arg2)
                    arg1 = None
                    if s != OpPtr:
                        now_prior_table.append(s)
                lastop = s
            else:
                # 两个操作符之间的项
                if arg1:
                    arg2 = s
                else:
                    arg1 = s
        prior_table = now_prior_table.copy()
    if DEBUG_CHECK:
        Print.clean_print(f"[§9SYNTAX§r] Parsing §b{grp}§r ok, as §b{prior_table[0]}")
    return prior_table[0]


def parse(syntax: str, types_register: REGISTER, level: int = 0):
    return deal_syntaxgrp(parse_as_chunks(syntax, types_register, level))


def multi_parse(syntax: str, local_vars: REGISTER):
    in_str = False
    syntaxs = []
    if not syntax.endswith(";"):
        syntax += ";"
    cache_pos = 0
    for i, c in enumerate(syntax):
        if c == '"':
            in_str = not in_str
            continue
        elif c == ";" and not in_str:
            syn = syntax[cache_pos:i]
            if syn.strip():
                syntaxs.append(parse(syn, local_vars))
                cache_pos = i + 1
                continue
            else:
                raise SyntaxError("分号前需要表达式")
    return syntaxs


register_func_syntax("非", BOOLEAN, (BOOLEAN,), lambda x: not x)

if __name__ == "__main__":
    # 测试
    DEBUG_CHECK = True
    try:

        def _de_optional_check(x: list):
            if len(x) not in (1, 2) or not isinstance(x[0], OptionalType):
                return "可空[任意类型] [, 默认值:任意类型]"
            elif len(x) == 2 and (gft := x[1]) != x[0].type:
                return f"可空[任意类型(当前为{gft})] [, 默认值(当前可用的):{gft}]"
            return None

        def _de_optional(t: None | Any, default: Any = None):
            if t is None:
                if default is None:
                    raise SystemExit
                else:
                    return default
            else:
                return t

        def try_int(n):
            try:
                return int(n)
            except:
                return None

        register_func_syntax("int", NUMBER, (NUMBER,), lambda x: try_int(x))
        register_func_syntax(
            "转换为整数", OptionalType(NUMBER), (STRING,), lambda x: try_int(x)
        )
        register_func_syntax(
            "获取列表项",
            lambda l: OptionalType(l[0].type.extra1),
            (LIST[ANY], NUMBER),
            lambda l, i: l[int(i)] if int(i) in range(len(l)) else None,
        )
        register_func_syntax(
            "转换为非空变量", lambda x: x[0].type, _de_optional_check, _de_optional
        )
        syntax = parse_as_chunks("int -1", {"触发词参数": LIST[STRING]})
        Print.clean_print(f"§2分割结果: §a{syntax}")
        syntax2 = deal_syntaxgrp(syntax)
        # syntaxs = 转换为非空变量 (转换为整数 转换为非空变量 (获取列表项 触发词参数, 2), "-1")
        # syntax = syntaxs[0]
        t = get_final_type(syntax2)
        Print.clean_print("§a-" * 25)
        print("表达式组:", syntax)
        print("表达式:", syntax2)
        print("类型:", t)
    except Exception as err:
        # print(err)
        Print.clean_print("§cCRASHED " + "=" * 50)
        import traceback

        traceback.print_exc()

    # will be crashed

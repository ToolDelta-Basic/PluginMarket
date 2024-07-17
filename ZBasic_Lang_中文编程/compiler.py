# 本模块功能: 对代码进行编译, 编译结果是包含每个代码指令(CodeUnit) 的代码块 (CompiledCode)

from typing import Callable
from syntax_compile import parse, multi_parse
from basic_types import *
from type_checker import get_final_type, find_pairs
from syntax_compile import register_func_syntax
from basic_codes import *

COMPILER = Callable[[list[str], REGISTER], CodeUnit]
EXECUTOR = Callable[[tuple, VAR_MAP], None]

class _ExtendCodes:
    cmds_cb_map: dict[str, tuple[COMPILER, int]] = {}
    cmds_exe_map: dict[int, EXECUTOR] = {}
    counter = 512

    def add_cmd(self, cmd: str, compiler: COMPILER, executor: EXECUTOR):
        self.counter += 1
        self.cmds_cb_map[cmd] = (compiler, self.counter)
        self.cmds_exe_map[self.counter] = executor

extend_codes = _ExtendCodes()

def multi_parse_and_raise(syntax: str, namespace: REGISTER):
    try:
        return multi_parse(syntax, namespace)
    except SyntaxError as e:
        raise CodeSyntaxError(e.args[0])

def _type_assert(check_type: ANY_TYPE, std_type: ANY_TYPE, err: str = "要求表达式的结果为 %s, 却收到 %s"):
    if check_type != std_type:
        type1name = check_type.name if isinstance(check_type, BasicType) else "可空类型[" + check_type.type.name + "]"
        type2name = std_type.name if isinstance(std_type, BasicType) else "可空类型[" + std_type.type.name + "]"
        raise CodeSyntaxError(err % (type2name, type1name))

def compile(code: str, in_namespace: REGISTER):
    code_block_signal_stack = [0]
    code_block_stack: list[CompiledCode] = [CompiledCode([])]

    # 原理:
    # 每级代码块都是一个 CompileCode 对象, 用一个栈储存 (code_block_stack)
    # 用于检测代码块是否正确结束 的是代码块标准栈 (code_block_signal_stack)
    # 每级的代码块都有一个命名空间 (namespace), 互相独立
    # 由于静态类型, 要让每个代码块都返回相同的命名空间, 如果不同, 就取相同部分
    # 免得出现变量未绑定的情况(If出现Else没有出现)
    # 而 LoopUntil 这种代码块, 命名空间也是独立的, 最后不会影响上级命名空间
    # 也就是说 LoopUntil 里的变量理论上都是私有的, 如果想影响全局, 就需要在外部代码块先定义了该变量名
    # 否则上一级代码块无法使用此变量

    def _append(opid: int, *args):
        # 在当前代码块添加代码
        code_block_stack[-1].add_code(CodeUnit(opid, *args))

    def _regist_type(name: str, type: ANY_TYPE):
        # 在当前代码块命名空间注册变量
        code_block_stack[-1].add_namespace({name: type})

    def _get_local_namespace():
        # 获取当前代码块的命名空间
        return code_block_stack[-1].out_namespace

    def _get_space(ind = -1):
        # 获取上层代码块(默认), -n=上n层
        return code_block_stack[ind]

    text_lines = code.split("\n")

    try:
        for _ln, line in enumerate(text_lines):
            ln = _ln + 1
            _cmds = line.split()
            if not _cmds:
                continue
            # Description
            if line.strip().startswith("#"):
                continue
            cmd = _cmds[0]
            args = _cmds[1:] if len(_cmds) > 0 else []
            # Identify commands
            match cmd:
                case "结束":
                    _append(OPs.END, None)
                case "赋值" | "设置":
                    if len(args) < 3:
                        raise CodeSyntaxError("赋值语句错误, 应为 赋值 <变量名> 为 <常量/表达式>")
                    var_name = args[0]
                    parsed_syntax = parse(" ".join(args[2:]), _get_local_namespace())
                    new_type = get_final_type(parsed_syntax)
                    # if (old_type := _get_local_namespace().get(var_name)) and old_type != new_type:
                    #    _type_assert(new_type, old_type, f"变量 {var_name} 新类型 {new_type} 与旧类型 {old_type} 不同")
                    #    raise
                    _regist_type(var_name, new_type)
                    _append(OPs.SET, var_name, parsed_syntax)
                case "如果":
                    # 结构(parent space):
                    #   cache1: ((if_syntax, if_code), (...elif_syntax, elif_code),)
                    if len(args) < 2:
                        raise CodeSyntaxError("如果 的语句格式: 如果 ... 那么")
                    if args[-1] != "那么":
                        raise CodeSyntaxError("如果 ... 语句需要以 '那么' 结尾")
                    condition = parse(" ".join(args[:-1]), _get_local_namespace())
                    _type_assert(get_final_type(condition), BOOLEAN)
                    _get_space().cache1 = [[condition, None]]
                    code_block_signal_stack.append(Signal.IF)
                    code_block_stack.append(CompiledCode([], _get_local_namespace().copy()))
                case "又或者":
                    if code_block_signal_stack[-1] not in (Signal.IF, Signal.ELIF):
                        raise CodeSyntaxError("又或者 语句之前应有 如果 或 又或者 语句")
                    if len(args) < 2:
                        raise CodeSyntaxError("如果 的语句格式: 又或者 ... 那么")
                    if args[-1] != "那么":
                        raise CodeSyntaxError("如果 ... 语句需要以 '那么' 结尾")
                    condition = parse(" ".join(args[:-1]), _get_local_namespace())
                    # 退出 如果/又或者 的代码块
                    code_block_signal_stack[-1] = Signal.ELIF
                    code_prev = code_block_stack.pop(-1)
                    # 在上层空间放入 上一个判断 的代码块
                    space = _get_space()
                    space.cache1[-1][1] = code_prev
                    # 放入 新代码块
                    space.cache1.append([condition, None])
                    code_block_stack.append(CompiledCode([], _get_local_namespace().copy()))
                case "否则":
                    if code_block_signal_stack[-1] not in (Signal.IF, Signal.ELIF):
                        raise CodeSyntaxError("否则 语句之前应有 如果 语句")
                    code_block_signal_stack[-1] = Signal.ELSE
                    code_prev = code_block_stack.pop(-1)
                    space = _get_space()
                    space.cache1[-1][1] = code_prev
                    # 放入 新代码块
                    # 此时 cache2 可以为 否则 代码块
                    code_block_stack.append(CompiledCode([], _get_local_namespace().copy()))
                case "结束如果":
                    if code_block_signal_stack[-1] not in (Signal.IF, Signal.ELSE, Signal.ELIF):
                        raise CodeSyntaxError("在这个位置无法结束 如果 语句块")
                    # 退出 如果/否则 的代码块
                    last_sign = code_block_signal_stack.pop(-1)
                    code_prev = code_block_stack.pop(-1)
                    # 回到 如果 的上层代码块
                    # 此时 code_else 为 否则 的代码块
                    # 判断提取俩代码块共有的命名空间, 作为导出的命名空间, 导出到上级代码块
                    if last_sign in (Signal.IF, Signal.ELIF):
                        space = _get_space()
                        space.cache1[-1][1] = code_prev
                        code_prev = None
                    namespaces = find_pairs([i[1].out_namespace for i in space.cache1])
                    _get_local_namespace().update(namespaces)
                    # 总的来说, 就是 (判定表达式, 成立执行, 不成立执行)
                    _append(OPs.ENDIF, space.cache1, code_prev)
                    space.clear_cache()
                case "循环执行直到":
                    if len(args) < 1:
                        raise CodeSyntaxError("循环执行直到 语句需要一个表达式")
                    parsed_syntax = parse(" ".join(args), _get_local_namespace())
                    _type_assert(get_final_type(parsed_syntax), BOOLEAN)
                    _get_space().cache1 = parsed_syntax
                    # 此时 cache1 为判定表达式
                    code_block_signal_stack.append(Signal.LOOP_UNTIL)
                    code_block_stack.append(CompiledCode([], _get_local_namespace().copy()))
                case "结束循环":
                    if code_block_signal_stack[-1] != Signal.LOOP_UNTIL:
                        raise CodeSyntaxError("结束循环 语句之前应有 循环执行直到 语句")
                    code_block_signal_stack.pop(-1)
                    cur_code = code_block_stack.pop(-1)
                    # 回到 循环执行直到 的上级代码块
                    space = _get_space()
                    _append(OPs.ENDLOOP, space.cache1, cur_code)
                    space.clear_cache()
                case "输出":
                    parsed_syntaxs = multi_parse_and_raise(" ".join(args), _get_local_namespace())
                    _append(OPs.PRINT, parsed_syntaxs)
                case "执行":
                    parsed_syntax = parse(" ".join(args), _get_local_namespace())
                    _type_assert(get_final_type(parsed_syntax), STRING)
                    _append(OPs.EXECMD, parsed_syntax)
                case "@导入变量":
                    if len(args) != 2:
                        raise CodeSyntaxError("@导入变量 的格式: @导入变量 <变量名> <类型>")
                    if code_block_signal_stack[-1] != Signal.GLOBAL:
                        raise CodeSyntaxError("@导入变量 只能在最外层代码块使用")
                    var_name = args[0]
                    try:
                        var_type = get_zhcn_type(args[1])
                    except ValueError as e:
                        raise CodeSyntaxError(e.args[0])
                    lc_namespace = _get_local_namespace()
                    if var_name in lc_namespace.keys() and lc_namespace[var_name] != var_type:
                        raise CodeSyntaxError(f"变量 {var_name} 不能重载类型 {var_type} 到其旧类型 {lc_namespace[var_name]}")
                    if (vc_type := in_namespace.get(var_name)) != var_type:
                        if vc_type is None:
                            raise CodeSyntaxError(f"无法导入变量 {var_name}")
                        else:
                            raise CodeSyntaxError(f"正常导入的变量类型为 {vc_type}, 与索取的 {var_type} 不同")
                    _get_space().add_namespace({var_name: var_type})
                case "聊天栏显示":
                    parsed_syntaxs = multi_parse_and_raise(" ".join(args), _get_local_namespace())
                    if len(parsed_syntaxs) != 2:
                        raise CodeSyntaxError("聊天栏显示 的格式: 聊天栏显示 <目标名:表达式>; <内容:表达式>")
                    target = parsed_syntaxs[0]
                    content = parsed_syntaxs[1]
                    _type_assert(get_final_type(target), STRING)
                    _type_assert(get_final_type(content), STRING)
                    _append(OPs.SAYTO, parsed_syntaxs[0], parsed_syntaxs[1])
                case "忽略空变量":
                    var_name = args[0]
                    var_old_type = _get_local_namespace().get(var_name)
                    if var_old_type is None:
                        raise CodeSyntaxError(f"变量 {var_name} 不存在")
                    if not isinstance(var_old_type, OptionalType):
                        raise CodeSyntaxError(f"变量 {var_name} 不是可空变量, 无需忽略")
                    _get_local_namespace()[var_name] = de_optional(var_old_type)
                    _append(OPs.IGNORE_NULL, var_name)
                case "等待":
                    wtime = parse(" ".join(args), _get_local_namespace())
                    if get_final_type(wtime) != NUMBER:
                        raise CodeSyntaxError("等待 参数 需要数值")
                    _append(OPs.SLEEP, wtime)
                case _:
                    cmd_cb, cid = extend_codes.cmds_cb_map.get(cmd, (None, 0))
                    if cmd_cb is None:
                        raise CodeSyntaxError(f"未知命令: {cmd}")
                    code_unit = cmd_cb(args, _get_local_namespace())
                    code_unit.id = cid
                    code_block_stack[-1].add_code(code_unit)

    except (CodeSyntaxError, SyntaxError) as err:
        raise CodeSyntaxError(f"第 {ln} 行出现问题: {err}")

    if code_block_signal_stack[-1] != 0:
        raise CodeSyntaxError(f"代码结尾有代码块 \"{get_code_block_zhcn(code_block_signal_stack[-1])}\"未结束")

    return code_block_stack[-1]
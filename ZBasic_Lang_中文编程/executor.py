# 本模块功能: 执行代码块 (run)
# 对于要在 Minecraft 中进行操作的代码指令, 需要先 set_game_ctrl 初始化游戏控制器

import time

from compiler import *
from syntax_lib import SYNTAX_PTRS
from tooldelta import GameCtrl, Print


def set_game_ctrl(g: GameCtrl):
    global game_ctrl
    game_ctrl = g


def print_value(sth: list[SYNTAX_PTRS], local_vars: VAR_MAP):
    Print.print_with_info(" ".join(str(i.eval(local_vars)) for i in sth), "§f ZBas §r")


def run(compiled_code: CompiledCode, local_vars: VAR_MAP):
    # 执行编译脚本
    return _run(compiled_code, local_vars)


_SIGN_DEFAULT = 1
_SIGN_OUT = 100


def _run(cmp_code: CompiledCode, local_vars: VAR_MAP):
    sign = _SIGN_DEFAULT
    for code in cmp_code.code_seq:
        code_id = code.id
        code_args = code.args
        match code_id:
            case OPs.SET:
                var_name, val = code_args
                local_vars[var_name] = val.eval(local_vars)
            case OPs.END:
                sign = _SIGN_OUT
            case OPs.ENDIF:
                if_code_p, else_code = code_args
                for cond, m_code in if_code_p:
                    if cond.eval(local_vars):
                        sign = _run(m_code, local_vars)
                        break
                else:
                    if else_code is not None:
                        sign = _run(else_code, local_vars)
            case OPs.ENDLOOP:
                cond, loop_code = code_args
                while not cond.eval(local_vars):
                    sign = _run(loop_code, local_vars)
            case OPs.PRINT:
                print_value(code_args[0], local_vars)
            case OPs.EXECMD:
                game_ctrl.sendwocmd(code_args[0].eval(local_vars))
            case OPs.SAYTO:
                game_ctrl.say_to(
                    code_args[0].eval(local_vars), code_args[1].eval(local_vars)
                )
            case OPs.IGNORE_NULL:
                if local_vars[code_args[0]] is None:
                    sign = _SIGN_OUT
            case OPs.SLEEP:
                time.sleep(max(0, code_args[0].eval(local_vars)))
            case _:
                if code_exec := extend_codes.cmds_exe_map.get(code_id):
                    code_exec(code_args, local_vars)
                else:
                    raise Exception(f"Unknown OP Code: {code_id}")
        if sign == _SIGN_OUT:
            break

    return sign

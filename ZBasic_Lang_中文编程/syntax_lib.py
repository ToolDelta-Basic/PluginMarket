# 运算优先级(由高到低, 括号默认最高):
# 函数运算(所以说函数参数里的运算需要带括号)
# 幂运算
# 乘除运算
# 加减运算
# 比较运算
# 和
# 或
# 注: 非运算为函数运算, 优先级与函数一样

from typing import Callable
from basic_types import *

class ConstPtr(Pattern):
    def __init__(self, c):
        if isinstance(c, Pattern):
            raise ValueError(f"Can't use pattern {c} as constant")
        self.c = c
        self.type = type(c)

    def __repr__(self) -> str:
        return f"ConstPtr({repr(self.c)})"

    def eval(self, _):
        return self.c

class VarPtr(Pattern):
    def __init__(self, name, type):
        self.name = name
        self.type = type

    def __repr__(self):
        return 'VarPtr(' + repr(self.name) + ')'

    def eval(self, local_vars: VAR_MAP):
        return local_vars[self.name]

class FuncPtr(Pattern):
    def __init__(self, name: str, args: tuple, restype: RES_TYPE , func: Callable[[VAR_MAP, tuple], Any]):
        self.name = name
        self.args = args
        self.restype = restype
        self._func = func

    def __repr__(self):
        return "FuncPtr("+repr(self.name)+",args=("+",".join(repr(i)for i in self.args)+"))"

    def eval(self, local_vars: VAR_MAP):
        return self._func(*(i.eval(local_vars) for i in self.args))

class OpPtr(Pattern):
    op = staticmethod(lambda x,y:None)
    name = "<初始运算符>"
    def __init__(self, arg1, arg2):
        self.arg1 = arg1
        self.arg2 = arg2

    def __repr__(self):
        return self.__class__.__name__+"("+repr(self.arg1)+","+repr(self.arg2)+")"

    def eval(self, local_vars: VAR_MAP):
        c1 = self.arg1.eval(local_vars)
        c2 = self.arg2.eval(local_vars)
        return self.op(c1, c2)

class AddPtr(OpPtr):
    name = "+"
    op = staticmethod(lambda x,y:x+y if isinstance(x,(int,float)) and isinstance(y,(int,float)) else str(x)+str(y))
class SubPtr(OpPtr):
    name = "-"
    op = staticmethod(lambda x,y:x-y)
class MulPtr(OpPtr):
    name = "*"
    op = staticmethod(lambda x,y:x*y)
class DivPtr(OpPtr):
    name = "/"
    op = staticmethod(lambda x,y:x/y)
class PowPtr(OpPtr):
    name = "^"
    op = staticmethod(lambda x,y:x**y)
class AndPtr(OpPtr):
    name = "和"
    op = staticmethod(lambda x,y:x and y)
class OrPtr(OpPtr):
    name = "或"
    op = staticmethod(lambda x,y:x or y)
class EqPtr(OpPtr):
    name = "等于"
    op = staticmethod(lambda x,y:x==y)
class LtPtr(OpPtr):
    name = "小于"
    op = staticmethod(lambda x,y:x<y)
class GtPtr(OpPtr):
    name = "大于"
    op = staticmethod(lambda x,y:x>y)

opmap = {
    "+": AddPtr,
    "-": SubPtr,
    "*": MulPtr,
    "/": DivPtr,
    "^": PowPtr,
    "=": EqPtr,
    "<": LtPtr,
    ">": GtPtr,
    "和": AndPtr,
    "或": OrPtr,
}

max_priority = 6

OP_CHARS = ''.join(i for i in opmap.keys())

SYNTAX_PTRS = VarPtr | OpPtr | ConstPtr | FuncPtr

def op_prior(o):
    "操作符优先级"
    if o  == OpPtr:
        # 根本不会被识别
        return 0
    elif o in [OrPtr]:
        return 1
    elif o in [AndPtr]:
        return 2
    elif o in [LtPtr, GtPtr, EqPtr]:
        return 3
    elif o in [AddPtr, SubPtr]:
        return 4
    elif o in [MulPtr, DivPtr]:
        return 5
    elif o in [PowPtr]:
        return 6
    else:
        raise SyntaxError(o)

def num3var(n: str, register: REGISTER = {}):
    "数字或字符串或是变量"
    if not isinstance(n, str):
        raise ValueError(f"num3var need str, not {n}")
    if n == "是":
        return ConstPtr(True)
    elif n == "否":
        return ConstPtr(False)
    if '"' in n:
        if not (n.startswith('"') and n.endswith('"')):
            raise SyntaxError("字符串未正确结束")
        if '"' in n[1:-1]:
            raise SyntaxError("字符串双引号位置异常")
        return ConstPtr(n[1:-1])
    try:
        if "." in n:
            return ConstPtr(float(n))
        else:
            return ConstPtr(int(n))
    except ValueError:
        if t:= register.get(n) is None:
            raise SyntaxError(f"未知或未完全绑定的变量: {n}")
        return VarPtr(n,t)

def subcls(i,cls):
    if type(i) != type:
        return False
    else:
        return issubclass(i,cls)
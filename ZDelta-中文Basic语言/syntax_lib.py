opcodes="+-*/^和或"
funopcodes=",()"

var_types = {}

__all__ = [
  "VarPtr",
  "FuncPtr",
  "OpPtr",
  "AddPtr",
  "SubPtr",
  "MulPtr",
  "DivPtr",
  "PowPtr",
  "AndPtr",
  "OrPtr"
]

class VarPtr:
  def __init__(self,name,type):
    self.name=name
    self.type=type
  def __repr__(self):
    return 'VarPtr('+repr(self.name)+')'
class FuncPtr:
  def __init__(self,name, args, restype):
    self.name=name
    self.args=args
    self.restype=restype
  def __repr__(self):
    return "FuncPtr("+repr(self.name)+",args=("+",".join(repr(i)for i in self.args)+"))"
class OpPtr:
  op=staticmethod(lambda x,y:None)
  name="<初始运算符>"
  def __init__(self,arg1,arg2):
    self.arg1=arg1
    self.arg2=arg2
  def __repr__(self):
    return self.__class__.__name__+"("+repr(self.arg1)+","+repr(self.arg2)+")"
  def calc(self):
    if isinstance(self.arg1,OpPtr):c1=self.arg1.calc()
    else:c1=self.arg1
    if isinstance(self.arg2,OpPtr):c2=self.arg2.calc()
    else:c2=self.arg2
    return self.op(c1,c2)

class AddPtr(OpPtr):
  name="+"
  op=staticmethod(lambda x,y:x+y if isinstance(x,(int,float)) and isinstance(y,(int,float)) else str(x)+str(y))
class SubPtr(OpPtr):
  name="-"
  op=staticmethod(lambda x,y:x-y)
class MulPtr(OpPtr):
  name="*"
  op=staticmethod(lambda x,y:x*y)
class DivPtr(OpPtr):
  name="/"
  op=staticmethod(lambda x,y:x/y)
class PowPtr(OpPtr):
  name="^"
  op=staticmethod(lambda x,y:x**y)
class AndPtr(OpPtr):
  name="和"
  op=staticmethod(lambda x,y:x and y)
class OrPtr(OpPtr):
  name="或"
  op=staticmethod(lambda x,y:x or y)

opmap={"+":AddPtr,"-":SubPtr,"*":MulPtr,"/":DivPtr,"^":PowPtr,"和":AndPtr,"或":OrPtr}
max_priority=5

def op_prior(o):
  "操作符优先级"
  if o==OpPtr:
    return 0
  elif o in [AddPtr,SubPtr]:
    return 1
  elif o in [MulPtr,DivPtr]:
    return 2
  elif o in [PowPtr]:
    return 3
  elif o in [OrPtr]:
    return 4
  elif o in [AndPtr]:
    return 5
  else:
    raise SyntaxError(o)

def num3var(n, loc_var_types: dict | None = None):
  "数字或是变量"
  try:
    if "." in n:
      return float(n)
    else:
      return int(n)
  except ValueError:
    if '"' in n:
      raise SyntaxError("暂不支持在表达式中使用双引号表示字符串, 请改用 设置变量 的方法设置字符串")
    t = var_types.get(n)
    if t is None and loc_var_types is not None:
      t = loc_var_types.get(n)
    if t is None:
      raise ValueError(f"未知类型: {n}, 或者是表达式错误")
    return VarPtr(n,t)

def subcls(i,cls):
  if type(i)!=type:
    return False
  else:
    return issubclass(i,cls)
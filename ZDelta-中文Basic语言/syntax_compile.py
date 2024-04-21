from syntax_lib import (
  FuncPtr,
  VarPtr,
  OpPtr,
  opcodes,
  opmap,
  num3var,
  subcls,
  max_priority,
  op_prior,
  var_types
)
from checker import fun_inputypechk, fun_restype, get_final_type
from basic_types import *

fun_stxs: list[str] = []
func_cbs: list = []

def register_func_syntax(stx: str, restype: int, input_type_checker=lambda _:True):
  fun_stxs.append(stx)
  fun_restype[stx]=restype
  fun_inputypechk[stx]=input_type_checker

def register_var(varname: str, vartype: int):
  var_types[varname]=vartype

def parse(pat: str) -> list:
  """
  解析表达式字符串
  传入:
      pat: 表达式组
  返回:
      表达式列表
  """
  if not pat.strip():
    print("警告: 输入空表达式")
  opseq=[]
  txt_cache=""
  cma_num,cma_txt=0,""
  is_fun=False
  fun_name=""
  funseq=[]
  for c in pat+"?":
    if c=="(":
      cma_num+=1
      if cma_num==1:
        continue
    elif c==")":
      cma_num-=1
      if cma_num<0:
        raise SyntaxError("括号没有正确闭合")
      if cma_num==0:
        if not cma_txt:
          raise SyntaxError("括号内容不能为空")
        if is_fun:
          funseq.append(parse(cma_txt))
        else:
          opseq.append(parse(cma_txt))
        cma_txt=""
        continue
    if cma_num:
      cma_txt+=c
    elif is_fun:
      # 正在接受函数参数
      if c in opcodes+"?":
        # 为操作符, 终止参数接收
        is_fun=False
        if txt_cache.strip():
          # 如果接收到了参数
          funseq.append(parse(txt_cache))
        # 不是为什么非得tuple啊
        # 有病吧, 没tuple 输出的函数就没参
        syntax_grp = tuple(deal_stxgrp(i) for i in funseq)
        opseq.append(deal_funptr(fun_name, syntax_grp))
        if c!="?":
          # 非结束运算符
          opseq.append(opmap.get(c))
        txt_cache=""
        funseq.clear()
      elif c==",":
        # 参数分隔
        if txt_cache:
          funseq.append(parse(txt_cache))
        else:
          raise SyntaxError("逗号分隔符前需要表达式")
        txt_cache=""
      else:
        txt_cache+=c
    elif c in " "+opcodes+"?":
      # 标志着一个函数名/变量名/常量的结束
      if c==" ":
        # 非括号内容, 非函数接收, 接收到了一个空格
        if txt_cache in fun_stxs:
          # 是函数调用
          is_fun=True
          fun_name=txt_cache
        elif txt_cache in var_types.keys():
          # 是已注册变量
          opseq.append(VarPtr(txt_cache, var_types[txt_cache]))
        elif txt_cache:
          # 不是函数调用 不是已知变量 则可能为变量等?
          opseq.append(num3var(txt_cache))
        txt_cache=""
      elif c in opcodes+"?":
        # 是操作符或者结束符
        if not txt_cache:
          # 操作符前的表达式为空
          # 但是有可能表达式缓存被自动清理了
          pass
          #raise SyntaxError("操作符前需要项")
        else:
          if txt_cache in fun_stxs:
            # 芝士函数, 但是没有传入参数就直接终止了
            opseq.append(deal_funptr(txt_cache, ()))
          elif txt_cache in var_types.keys():
            # 是已注册变量
            opseq.append(VarPtr(txt_cache, var_types[txt_cache]))
          elif txt_cache:
            # 不是函数调用 不是已知变量 则可能为变量等?
            opseq.append(num3var(txt_cache))
        if c!="?":
          opc=opmap.get(c)
          if opc is None:
            raise SyntaxError("运算符不正确: "+c)
          opseq.append(opc)
        txt_cache=""
    else:
      # 连续的文本
      txt_cache+=c
  if cma_num:
    raise SyntaxError("括号没有正确闭合")
  return opseq

def deal_funptr(fun_name, fun_args):
  assert isinstance(fun_name, str), "需要函数名"
  return FuncPtr(fun_name, fun_args, fun_restype[fun_name])

def deal_stxgrp(grp: list):
  """
  对表达式组进行优先分级

  Args:
      grp: 传入表达式组

  Returns:
      表达式基团
  """
  if not grp:
   raise ValueError("Empty syntax")
  opmode=-1
  for s in grp:
   if subcls(s,OpPtr):
    if opmode==1:
      raise SyntaxError("存在多重连在一起的运算符")
    opmode=1
   else:
    if opmode==0:
      raise SyntaxError("两个项之间需要运算符")
    else:opmode=0
  if subcls(grp[-1],OpPtr):
    raise SyntaxError("不能以运算符作为表达式结尾")
  prtable=grp.copy()
  for p in range(max_priority,0,-1):
   nprtable=[]
   arg1,arg2=[None]*2
   lastop=OpPtr
   for s in prtable+[OpPtr]:
    if subcls(s,OpPtr):
     if op_prior(s)==p:
      if op_prior(lastop)==p:
       arg1=lastop(arg1,arg2)
       arg2=None
     elif op_prior(s)<p:
      if op_prior(lastop)==p:
       nprtable.append(lastop(arg1,arg2))
       arg1=arg2=None
      elif op_prior(lastop)<p:
       nprtable.append(arg1)
       if arg2:
        raise Exception("what?!",arg1,arg2)
       arg1=None
      if s!=OpPtr:
       nprtable.append(s)
     lastop=s
    else:
     if arg1:arg2=s
     else:arg1=s
   prtable=nprtable.copy()
  return prtable[0]

if __name__=="__main__":
  import random
  register_func_syntax("int",0,lambda s:s[0]==s[1]==0)
  register_func_syntax("str_d1",0,lambda s:s[0]==0 and s[1]==1)
  register_func_syntax(
    "随机整数", NUMBER,
    lambda x:len(x)==2 and x[0]==x[1]==NUMBER
  )
  register_var("mk_str", STRING)
  syntax = parse('随机整数 1, 2')
  print("表达式组解析:", syntax)
  syntax_ok = deal_stxgrp(syntax)
  print("-----------")
  print("表达式组解析完成:", syntax_ok)
  try:
    t = get_final_type(syntax_ok)
    print("类型:", t)
  except Exception as err:
    print(err)
    import traceback
    #traceback.print_exc()
  # will be crashed
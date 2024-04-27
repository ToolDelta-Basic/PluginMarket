from basic_types import *

def identity_type(param: str):
    if is_valid_num(param):
        return NUMBER
    elif is_valid_str(param):
        return STRING
    else:
        return ANY

def auto_to_type_r(n: str, loc_vars_types: dict):
    t = identity_type(n)
    if t == ANY:
        if n in loc_vars_types:
            return n, loc_vars_types[n], False
        else:
            raise ValueError(f"无法取得 {n} 的类型")
    elif t == NUMBER:
        return to_number(n), NUMBER, True
    elif t == STRING:
        return to_string(n), STRING, True
    else:
        raise Exception

def is_valid_num(n: str):
    try:
        float(n)
        return True
    except:
        return False

def is_valid_str(n: str):
    return n.startswith('"') and n.endswith('"') and n.count('"') == 2

def to_string(n: str):
    return n[1:-1]

def to_number(n: str):
    s = float(n)
    if s % 1:
        return s
    else:
        return int(s)

def split_by_quote(n: str):
    res = []
    qopen = False
    cache = ""
    for char in n:
        if char == '"':
            if qopen:
                res.append('"' + cache + '"')
                cache = ""
                qopen = False
            else:
                qopen = True
        elif char == " " and not qopen:
            if cache:
                res.append(cache)
                cache = ""
        else:
            cache += char
    if cache:
        res.append(cache)
    if qopen:
        raise SyntaxError("双引号未正确闭合")
    return res
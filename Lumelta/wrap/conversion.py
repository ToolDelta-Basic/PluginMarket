def lua_table_to_python(obj):
    if "Table" in str(type(obj)):
        # 尝试判断是否为数组（连续的整数键）
        keys = list(obj.keys())
        is_array = True
        max_key = 0
        converted = {}
        
        for key in keys:
            value = obj[key]
            # 递归处理值
            converted_value = lua_table_to_python(value)
            converted[key] = converted_value
            
            # 检查键是否为连续整数
            if isinstance(key, int) and key > 0:
                if key > max_key:
                    max_key = key
            else:
                is_array = False
        
        # 如果是数组（键为 1 到 max_key 的连续整数）
        if is_array and max_key == len(keys):
            return [converted[i+1] for i in range(max_key)]
        else:
            return converted
    else:
        # 基础类型直接返回
        return obj

def python_to_lua_table(data, lua_runtime):
    if isinstance(data, dict):
        # 字典转为Lua table（键值对）
        lua_table = lua_runtime.table_from()
        for k, v in data.items():
            lua_table[k] = python_to_lua_table(v, lua_runtime)
        return lua_table
    elif isinstance(data, list):
        # 列表转为Lua table（索引从1开始）
        lua_table = lua_runtime.table_from()
        for i, item in enumerate(data, 1):  # Lua索引从1开始
            lua_table[i] = python_to_lua_table(item, lua_runtime)
        return lua_table
    else:
        # 基本类型直接返回（如str、int、float等）
        return data
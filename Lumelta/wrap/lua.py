from .safe import SafeList, SafeDict
import inspect

def python_index_to_lua_index(data):
    if isinstance(data, dict):
        for k, v in data.items():
            k = python_index_to_lua_index(v)
        data = SafeDict(data)
    elif isinstance(data, list):
        for i, v in enumerate(data):
            data[i] = python_index_to_lua_index(v)
        data.insert(0, None)
        data = SafeList(data)
    return data

def register_class(
    lua_runtime,
    cls,
    target_table,
    classes = [],
    max_depth: int = 1,
    depth: int = 0,
    registered_classes: set = None
):
    if registered_classes is None:
        registered_classes = set()  # 初始化循环引用保护集合
    
    if depth > max_depth or cls in registered_classes:
        return  # 达到深度限制或已注册过则跳过
    
    registered_classes.add(cls)  # 标记为已注册
    
    # 创建目标表（默认使用全局表或自定义表）
    if target_table is None:
        target_table = lua_runtime.globals()
    
    # 注册当前类的方法到目标表
    for name in dir(cls):
        if name.startswith('__'):
            continue  # 跳过特殊方法
        
        attr = getattr(cls, name)
        target_table[name] = attr  # 直接注册方法引用
    
    # 递归处理嵌套类属性
    if depth < max_depth:
        for name, attr in cls.__dict__.items():
            if not True in [str(type(attr)) == str(classe) for classe in classes]:
                continue

            if attr in registered_classes:
                continue  # 避免循环引用
            
            # 创建嵌套表
            nested_table = lua_runtime.table()
            target_table[name] = nested_table
            # 递归注册嵌套类
            register_class(
                lua_runtime,
                attr,
                target_table=nested_table,
                max_depth=max_depth,
                depth=depth + 1,
                registered_classes=registered_classes
            )

def register_module(lua_runtime, module_name, instance, classes = [], version='1.0.0'):
    """自动将Python类实例的方法注册为Lua模块"""
    """
    # 收集公共方法
    methods = {}
    for name in dir(instance):
        if name.startswith('_'):
            continue
        attr = getattr(instance, name)
        methods[name] = attr

    # 注册到Lua全局临时变量
    lua_globals = lua_runtime.globals()
    for method_name in methods:
        lua_global_name = f"{module_name}_{method_name}"
        lua_globals[lua_global_name] = getattr(instance, method_name)

    # 生成Lua模块加载代码
    method_entries = [f"{name} = {module_name}_{name}" for name in methods]
    lua_table = "{\n    " + ",\n    ".join(method_entries) + "\n}"
    """
    lua_runtime.globals()[module_name] = lua_runtime.table()
    register_class(lua_runtime, instance, lua_runtime.globals()[module_name], classes)
    lua_code = f'''
    package.preload['{module_name}'] = function()
        local module = {module_name}
        module._VERSION = '{version}'
        return module
    end
    '''
    lua_runtime.execute(lua_code)
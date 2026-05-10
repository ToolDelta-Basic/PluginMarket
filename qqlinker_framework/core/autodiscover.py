"""模块自动发现引擎"""
import importlib
import pkgutil
from typing import List, Type
from .module import Module


def discover_modules(
    package_name: str = "qqlinker_framework.modules"
) -> List[Type[Module]]:
    """递归扫描包，返回所有 Module 子类。

    Args:
        package_name: 包名。

    Returns:
        发现的模块类列表。
    """
    module_classes: List[Type[Module]] = []
    try:
        package = importlib.import_module(package_name)
    except ImportError:
        print(f"[AutoDiscover] 包 '{package_name}' 不存在，跳过自动发现")
        return module_classes
    _walk_package(package, module_classes)
    return module_classes


def _walk_package(package, result: List[Type[Module]]):
    """递归遍历包，收集 Module 子类。

    Args:
        package: Python 包对象。
        result: 结果列表，原地修改。
    """
    prefix = package.__name__ + "."
    for _, modname, ispkg in pkgutil.iter_modules(
        package.__path__, prefix=prefix
    ):
        if ispkg:
            try:
                sub_pkg = importlib.import_module(modname)
                _walk_package(sub_pkg, result)
            except Exception as e:
                print(f"[AutoDiscover] 导入子包 {modname} 失败: {e}")
        else:
            try:
                mod = importlib.import_module(modname)
            except Exception as e:
                print(f"[AutoDiscover] 导入模块 {modname} 失败: {e}")
                continue
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Module)
                    and attr is not Module
                    and getattr(attr, 'name', None)
                ):
                    result.append(attr)


def sort_by_dependencies(classes: List[Type[Module]]) -> List[Type[Module]]:
    """根据模块依赖进行拓扑排序，若存在循环依赖则返回原始顺序。

    Args:
        classes: 未排序的模块类列表。

    Returns:
        排序后的列表。
    """
    if not classes:
        return classes
    name_to_cls = {}
    for cls in classes:
        if not cls.name:
            print(f"[AutoDiscover] 模块类 {cls.__name__} 缺少 name，跳过排序")
            continue
        name_to_cls[cls.name] = cls

    in_degree = {cls.name: 0 for cls in classes if cls.name}
    graph = {cls.name: [] for cls in classes if cls.name}
    for cls in classes:
        if not cls.name:
            continue
        for dep in cls.dependencies:
            if dep in name_to_cls:
                graph[dep].append(cls.name)
                in_degree[cls.name] += 1
            else:
                print(f"[AutoDiscover] 模块 {cls.name} 依赖的 {dep} 未找到，忽略")

    queue = [name for name, degree in in_degree.items() if degree == 0]
    sorted_names = []
    while queue:
        name = queue.pop(0)
        sorted_names.append(name)
        for dependent in graph.get(name, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(sorted_names) != len(name_to_cls):
        print("[AutoDiscover] 检测到循环依赖，将使用原始顺序")
        return classes

    sorted_classes = []
    for name in sorted_names:
        sorted_classes.append(name_to_cls[name])
    for cls in classes:
        if cls not in sorted_classes:
            sorted_classes.append(cls)
    return sorted_classes
    
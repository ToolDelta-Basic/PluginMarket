"""模块自动发现引擎"""
import importlib
import logging
import pkgutil
from typing import List, Type
from .module import Module

logger = logging.getLogger(__name__)


def discover_modules(
    package_name: str = "qqlinker_framework.modules"
) -> List[Type[Module]]:
    """递归扫描包，返回所有 Module 子类。"""
    module_classes: List[Type[Module]] = []
    try:
        package = importlib.import_module(package_name)
    except ImportError:
        logger.warning("包 '%s' 不存在", package_name)
        return module_classes
    _walk_package(package, module_classes)
    return module_classes


def _walk_package(package, result: List[Type[Module]]):
    """递归遍历包，收集 Module 子类。"""
    prefix = package.__name__ + "."
    for _, modname, ispkg in pkgutil.iter_modules(
        package.__path__, prefix=prefix
    ):
        if ispkg:
            try:
                sub_pkg = importlib.import_module(modname)
                _walk_package(sub_pkg, result)
            except Exception as e:
                logger.exception("导入子包 %s 失败: %s", modname, e)
        else:
            try:
                mod = importlib.import_module(modname)
            except Exception as e:
                logger.exception("导入模块 %s 失败: %s", modname, e)
                continue
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Module)
                    and attr is not Module
                    and getattr(attr, "name", None)
                ):
                    result.append(attr)


def _build_dependency_graph(classes: List[Type[Module]]):
    """构建依赖关系图与入度表。"""
    name_to_cls = {}
    in_degree = {}
    graph = {}
    for cls in classes:
        if not cls.name:
            continue
        name_to_cls[cls.name] = cls
        in_degree[cls.name] = in_degree.get(cls.name, 0)
        graph[cls.name] = []
    for cls in classes:
        if not cls.name:
            continue
        for dep in cls.dependencies:
            if dep in name_to_cls:
                graph[dep].append(cls.name)
                in_degree[cls.name] += 1
            else:
                logger.warning(
                    "模块 %s 依赖的 %s 未找到", cls.name, dep
                )
    return name_to_cls, in_degree, graph


def _topological_sort(name_to_cls, in_degree, graph):
    """执行拓扑排序，返回排序后的类列表。"""
    queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_names = []
    while queue:
        name = queue.pop(0)
        sorted_names.append(name)
        for dependent in graph.get(name, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    if len(sorted_names) != len(name_to_cls):
        return None
    return [name_to_cls[name] for name in sorted_names]


def sort_by_dependencies(
    classes: List[Type[Module]],
) -> List[Type[Module]]:
    """根据模块依赖进行拓扑排序，若存在循环依赖则返回原始顺序。"""
    if not classes:
        return classes
    name_to_cls, in_degree, graph = _build_dependency_graph(classes)
    sorted_classes = _topological_sort(name_to_cls, in_degree, graph)
    if sorted_classes is None:
        logger.warning("检测到循环依赖，将使用原始顺序")
        return classes
    result = list(sorted_classes)
    for cls in classes:
        if cls not in result:
            result.append(cls)
    return result

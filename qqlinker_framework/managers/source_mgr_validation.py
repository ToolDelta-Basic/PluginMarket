import logging
from typing import Dict, List, Optional, Set, Type

from qqlinker_framework.core.module import Module


def check_circular_dependencies(mods: List[Module]) -> List[str]:
    """检测模块间的循环依赖（DFS 环检测）。

    Returns:
        涉及循环依赖的所有模块名列表（空表示无环）。
    """
    logger = logging.getLogger(__name__)

    dep_graph: Dict[str, Set[str]] = {}
    name_map: Dict[str, Module] = {}

    for mod in mods:
        name = getattr(mod, 'name', mod.__class__.__name__)
        name_map[name] = mod
        dep_graph[name] = set()

    for mod in mods:
        name = getattr(mod, 'name', mod.__class__.__name__)
        for srv_name in getattr(mod, 'required_services', []):
            if srv_name in name_map:
                dep_graph[name].add(srv_name)
        for dep_name in getattr(mod, 'dependencies', []):
            if dep_name in name_map:
                dep_graph[name].add(dep_name)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {name: WHITE for name in dep_graph}
    cycle_nodes: Set[str] = set()

    def dfs(node: str, path: List[str]) -> bool:
        color[node] = GRAY
        path.append(node)
        for neighbor in dep_graph.get(node, set()):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:]
                cycle_nodes.update(cycle)
                logger.error(
                    "⛔ 检测到循环依赖: %s → %s（通过 %s）",
                    node, neighbor, " → ".join(cycle),
                )
                return True
            if color[neighbor] == WHITE:
                dfs(neighbor, path)
        path.pop()
        color[node] = BLACK
        return False

    for node in list(dep_graph.keys()):
        if color.get(node) == WHITE:
            dfs(node, [])

    if cycle_nodes:
        logger.warning(
            "循环依赖涉及模块: %s。这些模块将按原始顺序加载。",
            ", ".join(sorted(cycle_nodes)),
        )

    return list(cycle_nodes)


def dry_run_import(module_cls: Type[Module]) -> Optional[Type[Module]]:
    """Dry-run 导入检查：验证模块类是否可以安全加载。

    Returns:
        模块类本身（检查通过），或 None（检查失败）。
    """
    logger = logging.getLogger(__name__)
    mod_name = getattr(module_cls, 'name', module_cls.__name__)

    # 检查 required_services 格式
    required = getattr(module_cls, 'required_services', None)
    if required is not None:
        if not isinstance(required, (list, tuple)):
            logger.error(
                "❌ 模块 '%s': required_services 必须是 list/tuple，实际 %s",
                mod_name, type(required).__name__,
            )
            return None
        for srv in required:
            if not isinstance(srv, str):
                logger.error(
                    "❌ 模块 '%s': required_services 中的元素必须是 str，实际 %s",
                    mod_name, type(srv).__name__,
                )
                return None

    # 检查 config_schema / default_config 格式
    for attr in ('config_schema', 'default_config'):
        val = getattr(module_cls, attr, None)
        if val is not None and not isinstance(val, dict):
            logger.error(
                "❌ 模块 '%s': %s 必须是 dict，实际 %s",
                mod_name, attr, type(val).__name__,
            )
            return None

    # 检查继承
    try:
        if not issubclass(module_cls, Module):
            logger.error("❌ 模块 '%s': 必须是 Module 的子类", mod_name)
            return None
    except TypeError:
        logger.error("❌ 模块 '%s': 不是有效的类", mod_name)
        return None

    # 尝试 __new__
    try:
        _ = module_cls.__new__(module_cls)
    except Exception as e:
        logger.error(
            "❌ 模块 '%s': 实例化失败: %s (%s)",
            mod_name, e, type(e).__name__,
        )
        return None

    logger.info(
        "✅ dry-run 通过: 模块 '%s' (required=%s)",
        mod_name, required if required else '[]',
    )
    return module_cls

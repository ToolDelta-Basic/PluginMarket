# modules/ai/tools/__init__.py
"""工具子包：自动发现并注册所有工具模块。"""
import importlib
import pkgutil
import logging

def register_all(tool_manager):
    """自动导入当前目录下的所有工具模块并调用 register_tools。

    Args:
        tool_manager: ToolManager 实例。
    """
    package = __package__
    for _, modname, ispkg in pkgutil.iter_modules(__path__, prefix=package + "."):
        if ispkg:
            continue
        try:
            mod = importlib.import_module(modname)
            if hasattr(mod, 'register_tools'):
                mod.register_tools(tool_manager)
                logging.getLogger(__name__).info("已注册工具组: %s", modname)
        except Exception as e:
            logging.getLogger(__name__).error("无法加载工具模块 %s: %s", modname, e)
            
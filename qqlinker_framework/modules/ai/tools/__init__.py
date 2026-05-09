# modules/ai/tools/__init__.py
import importlib
import pkgutil
import logging

def register_all(tool_manager):
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
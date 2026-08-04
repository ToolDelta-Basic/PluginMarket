# modules/ai/tools/__init__.py
import importlib
import logging
import os
import pkgutil

from qqlinker_framework.managers import ToolType


def register_all(tool_manager, services=None):
    """注册所有 AI 工具：Python 自动发现 + JSON 目录扫描。

    两步注册：
      1. 导入 Python 工具模块，调用其 register_tools()（注册回调函数）
      2. 扫描 JSON 定义目录，补充/更新 schema 信息
         已存在同名工具时只补充 JSON 中的元信息（description, parameters 等），
         不覆盖 callback。

    Args:
        tool_manager: ToolManager 实例。
        services: 可选的服务容器，用于工具回调访问其他服务。
    """
    logger = logging.getLogger(__name__)

    # ── 第一步：Python 模块自动发现（注册回调函数）──
    package = __package__
    for _, modname, ispkg in pkgutil.iter_modules(__path__, prefix=package + "."):
        if ispkg:
            continue
        try:
            mod = importlib.import_module(modname)
            if hasattr(mod, 'register_tools'):
                mod.register_tools(tool_manager, services=services)
                logger.info("已注册工具组: %s", modname)
        except Exception as e:
            logger.error("无法加载工具模块 %s: %s", modname, e)

    # ── 第二步：从 JSON 目录加载 AI 工具 schema ──
    _load_tools_from_json_dir(tool_manager, logger)


def _load_tools_from_json_dir(tool_manager, logger):
    """从 数据/工具/AI工具/ 目录扫描 JSON 定义文件。

    对于每个 JSON 文件：
      - 如果对应 name 的工具已注册（Python 模块提供），则用 JSON 信息
        补充/覆盖其参数定义（description、parameters、risk_level、api_type、
        category、timeout 等），但保留 Python 注册的 callback。
      - 如果对应 name 的工具尚未注册，则创建一个无回调的纯 schema 工具
        （作为占位，方便后续热加载回调）。

    支持两种格式：
      1. 直接工具 JSON：顶层包含 name/tool_type/parameters 等字段。
      2. 工具组 JSON：顶层包含 sub_tools 数组（如 记忆.json），
         每个 sub_tool 条目被展开为独立工具注册。
    """
    try:
        data_dir = _resolve_data_tools_dir(tool_manager)
    except Exception:
        logger.debug("无法获取数据目录，跳过 JSON 工具加载")
        return

    ai_tools_dir = os.path.join(data_dir, "AI工具")
    if not os.path.isdir(ai_tools_dir):
        logger.debug("AI 工具 JSON 目录不存在: %s", ai_tools_dir)
        return

    for fname in sorted(os.listdir(ai_tools_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(ai_tools_dir, fname)
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("读取工具 JSON 失败 %s: %s", path, e)
            continue

        # 处理两种格式：直接工具 vs 工具组
        if "sub_tools" in data:
            # 工具组格式（如 记忆.json）
            parent_category = data.get("category", "general")
            parent_risk = data.get("risk_level", "low")
            for sub in data["sub_tools"]:
                _apply_json_schema(tool_manager, sub, logger, path,
                                   parent_category, parent_risk)
        else:
            _apply_json_schema(tool_manager, data, logger, path)


def _apply_json_schema(tool_manager, data, logger, source_path,
                       fallback_category="general", fallback_risk="low"):
    """将单个工具的 JSON schema 应用到 ToolManager。

    如果工具已存在（Python 已注册回调），则补充/更新元信息；
    如果不存在，则创建纯 schema 占位（无回调）。
    """
    name = data.get("name")
    if not name:
        logger.warning("工具 JSON 缺少 name 字段: %s", source_path)
        return

    existing = tool_manager.get_tool(name)
    if existing:
        # 有 Python 回调：用 JSON 补充/覆盖元信息，保留 callback
        logger.debug("补充工具 '%s' 的 JSON schema (源: %s)", name, source_path)
        existing.description = data.get("description", existing.description)
        if "parameters" in data:
            existing.parameters = data["parameters"]
        existing.risk_level = data.get("risk_level", existing.risk_level)
        existing.require_confirm = data.get("require_confirm", existing.require_confirm)
        existing.admin_only = data.get("admin_only", existing.admin_only)
        existing.api_type = data.get("api_type", existing.api_type)
        if "category" in data:
            existing.category = data["category"]
        existing.timeout = data.get("timeout", existing.timeout)
        existing.enabled = data.get("enabled", existing.enabled)
        existing.required_config_keys = data.get("required_config_keys",
                                                  existing.required_config_keys)
        if data.get("tool_type"):
            existing.tool_type = data["tool_type"]
    else:
        # 无 Python 回调：创建纯 schema 占位（无 callback）
        logger.info("注册纯 schema 工具 '%s' (源: %s，无回调)", name, source_path)
        tool_manager.register_tool({
            "name": name,
            "description": data.get("description", ""),
            "parameters": data.get("parameters", {}),
            "tool_type": data.get("tool_type", ToolType.AI),
            "risk_level": data.get("risk_level", fallback_risk),
            "require_confirm": data.get("require_confirm", False),
            "admin_only": data.get("admin_only", False),
            "api_type": data.get("api_type", "generic"),
            "category": data.get("category", fallback_category),
            "timeout": data.get("timeout", 30),
            "enabled": data.get("enabled", True),
            "required_config_keys": data.get("required_config_keys", []),
            "callback": None,  # 无回调，待后续热加载
        })


def register_admin_tools(tool_manager):
    """扫描 数据/工具/管理工具/ 目录注册管理工具。

    管理工具通过 JSON schema 定义，由 AdminToolManager 编排执行，
    其回调函数通过热加载名称匹配。

    Args:
        tool_manager: ToolManager 实例。

    Returns:
        成功注册的管理工具数量。
    """
    logger = logging.getLogger(__name__)

    try:
        data_dir = _resolve_data_tools_dir(tool_manager)
    except Exception:
        logger.warning("无法获取数据目录，跳过管理工具注册")
        return 0

    admin_tools_dir = os.path.join(data_dir, "管理工具")
    return tool_manager.scan_directory(admin_tools_dir, tool_type=ToolType.ADMIN)


def _resolve_data_tools_dir(tool_manager) -> str:
    """解析 数据/工具/ 目录路径。

    尝试从 tool_manager._tool_folder 获取，失败则回退到相对路径推断。
    """
    if tool_manager._tool_folder and os.path.isdir(tool_manager._tool_folder):
        return tool_manager._tool_folder

    # 回退：从当前模块路径推断项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 向上走: tools -> ai -> modules -> qqlinker_framework
    framework_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    return os.path.join(framework_dir, "数据", "工具")

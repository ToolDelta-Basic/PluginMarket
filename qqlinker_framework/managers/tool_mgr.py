"""通用工具管理器 —— 管理工具注册、配置注入与执行

v2: 支持工具分类（AI 工具 vs 管理工具）。
- AI 工具: 给 AI function calling 使用，注册到 OpenAI schema
- 管理工具: 给 AdminToolManager 做工作流编排，不暴露给 AI
"""
import asyncio
import inspect
import os
import json
import logging
from typing import Callable, Dict, List, Optional, Any


class ToolType:
    """工具类型常量。"""
    AI = "ai"         # AI function calling 工具
    ADMIN = "admin"    # 管理工具（给 AdminToolManager 编排）

    # 合法类型集合
    VALID_TYPES = {AI, ADMIN}

    @classmethod
    def is_valid(cls, tool_type: str) -> bool:
        """检查工具类型是否合法。"""
        return tool_type in cls.VALID_TYPES


class ToolDefinition:
    """单个工具的描述、配置与回调封装。"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        callback: Optional[Callable] = None,
        timeout: int = 30,
        enabled: bool = True,
        risk_level: str = "low",
        require_confirm: bool = False,
        admin_only: bool = False,
        tool_type: str = ToolType.AI,
        api_type: str = "generic",
        category: str = "general",
        required_config_keys: Optional[List[str]] = None,
        **extra,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.callback = callback
        self.timeout = timeout
        self.enabled = enabled
        self.risk_level = risk_level
        self.require_confirm = require_confirm
        self.admin_only = admin_only
        self.tool_type = tool_type if ToolType.is_valid(tool_type) else ToolType.AI
        self.api_type = api_type
        self.category = category
        self.required_config_keys = required_config_keys or []
        self.extra = extra

    def to_openai_schema(self) -> dict:
        """转换为 OpenAI Function Calling 兼容的 schema 字典。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.parameters.keys()),
                },
            },
        }


class ToolManager:
    """工具管理器：注册、配置注入、执行调度。"""

    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self._config = None
        self._tool_folder: Optional[str] = None
        self._tool_data_folder: Optional[str] = None
        self._tool_config: Dict[str, Any] = {"api_providers": {}}
        self._initialized = False

    def init_with_services(self, services):
        """从服务容器获取配置管理器，加载工具目录和配置文件。"""
        self._config = services.get("config")
        data_dir = self._config.get_data_dir()
        # 工具相关文件放在 工具/ 目录下
        self._tool_folder = os.path.join(data_dir, "工具")
        if not os.path.exists(self._tool_folder):
            os.makedirs(self._tool_folder, exist_ok=True)
        # 工具数据目录（工具产生的数据）
        self._tool_data_folder = os.path.join(self._tool_folder, "工具数据")
        if not os.path.exists(self._tool_data_folder):
            os.makedirs(self._tool_data_folder, exist_ok=True)

        self._load_from_folder()

        config_path = os.path.join(self._tool_folder, "tool_config.json")
        if not os.path.exists(config_path):
            self._create_default_tool_config()
        else:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self._tool_config = json.load(f)
            except Exception as e:
                logging.getLogger(__name__).error(
                    "读取工具配置文件失败: %s", e
                )

        self._initialized = True

    def _create_default_tool_config(self):
        """创建包含示例 API 提供者的默认配置文件。"""
        if not self._tool_folder:
            return
        config_path = os.path.join(self._tool_folder, "tool_config.json")
        example = {
            "api_providers": {
                "硅基流动": {
                    "地址": "https://api.siliconflow.cn/v1",
                    "令牌": "请填写你的API密钥",
                },
                "百度千帆": {
                    "地址": "https://qianfan.baidubce.com",
                    "令牌": "请填写你的百度千帆API密钥",
                },
                "Scrapling服务": {
                    "地址": "http://127.0.0.1:8090",
                    "令牌": "你的API密钥",
                },
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(example, f, ensure_ascii=False, indent=2)
        self._tool_config = example
        logging.getLogger(__name__).info(
            "已生成示例工具配置文件，请修改 %s", config_path
        )

    def add_provider(
        self, name: str, address: str, token: Optional[str] = None
    ) -> bool:
        """添加新的 API 提供者，若已存在则返回 False。"""
        providers = self._tool_config.setdefault("api_providers", {})
        if name in providers:
            logging.getLogger(__name__).warning(
                "API 提供者 '%s' 已存在", name
            )
            return False
        providers[name] = {"地址": address, "令牌": token}
        self._save_tool_config()
        return True

    def _save_tool_config(self):
        """保存工具配置文件。"""
        if not self._tool_folder:
            return
        config_path = os.path.join(self._tool_folder, "tool_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self._tool_config, f, ensure_ascii=False, indent=2)

    def _load_from_folder(self):
        """从工具文件夹递归加载所有 JSON 工具定义文件。

        支持旧版扁平结构和新的子目录结构:
          - 数据/工具/*.json                    （旧版：扁平）
          - 数据/工具/AI工具/*.json             （新版：AI 工具）
          - 数据/工具/管理工具/*.json           （新版：管理工具）
        """
        if not self._tool_folder:
            return
        for root, dirs, files in os.walk(self._tool_folder):
            for fname in files:
                if not fname.endswith(".json") or fname == "tool_config.json":
                    continue
                path = os.path.join(root, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    name = data.get("name")
                    if not name or name in self.tools:
                        continue
                    self._register_from_dict(data)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        "加载工具文件 %s 失败: %s", fname, e
                    )

    def _register_from_dict(self, data: dict):
        """从字典注册工具实例。"""
        name = data["name"]
        known_fields = {
            "name", "description", "parameters", "callback",
            "timeout", "enabled", "risk_level", "require_confirm",
            "admin_only", "tool_type", "api_type", "category",
            "required_config_keys",
        }
        self.tools[name] = ToolDefinition(
            name=name,
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            callback=data.get("callback"),
            timeout=data.get("timeout", 30),
            enabled=data.get("enabled", True),
            risk_level=data.get("risk_level", "low"),
            require_confirm=data.get("require_confirm", False),
            admin_only=data.get("admin_only", False),
            tool_type=data.get("tool_type", ToolType.AI),
            api_type=data.get("api_type", "generic"),
            category=data.get("category", "general"),
            required_config_keys=data.get("required_config_keys", []),
            **{k: v for k, v in data.items() if k not in known_fields},
        )

    def scan_directory(self, directory_path: str, tool_type: Optional[str] = None) -> int:
        """扫描指定目录下所有 JSON 文件，注册工具。

        支持递归子目录扫描（os.walk）。
        如果指定 tool_type，只加载匹配类型的工具；同时将目录信息
        写入工具的 extra['_source_dir'] 方便追溯。

        Args:
            directory_path: 要扫描的目录路径。
            tool_type: 过滤工具类型（ToolType.AI / ToolType.ADMIN），None 加载全部。

        Returns:
            成功注册的工具数量。
        """
        if not os.path.isdir(directory_path):
            logging.getLogger(__name__).warning(
                "工具扫描目录不存在: %s", directory_path
            )
            return 0

        loaded = 0
        for root, dirs, files in os.walk(directory_path):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(root, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        "读取工具 JSON 失败 %s: %s", path, e
                    )
                    continue

                name = data.get("name")
                if not name:
                    logging.getLogger(__name__).warning(
                        "工具 JSON 缺少 name 字段: %s", path
                    )
                    continue

                # 类型过滤
                declared_type = data.get("tool_type", ToolType.AI)
                if tool_type and ToolType.is_valid(tool_type):
                    if declared_type != tool_type:
                        continue

                if name in self.tools:
                    logging.getLogger(__name__).debug(
                        "工具 '%s' 已存在，跳过 %s", name, path
                    )
                    continue

                # 记录来源目录
                data.setdefault("_source_dir", os.path.relpath(root, directory_path))
                self._register_from_dict(data)
                loaded += 1
                logging.getLogger(__name__).info(
                    "已从目录加载工具: %s (类型=%s)", name, declared_type
                )

        return loaded

    def register_tool(self, tool_def: dict) -> bool:
        """注册一个工具（外部接口）。"""
        name = tool_def.get("name")
        if not name:
            logging.getLogger(__name__).warning("工具定义缺少 name")
            return False
        if name in self.tools:
            logging.getLogger(__name__).warning(
                "工具 %s 已存在，注册失败", name
            )
            return False
        self._register_from_dict(tool_def)
        return True

    def unregister_tool(self, name: str):
        """注销指定名称的工具。"""
        self.tools.pop(name, None)

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义。"""
        return self.tools.get(name)

    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        """根据分类获取工具列表。"""
        return [t for t in self.tools.values() if t.category == category]

    def get_ai_tools(self) -> List[ToolDefinition]:
        """获取所有 AI 类型工具（供 function calling 暴露给 LLM）。"""
        return [t for t in self.tools.values() if t.tool_type == ToolType.AI]

    def get_admin_tools(self) -> List[ToolDefinition]:
        """获取所有管理类型工具（供 AdminToolManager 工作流编排）。"""
        return [t for t in self.tools.values() if t.tool_type == ToolType.ADMIN]

    def get_all_tools(self) -> List[ToolDefinition]:
        """返回所有已注册的工具定义。"""
        return list(self.tools.values())

    def get_tools_schema(self, only_enabled: bool = True, tool_type: Optional[str] = None) -> list[dict]:
        """获取工具的 OpenAI schema 列表。

        Args:
            only_enabled: 只返回启用的工具。
            tool_type: 过滤工具类型（ToolType.AI / ToolType.ADMIN），None 返回全部。
        """
        if tool_type and ToolType.is_valid(tool_type):
            return [
                t.to_openai_schema()
                for t in self.tools.values()
                if (t.enabled or not only_enabled) and t.tool_type == tool_type
            ]
        return [
            t.to_openai_schema()
            for t in self.tools.values()
            if t.enabled or not only_enabled
        ]

    def set_enabled(self, name: str, enabled: bool):
        """设置工具的启用状态。"""
        tool = self.tools.get(name)
        if tool:
            tool.enabled = enabled

    def is_tool_available(
        self, name: str, context: dict = None
    ) -> bool:
        """检查工具是否可用（考虑启用状态和管理员限制）。"""
        tool = self.tools.get(name)
        if not tool or not tool.enabled:
            return False
        if tool.admin_only and (
            not context or not context.get("is_admin")
        ):
            return False
        return True

    def _get_provider_config(self, provider_name: str) -> dict:
        """获取指定 API 提供者的配置（地址、令牌）。"""
        providers = self._tool_config.get("api_providers", {})
        return providers.get(provider_name, {})

    async def execute(
        self, name: str, arguments: dict, context: dict = None
    ) -> str:
        """执行一个工具，并返回结果字符串。"""
        tool = self.tools.get(name)
        if not tool:
            return f"工具 '{name}' 不存在"
        if not tool.enabled:
            return f"工具 '{name}' 已禁用"
        if tool.admin_only and (
            not context or not context.get("is_admin")
        ):
            return "权限不足：该工具仅限管理员使用"

        tool_config = {}
        for provider in tool.required_config_keys:
            provider_cfg = self._get_provider_config(provider)
            if provider_cfg:
                tool_config[provider] = provider_cfg

        try:
            if tool.callback:
                try:
                    sig = inspect.signature(tool.callback)
                    params = list(sig.parameters.keys())
                except (ValueError, TypeError):
                    params = []
                if len(params) >= 3:
                    result = tool.callback(arguments, context, tool_config)
                else:
                    result = tool.callback(arguments, context)
                # 检测协程返回值：同步函数可能返回 coroutine 对象
                if asyncio.iscoroutinefunction(tool.callback):
                    return await asyncio.wait_for(
                        result, timeout=tool.timeout
                    )
                if asyncio.iscoroutine(result):
                    return await asyncio.wait_for(
                        asyncio.ensure_future(result), timeout=tool.timeout
                    )
                return result
            return await self._execute_default(tool, arguments)
        except asyncio.TimeoutError:
            return f"工具 '{name}' 执行超时 ({tool.timeout}秒)"
        except Exception as e:
            logging.getLogger(__name__).error(
                "工具 '%s' 执行异常: %s", name, e
            )
            return f"工具执行出错: {str(e)}"

    @staticmethod
    async def _execute_default(
        tool: ToolDefinition, args: dict
    ) -> str:
        """默认工具执行器（当没有回调时）。"""
        return "该工具未提供回调函数，无法执行"

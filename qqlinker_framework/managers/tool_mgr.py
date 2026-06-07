"""通用工具管理器 —— 管理工具注册、配置注入与执行"""
import asyncio
import inspect
import os
import json
import logging
from typing import Callable, Dict, List, Optional, Any


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
        """从工具文件夹加载所有 JSON 工具定义文件。"""
        if not self._tool_folder:
            return
        for fname in os.listdir(self._tool_folder):
            if not fname.endswith(".json") or fname == "tool_config.json":
                continue
            path = os.path.join(self._tool_folder, fname)
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
            api_type=data.get("api_type", "generic"),
            category=data.get("category", "general"),
            required_config_keys=data.get("required_config_keys", []),
            **{
                k: v
                for k, v in data.items()
                if k
                not in [
                    "name",
                    "description",
                    "parameters",
                    "callback",
                    "timeout",
                    "enabled",
                    "risk_level",
                    "require_confirm",
                    "admin_only",
                    "api_type",
                    "category",
                    "required_config_keys",
                ]
            },
        )

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

    def get_all_tools(self) -> List[ToolDefinition]:
        """返回所有已注册的工具定义。"""
        return list(self.tools.values())

    def get_tools_schema(self, only_enabled: bool = True) -> list[dict]:
        """获取所有工具的 OpenAI schema 列表。"""
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

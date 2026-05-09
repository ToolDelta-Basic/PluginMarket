# managers/tool_mgr.py
"""通用工具管理器 —— 管理工具注册、配置注入与执行"""
import asyncio
import os
import json
import logging
import inspect
from typing import Callable, Dict, List, Optional, Any

try:
    import aiohttp
except ImportError:
    aiohttp = None

class ToolDefinition:
    def __init__(self, name: str, description: str, parameters: dict,
                 callback: Optional[Callable] = None, timeout: int = 30,
                 enabled: bool = True, risk_level: str = "low",
                 require_confirm: bool = False, admin_only: bool = False,
                 api_type: str = "generic", category: str = "general",
                 required_config_keys: Optional[List[str]] = None, **extra):
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
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.parameters.keys())
                }
            }
        }

class ToolManager:
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self._config = None
        self._tool_folder: Optional[str] = None
        self._tool_config: Dict[str, Any] = {"api_providers": {}}
        self._initialized = False

    def init_with_services(self, services):
        self._config = services.get("config")
        self._config.register_section("工具系统", {
            "数据目录": ""
        })
        data_dir = self._config.get_data_dir() if hasattr(self._config, 'get_data_dir') else "."
        custom_dir = self._config.get("工具系统.数据目录", "")
        if custom_dir:
            self._tool_folder = custom_dir
        else:
            self._tool_folder = os.path.join(data_dir, "tools")
        if not os.path.exists(self._tool_folder):
            os.makedirs(self._tool_folder, exist_ok=True)
        self._load_from_folder()

        config_path = os.path.join(self._tool_folder, "tool_config.json")
        if not os.path.exists(config_path):
            self._create_default_tool_config(config_path)
        else:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self._tool_config = json.load(f)
            except Exception as e:
                logging.getLogger(__name__).error("读取工具配置文件失败: %s", e)

        self._initialized = True

    def _create_default_tool_config(self, config_path: str):
        example = {
            "api_providers": {
                "硅基流动": {
                    "地址": "https://api.siliconflow.cn/v1",
                    "令牌": "请填写你的API密钥"
                },
                "百度千帆": {
                    "地址": "https://qianfan.baidubce.com",
                    "令牌": "请填写你的百度千帆API密钥"
                },
                "网页抓取代理": {
                    "地址": "http://proxy:8080",
                    "令牌": None
                }
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(example, f, ensure_ascii=False, indent=2)
        self._tool_config = example
        logging.getLogger(__name__).info("已生成示例工具配置文件，请修改 %s", config_path)

    def add_provider(self, name: str, address: str, token: Optional[str] = None) -> bool:
        """添加新的 API 提供者，若已存在则返回 False"""
        providers = self._tool_config.setdefault("api_providers", {})
        if name in providers:
            logging.getLogger(__name__).warning("API 提供者 '%s' 已存在", name)
            return False
        providers[name] = {"地址": address, "令牌": token}
        self._save_tool_config()
        logging.getLogger(__name__).info("已添加 API 提供者: %s", name)
        return True

    def _save_tool_config(self):
        config_path = os.path.join(self._tool_folder, "tool_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self._tool_config, f, ensure_ascii=False, indent=2)

    def _load_from_folder(self):
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
                logging.getLogger(__name__).error("加载工具文件 %s 失败: %s", fname, e)

    def _register_from_dict(self, data: dict):
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
            **{k: v for k, v in data.items() if k not in [
                "name","description","parameters","callback","timeout","enabled",
                "risk_level","require_confirm","admin_only","api_type","category",
                "required_config_keys"
            ]}
        )

    def register_tool(self, tool_def: dict) -> bool:
        name = tool_def.get("name")
        if not name:
            logging.getLogger(__name__).warning("工具定义缺少 name")
            return False
        if name in self.tools:
            logging.getLogger(__name__).warning("工具 %s 已存在，注册失败", name)
            return False
        self._register_from_dict(tool_def)
        return True

    def unregister_tool(self, name: str):
        self.tools.pop(name, None)

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self.tools.get(name)

    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        return [t for t in self.tools.values() if t.category == category]

    def get_all_tools(self) -> List[ToolDefinition]:
        return list(self.tools.values())

    def get_tools_schema(self, only_enabled: bool = True) -> list[dict]:
        return [t.to_openai_schema() for t in self.tools.values()
                if t.enabled or not only_enabled]

    def set_enabled(self, name: str, enabled: bool):
        tool = self.tools.get(name)
        if tool:
            tool.enabled = enabled

    def is_tool_available(self, name: str, context: dict = None) -> bool:
        tool = self.tools.get(name)
        if not tool or not tool.enabled:
            return False
        if tool.admin_only and (not context or not context.get("is_admin")):
            return False
        return True

    def _get_provider_config(self, provider_name: str) -> dict:
        providers = self._tool_config.get("api_providers", {})
        return providers.get(provider_name, {})

    async def execute(self, name: str, arguments: dict, context: dict = None) -> str:
        tool = self.tools.get(name)
        if not tool:
            return f"工具 '{name}' 不存在"
        if not tool.enabled:
            return f"工具 '{name}' 已禁用"
        if tool.admin_only and (not context or not context.get("is_admin")):
            return "权限不足：该工具仅限管理员使用"

        tool_config = {}
        for provider in tool.required_config_keys:
            provider_cfg = self._get_provider_config(provider)
            if provider_cfg:
                tool_config[provider] = provider_cfg

        try:
            if tool.callback:
                sig = inspect.signature(tool.callback)
                params = list(sig.parameters.keys())
                if len(params) >= 3:
                    result = tool.callback(arguments, context, tool_config)
                else:
                    result = tool.callback(arguments, context)
                if asyncio.iscoroutinefunction(tool.callback) or asyncio.iscoroutine(result):
                    return await asyncio.wait_for(result, timeout=tool.timeout)
                else:
                    return result
            return await self._execute_by_api_type(tool, arguments)
        except asyncio.TimeoutError:
            return f"工具 '{name}' 执行超时 ({tool.timeout}秒)"
        except Exception as e:
            logging.getLogger(__name__).error("工具 '%s' 执行异常: %s", name, e)
            return f"工具执行出错: {str(e)}"

    async def _execute_by_api_type(self, tool: ToolDefinition, args: dict) -> str:
        return "该工具未提供回调函数，无法执行"
# modules/ai/tools/web_search.py
"""网络搜索工具（百度千帆）"""
import logging
from typing import Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None

def register_tools(tool_manager):
    """注册 web_search 工具。"""
    async def handler(params: dict, context: dict, config: dict) -> str:
        """执行网络搜索。

        Args:
            params: {"query": "搜索关键词"}
            context: 执行上下文。
            config: 提供者配置，需包含 "百度千帆"。

        Returns:
            搜索结果文本。
        """
        if aiohttp is None:
            return "aiohttp 未安装"
        query = params.get("query", "")
        if not query:
            return "请提供搜索关键词"
        provider = config.get("百度千帆", {})
        address = provider.get("地址", "")
        token = provider.get("令牌", "")
        if not token:
            return "百度千帆 API 密钥未配置"
        url = f"{address}/v2/ai_search/web_search"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "messages": [{"role": "user", "content": query}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": 5}]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=15) as resp:
                    if resp.status != 200:
                        return f"搜索失败: HTTP {resp.status}"
                    data = await resp.json()
                    refs = data.get("references", [])
                    if not refs:
                        return "未找到相关结果"
                    lines = ["搜索结果："]
                    for ref in refs[:3]:
                        title = ref.get("title", "")
                        content = ref.get("content", "")[:200]
                        lines.append(f"📄 {title}\n{content}")
                    return "\n\n".join(lines)
        except Exception as e:
            return f"搜索异常: {str(e)}"

    tool_manager.register_tool({
        "name": "web_search",
        "description": "网络搜索。参数：query (搜索关键词)",
        "api_type": "generic",
        "parameters": {"query": {"type": "string", "description": "搜索关键词"}},
        "callback": handler,
        "timeout": 15,
        "enabled": True,
        "category": "network",
        "required_config_keys": ["百度千帆"]
    })
    
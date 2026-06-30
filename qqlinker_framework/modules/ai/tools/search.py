# modules/ai/tools/web_search.py

try:
    import aiohttp
except ImportError:
    aiohttp = None

from .safety import (
    clean_search_results,
    filter_ip_patterns,
    sanitize_prompt,
)

_QUERY_MAX_LENGTH = 500


def register_tools(tool_manager, **kwargs):
    """注册 web_search 工具。"""

    async def handler(params: dict, _context: dict, config: dict) -> str:
        """执行网络搜索。"""
        if aiohttp is None:
            return "aiohttp 未安装"
        query = params.get("query", "")
        if not query:
            return "请提供搜索关键词"

        # ── 安全校验：长度限制 ──
        if len(query) > _QUERY_MAX_LENGTH:
            return f"搜索关键词过长（最大 {_QUERY_MAX_LENGTH} 字符）"

        # ── 安全校验：IP 地址模式过滤 ──
        if filter_ip_patterns(query):
            return "搜索关键词包含不支持的查询模式"

        # ── 输入清洗 ──
        query = sanitize_prompt(query, _QUERY_MAX_LENGTH)

        provider = config.get("百度千帆", {})
        address = provider.get("地址", "")
        token = provider.get("令牌", "")
        if not token:
            return "百度千帆 API 密钥未配置"
        url = f"{address}/v2/ai_search/web_search"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messages": [{"role": "user", "content": query}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": 5}]
        }
        try:
            async with aiohttp.ClientSession() as session, \
                    session.post(
                        url, json=payload, headers=headers, timeout=15
                    ) as resp:
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
                    # ── 内容清洗：移除恶意链接模式 ──
                    content = clean_search_results(content)
                    lines.append(f"📄 {title}\n{content}")
                result = "\n\n".join(lines)
                # 整体清洗一次
                return clean_search_results(result)
        except Exception as e:
            return f"搜索异常: {str(e)}"

    tool_manager.register_tool({
        "name": "web_search",
        "description": "网络搜索。参数：query (搜索关键词)",
        "api_type": "generic",
        "parameters": {
            "query": {"type": "string", "description": "搜索关键词"}
        },
        "callback": handler,
        "timeout": 15,
        "enabled": True,
        "category": "network",
        "required_config_keys": ["百度千帆"],
    })

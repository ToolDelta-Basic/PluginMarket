# modules/ai/tools/rerank.py
"""文档重排序工具（硅基流动）"""

try:
    import aiohttp
except ImportError:
    aiohttp = None


def register_tools(tool_manager):
    """注册 rerank_documents 工具。"""

    async def handler(params: dict, _context: dict, config: dict) -> str:
        """调用硅基流动 Rerank API，对文档进行相关性排序。"""
        if aiohttp is None:
            return "aiohttp 未安装"
        query = params.get("query", "")
        documents_str = params.get("documents", "")
        documents = [d.strip() for d in documents_str.split("||") if d.strip()]
        if not query or not documents:
            return "请提供查询文本和候选文档（用 || 分隔）"
        provider = config.get("硅基流动", {})
        address = provider.get("地址", "")
        token = provider.get("令牌", "")
        if not token:
            return "硅基流动 API 密钥未配置"
        model = "BAAI/bge-reranker-v2-m3"
        url = f"{address}/rerank"
        payload = {
            "model": model,
            "query": query,
            "documents": documents,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session, \
                    session.post(
                        url, json=payload,
                        headers=headers, timeout=30
                    ) as resp:
                if resp.status != 200:
                    return f"重排序失败: {resp.status}"
                data = await resp.json()
                results = data.get("results", [])
                if not results:
                    return "无结果"
                sorted_results = sorted(
                    [r for r in results if r is not None],
                    key=lambda x: x.get("relevance_score", 0),
                    reverse=True
                )
                lines = ["重排序结果："]
                for i, r in enumerate(sorted_results, 1):
                    doc = r.get("document", {})
                    if isinstance(doc, dict):
                        text = doc.get("text", "")[:100]
                    else:
                        text = str(doc)[:100]
                    lines.append(f"{i}. {text}...")
                return "\n".join(lines)
        except Exception as e:
            return f"重排序异常: {str(e)}"

    tool_manager.register_tool({
        "name": "rerank_documents",
        "description": (
            "对候选文档重排序。参数：query (查询文本), "
            "documents (候选列表，以 || 分隔)"
        ),
        "api_type": "generic",
        "parameters": {
            "query": {"type": "string", "description": "查询文本"},
            "documents": {
                "type": "string",
                "description": "候选文档，用 || 分隔",
            },
        },
        "callback": handler,
        "timeout": 30,
        "enabled": True,
        "category": "ai",
        "required_config_keys": ["硅基流动"],
    })

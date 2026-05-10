# modules/ai/tools/web_scraper.py
"""网页抓取工具 —— 通过 Scrapling API 获取网页原文"""
import logging
from typing import Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None

async def _fetch_via_scrapling(url: str, address: str, token: str, timeout: int) -> str:
    """通过 Scrapling API 抓取网页内容。

    Args:
        url: 目标网页地址。
        address: API 地址。
        token: API 令牌。
        timeout: 超时秒数。

    Returns:
        抓取结果文本。
    """
    if aiohttp is None:
        return "错误：aiohttp 未安装，无法抓取网页"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"url": url}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{address}/fetch",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status == 401:
                    return "抓取失败：API 密钥无效"
                if resp.status == 402:
                    return "抓取失败：账户余额不足，请签到或充值"
                if resp.status != 200:
                    data = await resp.text()
                    return f"抓取失败：HTTP {resp.status} - {data[:200]}"
                
                data = await resp.json()
                content = data.get("content", "")
                title = data.get("title", "")
                if not content:
                    return f"抓取成功但内容为空（标题：{title}）"
                
                if len(content) > 5000:
                    content = content[:5000] + "…（内容已截断）"
                
                if title:
                    return f"网页标题：{title}\n\n{content}"
                return content

    except asyncio.TimeoutError:
        return f"请求超时（{timeout}秒）"
    except aiohttp.ClientError as e:
        return f"网络错误：{str(e)}"
    except Exception as e:
        logging.getLogger(__name__).error("网页抓取异常: %s", e)
        return f"抓取异常：{str(e)}"

def register_tools(tool_manager):
    """注册 web_scraper 工具。"""
    async def handler(params: dict, context: dict, config: dict) -> str:
        """执行网页抓取。

        Args:
            params: {"url": "...", "timeout": 15}
            context: 执行上下文。
            config: 提供者配置，需包含 "Scrapling服务"。

        Returns:
            抓取结果文本。
        """
        url = params.get("url", "")
        if not url:
            return "请提供要抓取的网页 URL"
        timeout = params.get("timeout", 15)
        
        provider = config.get("Scrapling服务", {})
        address = provider.get("地址", "")
        token = provider.get("令牌", "")
        if not address or not token:
            return "Scrapling 服务未配置，请在 tool_config.json 中填写地址和令牌"

        return await _fetch_via_scrapling(url, address, token, timeout)

    tool_manager.register_tool({
        "name": "web_scraper",
        "description": "抓取指定网页的原始内容。参数：url (网页地址), timeout (可选超时秒数)",
        "api_type": "generic",
        "parameters": {
            "url": {"type": "string", "description": "要抓取的网页完整URL"},
            "timeout": {"type": "integer", "description": "超时秒数（默认15）"}
        },
        "callback": handler,
        "timeout": 25,
        "enabled": True,
        "category": "network",
        "required_config_keys": ["Scrapling服务"]
    })
    
# modules/ai/tools/web_scraper.py
"""网页抓取工具 —— 通过 Scrapling API 获取网页原文

安全特性:
  - URL SSRF 防护（内网拒绝、协议检查、长度限制）
  - 请求超时强制上限（10 秒）
  - 响应体大小限制（2 MB）
"""
import asyncio
import logging

from .safety import validate_url

try:
    import aiohttp
except ImportError:
    aiohttp = None

# ── 安全限制 ──
_MAX_TIMEOUT = 10            # 请求超时上限（秒）
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 最大响应体大小（2 MB）


async def _fetch_via_scrapling(url: str, address: str, token: str,
                               timeout: int) -> str:
    """通过 Scrapling API 抓取网页内容。"""
    if aiohttp is None:
        return "错误：aiohttp 未安装，无法抓取网页"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"url": url}

    try:
        async with aiohttp.ClientSession() as session, \
                session.post(
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

            # 读取响应体，限制大小（2 MB）
            raw_data = await resp.read()
            if len(raw_data) > _MAX_RESPONSE_BYTES:
                raw_data = raw_data[:_MAX_RESPONSE_BYTES]
                logging.getLogger(__name__).warning(
                    "响应体超过 2MB 限制，已截断"
                )
            data_decoded = raw_data.decode("utf-8", errors="replace")
            import json
            data = json.loads(data_decoded)
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


def register_tools(tool_manager, **kwargs):
    """注册 web_scraper 工具。"""

    async def handler(params: dict, _context: dict, config: dict) -> str:
        """执行网页抓取。"""
        url = params.get("url", "")
        if not url:
            return "请提供要抓取的网页 URL"

        # ── SSRF 防护：URL 验证 ──
        valid, err = validate_url(url)
        if not valid:
            return f"URL 不安全：{err}"

        # 超时限制：不允许超过安全上限
        timeout = params.get("timeout", _MAX_TIMEOUT)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = _MAX_TIMEOUT
        if timeout > _MAX_TIMEOUT:
            timeout = _MAX_TIMEOUT

        provider = config.get("Scrapling服务", {})
        address = provider.get("地址", "")
        token = provider.get("令牌", "")
        if not address or not token:
            return "Scrapling 服务未配置，请在 tool_config.json 中填写地址和令牌"

        return await _fetch_via_scrapling(url, address, token, timeout)

    tool_manager.register_tool({
        "name": "web_scraper",
        "description": (
            "抓取指定网页的原始内容。参数：url (网页地址), "
            "timeout (可选超时秒数)"
        ),
        "api_type": "generic",
        "parameters": {
            "url": {"type": "string", "description": "要抓取的网页完整URL"},
            "timeout": {"type": "integer", "description": "超时秒数（默认10）"}
        },
        "callback": handler,
        "timeout": _MAX_TIMEOUT + 5,
        "enabled": True,
        "category": "network",
        "required_config_keys": ["Scrapling服务"],
    })

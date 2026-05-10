# modules/ai/tools/generate_image.py
"""图像生成工具（硅基流动）—— 返回 [IMAGE:url] 供 AI 核心解析发送"""

try:
    import aiohttp
except ImportError:
    aiohttp = None


def register_tools(tool_manager):
    """注册 generate_image 工具。"""

    async def handler(params: dict, _context: dict, config: dict) -> str:
        if aiohttp is None:
            return "aiohttp 未安装"
        prompt = params.get("prompt", "")
        if not prompt:
            return "请提供图片描述"
        provider = config.get("硅基流动", {})
        address = provider.get("地址", "")
        token = provider.get("令牌", "")
        if not token:
            return "硅基流动 API 密钥未配置"
        model = "Kwai-Kolors/Kolors"
        url = f"{address}/images/generations"
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session, \
                    session.post(
                        url, json=payload,
                        headers=headers, timeout=60
                    ) as resp:
                if resp.status != 200:
                    return f"图像生成失败: {resp.status}"
                data = await resp.json()
                if "data" in data and data["data"]:
                    img_url = data["data"][0].get("url", "")
                    if img_url:
                        return f"[IMAGE:{img_url}] 图片生成成功！"
                    return "图像生成无结果"
                return "图像生成无结果"
        except Exception as e:
            return f"图像生成异常: {str(e)}"

    tool_manager.register_tool({
        "name": "generate_image",
        "description": "根据描述生成图片。参数：prompt (字符串)",
        "api_type": "generic",
        "parameters": {
            "prompt": {"type": "string", "description": "图片描述"}
        },
        "callback": handler,
        "timeout": 60,
        "enabled": True,
        "category": "ai",
        "required_config_keys": ["硅基流动"],
    })

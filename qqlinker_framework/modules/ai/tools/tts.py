# modules/ai/tools/tts.py
"""文本转语音工具（硅基流动）"""
import base64

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    aiohttp = None
    HAS_AIOHTTP = False


def register_tools(tool_manager):
    """注册 siliconflow_tts 工具。"""

    async def handler(params: dict, _context: dict, config: dict) -> str:
        if not HAS_AIOHTTP:
            return ("aiohttp 依赖未安装，请执行 'qqdeps install' 安装，"
                    "或手动 pip install aiohttp")
        text = params.get("text", "")
        if not text:
            return "请提供文本内容"
        provider = config.get("硅基流动", {})
        address = provider.get("地址", "")
        token = provider.get("令牌", "")
        if not token:
            return "硅基流动 API 密钥未配置"
        model = "IndexTeam/IndexTTS-2"
        voice = "IndexTeam/IndexTTS-2:anna"
        url = f"{address}/audio/speech"
        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": "mp3"
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=30
            ) as resp:
                if resp.status != 200:
                    return f"语音生成失败: {resp.status}"
                audio_data = await resp.read()
                return f"base64://{base64.b64encode(audio_data).decode('utf-8')}"

    tool_manager.register_tool({
        "name": "siliconflow_tts",
        "description": "文本转语音。参数：text (要朗读的文本)",
        "api_type": "generic",
        "parameters": {"text": {"type": "string", "description": "文本内容"}},
        "callback": handler,
        "timeout": 30,
        "enabled": HAS_AIOHTTP,
        "category": "ai",
        "required_config_keys": ["硅基流动"],
    })

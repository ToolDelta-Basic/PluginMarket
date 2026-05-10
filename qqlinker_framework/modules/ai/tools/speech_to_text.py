# modules/ai/tools/speech_to_text.py
"""语音识别工具（硅基流动）"""

try:
    import aiohttp
except ImportError:
    aiohttp = None


def register_tools(tool_manager):
    """注册 speech_to_text 工具。"""

    async def handler(params: dict, _context: dict, config: dict) -> str:
        """调用硅基流动 ASR API，识别音频文件。"""
        if aiohttp is None:
            return "aiohttp 未安装"
        audio_url = params.get("url", "")
        if not audio_url:
            return "请提供音频文件 URL"
        provider = config.get("硅基流动", {})
        address = provider.get("地址", "")
        token = provider.get("令牌", "")
        if not token:
            return "硅基流动 API 密钥未配置"
        model = "TeleAI/TeleSpeechASR"
        transcribe_url = f"{address}/audio/transcriptions"
        headers_token = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url, timeout=30) as audio_resp:
                if audio_resp.status != 200:
                    return f"下载音频失败: {audio_resp.status}"
                audio_data = await audio_resp.read()
            form = aiohttp.FormData()
            form.add_field(
                "file", audio_data, filename="audio.wav",
                content_type="audio/wav"
            )
            form.add_field("model", model)
            async with session.post(
                transcribe_url, data=form,
                headers=headers_token, timeout=30
            ) as resp:
                if resp.status != 200:
                    return f"语音识别失败: {resp.status}"
                data = await resp.json()
                return data.get("text", "无识别结果")

    tool_manager.register_tool({
        "name": "speech_to_text",
        "description": "语音识别。参数：url (音频文件链接)",
        "api_type": "generic",
        "parameters": {
            "url": {"type": "string", "description": "音频文件URL"}
        },
        "callback": handler,
        "timeout": 30,
        "enabled": True,
        "category": "ai",
        "required_config_keys": ["硅基流动"],
    })

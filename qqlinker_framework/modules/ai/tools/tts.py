# modules/ai/tools/tts.py
"""文本转语音工具（硅基流动）

安全特性:
  - text 长度限制 500 字符
  - 发送前安全审核检查（audit.check_message）
"""
import base64
import logging

from .safety import sanitize_prompt

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    aiohttp = None
    HAS_AIOHTTP = False

_TEXT_MAX_LENGTH = 500
_logger = logging.getLogger(__name__)


def register_tools(tool_manager):
    """注册 siliconflow_tts 工具。"""

    async def handler(params: dict, _context: dict, config: dict) -> str:
        """调用硅基流动 TTS API，返回 base64 音频。"""
        if not HAS_AIOHTTP:
            return ("aiohttp 依赖未安装，请执行 'qqdeps install' 安装，"
                    "或手动 pip install aiohttp")
        text = params.get("text", "")
        if not text:
            return "请提供文本内容"

        # ── 安全校验：长度限制 ──
        if len(text) > _TEXT_MAX_LENGTH:
            return f"文本过长（最大 {_TEXT_MAX_LENGTH} 字符）"

        # ── 输入清洗 ──
        text = sanitize_prompt(text, _TEXT_MAX_LENGTH)

        # ── 安全审核：调用 audit.check_message（不可用则跳过）──
        try:
            services = tool_manager._root_services
            audit = services.get("audit")
            if audit:
                audit_result = await audit.check_message(
                    0, 0, f"[TTS请求] {text}"
                )
                if audit_result:
                    _logger.warning(
                        "TTS 被安全审核拦截: %s", audit_result
                    )
                    return "文本包含不安全内容，已被拦截"
        except Exception:
            pass

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
        async with aiohttp.ClientSession() as session, \
                session.post(
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

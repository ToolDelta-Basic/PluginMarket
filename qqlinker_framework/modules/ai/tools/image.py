# modules/ai/tools/generate_image.py
"""图像生成工具（硅基流动）—— 返回 [IMAGE:url] 供 AI 核心解析发送

安全特性:
  - prompt 长度限制 500 字符
  - 发送前安全审核检查（audit.check_message）
  - 返回图片 URL 受信任域名验证
"""
import logging

from .safety import is_trusted_image_host, sanitize_prompt

try:
    import aiohttp
except ImportError:
    aiohttp = None

_PROMPT_MAX_LENGTH = 500
_logger = logging.getLogger(__name__)


def register_tools(tool_manager):
    """注册 generate_image 工具。"""

    async def handler(params: dict, _context: dict, config: dict) -> str:
        """调用硅基流动生成图片，返回 IMAGE 标签。"""
        if aiohttp is None:
            return "aiohttp 未安装"
        prompt = params.get("prompt", "")
        if not prompt:
            return "请提供图片描述"

        # ── 安全校验：长度限制 ──
        if len(prompt) > _PROMPT_MAX_LENGTH:
            return f"图片描述过长（最大 {_PROMPT_MAX_LENGTH} 字符）"

        # ── 输入清洗 ──
        prompt = sanitize_prompt(prompt, _PROMPT_MAX_LENGTH)

        # ── 安全审核：调用 audit.check_message（不可用则跳过）──
        try:
            from qqlinker_framework.core.context import get_services
            services = tool_manager._root_services
            audit = services.get("audit")
            if audit:
                audit_result = await audit.check_message(
                    0, 0, f"[图片生成请求] {prompt}"
                )
                if audit_result:
                    _logger.warning(
                        "图片生成被安全审核拦截: %s", audit_result
                    )
                    return "图片描述包含不安全内容，已被拦截"
        except Exception:
            # audit 不可用或调用失败时不崩溃，继续执行
            pass

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
                        # ── URL 验证：检查是否为受信任域名 ──
                        if not is_trusted_image_host(img_url):
                            _logger.warning(
                                "图片 URL 来自非受信任域名: %s", img_url
                            )
                            return "生成的图片来自不可信来源，已拦截"
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

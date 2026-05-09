# modules/ai/llm_client.py
import json
import asyncio
import logging
from typing import Optional, Callable, List, Dict, Any

try:
    import aiohttp
except ImportError:
    aiohttp = None

class LLMClientFactory:
    def __init__(self, config):
        self.config = config
        self.api_base = config.get("AI助手.API地址", "https://api.siliconflow.cn/v1")
        self.api_key = config.get("AI助手.API密钥", "")
        self.model = config.get("AI助手.模型", "deepseek-chat")

    async def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None,
                   max_rounds: int = 5, tool_executor: Optional[Callable] = None) -> str:
        if not self.api_key:
            return "AI API 密钥未配置"
        if not aiohttp:
            return "aiohttp 依赖未安装"

        current_messages = messages.copy()
        for _ in range(max_rounds):
            payload = {
                "model": self.model,
                "messages": current_messages,
                "temperature": 0.7,
                "max_tokens": 1024
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.api_base}/chat/completions",
                        json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            logging.getLogger(__name__).error("LLM API 错误 %d: %s", resp.status, text)
                            return f"AI 请求失败: {resp.status}"
                        data = await resp.json()

                choice = data["choices"][0]
                message = choice["message"]

                # 处理工具调用
                if "tool_calls" in message and message["tool_calls"]:
                    current_messages.append(message)
                    for tc in message["tool_calls"]:
                        func = tc["function"]
                        name = func["name"]
                        try:
                            args = json.loads(func["arguments"])
                        except:
                            args = {}
                        if tool_executor:
                            try:
                                # 关键修复：确保 tool_executor 返回协程时正确 await
                                result = tool_executor(name, args)
                                if asyncio.iscoroutine(result):
                                    tool_result = await result
                                else:
                                    tool_result = result
                            except Exception as e:
                                tool_result = f"工具执行失败: {str(e)}"
                        else:
                            tool_result = "工具未实现"
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": str(tool_result)
                        })
                    continue

                # 正常文本回复
                return message.get("content", "")

            except asyncio.TimeoutError:
                return "AI 请求超时"
            except Exception as e:
                logging.getLogger(__name__).error("LLM 异常: %s", e)
                return f"AI 服务异常: {str(e)}"

        return "工具调用次数过多"
"""AI 主动发言引擎

ProactiveSpeaker 类：定时 asyncio 任务，监测群内消息活跃度，
在满足条件时自动调用 LLM 生成发言。
"""

import asyncio
import logging
import random
import time
from typing import Callable, Dict, List

_logger = logging.getLogger(__name__)


class ProactiveSpeaker:
    """主动发言引擎。

    机制：
      - 定时 asyncio 任务（默认 30s 间隔）
      - 检查群内自上次 AI 回复后的新消息数
      - 超过阈值（默认 10 条）且满足概率（默认 0.3）→ 调用 LLM 生成发言
      - 发言后进入冷却（默认 60s）
      - 开启时记录 warn 日志提示会增加 API 消耗

    Attributes:
        interval: 轮询间隔（秒）。
        threshold: 触发需要的累计新消息数。
        cooldown: 发言后冷却时间（秒）。
        probability: 在满足阈值时发言的概率 (0.0 ~ 1.0)。
    """

    def __init__(
        self,
        interval: float = 30.0,
        threshold: int = 10,
        cooldown: float = 60.0,
        probability: float = 0.3,
        *,
        get_memory: Callable[[int], List[Dict]] = None,
        add_memory: Callable[[int, Dict], None] = None,
        llm_chat: Callable[[List[Dict]], str] = None,
        send_group: Callable[[int, str], None] = None,
    ) -> None:
        self._interval = interval
        self._threshold = threshold
        self._cooldown = cooldown
        self._probability = probability

        # 回调节点
        self._get_memory = get_memory
        self._add_memory = add_memory
        self._llm_chat = llm_chat
        self._send_group = send_group

        # 状态
        self._msg_counters: Dict[int, int] = {}       # group_id → 新消息计数
        self._last_ai_reply: Dict[int, float] = {}    # group_id → 上次 AI 发言时间戳
        self._lock = asyncio.Lock()
        self._running = False

    def notify_message(self, group_id: int) -> None:
        """通知有新消息（由 AICore.on_group_message 调用）。"""
        self._msg_counters[group_id] = self._msg_counters.get(group_id, 0) + 1

    async def run(self) -> None:
        """主循环：每隔 interval 秒检查一次。"""
        self._running = True
        _logger.info(
            "主动发言引擎已启动 (间隔=%ss, 阈值=%d, 冷却=%ss, 概率=%.2f)",
            self._interval, self._threshold, self._cooldown, self._probability,
        )

        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _logger.error("主动发言引擎异常: %s", e)

    async def _tick(self) -> None:
        """单次检查：遍历所有活跃群，检查触发条件。"""
        async with self._lock:
            groups = list(self._msg_counters.keys())

        now = time.time()
        for group_id in groups:
            count = self._msg_counters.get(group_id, 0)
            if count < self._threshold:
                continue

            last_reply = self._last_ai_reply.get(group_id, 0)
            if now - last_reply < self._cooldown:
                continue

            # 概率判定
            if random.random() > self._probability:
                continue

            # 触发！
            _logger.info(
                "主动发言触发: 群=%d, 新消息=%d, 距离上次发言=%ds",
                group_id, count, int(now - last_reply),
            )

            # 重置计数器
            async with self._lock:
                self._msg_counters[group_id] = 0
                self._last_ai_reply[group_id] = now

            try:
                await self._speak(group_id)
            except Exception as e:
                _logger.error("主动发言失败 (群=%d): %s", group_id, e)

    async def _speak(self, group_id: int) -> None:
        """生成并发送一次主动发言。"""
        if not self._get_memory or not self._llm_chat or not self._send_group:
            _logger.warning("主动发言回调节点未完整注入，跳过")
            return

        # 获取最近对话记忆
        memory = await self._get_memory(group_id)
        if not memory:
            # 没有上下文，不凭空发言
            _logger.debug("群 %d 无对话记忆，跳过主动发言", group_id)
            return

        # 构建 prompt
        system_msg = {
            "role": "system",
            "content": (
                "你是一个活跃的群聊成员。请根据最近的群聊对话，"
                "用自然、友好的方式插一句话参与讨论。"
                "发言要简短（不超过100字），不要显得突兀或机器人。"
                "用中文发言。"
                "只输出你要发送的消息文本，不要包含任何前缀或说明。"
            ),
        }
        messages = [system_msg] + memory[-20:]

        # 调用 LLM
        response = await self._llm_chat(messages)
        if not response or not response.strip():
            return

        text = response.strip()

        # 记录到群记忆
        if self._add_memory:
            await self._add_memory(group_id, {"role": "assistant", "content": text})

        # 发送
        await self._send_group(group_id, text)
        _logger.info("主动发言已发送: 群=%d, 内容=%s", group_id, text[:80])

    def stop(self) -> None:
        """停止引擎。"""
        self._running = False

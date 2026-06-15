"""MessageBusLibrary — 消息发送 + 命令注册。

消息发送通过令牌桶队列削峰后由 adapter 发出。
命令注册提供简单的 trigger → callback 字典存储。
"""

import asyncio
import logging
import time

from ..core.channel import Library

logger = logging.getLogger(__name__)


# ── 令牌桶限流器 ──────────────────────────────────────────────

class _RateLimiter:
    """令牌桶限流器。

    Args:
        rate: 每 per_seconds 秒允许的消息数，默认 20。
        per_seconds: 时间窗口（秒），默认 60。
    """

    def __init__(self, rate: int = 20, per_seconds: float = 60.0) -> None:
        self._rate = rate
        self._interval = per_seconds / rate
        self._tokens = float(rate)
        self._last = time.monotonic()

    def acquire(self) -> bool:
        """尝试获取一个令牌。

        Returns:
            True 如果成功获取令牌（允许发送），否则 False。
        """
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(float(self._rate), self._tokens + elapsed / self._interval)
        self._last = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


# ── 异步消息队列 ──────────────────────────────────────────────

class _MessageQueue:
    """异步消息队列，令牌桶削峰后通过 adapter 发出。

    Args:
        adapter: 实现了 send_group_msg / send_private_msg 的对象。
        limiter: 令牌桶限流器实例。
    """

    def __init__(self, adapter, limiter: _RateLimiter) -> None:
        self._adapter = adapter
        self._limiter = limiter
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动队列消费协程。"""
        self._running = True
        self._task = asyncio.create_task(self._drain())

    async def stop(self) -> None:
        """停止队列消费。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def send_group(self, group_id: int, message: str) -> None:
        """发送群消息（入队）。

        Args:
            group_id: 目标群号。
            message: 消息文本。
        """
        await self._queue.put(("group", group_id, message))

    async def send_private(self, user_id: int, message: str) -> None:
        """发送私聊消息（入队）。

        Args:
            user_id: 目标用户 QQ 号。
            message: 消息文本。
        """
        await self._queue.put(("private", user_id, message))

    async def _drain(self) -> None:
        """后台协程：从队列取出消息，令牌桶限流后通过 adapter 发送。"""
        while self._running:
            try:
                msg_type, target, text = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                # 等令牌
                while not self._limiter.acquire():
                    await asyncio.sleep(0.1)
                # 发送
                if msg_type == "group":
                    self._adapter.send_group_msg(target, text)
                else:
                    self._adapter.send_private_msg(target, text)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("消息发送失败")


# ── 命令注册表 ────────────────────────────────────────────────

class _CommandRegistry:
    """命令注册表：trigger → {callback, description, ...} 的简单字典。

    不做路由匹配——由其他库负责。
    """

    def __init__(self) -> None:
        self._commands: dict[str, dict] = {}

    def register(self, trigger: str, callback, **kwargs) -> None:
        """注册一个命令。

        Args:
            trigger: 命令触发器字符串（如 "/help"）。
            callback: 可调用对象。
            **kwargs: 额外元数据（description, op_only, cooldown, min_uid, plugin 等）。
        """
        entry = {"trigger": trigger, "callback": callback}
        entry.update(kwargs)
        self._commands[trigger] = entry

    def unregister(self, trigger: str) -> None:
        """注销一个命令。

        Args:
            trigger: 命令触发器字符串。
        """
        self._commands.pop(trigger, None)

    def find(self, trigger: str) -> dict | None:
        """按 trigger 查找命令。

        Args:
            trigger: 命令触发器字符串。

        Returns:
            命令条目字典，找不到返回 None。
        """
        return self._commands.get(trigger)

    def list_all(self) -> list[dict]:
        """列出所有已注册命令。

        Returns:
            命令条目列表。
        """
        return list(self._commands.values())


# ── Library 入口 ──────────────────────────────────────────────

class MessageBusLibrary(Library):
    """消息总线库。

    挂载时注册两个服务：
    - ``command`` → _CommandRegistry 实例
    - ``message`` → _MessageQueue 实例（需要 adapter 可用）
    """

    name = "message_bus"
    version = "1.0.0"
    dependencies = ["core"]

    async def mount(self) -> None:
        adapter = self.services.try_get("adapter")

        # 命令注册表（总是可用）
        cmd_registry = _CommandRegistry()
        self.services.register("command", cmd_registry)
        self.commands = cmd_registry

        # 消息队列（需要 adapter）
        if adapter is not None:
            limiter = _RateLimiter(rate=20, per_seconds=60.0)
            queue = _MessageQueue(adapter, limiter)
            await queue.start()
            self.services.register("message", queue)
            self.messages = queue
            self._queue = queue
        else:
            logger.warning("adapter 不可用，消息队列未启动")

    async def unmount(self) -> None:
        if hasattr(self, '_queue'):
            await self._queue.stop()

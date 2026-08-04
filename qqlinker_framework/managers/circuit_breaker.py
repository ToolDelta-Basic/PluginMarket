from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass
from typing import Optional

_log = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    """熔断器状态。"""
    CLOSED = "closed"          # 正常
    OPEN = "open"              # 熔断
    HALF_OPEN = "half_open"    # 探测中


@dataclass
class CircuitBreakerConfig:
    """熔断器配置。

    属性:
        failure_threshold: 连续失败多少次后触发熔断
        cooldown_seconds: 熔断后冷却多少秒进入半开探测
        half_open_probes: 半开状态允许通过的探测请求数
        success_threshold: 半开状态下多少次成功后恢复为 CLOSED
    """
    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    half_open_probes: int = 2
    success_threshold: int = 2


class CircuitBreaker:
    """熔断器实现 — 连续失败 N 次后打开，冷却后半开探测。

    设计要点:
      - 异步安全：所有状态变更通过 asyncio.Lock 保护
      - 超时感知：只有连接超时 / 服务器错误才计入失败；
              客户端错误 (4xx) 不计入（是调用方的问题）
      - 自动恢复：状态机透明自动切换

    使用示例:
        breaker = CircuitBreaker()
        async with breaker:
            result = await some_http_call()
            # 成功：breaker 自动记录成功
    """

    def __init__(
        self,
        config: Optional[CircuitBreakerConfig] = None,
        name: str = "",
    ):
        """
        Args:
            config: 熔断器配置，None 使用默认值
            name: 熔断器名称（用于日志标识）
        """
        self.config = config or CircuitBreakerConfig()
        self.name = name or "unnamed"
        self._state = CircuitState.CLOSED
        self._failures: int = 0
        self._successes: int = 0
        self._opened_at: float = 0.0
        self._last_failure_time: float = 0.0
        self._last_failure_reason: str = ""
        self._lock = asyncio.Lock()

    # ── 状态查询 ────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """当前熔断器状态。"""
        return self._state

    @property
    def is_open(self) -> bool:
        """熔断器是否处于 OPEN（阻挡请求）。"""
        return self._state == CircuitState.OPEN

    @property
    def failures(self) -> int:
        """连续失败计数。"""
        return self._failures

    @property
    def opened_seconds_ago(self) -> Optional[float]:
        """OPEN 状态已持续秒数，非 OPEN 时返回 None。"""
        if self._state != CircuitState.OPEN:
            return None
        return time.time() - self._opened_at

    # ── 状态转换 ────────────────────────────────────────────

    async def _transition_to_open(self, reason: str = "") -> None:
        """转换到 OPEN 状态。"""
        self._state = CircuitState.OPEN
        self._opened_at = time.time()
        self._successes = 0
        _log.warning(
            "熔断器 '%s' → OPEN (失败=%d, 原因=%s, 冷却=%ds)",
            self.name, self._failures, reason, self.config.cooldown_seconds,
        )

    async def _transition_to_half_open(self) -> None:
        """转换到 HALF_OPEN 状态。"""
        self._state = CircuitState.HALF_OPEN
        self._failures = 0
        self._successes = 0
        _log.info("熔断器 '%s' → HALF_OPEN (探测中)", self.name)

    async def _transition_to_closed(self) -> None:
        """转换到 CLOSED 状态。"""
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        _log.info("熔断器 '%s' → CLOSED (已恢复)", self.name)

    # ── 入口点 ──────────────────────────────────────────────

    async def before_request(self) -> Optional[str]:
        """请求前检查：如果 OPEN 则返回拒绝原因字符串，否则放行。

        自动处理: OPEN → 冷却到期 → HALF_OPEN 探测

        Returns:
            None 表示放行；非空字符串表示拒绝原因。
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.time() - self._opened_at
                if elapsed >= self.config.cooldown_seconds:
                    await self._transition_to_half_open()
                else:
                    remaining = self.config.cooldown_seconds - elapsed
                    return (
                        f"熔断器 '{self.name}' 已打开 "
                        f"(剩余冷却 {remaining:.0f}s): {self._last_failure_reason}"
                    )
        return None

    async def on_success(self) -> None:
        """记录一次成功。HALF_OPEN 时足够成功后恢复 CLOSED。"""
        async with self._lock:
            # CLOSED 状态：重置失败计数，建立信用
            if self._state == CircuitState.CLOSED:
                self._failures = 0
                return

            # HALF_OPEN 状态：累计成功
            if self._state == CircuitState.HALF_OPEN:
                self._successes += 1
                if self._successes >= self.config.success_threshold:
                    await self._transition_to_closed()

    async def on_failure(self, reason: str = "", is_retryable: bool = True) -> None:
        """记录一次失败。只对可重试错误触发熔断。

        Args:
            reason: 失败原因描述（日志用）
            is_retryable: 是否为可重试错误（连接超时/5xx）。
                         客户端错误 (4xx) 传入 False 不触发熔断。
        """
        if not is_retryable:
            return

        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            self._last_failure_reason = reason

            if self._state == CircuitState.HALF_OPEN:
                # 半开探测失败 → 立即回 OPEN
                _log.warning(
                    "熔断器 '%s' HALF_OPEN 探测失败 → 重新 OPEN: %s",
                    self.name, reason,
                )
                await self._transition_to_open(reason)
            elif self._state == CircuitState.CLOSED:
                if self._failures >= self.config.failure_threshold:
                    await self._transition_to_open(reason)

    async def force_open(self) -> None:
        """强制打开熔断器（通常由外部信号触发，如 SSRF 检测反制）。"""
        async with self._lock:
            if self._state != CircuitState.OPEN:
                await self._transition_to_open("强制熔断")

    async def force_close(self) -> None:
        """强制关闭/重置熔断器（仅用于管理操作）。"""
        async with self._lock:
            await self._transition_to_closed()

    # ── 上下文管理器 ────────────────────────────────────────

    async def __aenter__(self):
        reject = await self.before_request()
        if reject is not None:
            raise CircuitBreakerOpenError(reject)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self.on_success()
        elif exc_type is not None:
            # 不吞异常，但记录失败
            is_retryable = isinstance(exc_val, (asyncio.TimeoutError, ConnectionError, OSError))
            await self.on_failure(
                reason=f"{exc_type.__name__}: {str(exc_val)[:100]}",
                is_retryable=is_retryable,
            )
        return False  # 不吞异常

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker('{self.name}', state={self._state.value}, "
            f"failures={self._failures}, successes={self._successes})"
        )


class CircuitBreakerOpenError(Exception):
    """熔断器打开时抛出的异常。调用方应捕获并降级处理。"""
    def __init__(self, reason: str = ""):
        super().__init__(reason)
        self.reason = reason

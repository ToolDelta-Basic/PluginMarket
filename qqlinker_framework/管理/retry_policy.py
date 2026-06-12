"""统一重试策略定义 — 指数退避 + 可重试错误分类。

═══════════════════════════════════════════════════════════════════════════
用途:
  - NetworkManager 的 http_get / http_post 自动应用此策略
  - 模块也可直接实例化用于自定义 HTTP 调用
  - 非幂等操作（POST/PUT）默认不重试，可显式设置 allow_post_retry=True

设计:
  - 指数退避: delay = backoff_base × backoff_factor^attempt，上限 max_backoff
  - 抖动: ±25% 随机抖动防止雷群效应
  - 可重试条件: 连接错误、超时、服务器 5xx、429 限流
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Type, Union

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 默认可重试的 HTTP 状态码
# ═══════════════════════════════════════════════════════════════

_RETRYABLE_STATUS_CODES: Tuple[int, ...] = (
    429,   # 速率限制
    500,   # 服务器内部错误
    502,   # 网关错误
    503,   # 服务不可用
    504,   # 网关超时
)

# 可重试的异常类型
_RETRYABLE_EXCEPTIONS: Tuple[Type[BaseException], ...] = (
    asyncio.TimeoutError,
    ConnectionError,
    OSError,         # 涵盖 ConnectionRefusedError, BrokenPipeError 等
)


@dataclass
class RetryPolicy:
    """重试策略配置 — 控制 HTTP 请求的重试行为。

    属性:
        max_retries: 最大重试次数（不含首次尝试）
        backoff_base: 初始退避秒数
        backoff_factor: 每次重试的退避倍增因子
        max_backoff: 最大退避秒数（硬上限）
        retry_on_status: 可重试的 HTTP 状态码元组
        retry_on_exceptions: 可重试的异常类型元组
        allow_post_retry: 是否对非幂等请求（POST/PUT/PATCH）启用重试
        jitter: 是否对退避延迟施加随机抖动

    使用示例:
        # 默认策略 — 3 次重试，适合读操作
        policy = RetryPolicy()

        # 自定义策略 — 5 次重试，允许 POST 重试
        policy = RetryPolicy(max_retries=5, backoff_base=2.0, allow_post_retry=True)

        # 不重试
        policy = RetryPolicy(max_retries=0)
    """

    max_retries: int = 3
    backoff_base: float = 1.0       # 秒
    backoff_factor: float = 2.0     # 指数退避因子
    max_backoff: float = 30.0       # 最大退避秒数
    retry_on_status: Tuple[int, ...] = field(default=_RETRYABLE_STATUS_CODES)
    retry_on_exceptions: Tuple[Type[BaseException], ...] = field(default=_RETRYABLE_EXCEPTIONS)
    allow_post_retry: bool = False
    jitter: bool = True

    # ── 内置策略预设 ────────────────────────────────────────

    @classmethod
    def none(cls) -> "RetryPolicy":
        """不重试策略。"""
        return cls(max_retries=0)

    @classmethod
    def fast(cls) -> "RetryPolicy":
        """快速重试: 2 次，0.5s 起始退避。"""
        return cls(max_retries=2, backoff_base=0.5)

    @classmethod
    def standard(cls) -> "RetryPolicy":
        """标准重试: 3 次，1s 起始退避。"""
        return cls(max_retries=3, backoff_base=1.0)

    @classmethod
    def cautious(cls) -> "RetryPolicy":
        """谨慎重试: 5 次，2s 起始退避，允许 POST 重试。"""
        return cls(max_retries=5, backoff_base=2.0, allow_post_retry=True)

    # ── 决策方法 ────────────────────────────────────────────

    def should_retry(
        self, attempt: int, error: Optional[Exception] = None,
        status_code: Optional[int] = None, method: str = "GET",
    ) -> bool:
        """判断当前是否应该重试。

        Args:
            attempt: 已完成的尝试次数（首次=0）
            error: 捕获到的异常（如果有）
            status_code: HTTP 状态码（如果有）
            method: HTTP 方法（GET/POST 等）

        Returns:
            True 表示应重试。
        """
        if attempt >= self.max_retries:
            return False

        # HTTP 错误 → 检查状态码
        if status_code is not None:
            if status_code in self.retry_on_status:
                return True
            # POST/PUT 请求默认不重试（非幂等）
            if method.upper() in ("POST", "PUT", "PATCH", "DELETE") and not self.allow_post_retry:
                return False
            return False

        # 异常 → 检查异常类型
        if error is not None:
            return isinstance(error, self.retry_on_exceptions)

        return False

    def delay_for(self, attempt: int) -> float:
        """计算第 attempt 次重试的退避延迟（秒）。

        Args:
            attempt: 当前重试序号（从 0 开始，0 = 第一次重试）

        Returns:
            等待秒数。
        """
        raw = min(
            self.backoff_base * (self.backoff_factor ** attempt),
            self.max_backoff,
        )
        if self.jitter:
            jitter_range = raw * 0.25
            return raw + random.uniform(-jitter_range, jitter_range)
        return raw

    def __repr__(self) -> str:
        return (
            f"RetryPolicy(max={self.max_retries}, base={self.backoff_base}s, "
            f"factor={self.backoff_factor}, cap={self.max_backoff}s, "
            f"post={self.allow_post_retry})"
        )


# ═══════════════════════════════════════════════════════════════
# 辅助函数：带重试策略的执行包装器
# ═══════════════════════════════════════════════════════════════

async def execute_with_retry(
    fn,
    *args,
    retry_policy: Optional[RetryPolicy] = None,
    method: str = "GET",
    **kwargs,
):
    """使用重试策略执行异步可调用对象。

    Args:
        fn: 异步 callable
        *args: 传递给 fn 的位置参数
        retry_policy: 重试策略，None 时使用 RetryPolicy.standard()
        method: HTTP 方法名（用于判断是否可重试 POST）
        **kwargs: 传递给 fn 的关键字参数

    Returns:
        fn 的返回值

    Raises:
        最后一次尝试的异常（重试耗尽后）
    """
    if retry_policy is None:
        retry_policy = RetryPolicy.standard()

    last_error: Optional[Exception] = None
    for attempt in range(retry_policy.max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if not retry_policy.should_retry(attempt, error=e, method=method):
                raise
            delay = retry_policy.delay_for(attempt)
            _log.debug(
                "重试 %d/%d (延迟 %.2fs): %s: %s",
                attempt + 1, retry_policy.max_retries,
                delay, type(e).__name__, str(e)[:120],
            )
            await asyncio.sleep(delay)

    # 理论上不会到达这里，但作为安全网
    if last_error:
        raise last_error

# noqa: PYL-R0201 (containment pattern — sync wrappers extract async detection, not a method usability issue)

import asyncio
import functools
import logging
import threading
import traceback
from typing import Any, Callable, Optional, TypeVar

F = TypeVar("F", bound=Callable)

_log = logging.getLogger(__name__)

# ── 全局状态 ─────────────────────────────────────────────────

_containment_lock = threading.Lock()

_shutdown_initiated = False
"""是否已发起安全卸载流程。防止多次触发。"""

_critical_failure_count = 0
"""关键路径连续失败计数。超过阈值触发自动卸载。"""

CRITICAL_FAILURE_THRESHOLD = 3
"""连续关键失败多少次后自动卸载整个插件。"""


def reset_failure_count():
    """重置关键失败计数器。"""
    global _critical_failure_count  # noqa: PYL-W0603 (containment state machine, intentional)
    with _containment_lock:
        _critical_failure_count = 0


def is_shutting_down() -> bool:
    """是否正在安全卸载中。"""
    with _containment_lock:
        return _shutdown_initiated


# ═══════════════════════════════════════════════════════════════
# L1: 单次调用的安全包装
# ═══════════════════════════════════════════════════════════════

def safe_call(
    func: Callable,
    *,
    on_error: Optional[Callable[[Exception], None]] = None,
    raise_on_critical: bool = False,
    context: str = "",
) -> Callable:
    """安全包装一个函数调用。任何异常被捕获，绝不向上抛。

    Args:
        func: 要包装的函数。
        on_error: 自定义错误处理回调。
        raise_on_critical: True 时记录到关键失败计数器。
        context: 调用上下文描述（用于日志）。

    Returns:
        包装后的函数。同步函数返回同步结果，异步函数返回 awaitable。
    """
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        """同步包装器：捕获 CancelledError。"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            _handle_caught(e, context, raise_on_critical)
            if on_error:
                try:
                    on_error(e)
                except Exception as e:
                    _log.warning("containment.sync_wrapper: %s", e)
            return None

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            return None
        except Exception as e:
            _handle_caught(e, context, raise_on_critical)
            if on_error:
                try:
                    on_error(e)
                except Exception as e:
                    _log.warning("containment.async_wrapper: %s", e)
            return None

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


def _handle_caught(e: Exception, context: str, critical: bool):
    """统一处理捕获的异常。

    Fix 5: 锁范围缩小为仅保护计数器原子操作，
    避免日志 I/O 和 trigger_safe_shutdown 在锁内阻塞。
    """
    global _critical_failure_count  # noqa: PYL-W0603 (containment state machine, intentional)

    from .error_hints import hint, ErrorMode

    # Fix 5: 仅锁内执行计数器原子操作
    with _containment_lock:
        if critical:
            _critical_failure_count += 1
            count = _critical_failure_count
        else:
            count = 0

    # Fix 5: 日志和卸载触发移到锁外
    if critical:
        prefix = f"[关键 #{count}] "
    else:
        prefix = "[非关键] "

    if ErrorMode.is_debug():
        _log.error(
            "%s%s异常: %s\n%s",
            prefix, context, e, traceback.format_exc(),
        )
    else:
        _log.error(
            "%s%s异常: %s。%s",
            prefix, context, e, hint["UNEXPECTED_ERROR"],
        )

    if critical and count >= CRITICAL_FAILURE_THRESHOLD:
        _log.critical(
            "关键路径连续失败 %d 次，触发自动卸载。"
            "框架将尝试安全退出，ToolDelta 不受影响。",
            count,
        )
        trigger_safe_shutdown()


# ═══════════════════════════════════════════════════════════════
# L2: 事件处理器的安全包装
# ═══════════════════════════════════════════════════════════════

def safe_handler(
    func: Callable,
    context: str = "",
    *,
    is_critical: bool = False,
) -> Callable:
    """安全包装事件处理器。

    与 safe_call 的区别: 额外处理 asyncio.CancelledError
    （ToolDelta 重载时可能触发），并自动记录到合适级别。
    """
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        """带取消安全的事件包装器。"""
        try:
            return func(*args, **kwargs)
        except asyncio.CancelledError:
            _log.debug("%s 处理器被取消 (CancelledError)", context)
            return None
        except Exception as e:
            _handle_caught(e, context, is_critical)
            return None

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            _log.debug("%s 处理器被取消 (CancelledError)", context)
            return None
        except Exception as e:
            _handle_caught(e, context, is_critical)
            return None

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


# ═══════════════════════════════════════════════════════════════
# L3: 框架安全卸载
# ═══════════════════════════════════════════════════════════════

_shutdown_callback: Optional[Callable] = None


def register_shutdown_callback(callback: Callable):
    """注册安全卸载回调（由 FrameworkHost 在启动时设置）。"""
    global _shutdown_callback  # noqa: PYL-W0603 (containment state machine, intentional)
    _shutdown_callback = callback


def trigger_safe_shutdown():
    """触发安全卸载流程。

    如果已注册回调，调用之；否则只标记状态。
    此函数可能被多次调用（幂等）。
    """
    global _shutdown_initiated  # noqa: PYL-W0603 (containment state machine, intentional)
    with _containment_lock:
        if _shutdown_initiated:
            return
        _shutdown_initiated = True

    _log.warning(
        "⚡ 框架安全卸载已触发。ToolDelta 将继续正常运行，本插件将退出。"
    )

    if _shutdown_callback:
        try:
            _shutdown_callback()
        except Exception as e:
            _log.error("安全卸载回调异常: %s", e)
            # 即使回调失败，也不重新抛出


# ═══════════════════════════════════════════════════════════════
# L4: 插件入口外层兜底
# ═══════════════════════════════════════════════════════════════

def plugin_wrapper(entry_func: Callable) -> Callable:
    """插件入口的外层兜底包装器。

    这是最后一道防线——如果任何异常逃逸到了这里，
    它会被记录但绝不会传播给 ToolDelta。

    用法:
        class MyPlugin(Plugin):
            @plugin_wrapper
            def on_active(self):
                ...
    """
    @functools.wraps(entry_func)
    def wrapper(*args, **kwargs):
        """入口包装器：捕获 SystemExit。"""
        try:
            return entry_func(*args, **kwargs)
        except SystemExit:
            # SystemExit 不能吞，但意味着故意退出
            return None
        except Exception as e:
            _log.critical(
                "⚠ 插件入口发生未捕获异常，框架将安全退出。"
                "ToolDelta 不受影响。错误: %s\n%s",
                e, traceback.format_exc(),
            )
            trigger_safe_shutdown()
            return None

    return wrapper


# ═══════════════════════════════════════════════════════════════
# 工具: 批量安全包装
# ═══════════════════════════════════════════════════════════════

def wrap_all_methods(obj: Any, prefix: str = "on_", is_critical: bool = False):
    """批量安全包装对象以 `prefix` 开头的方法。

    Args:
        obj: 要包装的对象实例。
        prefix: 方法名前缀过滤。
        is_critical: 是否为关键路径。

    Returns:
        包装的方法名列表。
    """
    wrapped = []
    for name in dir(obj):
        if not name.startswith(prefix):
            continue
        method = getattr(obj, name)
        if not callable(method):
            continue
        if getattr(method, '_contained', False):
            continue  # 已经包装过了

        ctx = f"{type(obj).__name__}.{name}"
        safe_method = safe_handler(method, context=ctx, is_critical=is_critical)
        safe_method._contained = True  # type: ignore[attr-defined]  # noqa: PYL-W0212 (same-package internal access, marker flag)
        setattr(obj, name, safe_method)
        wrapped.append(name)

    if wrapped:
        _log.debug("已安全包装 %d 个方法: %s", len(wrapped), wrapped)
    return wrapped

"""
CallContext — 不可变调用上下文，由框架在入口点设置，模块代码只能读取不可修改。

使用 contextvars.ContextVar 实现 asyncio 安全 + threading.local fallback。
"""
import contextvars
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

# ContextVar 存储（asyncio 安全）
_current: contextvars.ContextVar[Optional['CallContext']] = \
    contextvars.ContextVar("qqlinker_call_ctx", default=None)

# threading.local fallback（同步线程场景）
_tls = threading.local()


@dataclass(frozen=True)
class CallContext:
    """框架级调用上下文。frozen=True 保证不可变（模块代码无法篡改）。"""
    mid: int                           # 调用模块的 MID
    module_name: str = ""              # 模块完整路径名
    source: str = "internal"           # group_message|private_message|game_event|cron|admin_cli|internal
    trigger_type: str = ""             # 具体触发器描述
    entry_point: str = ""              # 框架入口点名称
    user_id: int = 0                   # QQ 用户 ID
    group_id: int = 0                  # QQ 群号
    user_nickname: str = ""            # QQ 用户昵称
    user_uid: int = 400                # QQ 用户的 UID 等级
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    depth: int = 0
    is_framework: bool = False         # 是否来自框架内部
    is_user_initiated: bool = False    # 是否由 QQ 用户消息触发

    @property
    def is_kernel(self) -> bool:
        return self.mid == 0

    @property
    def is_daemon(self) -> bool:
        return self.mid <= 100

    @property
    def mid_name(self) -> str:
        from .services import mid_label
        return mid_label(self.mid)

    def child(self, **overrides):
        """创建派生上下文。"""
        d = {
            "mid": self.mid, "module_name": self.module_name,
            "source": self.source, "trigger_type": self.trigger_type,
            "entry_point": self.entry_point, "user_id": self.user_id,
            "group_id": self.group_id, "user_nickname": self.user_nickname,
            "user_uid": self.user_uid, "call_id": self.call_id,
            "created_at": self.created_at, "depth": self.depth + 1,
            "is_framework": self.is_framework,
            "is_user_initiated": self.is_user_initiated,
        }
        d.update(overrides)
        return CallContext(**d)


def get_call_context() -> Optional[CallContext]:
    """获取当前调用上下文。先查 ContextVar，fallback threading.local。"""
    ctx = _current.get()
    if ctx is None:
        ctx = getattr(_tls, 'ctx', None)
    return ctx


def require_call_context() -> CallContext:
    """获取当前调用上下文，不存在时抛异常。"""
    ctx = get_call_context()
    if ctx is None:
        raise RuntimeError("CallContext 未设置。必须在框架入口点内调用。")
    return ctx


def set_call_context(ctx: CallContext) -> None:
    """设置当前调用上下文（框架内部用）。"""
    _current.set(ctx)
    _tls.ctx = ctx


def clear_call_context() -> None:
    """清除当前调用上下文。"""
    _current.set(None)
    try:
        del _tls.ctx
    except AttributeError:
        pass


class call_context_scope:
    """CallContext 上下文管理器（框架内部用）。

    with call_context_scope(ctx):
        ...
    """
    __slots__ = ('_ctx', '_token')

    def __init__(self, ctx: CallContext):
        self._ctx = ctx
        self._token = None

    def __enter__(self):
        self._token = _current.set(self._ctx)
        _tls.ctx = self._ctx
        return self

    def __exit__(self, *args):
        _current.reset(self._token)
        try:
            del _tls.ctx
        except AttributeError:
            pass

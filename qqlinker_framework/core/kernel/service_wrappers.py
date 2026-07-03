"""
ServiceWrapper — 自动从 CallContext 注入调用者身份的服务包装器。

所有通过 ServiceContainer.get() 返回的对安全服务自动包装，
方法调用时自动从 CallContext.mid 注入到目标方法的 identity 参数。
"""
import functools
import inspect
import logging
from typing import Any, Callable

_log = logging.getLogger(__name__)

# 需要身份注入的服务方法注册表
# service_name → {method_name → param_name}
_IDENTITY_INJECTION_MAP: dict = {
    "config": {
        "get": "requester_uid",
        "set": "requester_uid",
        "register_section": "caller_uid",
        "resolve_placeholders": "_requester_uid",
    },
    "group_config": {
        "get": "requester_uid",
        "get_group_module_config": "requester_uid",
        "register_module_schema": "caller_uid",
    },
    "message": {
        "send_group": "requester_uid",
        "send_private": "requester_uid",
    },
    "session_tracker": {
        "enter": "caller_mid",
        "leave": "caller_mid",
        "should_capture_commands": "caller_mid",
    },
}


class ServiceWrapper:
    """安全服务包装器。拦截方法调用，自动注入调用者 mid。

    模块通过 self.services.get("config") 获取的会是 ServiceWrapper(config_store)。
    当模块调用 config.get("key") 时，ServiceWrapper 自动从 CallContext 获取
    当前调用者 mid 并注入到 requester_uid 参数。
    """
    __slots__ = ('_target', '_service_name', '_inj')

    def __init__(self, target, service_name: str):
        object.__setattr__(self, '_target', target)
        object.__setattr__(self, '_service_name', service_name)
        object.__setattr__(self, '_inj', _IDENTITY_INJECTION_MAP.get(service_name, {}))

    def __getattr__(self, name: str):
        target = object.__getattribute__(self, '_target')
        inj_map = object.__getattribute__(self, '_inj')
        attr = getattr(target, name)

        if name in inj_map and callable(attr):
            param = inj_map[name]
            return _wrap_injected(attr, param)

        return attr

    def __setattr__(self, *args):
        raise AttributeError("ServiceWrapper 是只读包装器")

    def __repr__(self):
        return f"<ServiceWrapper({self._service_name})>"


def _wrap_injected(method, param_name: str):
    """包装方法，自动注入 CallContext.mid。兼容同步/异步。"""
    from .call_context import get_call_context

    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        ctx = get_call_context()
        if param_name in kwargs:
            # 调用方显式传了身份参数 → 以 CallContext 为准（防伪造）
            if ctx is not None and kwargs[param_name] != ctx.mid:
                _log.warning(
                    "安全: 调用方传入 %s=%d 与 CallContext.mid=%d 不一致，以实际 mid 为准",
                    param_name, kwargs[param_name], ctx.mid)
                kwargs[param_name] = ctx.mid
        elif ctx is not None:
            kwargs[param_name] = ctx.mid
        else:
            # 无 CallContext → 最严格限制
            kwargs[param_name] = 400
        return method(*args, **kwargs)

    if inspect.iscoroutinefunction(method):
        @functools.wraps(method)
        async def async_wrapper(*args, **kwargs):
            ctx = get_call_context()
            if param_name in kwargs:
                if ctx is not None and kwargs[param_name] != ctx.mid:
                    kwargs[param_name] = ctx.mid
            elif ctx is not None:
                kwargs[param_name] = ctx.mid
            else:
                kwargs[param_name] = 400
            return await method(*args, **kwargs)
        return async_wrapper

    return wrapper

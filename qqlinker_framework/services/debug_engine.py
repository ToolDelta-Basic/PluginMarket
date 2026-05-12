"""调试引擎 —— 框架级可观测性服务，提供模块调试操作注册、消息/API监控。"""
import asyncio
import logging
import time
from collections import deque
from typing import Callable, Dict, List, Optional, Any

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


class DebugEngine:
    """调试引擎，提供模块操作注册、消息通道监控、API调用记录。"""

    def __init__(self, services, config, event_bus):
        self._services = services
        self._config = config
        self._event_bus = event_bus
        self._ops: Dict[str, Dict[str, Callable]] = {}
        self._lock = asyncio.Lock()

        # 消息通道缓冲区
        self._msg_buffers: Dict[str, deque] = {
            "group": deque(maxlen=200),
            "game": deque(maxlen=200),
            "internal": deque(maxlen=200),
            "ws_raw": deque(maxlen=50),    # 较小，因可能很频繁
        }
        # API 调用日志缓冲区
        self._api_logs: deque = deque(maxlen=200)
        self._hooks_installed = False

    # ---------- 模块操作注册 ----------
    async def register_module(self, name: str, ops: Dict[str, Callable]):
        """注册一个模块的调试操作。"""
        async with self._lock:
            self._ops[name] = ops
            _logger.debug("注册调试模块: %s, 操作: %s", name, list(ops.keys()))

    async def unregister_module(self, name: str):
        """注销模块的所有调试操作。"""
        async with self._lock:
            self._ops.pop(name, None)

    def list_modules(self) -> List[str]:
        """返回已注册调试操作的模块名列表。"""
        return list(self._ops.keys())

    def list_ops(self, module: str) -> List[str]:
        """返回指定模块注册的操作名列表。"""
        return list(self._ops.get(module, {}).keys())

    async def call(self, module: str, op: str, **kwargs) -> str:
        """执行指定模块的调试操作，返回字符串结果。"""
        async with self._lock:
            ops = self._ops.get(module)
            if not ops:
                raise ValueError(f"模块 {module} 未注册调试操作")
            func = ops.get(op)
            if not func:
                raise ValueError(f"模块 {module} 未注册操作 {op}")
        try:
            result = func(**kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            return str(result) if not isinstance(result, str) else result
        except Exception as e:
            _logger.error("调试操作 %s.%s 异常: %s", module, op, e)
            return f"[调试错误] {e}"

    # ---------- 消息通道监控 ----------
    def install_hooks(self):
        """安装事件监听和 API 方法包装。"""
        if self._hooks_installed:
            return
        # 监听 EventBus 事件
        self._event_bus.subscribe("GroupMessageEvent", self._on_group_msg, 0)
        self._event_bus.subscribe("GameChatEvent", self._on_game_chat, 0)
        self._event_bus.subscribe("PlayerPositionEvent", self._on_pos, 0)
        # 包装适配器方法
        self._wrap_service("adapter", [
            "send_game_command_with_resp",
            "send_game_command_full",
            "get_online_players",
            "get_player_positions",
        ])
        # 尝试包装工具管理器（若尚未就绪，后续可再次尝试）
        self._wrap_service("tool", ["execute"])
        self._hooks_installed = True

    def _on_group_msg(self, event):
        self._msg_buffers["group"].append({
            "timestamp": time.time(),
            "user_id": event.user_id,
            "group_id": event.group_id,
            "nickname": event.nickname,
            "message": event.message[:500],
        })

    def _on_game_chat(self, event):
        self._msg_buffers["game"].append({
            "timestamp": time.time(),
            "player": event.player_name,
            "message": event.message[:500],
        })

    def _on_pos(self, event):
        self._msg_buffers["internal"].append({
            "timestamp": time.time(),
            "type": "PlayerPositionEvent",
            "players": len(event.positions),
            "sample": str(event.positions)[:200],
        })

    # ---------- API 包装辅助 ----------
    def _wrap_service(self, service_name: str, methods: List[str]):
        """包装指定服务的方法以记录调用。"""
        try:
            svc = self._services.get(service_name)
        except KeyError:
            _logger.debug("服务 %s 尚未注册，跳过包装", service_name)
            return
        for method_name in methods:
            if not hasattr(svc, method_name):
                continue
            original = getattr(svc, method_name)
            if getattr(original, "_debug_wrapped", False):
                continue
            def make_wrapper(orig, svc_name, m_name):
                if asyncio.iscoroutinefunction(orig):
                    async def async_wrapper(*args, **kwargs):
                        start = time.time()
                        try:
                            result = await orig(*args, **kwargs)
                        except Exception as e:
                            self._api_logs.append({
                                "timestamp": time.time(),
                                "service": svc_name,
                                "method": m_name,
                                "args": str(args)[:200],
                                "kwargs": str(kwargs)[:200],
                                "error": str(e),
                                "elapsed": time.time() - start,
                            })
                            raise
                        self._api_logs.append({
                            "timestamp": time.time(),
                            "service": svc_name,
                            "method": m_name,
                            "args": str(args)[:200],
                            "kwargs": str(kwargs)[:200],
                            "result": str(result)[:500],
                            "elapsed": time.time() - start,
                        })
                        return result
                    async_wrapper._debug_wrapped = True
                    async_wrapper.__doc__ = orig.__doc__
                    return async_wrapper
                else:
                    def sync_wrapper(*args, **kwargs):
                        start = time.time()
                        try:
                            result = orig(*args, **kwargs)
                        except Exception as e:
                            self._api_logs.append({
                                "timestamp": time.time(),
                                "service": svc_name,
                                "method": m_name,
                                "args": str(args)[:200],
                                "kwargs": str(kwargs)[:200],
                                "error": str(e),
                                "elapsed": time.time() - start,
                            })
                            raise
                        self._api_logs.append({
                            "timestamp": time.time(),
                            "service": svc_name,
                            "method": m_name,
                            "args": str(args)[:200],
                            "kwargs": str(kwargs)[:200],
                            "result": str(result)[:500],
                            "elapsed": time.time() - start,
                        })
                        return result
                    sync_wrapper._debug_wrapped = True
                    sync_wrapper.__doc__ = orig.__doc__
                    return sync_wrapper

    # ---------- 查询接口 ----------
    def get_message_log(self, channel: str, limit: int = 20) -> List[Dict]:
        """返回指定通道的最近消息。"""
        buf = self._msg_buffers.get(channel)
        if not buf:
            raise ValueError(f"未知通道: {channel}")
        return list(buf)[-limit:]

    def get_api_log(self, limit: int = 20) -> List[Dict]:
        """返回最近的 API 调用日志。"""
        return list(self._api_logs)[-limit:]

    def clear_logs(self, channel: str = None):
        """清空指定或全部缓冲区。"""
        if channel:
            if channel in self._msg_buffers:
                self._msg_buffers[channel].clear()
            elif channel == "api":
                self._api_logs.clear()
        else:
            for buf in self._msg_buffers.values():
                buf.clear()
            self._api_logs.clear()

    # ---------- 动态包装接口 ----------
    def wrap_now(self, service_name: str, methods: List[str]):
        """立即包装指定的已注册服务（供模块在服务就绪后调用）。"""
        self._wrap_service(service_name, methods)

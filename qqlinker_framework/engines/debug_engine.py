# pylint: disable=protected-access
import os
import asyncio
import logging
import time
from collections import deque
from typing import Callable, Dict, List, Optional, Any

from ..core.kernel.events import GroupMessageEvent, GameChatEvent, PlayerPositionEvent
from ..libraries.core.engine import Engine, EngineConfig

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


class DebugEngine(Engine):
    """调试引擎，提供模块操作注册、消息通道监控、API调用记录。

    引擎定义:
      挂载 ws_client/adapter 库提供消息通道监控和 API 调用记录能力，
      对外提供 "debug" 服务。
    """

    config = EngineConfig(
        name="debug_engine",
        version="1.0.0",
        mounts=["adapter", "tool"],
        pipeline=["monitor", "record", "query"],
        provides=["debug"],
    )

    def __init__(self, services, config, event_bus):
        super().__init__(services, event_bus)
        self._services = services
        self._config = config
        self._event_bus = event_bus
        self._ops: Dict[str, Dict[str, Callable]] = {}
        self._lock = asyncio.Lock()

        # 安全检查: 生产模式下强制禁用调试引擎
        # 仅在 __debug__=True 且显式设置 调试.生产模式禁用=false 时启用
        force_debug = os.environ.get("QQLINKER_FORCE_DEBUG", "0") == "1"
        config_allow = not config.get("调试.生产模式禁用", True)
        if not force_debug and (not __debug__ or not config_allow):
            self._disabled = True
            _logger.warning(
                "⚠️ 调试引擎已禁用。"
                "开发模式: 设置 QQLINKER_FORCE_DEBUG=1 + 调试.生产模式禁用=false"
            )
        else:
            self._disabled = False

        self._msg_buffers: Dict[str, deque] = {
            "group": deque(maxlen=200),
            "game": deque(maxlen=200),
            "internal": deque(maxlen=200),
            "ws_raw": deque(maxlen=50),
        }
        self._api_logs: deque = deque(maxlen=200)
        self._hooks_installed = False

        self._counters = {
            "group_msgs": 0,
            "game_msgs": 0,
            "api_calls": 0,
            "api_errors": 0,
            "slow_api_calls": 0,
        }
        self._slow_threshold = 1.0

    # ---------- 模块操作注册 ----------
    async def register_module(self, name: str, ops: Dict[str, Callable]):
        """注册一个模块的调试操作。"""
        if self._disabled:
            _logger.debug(
                "调试引擎已禁用，忽略 register_module(%s)", name
            )
            return
        async with self._lock:
            self._ops[name] = ops

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
        if self._disabled:
            return "[调试引擎已禁用]"
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
        if self._disabled:
            _logger.debug("调试引擎已禁用，跳过 install_hooks")
            return
        if self._hooks_installed:
            return
        self._event_bus.subscribe(GroupMessageEvent, self._on_group_msg, 0)
        self._event_bus.subscribe(GameChatEvent, self._on_game_chat, 0)
        self._event_bus.subscribe(PlayerPositionEvent, self._on_pos, 0)
        self._wrap_service("adapter", [
            "send_game_command_with_resp",
            "send_game_command_full",
            "get_online_players",
        ])
        self._wrap_service("tool", ["execute"])
        self._hooks_installed = True

    def _on_group_msg(self, event):
        """记录群消息到缓冲区。"""
        self._msg_buffers["group"].append({
            "timestamp": time.time(),
            "user_id": event.user_id,
            "group_id": event.group_id,
            "nickname": event.nickname,
            "message": event.message[:500],
        })
        self._counters["group_msgs"] += 1

    def _on_game_chat(self, event):
        """记录游戏聊天消息到缓冲区。"""
        self._msg_buffers["game"].append({
            "timestamp": time.time(),
            "player": event.player_name or "",
            "message": (event.message or "")[:500],
        })
        self._counters["game_msgs"] += 1

    def _on_pos(self, event):
        """记录玩家坐标事件简况。"""
        self._msg_buffers["internal"].append({
            "timestamp": time.time(),
            "type": "PlayerPositionEvent",
            "players": len(event.positions),
            "sample": str(event.positions)[:200],
        })

    # ---------- API 包装 ----------
    def _wrap_service(self, service_name: str, methods: List[str]):
        """包装指定服务的方法，用于记录调用日志和指标。"""
        try:
            svc = self._services.get(service_name)
        except KeyError:
            return
        for method_name in methods:
            if not hasattr(svc, method_name):
                continue
            original = getattr(svc, method_name)
            if getattr(original, "_debug_wrapped", False):
                continue

            if asyncio.iscoroutinefunction(original):
                wrapper = self._make_async_wrapper(
                    original, service_name, method_name,
                )
            else:
                wrapper = self._make_sync_wrapper(
                    original, service_name, method_name,
                )
            setattr(svc, method_name, wrapper)

    def _make_async_wrapper(self, original, svc_name, m_name):
        """为异步方法创建记录包装器。"""
        async def wrapper(*args, **kwargs):
            """自动记录异步API调用的耗时、参数与异常。"""
            start = time.time()
            try:
                result = await original(*args, **kwargs)
            except Exception as exc:
                self._record_api_call(
                    svc_name, m_name,
                    str(args)[:200], str(kwargs)[:200],
                    None, exc, time.time() - start,
                )
                raise
            self._record_api_call(
                svc_name, m_name,
                str(args)[:200], str(kwargs)[:200],
                result, None, time.time() - start,
            )
            return result
        wrapper._debug_wrapped = True
        wrapper.__doc__ = original.__doc__
        return wrapper

    def _make_sync_wrapper(self, original, svc_name, m_name):
        """为同步方法创建记录包装器。"""
        def wrapper(*args, **kwargs):
            """自动记录同步API调用的耗时、参数与异常。"""
            start = time.time()
            try:
                result = original(*args, **kwargs)
            except Exception as exc:
                self._record_api_call(
                    svc_name, m_name,
                    str(args)[:200], str(kwargs)[:200],
                    None, exc, time.time() - start,
                )
                raise
            self._record_api_call(
                svc_name, m_name,
                str(args)[:200], str(kwargs)[:200],
                result, None, time.time() - start,
            )
            return result
        wrapper._debug_wrapped = True
        wrapper.__doc__ = original.__doc__
        return wrapper

    def _record_api_call(
        self, service, method, args, kwargs, result, error, elapsed,
    ):
        """记录一次 API 调用并更新计数器。"""
        self._api_logs.append({
            "timestamp": time.time(),
            "service": service,
            "method": method,
            "args": args,
            "kwargs": kwargs,
            "result": str(result)[:500] if error is None else None,
            "error": str(error) if error else None,
            "elapsed": elapsed,
        })
        self._counters["api_calls"] += 1
        if error:
            self._counters["api_errors"] += 1
        if elapsed > self._slow_threshold:
            self._counters["slow_api_calls"] += 1
            _logger.warning(
                "慢API调用: %s.%s 耗时 %.2fs", service, method, elapsed,
            )

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

    def get_counters(self) -> Dict[str, int]:
        """返回消息量和 API 调用指标。"""
        return self._counters.copy()

    def wrap_now(self, service_name: str, methods: List[str]):
        """立即包装指定的已注册服务。"""
        if self._disabled:
            return
        self._wrap_service(service_name, methods)

    # ═══════════════════════════════════════════════════════════
    # Engine 生命周期
    # ═══════════════════════════════════════════════════════════

    async def ignite(self) -> None:
        """启动引擎 — 验证依赖库，安装监控钩子。"""
        if not self._verify_mounts():
            _logger.warning(
                "调试引擎启动: 部分依赖库未就绪，继续以降级模式运行"
            )
        self.install_hooks()
        _logger.info("调试引擎已启动 v%s", self.config.version)

    async def extinguish(self) -> None:
        """停止引擎 — 清空缓冲区。"""
        self.clear_logs()
        _logger.info("调试引擎已停止")

"""
IPCEventBridge — LaneRouter ↔ IPC 进程桥接

将 LaneRouter 事件序列化后通过 IPC 发送到 Worker 进程，
Worker 处理完通过 IPC 回传结果，桥接器再将结果发布回 LaneRouter。

设计原则:
  - IPC 是可选的 — 未配置时框架保持单进程运行
  - 桥接器位于 LaneRouter 和 PipelineEngine 之间
  - Worker 进程崩溃不影响主进程，自动故障转移
  - 每个 lane 可独立配置是否桥接到 IPC

用法:
    router = LaneRouter()
    bridge = IPCEventBridge(router, ipc_client=client)
    await bridge.bridge_lane("chat")  # 将 chat lane 桥接到 IPC
    # 此后 chat lane 的事件会先序列化 → IPC → worker 处理 → 回传结果
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger(__name__)


# ── Robust import helper for EventSerializer ──
def _get_event_serializer():
    """导入 EventSerializer，支持多种包路径。"""
    for path in ['core.ipc.bridge', 'qqlinker_framework.core.ipc.bridge']:
        try:
            mod = __import__(path, fromlist=['EventSerializer'])
            return mod.EventSerializer
        except (ImportError, ValueError):
            continue
    raise ImportError(
        "core.ipc.bridge 不可用。请确保 core/ipc/bridge.py 存在且 QQ 框架根目录在 sys.path 中"
    )

_EventSerializer = None  # lazily cached


class IPCEventBridge:
    """LaneRouter ↔ IPC 进程桥接器。

    将 LaneRouter 事件序列化后通过 IPC 发送到 Worker 进程，
    Worker 处理完通过 IPC 回传结果。

    属性:
        _router: LaneRouter 实例
        _ipc_client: IPCClient 实例
        _bridged_lanes: 已桥接的 lane 名称集合
        _pending: 等待 worker 响应的事件映射 (event_id → Future)
        _worker_handler: worker 结果回传的 handler 回调
        _stats: 统计信息
    """

    def __init__(self, router, ipc_client=None):
        self._router = router
        self._ipc_client = ipc_client
        self._bridged_lanes: Dict[str, str] = {}  # lane_name → worker_method
        self._pending: Dict[str, asyncio.Future] = {}
        self._worker_handler: Optional[Callable] = None
        self._recv_task: Optional[asyncio.Task] = None

        # 故障转移
        self._fallback_handlers: Dict[str, List[Callable]] = {}

        # 统计
        self.stats = {
            "events_sent": 0,
            "events_received": 0,
            "events_failed": 0,
            "events_fallback": 0,
            "last_send_time": 0.0,
            "last_recv_time": 0.0,
        }

    @property
    def ipc_client(self):
        return self._ipc_client

    @ipc_client.setter
    def ipc_client(self, client):
        """运行时更换 IPC 客户端。"""
        self._ipc_client = client

    # ── Lane 桥接 ─────────────────────────────

    async def bridge_lane(self, lane_name: str, worker_method: str = "bridge.process_event"):
        """将某个 lane 的事件桥接到 IPC worker pool。

        桥接后的工作流:
          1. 原 handler 不再直接处理事件
          2. 桥接器拦截事件 → 序列化 → IPC call → worker 进程
          3. worker 处理完通过 IPC 回传结果
          4. 桥接器将结果发布回 LaneRouter

        Args:
            lane_name: Lane 名称（如 "chat", "ai", "realtime"）。
            worker_method: Worker 端的 IPC 方法名。

        Raises:
            ValueError: IPC 客户端未配置。
        """
        if self._ipc_client is None:
            raise ValueError(
                f"无法桥接 lane '{lane_name}': IPC 客户端未配置。"
                f"请先设置 bridge.ipc_client"
            )

        if lane_name in self._bridged_lanes:
            _log.warning("Lane '%s' 已桥接，跳过", lane_name)
            return

        self._bridged_lanes[lane_name] = worker_method

        # 保存原订阅者作为故障转移 handler
        lane = self._router._lanes.get(lane_name)
        if lane and lane._subscribers:
            self._fallback_handlers[lane_name] = list(lane._subscribers)
            # 清空原订阅者（桥接器接管）
            lane._subscribers.clear()

        # 注册桥接 handler 到 lane
        self._router.subscribe(
            type("_BridgeEvent", (), {"lane": lane_name}),
            self._on_bridged_event,
            priority=-999,  # 最低优先级，确保其他 handler 先执行
        )

        _log.info(
            "Lane '%s' 已桥接到 IPC (worker_method=%s)",
            lane_name, worker_method,
        )

    async def unbridge_lane(self, lane_name: str):
        """解除 lane 的 IPC 桥接，恢复本地处理。"""
        if lane_name not in self._bridged_lanes:
            return

        del self._bridged_lanes[lane_name]

        # 恢复原订阅者
        lane = self._router._lanes.get(lane_name)
        if lane and lane_name in self._fallback_handlers:
            for handler in self._fallback_handlers[lane_name]:
                if handler not in lane._subscribers:
                    lane._subscribers.append(handler)
            del self._fallback_handlers[lane_name]

        _log.info("Lane '%s' 已解除 IPC 桥接", lane_name)

    # ── 事件发送 ──────────────────────────────

    async def send_event(self, event) -> bool:
        """序列化事件 → IPC → worker 进程处理。

        Args:
            event: 框架事件对象。

        Returns:
            True 表示发送成功，False 表示失败（触发故障转移）。
        """
        if self._ipc_client is None:
            return False

        lane_name = getattr(event, 'lane', 'chat')
        worker_method = self._bridged_lanes.get(lane_name, "bridge.process_event")

        try:
            # 序列化事件
            serialized = _get_event_serializer().serialize_event(event, topic=lane_name)
            self.stats["events_sent"] += 1
            self.stats["last_send_time"] = time.time()

            # 通过 IPC 发送（异步，不等待响应）
            await self._ipc_client.notify("bridge.event", serialized)
            return True

        except Exception as exc:
            _log.error(
                "IPC 发送事件 '%s' 失败: %s，触发故障转移",
                type(event).__name__, exc,
            )
            self.stats["events_failed"] += 1
            await self._fallback(event)
            return False

    async def send_event_and_wait(self, event, timeout: float = 10.0):
        """序列化事件 → IPC call → 等待 worker 处理结果。

        Args:
            event: 框架事件对象。
            timeout: 等待超时（秒）。

        Returns:
            worker 处理后的结果，或 None（超时/失败）。

        Raises:
            IPCError: IPC 通信异常。
        """
        if self._ipc_client is None:
            return None

        lane_name = getattr(event, 'lane', 'chat')
        worker_method = self._bridged_lanes.get(lane_name, "bridge.process_event")

        serialized = _get_event_serializer().serialize_event(event, topic=lane_name)

        try:
            result = await asyncio.wait_for(
                self._ipc_client.call(worker_method, serialized),
                timeout=timeout,
            )
            self.stats["events_received"] += 1
            self.stats["last_recv_time"] = time.time()
            return result
        except asyncio.TimeoutError:
            _log.warning("IPC call '%s' 超时 (%.1fs)", worker_method, timeout)
            self.stats["events_failed"] += 1
            await self._fallback(event)
            return None
        except Exception as exc:
            _log.error("IPC call '%s' 异常: %s", worker_method, exc)
            self.stats["events_failed"] += 1
            await self._fallback(event)
            return None

    # ── Worker 结果回传 ───────────────────────

    async def on_worker_result(self, result: dict):
        """Worker 结果回传 → 发布回 LaneRouter。

        Args:
            result: worker 返回的 dict，包含重建后的事件数据。
        """
        try:
            event, topic, event_id, priority = _get_event_serializer().deserialize_from_worker(result)
            self.stats["events_received"] += 1
            self.stats["last_recv_time"] = time.time()

            # 发布回 LaneRouter
            await self._router.publish(event, priority=priority)
            _log.debug(
                "Worker 结果已回传: %s (event_id=%s, topic=%s)",
                type(event).__name__, event_id, topic,
            )
        except Exception as exc:
            _log.error("Worker 结果解析失败: %s", exc)
            self.stats["events_failed"] += 1

    # ── 内部方法 ──────────────────────────────

    async def _on_bridged_event(self, event):
        """Lane 的桥接 handler — 被 LaneRouter 的 worker 调用。

        此方法拦截 lane 中的事件，通过 IPC 发送到 worker 进程。
        """
        lane_name = getattr(event, 'lane', 'chat')
        if lane_name not in self._bridged_lanes:
            return

        await self.send_event_and_wait(event)

    async def _fallback(self, event):
        """故障转移 — 当 IPC 不可用时，回退到本地 handler。"""
        lane_name = getattr(event, 'lane', 'chat')
        handlers = self._fallback_handlers.get(lane_name, [])
        self.stats["events_fallback"] += 1
        _log.warning(
            "IPC 不可用，lane '%s' 回退到本地 handler (%d 个)",
            lane_name, len(handlers),
        )
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as exc:
                _log.error("故障转移 handler 异常: %s", exc)

    # ── 生命周期 ──────────────────────────────

    async def start(self):
        """启动桥接器（确保 IPC 客户端已连接）。"""
        if self._ipc_client:
            await self._ipc_client.ensure_connected()
            _log.info("IPCEventBridge 已启动 (%d 个桥接 lane)", len(self._bridged_lanes))

    async def stop(self):
        """停止桥接器，恢复所有 lane。"""
        for lane_name in list(self._bridged_lanes.keys()):
            await self.unbridge_lane(lane_name)
        _log.info("IPCEventBridge 已停止")

    # ── 查询 ──────────────────────────────────

    def bridged_lanes(self) -> List[str]:
        """返回已桥接的 lane 列表。"""
        return list(self._bridged_lanes.keys())

    def is_bridged(self, lane_name: str) -> bool:
        """检查 lane 是否已桥接。"""
        return lane_name in self._bridged_lanes

    def stat_snapshot(self) -> Dict[str, Any]:
        """返回统计快照。"""
        return {
            **self.stats,
            "bridged_lanes": self.bridged_lanes(),
            "pending_count": len(self._pending),
        }

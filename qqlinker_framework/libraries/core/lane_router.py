from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from .priority_queue import PriorityEventQueue

_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# LaneConfig — 每条 lane 的配置
# ═══════════════════════════════════════════════════════════

@dataclass
class LaneConfig:
    """Lane 运行时配置。"""

    workers: int = 1
    """worker 协程数。"""

    timeout: float = 30.0
    """单个 handler 超时（秒）。"""

    max_queue: int = 1000
    """队列最大容量。0 = 无界。"""

    backpressure: str = "drop_oldest"
    """背压策略: reject | drop_oldest | drop_newest | unbounded"""

    dynamic: bool = False
    """是否为动态创建（可被清理）。"""

    created_at: float = 0.0
    """创建时间戳。"""


# ============================================================
# 内置 Lane 配置表
# ============================================================

BUILTIN_LANES: Dict[str, LaneConfig] = {
    "critical": LaneConfig(
        workers=1, timeout=5.0, max_queue=0,
        backpressure="unbounded",
    ),
    "admin": LaneConfig(
        workers=2, timeout=10.0, max_queue=100,
        backpressure="reject",
    ),
    "realtime": LaneConfig(
        workers=4, timeout=3.0, max_queue=500,
        backpressure="drop_oldest",
    ),
    "chat": LaneConfig(
        workers=8, timeout=30.0, max_queue=1000,
        backpressure="drop_oldest",
    ),
    "ai": LaneConfig(
        workers=2, timeout=120.0, max_queue=20,
        backpressure="reject",
    ),
    "background": LaneConfig(
        workers=1, timeout=60.0, max_queue=0,
        backpressure="drop_newest",
    ),
}

# ============================================================
# 动态 Lane 默认配置
# ============================================================

DYNAMIC_LANE_DEFAULTS = LaneConfig(
    workers=1, timeout=30.0, max_queue=100,
    backpressure="drop_oldest",
    dynamic=True,
)


# ═══════════════════════════════════════════════════════════
# Lane — 独立执行上下文
# ═══════════════════════════════════════════════════════════

class Lane:
    """一条 lane = 独立队列 + worker pool + 订阅者集合。"""

    def __init__(self, name: str, config: LaneConfig):
        self.name = name
        self.config = config
        self.queue = PriorityEventQueue(max_size=config.max_queue)
        self._subscribers: List[Callable] = []
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
        self.last_publish_time: float = 0.0
        self._total_processed: int = 0
        self._total_dropped: int = 0

    # ── 订阅管理 ──────────────────────────────

    def subscribe(self, handler: Callable, priority: int = 0):
        """注册 handler。priority 保留用于未来扩展。"""
        if handler not in self._subscribers:
            self._subscribers.append(handler)

    def unsubscribe(self, handler: Callable):
        """移除 handler。"""
        try:
            self._subscribers.remove(handler)
        except ValueError:
            pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # ── 生命周期 ──────────────────────────────

    async def start(self):
        """启动 worker pool。"""
        if self._running:
            return
        self._running = True
        self._shutdown_event.clear()

        for i in range(self.config.workers):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)

        if self.config.workers > 0:
            _log.debug("Lane '%s' 已启动 (%d workers)", self.name, self.config.workers)

    async def stop(self):
        """停止 worker pool，清空队列。"""
        if not self._running:
            return
        self._running = False
        self._shutdown_event.set()

        # 取消所有 worker
        for task in self._workers:
            task.cancel()
        self._workers.clear()

        # 清空队列
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Exception:
                break

        _log.debug("Lane '%s' 已停止 (已处理 %d, 丢弃 %d)",
                   self.name, self._total_processed, self._total_dropped)

    # ── 事件发布 ──────────────────────────────

    async def publish(self, event, priority: int = 0) -> bool:
        """发布事件到此 lane 的队列。

        Returns:
            True 表示入队成功，False 表示被背压丢弃。
        """
        self.last_publish_time = time.time()

        # critical lane: 跳过队列，直接执行
        if self.config.max_queue == 0 and self.config.backpressure == "unbounded":
            # 同步执行所有 handler（不排队）
            await self._dispatch(event)
            return True

        ok = await self.queue.put(event, priority)
        if not ok:
            self._total_dropped += 1
            if self.config.backpressure == "reject":
                _log.warning(
                    "Lane '%s' 队列满 (%d), reject 事件 %s",
                    self.name, self.config.max_queue, type(event).__name__,
                )
            elif self.config.backpressure == "drop_oldest":
                # 丢弃最旧 → 尝试放新
                try:
                    self.queue.get_nowait()
                    ok = self.queue.put_nowait(event, priority)
                    if ok:
                        self._total_dropped -= 1  # 修正计数
                except Exception:
                    pass
            elif self.config.backpressure == "drop_newest":
                _log.debug(
                    "Lane '%s' 队列满，静默丢弃 %s",
                    self.name, type(event).__name__,
                )
        return ok

    # ── Worker 循环 ──────────────────────────

    async def _worker(self, worker_id: int):
        """Worker 协程：从队列取事件 → 分发给订阅者。"""
        while self._running:
            try:
                # 等待事件（带超时，可响应 shutdown）
                event = await asyncio.wait_for(
                    self.queue.get(), timeout=0.5
                )
                await self._dispatch(event)
                self._total_processed += 1
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                _log.exception("Lane '%s' worker-%d 异常", self.name, worker_id)

    async def _dispatch(self, event):
        """将事件分发给所有订阅者。"""
        if not self._subscribers:
            return

        for handler in self._subscribers:
            handler_name = getattr(handler, '__name__', repr(handler))
            try:
                if asyncio.iscoroutinefunction(handler):
                    await asyncio.wait_for(
                        handler(event),
                        timeout=self.config.timeout,
                    )
                else:
                    handler(event)
            except asyncio.TimeoutError:
                _log.error(
                    "Lane '%s' handler '%s' 超时 (%.1fs)",
                    self.name, handler_name, self.config.timeout,
                )
            except Exception:
                _log.exception(
                    "Lane '%s' handler '%s' 异常",
                    self.name, handler_name,
                )


# ═══════════════════════════════════════════════════════════
# LaneRouter — 事件路由器
# ═══════════════════════════════════════════════════════════

class LaneRouter:
    """原子级事件路由器。

    用法:
        router = LaneRouter()
        await router.start()
        router.subscribe(GroupMessageEvent, my_handler)
        await router.publish(event)
        await router.stop()
    """

    def __init__(self):
        self._lanes: Dict[str, Lane] = {}
        self._event_lane_map: Dict[type, str] = {}
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    # ── 生命周期 ──────────────────────────────

    async def start(self):
        """启动所有内置 lane。"""
        if self._running:
            return

        for name, config in BUILTIN_LANES.items():
            if name not in self._lanes:
                # 尚未通过 subscribe() 创建 → 新建
                lane = Lane(name=name, config=config)
                self._lanes[name] = lane
            await self._lanes[name].start()

        self._running = True
        _log.info("LaneRouter 已启动 (%d 条 lane)", len(self._lanes))

    async def stop(self):
        """停止所有 lane。"""
        self._running = False

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        for lane in list(self._lanes.values()):
            await lane.stop()
        self._lanes.clear()
        self._event_lane_map.clear()
        _log.info("LaneRouter 已停止")

    # ── 订阅 ──────────────────────────────────

    def subscribe(self, event_class: type, handler: Callable, priority: int = 0):
        """订阅事件类型。

        Args:
            event_class: 事件类（类对象，非字符串）。
            handler: 处理器函数/协程。
            priority: lane 内优先级（0=普通，正值=更高）。
        """
        lane_name = self._resolve_lane(event_class)
        lane = self._get_or_create_lane(lane_name)
        lane.subscribe(handler, priority)

        # 缓存映射
        self._event_lane_map[event_class] = lane_name

    def unsubscribe(self, event_class: type, handler: Callable):
        """取消订阅。"""
        lane_name = self._event_lane_map.get(event_class)
        if lane_name and lane_name in self._lanes:
            self._lanes[lane_name].unsubscribe(handler)

    # ── 发布 ──────────────────────────────────

    async def publish(self, event, priority: int = 0) -> bool:
        """发布事件到对应 lane。

        Args:
            event: 事件实例（必须有 lane 属性）。
            priority: lane 内优先级。未指定时使用 event.priority。

        Returns:
            True 表示入队成功，False 表示被背压拒绝。
        """
        lane_name = getattr(event, 'lane', None) or self._resolve_lane(type(event))
        lane = self._get_or_create_lane(lane_name)

        if priority == 0:
            priority = getattr(event, 'priority', 0)

        return await lane.publish(event, priority)

    # ── 内部方法 ──────────────────────────────

    def _resolve_lane(self, event_class: type) -> str:
        """从事件类解析 lane 名称。"""
        # 优先取类属性的 lane
        cls_lane = getattr(event_class, 'lane', None)
        if cls_lane and isinstance(cls_lane, str):
            return cls_lane

        # 已知映射
        cached = self._event_lane_map.get(event_class)
        if cached:
            return cached

        # 默认
        return "chat"

    def _get_or_create_lane(self, lane_name: str) -> Lane:
        """获取或懒创建 lane。"""
        if lane_name in self._lanes:
            return self._lanes[lane_name]

        # 内置表中有配置 → 使用
        if lane_name in BUILTIN_LANES:
            config = BUILTIN_LANES[lane_name]
            config.created_at = time.time()
        else:
            # 动态创建
            config = LaneConfig(
                workers=DYNAMIC_LANE_DEFAULTS.workers,
                timeout=DYNAMIC_LANE_DEFAULTS.timeout,
                max_queue=DYNAMIC_LANE_DEFAULTS.max_queue,
                backpressure=DYNAMIC_LANE_DEFAULTS.backpressure,
                dynamic=True,
                created_at=time.time(),
            )

        lane = Lane(name=lane_name, config=config)
        if self._running:
            # 如果 router 已经启动，立即启动新 lane
            loop = asyncio.get_event_loop()
            loop.create_task(lane.start())

        self._lanes[lane_name] = lane
        _log.info("Lane 已创建: %s (dynamic=%s)", lane_name, lane.config.dynamic)
        return lane

    # ── 动态 Lane 清理 ────────────────────────

    async def start_cleanup(self, interval: float = 300.0):
        """启动定期清理任务（每 interval 秒）。"""
        if self._cleanup_task and not self._cleanup_task.done():
            return

        async def _cleanup_loop():
            while self._running:
                await asyncio.sleep(interval)
                await self._sweep_dynamic_lanes()

        self._cleanup_task = asyncio.create_task(_cleanup_loop())
        _log.info("Lane 清理任务已启动 (间隔=%ss)", interval)

    async def _sweep_dynamic_lanes(self):
        """清理无活动的动态 lane。"""
        now = time.time()
        to_remove = []

        for name, lane in list(self._lanes.items()):
            if not lane.config.dynamic:
                continue
            if lane.subscriber_count > 0:
                continue
            if not lane.queue.empty():
                continue
            if now - lane.last_publish_time < 600:  # 10 分钟内有活动
                continue

            to_remove.append(name)

        for name in to_remove:
            await self._lanes[name].stop()
            del self._lanes[name]
            # 清理相关的事件映射
            self._event_lane_map = {
                k: v for k, v in self._event_lane_map.items()
                if v != name
            }
            _log.info("动态 lane 已清理: %s", name)

    # ── 查询 ──────────────────────────────────

    def lane_stats(self) -> Dict[str, Dict[str, Any]]:
        """返回所有 lane 的统计信息。"""
        return {
            name: {
                "workers": lane.config.workers,
                "subscribers": lane.subscriber_count,
                "queue_size": lane.queue.qsize(),
                "total_processed": lane._total_processed,
                "total_dropped": lane._total_dropped,
                "last_publish": lane.last_publish_time,
                "dynamic": lane.config.dynamic,
            }
            for name, lane in self._lanes.items()
        }

    def lane_names(self) -> List[str]:
        """返回所有 lane 名称。"""
        return list(self._lanes.keys())

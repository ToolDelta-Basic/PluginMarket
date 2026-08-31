"""
Pipeline Engine — 主题管道分支路由

将消息流按 topic 分叉到独立管道分支，每条分支有自己的队列和 worker 池。
解决单线程线性处理时的性能瓶颈（如 AI 处理阻塞 60s 导致其他消息卡住）。

与 LaneRouter 的关系：
  LaneRouter 是粗粒度事件隔离层（critical/chat/ai/realtime 等 lane）
  PipelineEngine 是细粒度业务路由层（命令分发/规则匹配/topic 路由）

典型流:
  LaneRouter.chat → 群消息 → PipelineEngine → topic路由 → 命令分支/AI分支/管理分支
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger("qqlinker.pipeline")


# ═══════════════════════════════════════════════════════════
# PipelineBranch — 独立队列 + 处理器链 + worker 池
# ═══════════════════════════════════════════════════════════

class PipelineBranch:
    """一条管道分支 = 独立队列 + 处理器链。

    每个分支有自己的 asyncio.Queue 和 worker 协程池。
    handler 按注册顺序依次执行（链式处理），而非广播。
    """

    def __init__(self, name: str, workers: int = 2, timeout: float = 30.0,
                 max_queue: int = 1000):
        self.name = name
        self.workers = workers
        self.timeout = timeout
        self.max_queue = max_queue

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)
        self._handlers: List[Callable] = []
        self._worker_tasks: List[asyncio.Task] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

        # 统计
        self.total_processed: int = 0
        self.total_dropped: int = 0
        self.total_timeouts: int = 0
        self.total_errors: int = 0
        self.last_push_time: float = 0.0

        # IPC 传输
        self._ipc_enabled: bool = False
        self._ipc_pool = None
        self._ipc_serializer = None
        self._ipc_fallback_handlers: List[Callable] = []

    # ── Handler 管理 ──────────────────────────

    def add_handler(self, handler: Callable):
        """添加处理器到链末端。

        handler 签名: async def handler(event) -> None
        或同步: def handler(event) -> None

        多个 handler 按注册顺序依次执行（链式处理模式）。
        """
        if handler not in self._handlers:
            self._handlers.append(handler)

    def remove_handler(self, handler: Callable):
        """移除处理器。"""
        try:
            self._handlers.remove(handler)
        except ValueError:
            pass

    @property
    def handler_count(self) -> int:
        return len(self._handlers)

    # ── 生命周期 ──────────────────────────────

    async def start(self):
        """启动 worker 池。"""
        if self._running:
            return
        self._running = True
        self._shutdown_event.clear()

        for i in range(self.workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._worker_tasks.append(task)

        _log.debug("Pipeline branch '%s' 已启动 (%d workers)", self.name, self.workers)

    async def stop(self):
        """停止 worker 池，清空队列。"""
        if not self._running:
            return
        self._running = False
        self._shutdown_event.set()

        # 取消所有 worker
        for task in self._worker_tasks:
            task.cancel()
        self._worker_tasks.clear()

        # 清空队列
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        _log.debug(
            "Pipeline branch '%s' 已停止 (已处理=%d, 丢弃=%d, 超时=%d, 错误=%d)",
            self.name, self.total_processed, self.total_dropped,
            self.total_timeouts, self.total_errors,
        )

    # ── 入队 ──────────────────────────────────

    async def push(self, event) -> bool:
        """推入事件到此分支的队列。

        Returns:
            True 表示入队成功，False 表示队列满被丢弃。
        """
        self.last_push_time = time.time()

        if self.queue.full():
            self.total_dropped += 1
            _log.warning(
                "Pipeline branch '%s' 队列满 (max=%d), 事件被丢弃: %s",
                self.name, self.max_queue, type(event).__name__,
            )
            return False

        await self.queue.put(event)
        return True

    def push_nowait(self, event) -> bool:
        """同步入队（不阻塞）。"""
        self.last_push_time = time.time()

        if self.queue.full():
            self.total_dropped += 1
            return False

        self.queue.put_nowait(event)
        return True

    # ── Worker 循环 ───────────────────────────

    async def _worker_loop(self, worker_id: int):
        """Worker 协程：从队列取事件 → 依次执行 handler 链。"""
        while self._running:
            try:
                # 等待事件（1s 超时，可响应 shutdown）
                event = await asyncio.wait_for(
                    self.queue.get(), timeout=1.0
                )
                await self._execute_chain(event)
                self.total_processed += 1
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                _log.exception(
                    "Pipeline branch '%s' worker-%d 异常",
                    self.name, worker_id,
                )

    async def _execute_chain(self, event):
        """依次执行 handler 链。"""
        if not self._handlers:
            return

        for handler in self._handlers:
            handler_name = getattr(handler, '__name__', repr(handler))
            try:
                if asyncio.iscoroutinefunction(handler):
                    await asyncio.wait_for(
                        handler(event),
                        timeout=self.timeout,
                    )
                else:
                    handler(event)
            except asyncio.TimeoutError:
                self.total_timeouts += 1
                _log.error(
                    "Pipeline branch '%s' handler '%s' 超时 (%.1fs)",
                    self.name, handler_name, self.timeout,
                )
            except Exception:
                self.total_errors += 1
                _log.exception(
                    "Pipeline branch '%s' handler '%s' 异常",
                    self.name, handler_name,
                )

    # ── IPC 传输 ─────────────────────────────

    def enable_ipc(self, ipc_pool=None, serializer=None):
        """将本分支的处理器迁移到 IPC worker 池中执行。

        Worker 进程崩溃不影响主进程，自动故障转移。

        工作原理:
          1. 保存当前 handler 链作为故障转移后备
          2. 注入 IPC dispatcher 作为新 handler
          3. 事件进入队列后 → IPC dispatcher → worker 进程 → 处理 → 结果回传
          4. worker 不可用时自动降级为本地处理

        Args:
            ipc_pool: WorkerPool 实例或任何实现了 call(method, params) 的对象。
            serializer: EventSerializer 兼容的序列化器（默认自动导入）。

        Example:
            branch = engine.get_branch("ai_processing")
            branch.enable_ipc(pool)
            # 此后 AI 处理在 worker 进程中执行，主进程不阻塞
        """
        if ipc_pool is None:
            raise ValueError("ipc_pool 不能为 None")

        if serializer is None:
            # Try multiple import paths for EventSerializer
            for path in ['core.ipc.bridge', 'qqlinker_framework.core.ipc.bridge']:
                try:
                    mod = __import__(path, fromlist=['EventSerializer'])
                    serializer = mod.EventSerializer
                    break
                except ImportError:
                    continue
            if serializer is None:
                raise ImportError(
                    "'core.ipc.bridge' 不可用。"
                    "请先确保 core/ipc/bridge.py 存在"
                )

        # 保存原 handler 链作为故障转移后备
        self._ipc_fallback_handlers = list(self._handlers)
        self._ipc_pool = ipc_pool
        self._ipc_serializer = serializer
        self._ipc_enabled = True

        # 替换 handler 链为 IPC dispatcher
        self._handlers.clear()
        self.add_handler(self._ipc_dispatch_handler)

        _log.info(
            "Pipeline branch '%s' 已启用 IPC 传输 (fallback=%d handlers)",
            self.name, len(self._ipc_fallback_handlers),
        )

    def disable_ipc(self):
        """禁用 IPC 传输，恢复本地 handler 链。"""
        if not getattr(self, '_ipc_enabled', False):
            return

        self._handlers.clear()
        if hasattr(self, '_ipc_fallback_handlers'):
            for handler in self._ipc_fallback_handlers:
                self.add_handler(handler)

        self._ipc_enabled = False
        _log.info("Pipeline branch '%s' 已禁用 IPC 传输", self.name)

    async def _ipc_dispatch_handler(self, event):
        """IPC 调度 handler — 序列化事件 → IPC → worker → 处理。"""
        import asyncio
        import time

        pool = getattr(self, '_ipc_pool', None)
        serializer = getattr(self, '_ipc_serializer', None)
        if pool is None or serializer is None:
            await self._ipc_fallback(event)
            return

        try:
            # 序列化事件
            serialized = serializer.serialize_event(event, topic=self.name)

            # 通过 IPC 发送（call 等待结果, notify 不等待）
            if hasattr(pool, 'call'):
                try:
                    result = await asyncio.wait_for(
                        pool.call("pipeline.process", serialized),
                        timeout=self.timeout,
                    )
                    if isinstance(result, dict) and '_type' in result:
                        # Worker 返回了修改后的事件
                        rebuilt = serializer.deserialize(result)
                        # 不重新入队，直接应用回原事件
                    self.total_processed += 1
                except asyncio.TimeoutError:
                    self.total_timeouts += 1
                    _log.warning(
                        "Pipeline branch '%s' IPC 调度超时 (%.1fs)，回退到本地",
                        self.name, self.timeout,
                    )
                    await self._ipc_fallback(event)
            elif hasattr(pool, 'notify'):
                await pool.notify("pipeline.event", serialized)
                self.total_processed += 1
            else:
                await self._ipc_fallback(event)

        except Exception as exc:
            self.total_errors += 1
            _log.error(
                "Pipeline branch '%s' IPC 调度异常: %s，回退到本地",
                self.name, exc,
            )
            await self._ipc_fallback(event)

    async def _ipc_fallback(self, event):
        """IPC 故障转移 — 使用原 handler 链本地处理。"""
        handlers = getattr(self, '_ipc_fallback_handlers', [])
        if not handlers:
            return
        for handler in handlers:
            handler_name = getattr(handler, '__name__', repr(handler))
            try:
                if asyncio.iscoroutinefunction(handler):
                    await asyncio.wait_for(
                        handler(event),
                        timeout=self.timeout,
                    )
                else:
                    handler(event)
            except asyncio.TimeoutError:
                _log.error(
                    "IPC fallback handler '%s' 超时", handler_name,
                )
            except Exception:
                _log.exception(
                    "IPC fallback handler '%s' 异常", handler_name,
                )

    @property
    def ipc_enabled(self) -> bool:
        """检查 IPC 传输是否已启用。"""
        return getattr(self, '_ipc_enabled', False)

    # ── 查询 ──────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """返回分支统计信息。"""
        return {
            "name": self.name,
            "workers": self.workers,
            "timeout": self.timeout,
            "handlers": self.handler_count,
            "queue_size": self.queue.qsize(),
            "max_queue": self.max_queue,
            "total_processed": self.total_processed,
            "total_dropped": self.total_dropped,
            "total_timeouts": self.total_timeouts,
            "total_errors": self.total_errors,
            "last_push": self.last_push_time,
            "running": self._running,
            "ipc_enabled": self._ipc_enabled,
        }


# ═══════════════════════════════════════════════════════════
# 内置分支默认配置
# ═══════════════════════════════════════════════════════════

def _default_branches() -> Dict[str, PipelineBranch]:
    """创建内置分支。

    admin_commands: 管理命令（高优先级，小队列，快速处理）
    game_commands:  游戏命令（高频，多 worker）
    ai_processing:  AI 处理（慢，长超时，小队列防堆积）
    general:        通用消息（默认路由）
    background:     后台任务（低优先级，单 worker）
    """
    return {
        "admin_commands": PipelineBranch(
            "admin_commands",
            workers=2,
            timeout=10.0,
            max_queue=50,
        ),
        "game_commands": PipelineBranch(
            "game_commands",
            workers=4,
            timeout=5.0,
            max_queue=200,
        ),
        "ai_processing": PipelineBranch(
            "ai_processing",
            workers=2,
            timeout=120.0,
            max_queue=20,
        ),
        "general": PipelineBranch(
            "general",
            workers=4,
            timeout=30.0,
            max_queue=500,
        ),
        "background": PipelineBranch(
            "background",
            workers=1,
            timeout=60.0,
            max_queue=100,
        ),
    }


# ═══════════════════════════════════════════════════════════
# PipelineEngine — 管道引擎控制器
# ═══════════════════════════════════════════════════════════

class PipelineEngine:
    """管道引擎 — 管理多个 PipelineBranch，按 topic 路由事件。

    用法:
        engine = PipelineEngine(event_bus)
        await engine.start()

        # 声明路由映射
        engine.declare_topic("admin_commands", "admin_commands")
        engine.declare_topic("game_commands", "game_commands")
        engine.declare_topic("ai_processing", "ai_processing")

        # 注册 handler
        engine.get_branch("admin_commands").add_handler(admin_handler)

        # 路由事件
        await engine.route(event, topic="admin_commands")

        await engine.stop()
    """

    def __init__(self, event_bus=None):
        """初始化管道引擎。

        Args:
            event_bus: LaneRouter 实例（可选，用于订阅事件）。
        """
        self._event_bus = event_bus
        self._branches: Dict[str, PipelineBranch] = {}
        self._topic_map: Dict[str, str] = {}  # topic → branch_name
        self._running = False

        # 创建内置分支
        builtin = _default_branches()
        self._branches.update(builtin)

        # 默认 topic 映射（topic → branch 同名）
        for name in builtin:
            self._topic_map[name] = name

    # ── 分支管理 ──────────────────────────────

    def create_branch(self, name: str, workers: int = 2,
                      timeout: float = 30.0, max_queue: int = 100) -> PipelineBranch:
        """创建命名分支。

        如果分支已存在，返回已有分支。
        自动声明分支名称为 topic（可直接用 name 路由）。
        """
        if name in self._branches:
            return self._branches[name]

        branch = PipelineBranch(
            name=name,
            workers=workers,
            timeout=timeout,
            max_queue=max_queue,
        )
        self._branches[name] = branch

        # 自动声明分支名称为 topic
        self._topic_map.setdefault(name, name)

        # 如果引擎已启动，立即启动新分支
        if self._running:
            asyncio.create_task(branch.start())

        _log.info("Pipeline branch 已创建: %s (workers=%d, timeout=%.1f)",
                  name, workers, timeout)
        return branch

    def get_branch(self, name: str) -> Optional[PipelineBranch]:
        """获取分支（不存在返回 None）。"""
        return self._branches.get(name)

    def has_branch(self, name: str) -> bool:
        """检查分支是否存在。"""
        return name in self._branches

    def list_branches(self) -> List[str]:
        """列出所有分支名称。"""
        return list(self._branches.keys())

    # ── Topic 路由映射 ────────────────────────

    def declare_topic(self, topic: str, branch_name: str):
        """声明 topic → branch 映射。

        模块可调用此方法将 topic 路由到特定分支。
        如: engine.declare_topic("ai_processing", "ai_processing")
        """
        self._topic_map[topic] = branch_name
        _log.debug("Topic 映射: '%s' → branch '%s'", topic, branch_name)

    def get_topic_branch(self, topic: str) -> str:
        """获取 topic 对应的分支名。未声明则返回 "general"。"""
        return self._topic_map.get(topic, "general")

    def list_topics(self) -> Dict[str, str]:
        """列出所有 topic → branch 映射。"""
        return dict(self._topic_map)

    # ── 生命周期 ──────────────────────────────

    async def start(self):
        """启动所有分支的 worker 池。"""
        if self._running:
            return

        for name, branch in self._branches.items():
            await branch.start()

        self._running = True
        _log.info("PipelineEngine 已启动 (%d 个分支)", len(self._branches))

    async def stop(self):
        """停止所有分支。"""
        if not self._running:
            return

        self._running = False

        for name, branch in list(self._branches.items()):
            await branch.stop()

        _log.info("PipelineEngine 已停止")

    # ── 事件路由 ──────────────────────────────

    async def route(self, event, topic: str = "general") -> bool:
        """将事件路由到对应分支的队列。

        Args:
            event: 事件对象。
            topic: 主题字符串，决定路由到哪个分支。

        Returns:
            True 表示入队成功，False 表示被丢弃。
        """
        branch_name = self._topic_map.get(topic, "general")
        branch = self._branches.get(branch_name)

        if branch is None:
            # 自动创建缺失分支
            branch = self.create_branch(
                name=branch_name,
                workers=2,
                timeout=30.0,
                max_queue=100,
            )

        return await branch.push(event)

    # ── 事件总线的回调 ────────────────────────

    async def _on_chat_event(self, event):
        """LaneRouter 的 GroupMessageEvent 回调。

        解析事件中的 topic 信息并路由到对应管道分支。
        如果事件已被处理（handled=True），则跳过。
        """
        # 跳过已处理的事件
        if getattr(event, 'handled', False):
            return

        # 从事件中提取 topic（由命令注册表或模块指定）
        topic = getattr(event, 'pipeline_topic', None) or "general"

        await self.route(event, topic=topic)

    # ── 统计查询 ──────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """返回所有分支的统计信息。"""
        return {
            name: branch.stats()
            for name, branch in self._branches.items()
        }

    def branch_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """返回指定分支的统计信息。"""
        branch = self._branches.get(name)
        if branch is None:
            return None
        return branch.stats()

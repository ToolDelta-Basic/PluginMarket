"""事件循环心跳看门狗 — 假死检测 + 降级恢复

═══════════════════════════════════════════════════════════════════════════
 设计
═══════════════════════════════════════════════════════════════════════════
 · last_event_loop_heartbeat  — 记录事件循环最后一次心跳时间
 · _heartbeat_loop()           — 每 N 秒更新时间戳（需要事件循环响应）
 · _watchdog_loop()             — 外部线程同步检查心跳是否过期
 · 假死处理                    — 停用非核心服务（优雅降级）而非直接崩溃
 ═══════════════════════════════════════════════════════════════════════════

 集成:
   - host.py: start() 中通过 monitoring 模块或直接导入启动
   - degradation.py: 假死时调用 degrade_all_noncritical()
 ═══════════════════════════════════════════════════════════════════════════
"""
import asyncio
import logging
import os
import time
import threading
from typing import Optional

_log = logging.getLogger(__name__)

# ── 常量 ──
DEFAULT_WATCHDOG_INTERVAL = 10.0          # 监控线程检查间隔
DEFAULT_HEARTBEAT_TIMEOUT = 30.0          # 心跳超时（认为事件循环已假死）
DEFAULT_HEARTBEAT_INTERVAL = 2.0          # 心跳更新间隔
DEFAULT_RECOVERY_GRACE = 10.0             # 降级后的恢复观察期
MAX_CONSECUTIVE_TIMEOUTS = 3              # 连续超时次数阈值（超过才触发降级）


class EventLoopWatchdog:
    """事件循环假死检测看门狗。

    通过记录 last_event_loop_heartbeat 时间戳，由独立线程
    定期检查事件循环是否仍在响应。

    假死时执行降级（停用非核心服务）而非直接崩溃。
    连续多次超时后才触发降级，避免偶发 GC 暂停误报。
    """

    def __init__(
        self,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
        degradation=None,
        *,
        heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
        watchdog_interval: float = DEFAULT_WATCHDOG_INTERVAL,
        recovery_grace: float = DEFAULT_RECOVERY_GRACE,
    ):
        # 如果未提供事件循环，使用当前运行中的或默认
        if event_loop is None:
            try:
                event_loop = asyncio.get_running_loop()
            except RuntimeError:
                event_loop = asyncio.get_event_loop()
        self._loop = event_loop

        self._degradation = degradation

        self._heartbeat_timeout = heartbeat_timeout
        self._heartbeat_interval = heartbeat_interval
        self._watchdog_interval = watchdog_interval
        self._recovery_grace = recovery_grace

        # ── 心跳时间戳（由事件循环中的协程更新）──
        self._last_event_loop_heartbeat: float = 0.0

        # ── 运行时状态 ──
        self._watchdog_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._stopped = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        # ── 假死检测状态 ──
        self._consecutive_timeouts: int = 0
        self._last_timeout_at: float = 0.0
        self._degradation_applied: bool = False
        self._frozen_count: int = 0

        # ── 模块级超时检测 ──
        self._module_last_active: dict[str, float] = {}
        self._module_timeout_seconds: float = 60.0

        # ── 监控统计 ──
        self._total_checks: int = 0
        self._total_healthy: int = 0
        self._total_missed: int = 0
        self._total_degradations: int = 0

    # ═══════════════════════════════════════════════════════════
    # 心跳更新（由事件循环中的协程调用）
    # ═══════════════════════════════════════════════════════════

    def update_heartbeat(self) -> None:
        """更新事件循环心跳时间戳（由事件循环协程调用）。"""
        self._last_event_loop_heartbeat = time.time()

    # ═══════════════════════════════════════════════════════════
    # 模块级超时检测
    # ═══════════════════════════════════════════════════════════

    def update_module_activity(self, module_name: str) -> None:
        """记录模块的最后活跃时间。

        模块每次完成一轮处理（如一条消息、一次定时任务）后
        应调用此方法更新时间戳。

        Args:
            module_name: 模块名称。
        """
        self._module_last_active[module_name] = time.time()

    def _check_module_timeouts(self, now: float) -> None:
        """检查是否有模块超过超时阈值未更新且仍在加载列表中。

        超时的模块记录 ERROR 日志，不会自动触发降级。

        Args:
            now: 当前时间戳。
        """
        if not self._module_last_active:
            return
        for mod_name, last_ts in list(self._module_last_active.items()):
            elapsed = now - last_ts
            if elapsed > self._module_timeout_seconds:
                _log.error(
                    "⏰ 模块 '%s' 超时: %.1fs 未更新活跃状态 (阈值: %.1fs)",
                    mod_name, elapsed, self._module_timeout_seconds,
                )

    async def _heartbeat_loop(self) -> None:
        """事件循环内心跳协程: 每 N 秒更新时间戳。"""
        while not self._stopped:
            try:
                # 更新心跳
                self.update_heartbeat()
                # 等待下次更新
                await asyncio.sleep(self._heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.error("心跳协程异常: %s", e)
                await asyncio.sleep(1.0)  # 异常后短暂退避

    # ═══════════════════════════════════════════════════════════
    # 监控线程（独立于事件循环）
    # ═══════════════════════════════════════════════════════════

    def _watchdog_loop(self) -> None:
        """监控线程主循环: 检查事件循环心跳是否过期。"""
        _log.info(
            "看门狗线程已启动 (timeout=%.1fs, interval=%.1fs)",
            self._heartbeat_timeout, self._watchdog_interval,
        )
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._watchdog_interval)
            if self._stopped:
                break

            self._total_checks += 1
            now = time.time()

            if self._last_event_loop_heartbeat == 0.0:
                # 尚未开始心跳（初始化阶段）
                continue

            elapsed = now - self._last_event_loop_heartbeat
            if elapsed > self._heartbeat_timeout:
                # 心跳超时
                self._total_missed += 1
                self._consecutive_timeouts += 1
                self._last_timeout_at = now
                _log.error(
                    "⚠️ 事件循环假死检测: 心跳超时 %.1fs (已连续 %d 次)",
                    elapsed, self._consecutive_timeouts,
                )

                # ── 模块级超时检测 ──
                self._check_module_timeouts(now)

                if (self._consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS
                        and not self._degradation_applied):
                    self._handle_frozen()
            else:
                # 心跳正常
                self._total_healthy += 1
                if self._consecutive_timeouts > 0:
                    _log.info(
                        "✅ 事件循环已恢复 (上次超时 %.1fs 前)",
                        now - self._last_timeout_at,
                    )
                self._consecutive_timeouts = 0

                # 降级后恢复检测
                if self._degradation_applied:
                    if elapsed < self._recovery_grace:
                        _log.info(
                            "事件循环正在恢复观察期 (%.1fs < %.1fs)",
                            elapsed, self._recovery_grace,
                        )
                    else:
                        _log.info("✅ 降级后观察期结束，事件循环稳定运行")
                        self._degradation_applied = False

    def _handle_frozen(self) -> None:
        """处理事件循环假死: 执行降级而非直接崩溃。

        降级动作:
          1. 记录假死事件
          2. 调用 degradation.degrade_all_noncritical() 停用非核心服务
          3. 尝试触发事件循环中的降级回调
        """
        self._frozen_count += 1
        self._degradation_applied = True
        _log.critical(
            "🧊 事件循环假死 (第 %d 次), 连续 %d 次超时。执行紧急降级...",
            self._frozen_count, self._consecutive_timeouts,
        )

        # ── 模块级超时检测（假死时也检查一次）──
        self._check_module_timeouts(time.time())

        # ── 降级: 停用非核心服务 ──
        if self._degradation is not None:
            try:
                degraded = self._degradation.degrade_all_noncritical()
                self._total_degradations += 1
                _log.warning(
                    "紧急降级: 已停用 %d 个非核心服务: %s",
                    len(degraded), ", ".join(degraded) if degraded else "(无)",
                )
            except Exception as e:
                _log.error("紧急降级执行失败: %s", e)

        # ── 尝试写入假死标记文件（供外部 cron/monitor 读取）──
        try:
            frozen_path = "/tmp/qqlinker_framework_frozen"
            with open(frozen_path, 'w') as f:
                f.write(str(int(time.time())))
        except OSError:
            pass

        # ── 触发事件循环中的降级回调（如果循环本身恢复）──
        if not self._stopped:
            try:
                self._loop.call_soon_threadsafe(
                    lambda: _log.warning("事件循环已恢复响应 — 正在降级模式运行")
                )
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════

    async def start(self) -> None:
        """启动看门狗（必须在事件循环中调用）。"""
        if self._stopped:
            return

        # 启动事件循环内心跳协程
        self.update_heartbeat()  # 初始心跳
        self._heartbeat_task = self._loop.create_task(self._heartbeat_loop())

        # 启动独立监控线程
        if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name="watchdog-thread",
                daemon=True,
            )
            self._watchdog_thread.start()

        _log.info(
            "事件循环看门狗已启动 (heartbeat=%.1fs, watchdog=%.1fs, timeout=%.1fs)",
            self._heartbeat_interval, self._watchdog_interval, self._heartbeat_timeout,
        )

    async def stop(self) -> None:
        """停止看门狗。"""
        if self._stopped:
            return
        self._stopped = True
        self._stop_event.set()

        # 取消心跳协程，防止 pending task
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # 清理假死标记文件
        try:
            frozen_path = "/tmp/qqlinker_framework_frozen"
            if os.path.exists(frozen_path):
                os.unlink(frozen_path)
        except OSError:
            pass

        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=5.0)
            if self._watchdog_thread.is_alive():
                _log.warning("看门狗线程未能在 5s 内退出")

        _log.info(
            "看门狗已停止 (总检查=%d, 健康=%d, 超时=%d, 降级=%d, 假死=%d)",
            self._total_checks, self._total_healthy,
            self._total_missed, self._total_degradations, self._frozen_count,
        )

    # ═══════════════════════════════════════════════════════════
    # 状态查询
    # ═══════════════════════════════════════════════════════════

    @property
    def last_heartbeat_ts(self) -> float:
        """返回最后一次心跳时间戳。"""
        return self._last_event_loop_heartbeat

    @property
    def seconds_since_last_heartbeat(self) -> float:
        """返回距离上次心跳的秒数。"""
        if self._last_event_loop_heartbeat == 0.0:
            return -1.0
        return time.time() - self._last_event_loop_heartbeat

    @property
    def is_frozen(self) -> bool:
        """当前是否认为事件循环假死。"""
        if self._last_event_loop_heartbeat == 0.0:
            return False
        return (time.time() - self._last_event_loop_heartbeat) > self._heartbeat_timeout

    @property
    def consecutive_timeouts(self) -> int:
        """连续超时次数。"""
        return self._consecutive_timeouts

    @property
    def degradation_applied(self) -> bool:
        """是否已应用紧急降级。"""
        return self._degradation_applied

    def get_stats(self) -> dict:
        """返回看门狗统计信息。"""
        return {
            "total_checks": self._total_checks,
            "total_healthy": self._total_healthy,
            "total_missed": self._total_missed,
            "total_degradations": self._total_degradations,
            "frozen_count": self._frozen_count,
            "consecutive_timeouts": self._consecutive_timeouts,
            "degradation_applied": self._degradation_applied,
            "last_heartbeat": self._last_event_loop_heartbeat,
            "seconds_since_heartbeat": self.seconds_since_last_heartbeat,
        }

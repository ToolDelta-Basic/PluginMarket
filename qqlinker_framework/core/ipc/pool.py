"""WorkerPool — 子进程池管理.

特性:
    - 用 subprocess 启停 worker 进程
    - 崩溃自动重启，最多 3 次 / 5 分钟
    - 入口指向 core.ipc.worker
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

RESTART_LIMIT = 3
RESTART_WINDOW = 300  # 5 分钟 (秒)


class WorkerPool:
    """管理一组 worker 子进程."""

    def __init__(self, socket_path: str, count: int = 1) -> None:
        self._path = socket_path
        self._count = max(count, 1)
        self._processes: list[asyncio.subprocess.Process] = []
        self._restarts: list[float] = []  # 重启时间戳
        # v11: 可自定义 worker 启动命令
        self._worker_cmd: list = []
        # v1.4.3: 停止标志 + monitor task 追踪（防止 pending task）
        self._stopping = False
        self._monitor_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """启动所有 worker 进程."""
        for i in range(self._count):
            await self._start_one(i)
        logger.info("WorkerPool started %d worker(s)", self._count)

    async def stop_all(self) -> None:
        """停止所有 worker 进程并取消所有 monitor task。"""
        self._stopping = True
        # 取消所有 monitor task，防止 pending task
        for task in list(self._monitor_tasks):
            task.cancel()
        if self._monitor_tasks:
            await asyncio.gather(*self._monitor_tasks, return_exceptions=True)
        self._monitor_tasks.clear()
        for proc in self._processes:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
        self._processes.clear()
        # 清理 socket
        try:
            os.unlink(self._path)
        except OSError:
            pass
        logger.info("WorkerPool stopped")

    async def _start_one(self, index: int) -> None:
        """启动一个 worker 进程并启动监控."""
        if self._worker_cmd:
            cmd = self._worker_cmd
        else:
            cmd = [sys.executable, "-m", "core.ipc.worker", self._path]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes.append(proc)
        logger.info("Worker %d started (pid=%d)", index, proc.pid)
        # 后台监控
        task = asyncio.create_task(self._monitor(index, proc))
        self._monitor_tasks.add(task)
        task.add_done_callback(self._monitor_tasks.discard)

    async def _monitor(self, index: int, proc: asyncio.subprocess.Process) -> None:
        """监控 worker 进程退出并决定是否重启。"""
        try:
            await proc.wait()
        except asyncio.CancelledError:
            # stop_all 取消时直接退出
            return
        logger.warning("Worker %d (pid=%d) exited with code %d", index, proc.pid, proc.returncode)

        # 停止中不重启
        if self._stopping:
            return

        # 清理重启记录 (滑动窗口)
        now = time.time()
        self._restarts = [t for t in self._restarts if now - t < RESTART_WINDOW]

        if len(self._restarts) >= RESTART_LIMIT:
            logger.error(
                "Worker %d: restart limit reached (%d in %ds), NOT restarting",
                index, RESTART_LIMIT, RESTART_WINDOW,
            )
            return

        self._restarts.append(now)
        delay = min(2 ** len(self._restarts), 10)  # 指数退避
        logger.info("Worker %d: restarting in %.1fs", index, delay)
        await asyncio.sleep(delay)
        # 在池中移除旧进程引用
        try:
            self._processes.remove(proc)
        except ValueError:
            pass
        await self._start_one(index)

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "WorkerPool":
        await self.start_all()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop_all()

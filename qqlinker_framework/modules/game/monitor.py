"""TPS 估算模块，通过定时执行 /list 命令测量服务器性能。"""
import asyncio
import time
from collections import deque
from typing import Optional

from ...core.module import Module
from ...core.decorators import command


class TPSService:
    """TPS 估算服务，维护滑动平均 TPS。"""

    def __init__(self, base_response: float = 0.05):
        self._tps = 20.0
        self._base = base_response
        self._history = deque(maxlen=20)
        self._lock = asyncio.Lock()

    def update(self, elapsed: float):
        """根据命令响应时间更新 TPS 估算。"""
        if elapsed <= 0:
            return
        est = max(1.0, 20.0 * (self._base / elapsed))
        self._history.append(est)
        self._tps = sum(self._history) / len(self._history)

    @property
    def tps(self) -> float:
        """返回当前滑动平均 TPS（保留一位小数）。"""
        return round(self._tps, 1)


class TPSMonitorModule(Module):
    """TPS 监控模块，提供 .性能 命令和 'tps' 服务。"""

    name = "tps_monitor"
    uid = 1000  # service: 服务引擎
    version = (1, 0, 0)

    default_config = {
        "TPS监控": {
            "测量间隔秒": 30,
            "基础响应时间": 0.05,
            "命令超时": 3.0,
        }
    }
    version = (1, 0, 0)
    required_services = ["config", "adapter"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._interval = None
        self._cmd_timeout = None
        self._service = None
        self._task = None

    async def on_init(self):
        """注册配置节、初始化服务、启动后台测量。"""

        async def _dbg_tps():
            """调试端点。"""
            svc = self.services.get("tps")
            return str({"tps": getattr(svc, "tps", "N/A")})

        try:
            debug = self.services.get("debug")
            await debug.register_module(
                self.name, {"tps": _dbg_tps}
            )
        except KeyError:
            pass

        cfg = self.config.get("TPS监控")
        self._interval = cfg.get("测量间隔秒", 30)
        base_resp = cfg.get("基础响应时间", 0.05)
        self._cmd_timeout = cfg.get("命令超时", 3.0)

        self._service = TPSService(base_response=base_resp)
        self.services.register("tps", self._service)

        self.register_command(
            ".性能", self._cmd_tps,
            description="查看服务器 TPS 估算值",
        )

        self._task = asyncio.ensure_future(self._measure_loop())

    async def on_stop(self):
        """模块停止时取消后台测量任务。"""
        if self._task:
            self._task.cancel()

    async def _measure_loop(self):
        """后台循环，定期发送 /list 命令并计算 TPS。"""
        while True:
            try:
                await asyncio.sleep(self._interval)
                start = time.monotonic()
                resp = self.adapter.send_game_command_with_resp(
                    "/list", timeout=self._cmd_timeout
                )
                elapsed = time.monotonic() - start
                if resp is not None:
                    self._service.update(elapsed)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    @command(".性能")
    async def _cmd_tps(self, ctx):
        """回复当前 TPS 估算值。"""
        tps = self._service.tps
        await ctx.reply(f"当前服务器 TPS 估算：{tps} (参考值)")

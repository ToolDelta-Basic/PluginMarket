"""运行时守护引导库 — 从 host.py.start() 提取。

职责：资源守护者、健康评分、TelemetryHub、看门狗、StressTester。
"""
import logging

from ..core.kernel.services import TIER_DAEMON, MID_SERVICE

_log = logging.getLogger(__name__)


class RuntimeBootstrap:
    """运行时守护服务引导库。"""

    async def mount(self, host) -> None:
        logger = logging.getLogger(__name__)

        # 资源守护者
        await host.guardian.start()
        host.services.register("guardian", host.guardian, uid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")

        # 健康评分
        host.services.register("health_scorer", host.health_scorer, uid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")

        # TelemetryHub
        host.services.register("telemetry", host.telemetry, uid=MID_SERVICE,
                               _caller="qqlinker_framework.core.host")
        logger.info("TelemetryHub 已注册")

        logger.info("模块健康评分器已注册")

        # 看门狗
        try:
            from ..core.drivers.watchdog import EventLoopWatchdog
            host._watchdog = EventLoopWatchdog(
                event_loop=host._main_loop,
                degradation=host.degradation,
            )
            await host._watchdog.start()
            host.services.register("watchdog", host._watchdog, uid=TIER_DAEMON,
                                   _caller="qqlinker_framework.core.host")
        except Exception as e:
            logger.warning("看门狗启动失败（非关键）: %s", e)
            host.degradation.on_service_fail("watchdog", str(e), e)

        # StressTester
        try:
            from ..core.kernel.stress_tester import StressTester
            host._stress_tester = StressTester(host, data_path=host.data_path)
            host._stress_tester.start()
        except Exception as e:
            logger.warning("StressTester 启动失败（非关键）: %s", e)

    async def unmount(self, host) -> None:
        pass

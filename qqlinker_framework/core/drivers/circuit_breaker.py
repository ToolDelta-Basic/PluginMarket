import asyncio
import logging
import time
from typing import Dict, Optional

# ── 熔断器常量 ──
CIRCUIT_BREAKER_WINDOW = 60.0       # 60 秒故障窗口
CIRCUIT_BREAKER_THRESHOLD = 3       # 窗口内 3 次连续失败触发熔断
CIRCUIT_BREAKER_COOLDOWN = 120.0    # 熔断 120 秒后尝试恢复

_logger = logging.getLogger(__name__)


class CircuitBreaker:
    """模块级熔断器。

    跟踪各模块的失败计数，超过阈值后熔断，冷却后半开恢复。

    状态结构:
        _breakers[module_name] = {
            "failures": [(timestamp, error_type), ...],
            "open_since": timestamp or 0,
            "total_failures": int,
        }
    """

    def __init__(
        self,
        window: float = CIRCUIT_BREAKER_WINDOW,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        cooldown: float = CIRCUIT_BREAKER_COOLDOWN,
        services=None,
    ):
        self._breakers: Dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._window = window
        self._threshold = threshold
        self._cooldown = cooldown
        self._services = services

    async def is_open(self, module_name: str) -> bool:
        """检查模块熔断器是否开启。返回 True 表示熔断中（拒绝执行）。"""
        async with self._lock:
            cb = self._breakers.get(module_name)
            if cb is None:
                return False
            if cb.get("open_since", 0) > 0:
                elapsed = time.time() - cb["open_since"]
                if elapsed < self._cooldown:
                    remain = self._cooldown - elapsed
                    _logger.warning(
                        "熔断器: 模块 '%s' 已熔断 (剩余 %.0fs)",
                        module_name, remain,
                    )
                    return True
                else:
                    # 熔断期结束，尝试半开（half-open）恢复
                    cb["open_since"] = 0.0
                    _logger.info(
                        "熔断器: 模块 '%s' 进入半开恢复状态", module_name,
                    )
                    return False
            return False

    async def record_failure(self, module_name: str, error: str = "") -> None:
        """记录模块命令执行失败，超过阈值则熔断。"""
        now = time.time()
        async with self._lock:
            if module_name not in self._breakers:
                self._breakers[module_name] = {
                    "failures": [],
                    "open_since": 0.0,
                    "total_failures": 0,
                }
            cb = self._breakers[module_name]

            recent = [f for f in cb["failures"] if now - f[0] < self._window]
            recent.append((now, error[:100] if error else "unknown"))
            cb["failures"] = recent
            cb["total_failures"] += 1

            if len(recent) >= self._threshold:
                cb["open_since"] = now
                _logger.error(
                    "⚡ 熔断器触发: 模块 '%s' 在 %.0fs 内连续 %d 次失败，"
                    "已熔断 %ds",
                    module_name, self._window,
                    self._threshold, int(self._cooldown),
                )
                # 通知降级引擎
                try:
                    degradation = (
                        self._services.try_get("degradation")
                        if self._services else None
                    )
                    if degradation:
                        degradation.on_service_fail(
                            f"module:{module_name}",
                            f"circuit_breaker_open: {len(recent)} failures in {self._window}s",
                        )
                except Exception as e:
                    _logger.debug("熔断器通知降级引擎失败: %s", e)

    async def record_success(self, module_name: str) -> None:
        """命令执行成功后重置熔断器（半开恢复确认）。"""
        async with self._lock:
            if module_name in self._breakers:
                cb = self._breakers[module_name]
                if cb.get("open_since", 0) == 0.0 and len(cb.get("failures", [])) > 0:
                    cb["failures"] = []
                    _logger.info(
                        "熔断器: 模块 '%s' 已恢复 (半开确认)", module_name,
                    )
                    try:
                        degradation = (
                            self._services.try_get("degradation")
                            if self._services else None
                        )
                        if degradation:
                            degradation.clear_degraded(f"module:{module_name}")
                    except Exception as e:
                        _logger.debug("熔断器清除降级状态失败: %s", e)

    def get_status(self) -> Dict[str, dict]:
        """返回所有熔断器状态（供监控/控制台查询）。"""
        now = time.time()
        return {
            name: {
                "open": cb.get("open_since", 0) > 0,
                "open_since": cb.get("open_since", 0),
                "recent_failures": len(cb.get("failures", [])),
                "total_failures": cb.get("total_failures", 0),
                "cooldown_remaining": max(
                    0, self._cooldown - (now - cb.get("open_since", 0))
                ) if cb.get("open_since", 0) > 0 else 0,
            }
            for name, cb in self._breakers.items()
        }

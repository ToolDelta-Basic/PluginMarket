import logging
import time
from typing import Dict, List, Optional, Set

_log = logging.getLogger(__name__)

# ── 服务分级 ──
# 关键服务: 框架核心功能，失败意味着框架不可用
CRITICAL_SERVICES: Set[str] = {
    "command",     # 命令管理器
    "message",     # 消息管理器
    "config",      # 配置管理器
    "event_bus",   # 事件总线
    "adapter",     # 适配器
    "_host",       # 框架主机引用
    "services",    # 服务容器自身
}

# 非关键服务: 框架增强功能，失败不影响核心运行
NONCRITICAL_SERVICES: Set[str] = {
    "redis",          # Redis 缓存（去重引擎的分布式层）
    "dedup",          # 去重引擎
    "webpanel",       # Web 面板
    "debug_engine",   # 调试引擎
    "market_server",  # 模块市场服务器
    "market",         # 模块市场聚合器
    "ws_client",      # WebSocket 客户端（非核心）
    "guardian",       # 资源守护者
    "tool",           # 工具管理器
    "robot_registry", # 多机器人注册表
    "gatekeeper",     # 能力安全桥
}

# 可以降级加载的模块（required_services 中缺失非关键服务时不抛异常）
DEGRADABLE_SERVICES: Set[str] = NONCRITICAL_SERVICES.copy()


class GracefulDegradation:
    """优雅降级引擎: 服务失败时分级处理，非关键降级，关键恐慌。

    用法:
        degradation = GracefulDegradation(
            event_bus=event_bus,
            on_panic=my_panic_handler,
        )
        # 非关键服务失败
        degradation.on_service_fail("redis")
        # → 日志警告，记录降级状态，不崩溃
        #
        # 关键服务失败
        degradation.on_service_fail("command")
        # → 日志严重错误，发布 PanicEvent，调用 on_panic 回调
    """

    def __init__(
        self,
        event_bus=None,
        on_panic=None,
        critical_services: Optional[Set[str]] = None,
        noncritical_services: Optional[Set[str]] = None,
    ):
        self.event_bus = event_bus
        self.on_panic = on_panic

        self._critical = critical_services or CRITICAL_SERVICES.copy()
        self._noncritical = noncritical_services or NONCRITICAL_SERVICES.copy()

        # 降级状态追踪
        self._degraded: Dict[str, str] = {}    # service_name → reason
        self._degraded_modules: Dict[str, str] = {}  # module_name → reason
        self._last_failure: Dict[str, float] = {}  # service → timestamp

        # 恐慌状态
        self._panic_triggered: bool = False
        self._panic_reason: str = ""

        # 降级事件计数器
        self._degradation_count: int = 0
        self._panic_count: int = 0

    # ═══════════════════════════════════════════════════════════
    # 服务分级判断
    # ═══════════════════════════════════════════════════════════

    def is_critical(self, service_name: str) -> bool:
        """判断服务是否属于关键服务。"""
        return service_name in self._critical

    def is_noncritical(self, service_name: str) -> bool:
        """判断服务是否属于非关键服务。"""
        return service_name in self._noncritical

    def is_degradable(self, service_name: str) -> bool:
        """判断服务缺失时是否可以降级运行（而非崩溃）。"""
        return service_name in self._noncritical or service_name in DEGRADABLE_SERVICES

    # ═══════════════════════════════════════════════════════════
    # 服务失败处理
    # ═══════════════════════════════════════════════════════════

    def on_service_fail(
        self,
        service_name: str,
        reason: str = "",
        exc: Optional[Exception] = None,
    ) -> bool:
        """服务失败回调。返回 True 表示已降级处理，False 表示触发恐慌。

        非关键服务失败:
          - 记录 WARNING 日志
          - 记录降级状态
          - 增加降级计数器
          - 返回 True（已降级，调用方可继续）

        关键服务失败:
          - 记录 CRITICAL 日志
          - 触发恐慌
          - 增加恐慌计数器
          - 返回 False（恐慌，调用方应停止）
        """
        self._last_failure[service_name] = time.time()

        if self.is_critical(service_name):
            return self._handle_critical_failure(service_name, reason, exc)
        else:
            return self._handle_noncritical_failure(service_name, reason, exc)

    def on_module_fail(
        self,
        module_name: str,
        reason: str = "",
        exc: Optional[Exception] = None,
    ) -> bool:
        """模块失败回调。非关键模块降级，关键模块可能触发部分恐慌。"""
        self._degraded_modules[module_name] = reason
        self._degradation_count += 1

        exc_info = f": {exc}" if exc else ""
        _log.warning(
            "🔶 模块降级: '%s' (原因=%s)%s | 模块已隔离，框架继续运行",
            module_name, reason, exc_info,
        )
        # 模块失败始终降级（关键服务 = 基础设施，模块 = 业务逻辑）
        return True

    # ── 内部实现 ──

    def _handle_noncritical_failure(
        self, service_name: str, reason: str, exc: Optional[Exception]
    ) -> bool:
        """处理非关键服务失败: 降级运行。"""
        self._degraded[service_name] = reason or "initialization_failed"
        self._degradation_count += 1

        exc_info = f": {exc}" if exc else ""
        _log.warning(
            "🔶 服务降级: '%s' (非关键) — %s%s | 框架继续运行",
            service_name, reason or "初始化失败", exc_info,
        )
        return True

    def _handle_critical_failure(
        self, service_name: str, reason: str, exc: Optional[Exception]
    ) -> bool:
        """处理关键服务失败: 触发恐慌。"""
        self._panic_triggered = True
        self._panic_reason = f"关键服务 '{service_name}' 失败: {reason or '未知原因'}"
        self._panic_count += 1

        exc_info = f": {exc}" if exc else ""
        _log.critical(
            "🚨 恐慌: 关键服务 '%s' 失败 — %s%s | 框架可能无法正常运行",
            service_name, reason or "未知原因", exc_info,
        )

        # 异步发布 PanicEvent（如果事件总线可用）
        if self.event_bus is not None:
            try:
                import asyncio
                from .events import SystemPanicEvent
                event = SystemPanicEvent(
                    service=service_name,
                    reason=self._panic_reason,
                )
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self.event_bus.publish(event)
                    )
                except RuntimeError as e:
                    # 无运行中的事件循环（初始化早期阶段）
                    _log.debug("degradation._handle_critical_failure: %s", e)
            except ImportError as e:
                _log.debug("degradation.degradation: %s", e)

        # 调用外部恐慌回调
        if self.on_panic is not None:
            try:
                self.on_panic(self._panic_reason)
            except Exception as e:
                _log.error("恐慌回调本身也失败了: %s", e)

        return False

    # ═══════════════════════════════════════════════════════════
    # 批量降级（死锁 watchdog 使用）
    # ═══════════════════════════════════════════════════════════

    def degrade_all_noncritical(self) -> List[str]:
        """批量降级所有已注册的非关键服务（死锁恢复时使用）。

        Returns:
            被降级的服务名称列表。
        """
        degraded = []
        for service_name in list(self._noncritical):
            if service_name not in self._degraded:
                self._degraded[service_name] = "emergency_degradation"
                degraded.append(service_name)
                _log.warning(
                    "🔶 紧急降级: '%s' (假死恢复)", service_name
                )
        self._degradation_count += len(degraded)
        return degraded

    # ═══════════════════════════════════════════════════════════
    # 状态查询
    # ═══════════════════════════════════════════════════════════

    @property
    def is_degraded(self) -> bool:
        """是否有任何服务处于降级状态。"""
        return len(self._degraded) > 0

    @property
    def is_panicked(self) -> bool:
        """是否已触发恐慌。"""
        return self._panic_triggered

    @property
    def panic_reason(self) -> str:
        """恐慌原因。"""
        return self._panic_reason

    def get_degraded_services(self) -> Dict[str, str]:
        """返回所有已降级的服务及其原因。"""
        return dict(self._degraded)

    def get_degraded_modules(self) -> Dict[str, str]:
        """返回所有已降级的模块及其原因。"""
        return dict(self._degraded_modules)

    def get_status_summary(self) -> dict:
        """返回完整的降级状态摘要。"""
        return {
            "degraded_services": dict(self._degraded),
            "degraded_modules": dict(self._degraded_modules),
            "degradation_count": self._degradation_count,
            "panic_triggered": self._panic_triggered,
            "panic_reason": self._panic_reason,
            "panic_count": self._panic_count,
            "last_failures": {
                k: v for k, v in sorted(
                    self._last_failure.items(),
                    key=lambda x: x[1], reverse=True,
                )[:10]  # 最近 10 条
            },
        }

    def reset_panic(self) -> None:
        """重置恐慌状态（手动恢复后使用）。"""
        self._panic_triggered = False
        self._panic_reason = ""
        _log.info("恐慌状态已重置")

    def clear_degraded(self, service_name: str) -> bool:
        """清除指定服务的降级状态（服务恢复后使用）。"""
        if service_name in self._degraded:
            del self._degraded[service_name]
            _log.info("服务 '%s' 降级状态已清除", service_name)
            return True
        return False

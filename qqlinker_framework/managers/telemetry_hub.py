import collections
import logging
import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)


# ── MetricQuery 辅助类 ────────────────────────────────────────

class MetricQuery:
    """指标查询构建器 — 支持链式调用进行窗口聚合。

    用法:
        hub.metric("cmd.latency_ms").window(300).p50()
        hub.metric("ws.message.in").window(60).count()
        hub.metric("module.error").where(lambda m: m["module"] != "kernel").count()
    """

    def __init__(self, name: str, data: List[Tuple[float, Any]]):
        self._name = name
        self._data = data  # reference to the raw list
        self._window_seconds: Optional[float] = None
        self._predicate: Optional[Callable[[Any], bool]] = None

    def window(self, seconds: int) -> "MetricQuery":
        """设置时间窗口（秒），只考虑最近 N 秒内的数据点。"""
        self._window_seconds = seconds
        return self

    def where(self, pred: Callable[[Any], bool]) -> "MetricQuery":
        """设置过滤条件，pred 接受单个数据点 value 返回 bool。"""
        self._predicate = pred
        return self

    def _filtered(self) -> List[Any]:
        """返回经过窗口和条件过滤后的值列表（O(n) 单次扫描）。"""
        now = time.time()
        result = []
        # 从尾往前扫描（数据按时间升序，尾部最新）
        for ts, value in reversed(self._data):
            if self._window_seconds is not None:
                if now - ts > self._window_seconds:
                    break  # 超出窗口，更早的也不要了
            if self._predicate is not None:
                if not self._predicate(value):
                    continue
            result.append(value)
        result.reverse()  # 恢复时间升序
        return result

    # ── 聚合函数 ──

    def count(self) -> int:
        """返回窗口内的数据点数量。"""
        return len(self._filtered())

    def sum(self) -> float:
        """返回窗口内所有数据点的数值总和。"""
        vals = self._filtered()
        if not vals:
            return 0.0
        numeric = self._to_numbers(vals)
        return sum(numeric)

    def avg(self) -> float:
        """返回窗口内数据点的平均值。"""
        vals = self._filtered()
        numeric = self._to_numbers(vals)
        if not numeric:
            return 0.0
        return sum(numeric) / len(numeric)

    def p50(self) -> float:
        """返回窗口内数据点的中位数（50th percentile）。"""
        return self._percentile(50.0)

    def p95(self) -> float:
        """返回窗口内数据点的 95th percentile。"""
        return self._percentile(95.0)

    def p99(self) -> float:
        """返回窗口内数据点的 99th percentile。"""
        return self._percentile(99.0)

    def max(self) -> float:
        """返回窗口内最大值。"""
        numeric = self._to_numbers(self._filtered())
        if not numeric:
            return 0.0
        return max(numeric)

    def min(self) -> float:
        """返回窗口内最小值。"""
        numeric = self._to_numbers(self._filtered())
        if not numeric:
            return 0.0
        return min(numeric)

    def values(self) -> List[Any]:
        """返回经过窗口和条件过滤后的原始值列表。"""
        return self._filtered()

    # ── 内部辅助 ──

    def _to_numbers(self, vals: List[Any]) -> List[float]:
        """将值列表转为数值列表：非数值按 0 处理，dict 取 _payload。
        非阻塞且纯 Python，无第三方依赖。
        """
        result = []
        for v in vals:
            if isinstance(v, (int, float)):
                result.append(float(v))
            elif isinstance(v, dict):
                # 提取常见的数字字段
                num = None
                for field in ("elapsed_ms", "count", "latency", "value",
                              "size", "score"):
                    if field in v and isinstance(v[field], (int, float)):
                        num = v[field]
                        break
                if num is not None:
                    result.append(float(num))
                else:
                    result.append(0.0)
            else:
                result.append(0.0)
        return result

    def _percentile(self, pct: float) -> float:
        """使用最近邻方法计算分位数（纯 Python，单次排序）。"""
        numeric = self._to_numbers(self._filtered())
        if not numeric:
            return 0.0
        sorted_vals = sorted(numeric)
        n = len(sorted_vals)
        # 最近邻方法: rank = ceil(pct/100 * n)
        rank = math.ceil(pct / 100.0 * n)
        # rank 是 1-indexed
        idx = max(0, min(n - 1, rank - 1))
        return sorted_vals[idx]


# ── AlertRule ────────────────────────────────────────────────

class AlertRule:
    """告警规则定义。

    action 可取值:
      - "degrade_module": 降级触发模块
      - "log": 仅记录日志
      - callable: 自定义回调
    """

    def __init__(self, name: str, condition_fn: Callable[[], bool],
                 window: int, action: Any = "log",
                 cooldown: float = 60.0):
        self.name = name
        self.condition_fn = condition_fn
        self.window = window  # 检查间隔（秒）
        self.action = action
        self.cooldown = cooldown  # 触发后冷却时间
        self._last_check: float = 0.0
        self._last_trigger: float = 0.0
        self._trigger_count: int = 0

    def should_check(self, now: float) -> bool:
        """是否到了检查时间。"""
        return (now - self._last_check) >= self.window

    def in_cooldown(self, now: float) -> bool:
        """是否在冷却中。"""
        return self._last_trigger > 0 and (now - self._last_trigger) < self.cooldown

    def check_and_act(self, hub: "TelemetryHub") -> bool:
        """检查条件并在满足时触发 action。"""
        now = time.time()
        self._last_check = now
        if self.in_cooldown(now):
            return False
        try:
            if self.condition_fn():
                self._last_trigger = now
                self._trigger_count += 1
                _log.warning(
                    "告警 '%s' 触发 (第#%d 次)", self.name, self._trigger_count
                )
                self._execute_action(hub)
                return True
        except Exception as e:
            _log.error("告警 '%s' 条件检查异常: %s", self.name, e)
        return False

    def _execute_action(self, hub: "TelemetryHub") -> None:
        """执行告警动作。"""
        action = self.action
        if action == "log":
            return  # 日志已记录
        elif action == "degrade_module":
            if hasattr(hub, 'health_scorer') and hub.health_scorer:
                degradation = getattr(hub.health_scorer, 'degradation', None)
                if degradation is None and hasattr(hub, 'event_bus'):
                    # 尝试从 event_bus 或 services 获取降级引擎
                    pass
        elif callable(action):
            try:
                action(hub)
            except Exception as e:
                _log.error("告警 '%s' action 回调异常: %s", self.name, e)


# ── TelemetryHub ─────────────────────────────────────────────

class TelemetryHub:
    """统一可观测性中心 — 从所有系统组件收集指标、做窗口聚合、触发告警。

    用法:
        hub = TelemetryHub(event_bus, health_scorer)
        hub.record("module.command.done", {"module": "help", "elapsed_ms": 12})
        hub.metric("module.command.done").window(300).avg()
        hub.snapshot()
        hub.summary()
    """

    _MAX_WINDOW = 3600  # 最多保留 1h 数据

    def __init__(self, event_bus=None, health_scorer=None):
        self.event_bus = event_bus
        self.health_scorer = health_scorer
        self._metrics: Dict[str, List[Tuple[float, Any]]] = \
            collections.defaultdict(list)
        self._alerts: Dict[str, AlertRule] = {}
        self._start_time: float = time.time()

    # ── 记录 ──

    def record(self, name: str, value: Any) -> None:
        """记录一个指标点。O(1) 操作，append + 裁剪过期数据。

        name 如 'module.command.done', 'ws.message.in', 'module.lifecycle'。
        value 可以是任意类型（int/float/dict/str）。
        """
        now = time.time()
        self._metrics[name].append((now, value))
        # 裁剪超出窗口的旧数据（O(k) 其中 k 为过期项数量）
        self._trim_metric(name, now)

    def _trim_metric(self, name: str, now: float) -> None:
        """裁剪指定指标中超过 MAX_WINDOW 的旧数据点。"""
        data = self._metrics[name]
        cutoff = now - self._MAX_WINDOW
        # 从头部移除过期项（列表小，无需 deque）
        trim_idx = 0
        for ts, _val in data:
            if ts >= cutoff:
                break
            trim_idx += 1
        if trim_idx > 0:
            del data[:trim_idx]

    # ── 查询 ──

    def metric(self, name: str) -> MetricQuery:
        """创建指标查询: hub.metric('cmd.latency').window(300).p50()"""
        data = self._metrics.get(name, [])
        return MetricQuery(name, data)

    def snapshot(self) -> dict:
        """返回当前全量快照（不含原始数据，仅统计摘要）。"""
        now = time.time()
        result = {
            "uptime_seconds": round(now - self._start_time, 1),
            "metrics_count": len(self._metrics),
            "alerts_count": len(self._alerts),
            "metrics": {},
        }
        for name, data in list(self._metrics.items())[:50]:  # 最多 50 个指标
            # 聚合最近 300s 的数据
            q = MetricQuery(name, data).window(300)
            result["metrics"][name] = {
                "count": q.count(),
                "avg": q.avg(),
                "p50": q.p50(),
                "p95": q.p95(),
                "p99": q.p99(),
            }
        return result

    def summary(self) -> dict:
        """返回人类可读的健康摘要。"""
        now = time.time()
        uptime = now - self._start_time
        total_metrics = len(self._metrics)
        total_alerts = len(self._alerts)
        triggered_alerts = sum(
            1 for a in self._alerts.values() if a._trigger_count > 0
        )

        # 获取健康评分摘要
        health_summary = {}
        if self.health_scorer:
            try:
                health_summary = self.health_scorer.get_summary()
            except Exception as e:
                _log.debug("telemetry_hub.summary: %s", e)

        return {
            "uptime_seconds": round(uptime, 1),
            "uptime_human": self._format_duration(uptime),
            "total_metrics": total_metrics,
            "total_alerts": total_alerts,
            "triggered_alerts": triggered_alerts,
            "health": health_summary,
        }

    # ── 告警 ──

    def alert(self, name: str, condition_fn: Callable[[], bool],
              window: int = 60, action: Any = "log",
              cooldown: float = 60.0) -> AlertRule:
        """注册告警规则。

        Args:
            name: 告警名称
            condition_fn: 条件函数，返回 True 触发告警
            window: 检查间隔（秒）
            action: "log" / "degrade_module" / callable
            cooldown: 触发后冷却时间（秒）
        """
        rule = AlertRule(
            name=name,
            condition_fn=condition_fn,
            window=window,
            action=action,
            cooldown=cooldown,
        )
        self._alerts[name] = rule
        return rule

    def remove_alert(self, name: str) -> bool:
        """移除告警规则。"""
        if name in self._alerts:
            del self._alerts[name]
            return True
        return False

    async def check_alerts(self) -> List[str]:
        """检查所有告警规则（由框架定时调用）。"""
        triggered = []
        for name, rule in list(self._alerts.items()):
            now = time.time()
            if rule.should_check(now):
                if rule.check_and_act(self):
                    triggered.append(name)
        return triggered

    # ── 辅助 ──

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """将秒数格式化为人类可读字符串。"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        elif seconds < 86400:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"{h}h{m}m"
        else:
            d = int(seconds // 86400)
            h = int((seconds % 86400) // 3600)
            return f"{d}d{h}h"

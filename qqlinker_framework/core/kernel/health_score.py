import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

# ── 评分等级 ──────────────────────────────────────────────


def health_level(score: float) -> str:
    """评分 → 等级标签"""
    if score >= 80:
        return "healthy"
    elif score >= 60:
        return "attention"
    elif score >= 40:
        return "degraded"
    else:
        return "unhealthy"


def health_emoji(score: float) -> str:
    """评分 → emoji"""
    if score >= 80:
        return "✅"
    elif score >= 60:
        return "⚠️"
    elif score >= 40:
        return "🔶"
    else:
        return "🔴"


# ── 维度配置 ──────────────────────────────────────────────

@dataclass
class DimensionConfig:
    """单个评分维度的配置"""
    name: str
    max_score: float = 25.0  # 满分
    weight: float = 1.0      # 权重


DEFAULT_DIMENSIONS = {
    "stability":  DimensionConfig("stability", max_score=25.0),
    "performance": DimensionConfig("performance", max_score=25.0),
    "resource":   DimensionConfig("resource", max_score=25.0),
    "error":      DimensionConfig("error", max_score=25.0),
}


@dataclass
class ModuleHealthState:
    """单个模块的健康状态快照"""
    module_name: str
    score: float = 100.0
    dimensions: Dict[str, float] = field(default_factory=lambda: {
        "stability": 25.0,
        "performance": 25.0,
        "resource": 25.0,
        "error": 25.0,
    })

    # 原子计数器
    _start_count: int = 0
    _start_fail_count: int = 0
    _init_time: float = 0.0
    _cmd_total_time: float = 0.0
    _cmd_count: int = 0
    _cmd_fail_count: int = 0
    _violation_count: int = 0
    _degradation_count: int = 0
    _exception_count: int = 0

    # 防过高评分衰减
    _last_decay_time: float = 0.0

    def _decay_if_needed(self):
        """随时间自动衰减评分（模拟自然磨损）。"""
        now = time.time()
        if not self._last_decay_time:
            self._last_decay_time = now
            return
        elapsed = now - self._last_decay_time
        # 每小时衰减 0.5 分（仅对高性能/高资源维度）
        decay_days = elapsed / 3600.0
        if decay_days > 0.1:  # 至少 6 分钟
            decay_amount = min(2.0, decay_days * 0.5)
            # 缓慢衰减 performance 和 resource
            for dim in ("performance", "resource"):
                current = self.dimensions.get(dim, 25.0)
                # 不低于最大维度分-20
                floor = max(0, self.dimensions.get("stability", 25.0) - 20)
                self.dimensions[dim] = max(current - decay_amount * 0.1, floor / 4.0)
            self._last_decay_time = now
            self._recalc()

    def _recalc(self):
        """重新计算总分"""
        total = sum(self.dimensions.values())
        self.score = round(max(0.0, min(100.0, total)), 1)

    # ── 稳定性维度 ──

    def record_module_init(self, success: bool = True):
        """模块初始化成功/失败"""
        self._init_time = time.time()
        self._start_count += 1
        if not success:
            self._start_fail_count += 1

        total = max(1, self._start_count)
        fail_rate = self._start_fail_count / total

        if fail_rate == 0:
            self.dimensions["stability"] = 25.0
        elif fail_rate < 0.1:
            self.dimensions["stability"] = 20.0
        elif fail_rate < 0.25:
            self.dimensions["stability"] = 15.0
        elif fail_rate < 0.5:
            self.dimensions["stability"] = 10.0
        else:
            self.dimensions["stability"] = 5.0

        # 运行时间奖励（超过 10 分钟给额外分）
        if self._init_time > 0 and time.time() - self._init_time > 600:
            self.dimensions["stability"] = min(25.0, self.dimensions["stability"] + 2.0)

        self._recalc()

    def record_module_runtime(self, runtime_seconds: float):
        """基于运行时间的稳定性调整"""
        if runtime_seconds > 3600:  # >1h
            self.dimensions["stability"] = min(25.0, self.dimensions["stability"] + 1.0)
            self._recalc()

    # ── 性能维度 ──

    def record_command_exec(self, elapsed_ms: float, success: bool = True):
        """记录命令执行时间"""
        self._cmd_total_time += elapsed_ms
        self._cmd_count += 1

        if not success:
            self._cmd_fail_count += 1

        avg_ms = self._cmd_total_time / max(1, self._cmd_count)

        # 基于平均执行时间打分
        if avg_ms < 50:
            self.dimensions["performance"] = 25.0
        elif avg_ms < 200:
            self.dimensions["performance"] = 22.0
        elif avg_ms < 500:
            self.dimensions["performance"] = 18.0
        elif avg_ms < 1000:
            self.dimensions["performance"] = 14.0
        elif avg_ms < 3000:
            self.dimensions["performance"] = 10.0
        else:
            self.dimensions["performance"] = 5.0

        # 失败率惩罚
        if self._cmd_count > 5:
            fail_rate = self._cmd_fail_count / self._cmd_count
            if fail_rate > 0.5:
                self.dimensions["performance"] = max(2.0, self.dimensions["performance"] - 8.0)
            elif fail_rate > 0.25:
                self.dimensions["performance"] = max(4.0, self.dimensions["performance"] - 4.0)

        self._recalc()

    # ── 资源维度 ──

    def record_violation(self, count: int = 1):
        """记录资源违规"""
        self._violation_count += count
        if self._violation_count <= 2:
            self.dimensions["resource"] = 20.0
        elif self._violation_count <= 5:
            self.dimensions["resource"] = 15.0
        elif self._violation_count <= 10:
            self.dimensions["resource"] = 10.0
        else:
            self.dimensions["resource"] = 3.0
        self._recalc()

    def record_message_sent(self, rate: float = 1.0):
        """记录消息发送（rate 越高越健康）"""
        # 消息发送量在合理范围内加分（最多 +3）
        if rate < 1.0:  # 低于正常频率
            bonus = rate * 3.0
            self.dimensions["resource"] = min(25.0, self.dimensions["resource"] + bonus)
        self._recalc()

    # ── 异常维度 ──

    def record_exception(self, count: int = 1):
        """记录异常"""
        self._exception_count += count
        if self._exception_count <= 2:
            self.dimensions["error"] = 20.0
        elif self._exception_count <= 5:
            self.dimensions["error"] = 15.0
        elif self._exception_count <= 10:
            self.dimensions["error"] = 10.0
        else:
            self.dimensions["error"] = 3.0
        self._recalc()

    def record_degradation(self, count: int = 1):
        """记录降级"""
        self._degradation_count += count
        penalty = self._degradation_count * 5.0
        self.dimensions["error"] = max(2.0, self.dimensions["error"] - penalty)
        self._recalc()


class ModuleHealthScorer:
    """模块健康评分系统。

    每个模块在 on_init 时注册到 scorer。
    提供评分查询、持久化、汇总功能。
    """

    DATA_FILE = "data/module_health.json"

    def __init__(self, data_path: str = "."):
        self._data_path = data_path
        self._states: Dict[str, ModuleHealthState] = {}
        self._module_order: List[str] = []  # 保持注册顺序
        self._load()

    # ── 模块注册 ──

    def register_module(self, module_name: str) -> ModuleHealthState:
        """注册一个模块（幂等），返回其健康状态"""
        if module_name in self._states:
            return self._states[module_name]

        state = ModuleHealthState(module_name=module_name)
        self._states[module_name] = state
        self._module_order.append(module_name)
        _log.debug("健康评分: 已注册模块 '%s'", module_name)
        return state

    def get_state(self, module_name: str) -> Optional[ModuleHealthState]:
        """获取模块健康状态"""
        return self._states.get(module_name)

    # ── 评分查询 ──

    def get_health(self, module_name: str) -> dict:
        """获取单个模块的健康评分详情

        Returns:
            dict with keys: module_name, score, level, emoji, dimensions, stats
        """
        state = self._states.get(module_name)
        if state is None:
            return {
                "module_name": module_name,
                "score": 100.0,
                "level": "healthy",
                "emoji": "✅",
                "dimensions": {
                    "stability": 25.0,
                    "performance": 25.0,
                    "resource": 25.0,
                    "error": 25.0,
                },
                "stats": {
                    "start_count": 0,
                    "cmd_count": 0,
                    "exception_count": 0,
                    "violation_count": 0,
                    "degradation_count": 0,
                },
            }

        state._decay_if_needed()
        return {
            "module_name": module_name,
            "score": state.score,
            "level": health_level(state.score),
            "emoji": health_emoji(state.score),
            "dimensions": dict(state.dimensions),
            "stats": {
                "start_count": state._start_count,
                "start_fail_count": state._start_fail_count,
                "cmd_count": state._cmd_count,
                "cmd_fail_count": state._cmd_fail_count,
                "exception_count": state._exception_count,
                "violation_count": state._violation_count,
                "degradation_count": state._degradation_count,
            },
        }

    def get_all_health(self) -> List[dict]:
        """获取所有模块的健康评分（按评分从低到高排序）"""
        results = [self.get_health(name) for name in self._module_order]
        results.sort(key=lambda x: x["score"])
        return results

    def get_summary(self) -> dict:
        """获取健康评分汇总"""
        all_health = self.get_all_health()
        if not all_health:
            return {"total": 0, "healthy": 0, "attention": 0,
                    "degraded": 0, "unhealthy": 0}

        counts = {"healthy": 0, "attention": 0, "degraded": 0, "unhealthy": 0}
        total_score = 0.0
        for h in all_health:
            counts[h["level"]] = counts.get(h["level"], 0) + 1
            total_score += h["score"]

        return {
            "total": len(all_health),
            "average_score": round(total_score / len(all_health), 1),
            **counts,
        }

    def get_lowest(self, n: int = 5) -> List[dict]:
        """获取评分最低的 n 个模块"""
        all_health = self.get_all_health()
        return all_health[:n]

    # ── 评分调整（供 routing 和 guardian 调用）──

    def on_command_success(self, module_name: str, elapsed_ms: float = 0):
        """命令执行成功时调用"""
        state = self._states.get(module_name)
        if state:
            state.record_command_exec(elapsed_ms, success=True)

    def on_command_failure(self, module_name: str, elapsed_ms: float = 0,
                           exception: Optional[Exception] = None):
        """命令执行失败时调用"""
        state = self._states.get(module_name)
        if state:
            state.record_command_exec(elapsed_ms, success=False)
            state.record_exception(1)

    def on_module_init(self, module_name: str, success: bool = True):
        """模块初始化时调用"""
        state = self._states.get(module_name)
        if state:
            state.record_module_init(success)

    def on_violation(self, module_name: str):
        """资源违规时调用（供 guardian）"""
        state = self._states.get(module_name)
        if state:
            state.record_violation(1)

    def on_degradation(self, module_name: str):
        """模块降级时调用"""
        state = self._states.get(module_name)
        if state:
            state.record_degradation(1)

    # ── 持久化 ──

    def _data_file_path(self) -> str:
        return os.path.join(self._data_path, self.DATA_FILE)

    def save(self):
        """持久化所有健康评分到磁盘"""
        path = self._data_file_path()
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        data = {}
        for name, state in self._states.items():
            data[name] = {
                "score": state.score,
                "dimensions": state.dimensions,
                "stats": {
                    "start_count": state._start_count,
                    "start_fail_count": state._start_fail_count,
                    "cmd_count": state._cmd_count,
                    "cmd_fail_count": state._cmd_fail_count,
                    "exception_count": state._exception_count,
                    "violation_count": state._violation_count,
                    "degradation_count": state._degradation_count,
                },
                "init_time": state._init_time,
                "last_decay_time": state._last_decay_time,
            }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            _log.debug("健康评分已保存到 %s (共 %d 个模块)", path, len(data))
        except IOError as e:
            _log.warning("保存健康评分失败: %s", e)

    def _load(self):
        """从磁盘加载历史评分"""
        path = self._data_file_path()
        if not os.path.exists(path):
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            load_count = 0
            for name, entry in data.items():
                state = ModuleHealthState(
                    module_name=name,
                    score=entry.get("score", 100.0),
                    dimensions=entry.get("dimensions", {
                        "stability": 25.0, "performance": 25.0,
                        "resource": 25.0, "error": 25.0,
                    }),
                )
                stats = entry.get("stats", {})
                state._start_count = stats.get("start_count", 0)
                state._start_fail_count = stats.get("start_fail_count", 0)
                state._cmd_count = stats.get("cmd_count", 0)
                state._cmd_fail_count = stats.get("cmd_fail_count", 0)
                state._exception_count = stats.get("exception_count", 0)
                state._violation_count = stats.get("violation_count", 0)
                state._degradation_count = stats.get("degradation_count", 0)
                state._init_time = entry.get("init_time", 0)
                state._last_decay_time = entry.get("last_decay_time", 0)

                self._states[name] = state
                self._module_order.append(name)
                load_count += 1

            _log.info("已加载历史健康评分: %d 个模块", load_count)
        except (json.JSONDecodeError, IOError) as e:
            _log.warning("加载历史健康评分失败: %s", e)

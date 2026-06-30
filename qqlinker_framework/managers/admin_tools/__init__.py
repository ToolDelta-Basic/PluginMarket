from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from qqlinker_framework.core.kernel.audit import audit_log, AuditLevel
from qqlinker_framework.core.kernel.services import (
    TIER_KERNEL,
    TIER_DAEMON,
    TIER_SERVICE,
    TIER_APP,
    UID_NOBODY,
    tier_label,
)
from ...libraries.core.scanner import Scanner

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 失败策略
# ═══════════════════════════════════════════════════════════════

class FailStrategy(Enum):
    """工作流步骤失败时的行为策略。"""
    STOP_ON_ERROR = auto()       # 遇错停止（默认）
    CONTINUE_ON_ERROR = auto()   # 忽略继续
    ROLLBACK_ON_ERROR = auto()   # 回滚已执行的步骤


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class WorkflowStep:
    """工作流中的一个步骤 — 调用某个模块的 @exec_exposed 方法。

    Args:
        description: 人类可读的步骤描述
        module: 目标模块名
        method: 目标方法名
        args: 静态参数（dict 或 list），与 args_from_ctx 互斥
        args_from_ctx: 从执行上下文中提取参数（True 表示传入整个 ctx）
        rollback_module: 回滚时删除的模块名（可选，默认同 module）
        rollback_method: 回滚时删除的方法名（可选）
        rollback_args: 回滚时删除的参数
        timeout: 单步超时秒数
    """
    description: str
    module: str
    method: str
    args: Optional[Any] = None          # dict → 关键字参数, list → 位置参数
    args_from_ctx: bool = False         # True 时传入 ctx
    rollback_module: Optional[str] = None
    rollback_method: Optional[str] = None
    rollback_args: Optional[Any] = None
    timeout: float = 30.0


@dataclass
class WorkflowDefinition:
    """完整的工作流定义。"""
    name: str
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    fail_strategy: FailStrategy = FailStrategy.STOP_ON_ERROR
    require_confirm: bool = False
    min_tier: str = "daemon"            # 最低允许执行层级
    source: str = "python"              # "python" | "json"
    # 回滚步骤（自动从 steps 反序推导，也可手动指定）
    _rollback_steps: List[WorkflowStep] = field(default_factory=list, repr=False)


@dataclass
class StepResult:
    """单步执行结果。"""
    step: WorkflowStep
    success: bool
    result: Any = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class WorkflowResult:
    """工作流全体执行结果。"""
    workflow_name: str
    success: bool
    steps: List[StepResult] = field(default_factory=list)
    total_elapsed_ms: float = 0.0
    rollback_performed: bool = False
    rollback_results: List[StepResult] = field(default_factory=list)

    @property
    def failed_step(self) -> Optional[StepResult]:
        """返回第一个失败的步骤。"""
        for s in self.steps:
            if not s.success:
                return s
        return None


# ═══════════════════════════════════════════════════════════════
# AdminToolManager
# ═══════════════════════════════════════════════════════════════

class AdminToolManager:
    """管理工具编排器 — 组合调用模块 @exec_exposed 方法。

    FrameworkHost 在 start() 中创建此实例并通过
    self.services.register("admin_tool", instance) 暴露给模块。
    """

    def __init__(self, services: Any):
        """
        Args:
            services: root 级 ServiceContainer
        """
        self._services = services
        self._workflows: Dict[str, WorkflowDefinition] = {}
        self._lock = threading.Lock()
        self._json_scan_dir: Optional[str] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._file_watcher: Any = None  # FileWatcher 实例（热重载）
        self._pending_confirms: Dict[str, Dict[str, Any]] = {}
        # 热重载状态记录
        self._last_scan_mtimes: Dict[str, float] = {}

    # ── 初始化 ──

    def init_with_services(self, services: Any = None) -> None:
        """从服务容器初始化数据目录和 JSON 扫描。

        在 FrameworkHost.start() 中调用。
        """
        svc = services or self._services
        try:
            cfg = svc.get("config")
            data_dir = cfg.get_data_dir()
        except Exception:
            try:
                host = svc.get("_host")
                data_dir = getattr(host, 'data_path', '.')
            except Exception:
                data_dir = '.'

        self._json_scan_dir = os.path.join(data_dir, "管理工具")
        os.makedirs(self._json_scan_dir, exist_ok=True)

        # 初次扫描
        self._scan_json_workflows()
        _log.info(
            "管理工具编排器已初始化 (数据目录: %s, 已加载 %d 个工作流)",
            self._json_scan_dir, len(self._workflows),
        )

    # ── 工作流注册 ──

    def register_workflow(
        self,
        name: str,
        steps: List[Union[WorkflowStep, Dict[str, Any]]],
        description: str = "",
        fail_strategy: Union[FailStrategy, str] = FailStrategy.STOP_ON_ERROR,
        require_confirm: bool = False,
        min_tier: str = "daemon",
        source: str = "python",
    ) -> Optional[WorkflowDefinition]:
        """注册一个工作流。

        Args:
            name: 工作流唯一名称
            steps: 步骤列表（WorkflowStep 或 dict）
            description: 人类可读描述
            fail_strategy: 失败策略
            require_confirm: 是否需要执行前确认
            min_tier: 最低允许执行层级
            source: 来源标记 ("python" 或 "json")

        Returns:
            注册的 WorkflowDefinition，若名称冲突则返回 None
        """
        if isinstance(fail_strategy, str):
            fail_strategy = _parse_fail_strategy(fail_strategy)

        # 标准化步骤
        parsed_steps: List[WorkflowStep] = []
        for step in steps:
            if isinstance(step, WorkflowStep):
                parsed_steps.append(step)
            elif isinstance(step, dict):
                parsed_steps.append(_step_from_dict(step))
            else:
                _log.warning("无效的步骤类型: %s", type(step))
                continue

        wf = WorkflowDefinition(
            name=name,
            description=description,
            steps=parsed_steps,
            fail_strategy=fail_strategy,
            require_confirm=require_confirm,
            min_tier=min_tier,
            source=source,
        )

        # 自动推导回滚步骤
        wf._rollback_steps = _derive_rollback_steps(parsed_steps, fail_strategy)

        with self._lock:
            if name in self._workflows:
                _log.warning("工作流 '%s' 已存在，拒绝重复注册", name)
                return None
            self._workflows[name] = wf
            _log.info(
                "工作流已注册: '%s' (%d 步, 失败策略=%s, 来源=%s)",
                name, len(parsed_steps), fail_strategy.name, source,
            )
            return wf

    def unregister_workflow(self, name: str) -> bool:
        """注销工作流（仅注销非 JSON 来源的）。"""
        with self._lock:
            wf = self._workflows.get(name)
            if wf is None:
                return False
            if wf.source == "json":
                _log.warning("JSON 工作流 '%s' 不可通过 API 注销，请删除 JSON 文件后重扫", name)
                return False
            del self._workflows[name]
            _log.info("工作流已注销: '%s'", name)
            return True

    # ── 工作流执行 ──

    async def execute_workflow(
        self,
        name: str,
        ctx: Any,
        *,
        bypass_confirm: bool = False,
        caller_uid: int = UID_NOBODY,
    ) -> WorkflowResult:
        """执行一个命名工作流。

        Args:
            name: 工作流名称
            ctx: 执行上下文（CommandContext 或兼容对象）
            bypass_confirm: 跳过确认（用于已确认的执行）
            caller_uid: 调用方 UID（用于权限检查）

        Returns:
            WorkflowResult — 包含每步结果的完整报告
        """
        with self._lock:
            wf = self._workflows.get(name)

        if wf is None:
            return WorkflowResult(
                workflow_name=name,
                success=False,
                steps=[StepResult(
                    step=WorkflowStep(description="工作流未找到", module="", method=""),
                    success=False,
                    error=f"工作流 '{name}' 未注册",
                )],
            )

        # 权限检查
        caller_tier = tier_label(caller_uid) if caller_uid else "nobody"
        tier_rank_map = {
            "root": 0, "kernel": 0, "daemon": 100,
            "service": 200, "app": 300, "nobody": 400,
        }
        caller_rank = tier_rank_map.get(caller_tier, 99)
        min_rank = tier_rank_map.get(wf.min_tier, 99)
        if caller_rank > min_rank:
            return WorkflowResult(
                workflow_name=name,
                success=False,
                steps=[StepResult(
                    step=WorkflowStep(description="权限不足", module="", method=""),
                    success=False,
                    error=f"{caller_tier}(uid={caller_uid}) 无权执行 '{name}' (至少需要 {wf.min_tier})",
                )],
            )

        # 确认检查
        if wf.require_confirm and not bypass_confirm:
            confirm_key = f"{ctx.user_id}:{name}:{int(time.time())}"
            self._pending_confirms[confirm_key] = {
                "name": name,
                "ctx_user_id": ctx.user_id,
                "timestamp": time.time(),
            }
            # 返回一个特殊结果，由调用方处理确认 UI
            return WorkflowResult(
                workflow_name=name,
                success=False,
                steps=[StepResult(
                    step=WorkflowStep(description="需要确认", module="", method=""),
                    success=False,
                    error=f"工作流 '{name}' 需要确认（{wf.description}）。请追加 --confirm 确认执行。\n确认密钥: {confirm_key}",
                )],
            )

        # 审计日志
        audit_log(
            sender=f"uid:{caller_uid}",
            action=f"workflow.execute.{name}",
            target=str(getattr(ctx, 'group_id', '')),
            detail=f"steps={len(wf.steps)} strategy={wf.fail_strategy.name}",
            level=AuditLevel.WARNING,
            group_id=getattr(ctx, 'group_id', None),
        )

        start_time = time.time()
        step_results: List[StepResult] = []
        rollback_done = False
        rollback_results: List[StepResult] = []

        for i, step in enumerate(wf.steps):
            result = await self._execute_step(step, ctx, caller_uid)
            step_results.append(result)
            _log.info(
                "工作流 '%s' 第 %d/%d 步: %s → %s (%.0fms)",
                name, i + 1, len(wf.steps),
                step.description,
                "✅" if result.success else f"❌ {result.error}",
                result.elapsed_ms,
            )

            if not result.success:
                if wf.fail_strategy == FailStrategy.STOP_ON_ERROR:
                    _log.warning(
                        "工作流 '%s' 在第 %d 步 '%s' 失败，停止执行",
                        name, i + 1, step.description,
                    )
                    break
                elif wf.fail_strategy == FailStrategy.ROLLBACK_ON_ERROR:
                    _log.warning(
                        "工作流 '%s' 在第 %d 步 '%s' 失败，开始回滚",
                        name, i + 1, step.description,
                    )
                    rollback_results = await self._perform_rollback(
                        wf, step_results, ctx, caller_uid,
                    )
                    rollback_done = True
                    break
                elif wf.fail_strategy == FailStrategy.CONTINUE_ON_ERROR:
                    _log.warning(
                        "工作流 '%s' 第 %d 步 '%s' 失败，忽略继续",
                        name, i + 1, step.description,
                    )
                    continue

        total_elapsed = (time.time() - start_time) * 1000
        all_ok = all(r.success for r in step_results) and not rollback_done

        result = WorkflowResult(
            workflow_name=name,
            success=all_ok,
            steps=step_results,
            total_elapsed_ms=total_elapsed,
            rollback_performed=rollback_done,
            rollback_results=rollback_results,
        )

        # 审计日志 — 执行完成
        audit_log(
            sender=f"uid:{caller_uid}",
            action=f"workflow.complete.{name}",
            target=str(getattr(ctx, 'group_id', '')),
            detail=f"success={all_ok} rollback={rollback_done} elapsed={total_elapsed:.0f}ms",
            level=AuditLevel.INFO,
            group_id=getattr(ctx, 'group_id', None),
        )

        return result

    async def _execute_step(
        self, step: WorkflowStep, ctx: Any, caller_uid: int,
    ) -> StepResult:
        """执行单个工作流步骤 — 通过 gatekeeper 的 模块.调用 bridge。"""
        start = time.time()
        try:
            # 通过 gatekeeper bridge 调用目标方法
            bridge = None
            try:
                host = self._services.get("_host")
                bridge = getattr(host, 'gatekeeper', None)
            except Exception as e:
                _log.warning("__init__._execute_step: %s", e)

            if bridge is None:
                raise RuntimeError("gatekeeper bridge 不可用")

            # 准备参数
            if step.args_from_ctx:
                call_args = [ctx]
            elif isinstance(step.args, dict):
                call_args = [step.args]
            elif isinstance(step.args, list):
                call_args = list(step.args)
            else:
                call_args = []

            # 通过 bridge 调用（带超时）
            result = await asyncio.wait_for(
                bridge.call_async("模块.调用", caller_uid, step.module, step.method, call_args),
                timeout=step.timeout,
            )

            elapsed = (time.time() - start) * 1000
            return StepResult(
                step=step, success=True, result=result, elapsed_ms=elapsed,
            )
        except asyncio.TimeoutError:
            elapsed = (time.time() - start) * 1000
            return StepResult(
                step=step, success=False,
                error=f"步骤超时 ({step.timeout}s): {step.module}.{step.method}",
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return StepResult(
                step=step, success=False,
                error=f"{type(e).__name__}: {e}",
                elapsed_ms=elapsed,
            )

    async def _perform_rollback(
        self,
        wf: WorkflowDefinition,
        completed_steps: List[StepResult],
        ctx: Any,
        caller_uid: int,
    ) -> List[StepResult]:
        """执行回滚 — 逆序执行回滚步骤。"""
        results: List[StepResult] = []
        rollback_steps = wf._rollback_steps

        if not rollback_steps:
            _log.info("工作流 '%s' 无回滚步骤可执行", wf.name)
            return results

        _log.info(
            "开始回滚工作流 '%s' (%d 步)",
            wf.name, len(rollback_steps),
        )

        for step in rollback_steps:
            result = await self._execute_step(step, ctx, caller_uid)
            results.append(result)
            _log.info(
                "回滚步骤 '%s': %s",
                step.description, "✅" if result.success else f"❌ {result.error}",
            )
            # 回滚通常遇错继续（不回滚的回滚）
            if not result.success:
                _log.warning("回滚步骤 '%s' 失败: %s", step.description, result.error)

        return results

    # ── 确认管理 ──

    def confirm_execution(self, key: str) -> Tuple[bool, Optional[str]]:
        """确认一个待确认的工作流执行。

        Returns:
            (是否有效, 工作流名称)
        """
        pending = self._pending_confirms.pop(key, None)
        if pending is None:
            # 检查是否是过期的确认
            for k, v in list(self._pending_confirms.items()):
                if time.time() - v.get("timestamp", 0) > 300:  # 5 分钟过期
                    self._pending_confirms.pop(k, None)
            return False, None
        # 检查过期
        if time.time() - pending.get("timestamp", 0) > 300:
            return False, None
        return True, pending["name"]

    # ── 工作流查询 ──

    def list_workflows(self, caller_uid: int = UID_NOBODY) -> List[Dict[str, Any]]:
        """列出所有可用工作流（按调用方 UID 过滤）。"""
        caller_tier = tier_label(caller_uid) if caller_uid else "nobody"
        tier_rank_map = {
            "root": 0, "kernel": 0, "daemon": 100,
            "service": 200, "app": 300, "nobody": 400,
        }
        caller_rank = tier_rank_map.get(caller_tier, 99)

        result: List[Dict[str, Any]] = []
        with self._lock:
            for wf in self._workflows.values():
                min_rank = tier_rank_map.get(wf.min_tier, 99)
                accessible = caller_rank <= min_rank
                result.append({
                    "name": wf.name,
                    "description": wf.description,
                    "steps_count": len(wf.steps),
                    "fail_strategy": wf.fail_strategy.name,
                    "require_confirm": wf.require_confirm,
                    "min_tier": wf.min_tier,
                    "accessible": accessible,
                    "source": wf.source,
                    "steps": [
                        {"description": s.description, "module": s.module, "method": s.method}
                        for s in wf.steps
                    ],
                })
        result.sort(key=lambda x: x["name"])
        return result

    def get_workflow(self, name: str) -> Optional[WorkflowDefinition]:
        """获取工作流定义。"""
        with self._lock:
            return self._workflows.get(name)

    def workflow_count(self) -> int:
        """返回已注册的工作流数。"""
        with self._lock:
            return len(self._workflows)

    # ── JSON 扫描 & 热重载 ──

    def _scan_json_workflows(self) -> int:
        """从 数据/管理工具/ 扫描 JSON 工作流定义。"""
        if not self._json_scan_dir or not os.path.isdir(self._json_scan_dir):
            return 0

        count = 0
        loaded_names: set = set()

        scanner = Scanner(self._json_scan_dir)
        results = scanner.find("*.json", track_mtime=True)

        for path, mtime in results:
            fname = path.name
            path_str = str(path)
            try:
                # 检查文件是否自上次扫描后修改
                prev_mtime = self._last_scan_mtimes.get(path_str, 0)
                if prev_mtime and prev_mtime >= mtime:
                    # 文件未修改，跳过（但仍需记录名称以防被误删）
                    with self._lock:
                        # 从现有工作流中找同名 JSON 工作流
                        for wf_name, wf in self._workflows.items():
                            if wf.source == "json" and wf_name == fname.replace(".json", ""):
                                loaded_names.add(wf.name)
                                break
                    continue

                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                name = data.get("name", fname.replace(".json", ""))
                description = data.get("description", "")
                fail_strategy_str = data.get("fail_strategy", "stop_on_error")
                fail_strategy = _parse_fail_strategy(fail_strategy_str)
                require_confirm = data.get("require_confirm", False)
                min_tier = data.get("min_tier", "daemon")

                # 解析步骤
                steps: List[WorkflowStep] = []
                for step_data in data.get("steps", []):
                    step = _step_from_dict(step_data)
                    steps.append(step)

                # 注册/更新
                with self._lock:
                    # 移除同名的旧 JSON 工作流
                    existing = self._workflows.get(name)
                    if existing and existing.source == "json":
                        del self._workflows[name]

                    wf = WorkflowDefinition(
                        name=name,
                        description=description,
                        steps=steps,
                        fail_strategy=fail_strategy,
                        require_confirm=require_confirm,
                        min_tier=min_tier,
                        source="json",
                    )
                    wf._rollback_steps = _derive_rollback_steps(steps, fail_strategy)
                    self._workflows[name] = wf
                    loaded_names.add(name)

                self._last_scan_mtimes[path_str] = mtime
                count += 1
                _log.debug("JSON 工作流已加载: '%s' (%d 步)", name, len(steps))

            except json.JSONDecodeError as e:
                _log.error("JSON 工作流文件 '%s' 格式错误: %s", fname, e)
            except Exception as e:
                _log.error("加载 JSON 工作流 '%s' 失败: %s", fname, e)

        # 清理已删除的 JSON 文件对应的工作流
        with self._lock:
            removed = []
            for wf_name, wf in list(self._workflows.items()):
                if wf.source == "json" and wf_name not in loaded_names:
                    del self._workflows[wf_name]
                    removed.append(wf_name)
            if removed:
                _log.info("已清理 %d 个过期的 JSON 工作流: %s", len(removed), removed)

        return count

    async def reload_json_workflows(self) -> int:
        """热重载所有 JSON 工作流定义。"""
        self._last_scan_mtimes.clear()  # 强制重新扫描
        count = self._scan_json_workflows()
        _log.info("JSON 工作流热重载完成，加载 %d 个工作流", count)
        return count

    # ── 热重载文件监控 ──

    async def start_file_watcher(self, interval: float = 10.0) -> None:
        """启动文件变化监控（定期扫描 数据/管理工具/ 目录）。"""
        if self._watch_task and not self._watch_task.done():
            return

        async def _watcher():
            while True:
                try:
                    await asyncio.sleep(interval)
                    self._scan_json_workflows()
                except asyncio.CancelledError:
                    break
                except Exception:
                    _log.exception("文件监控循环异常")

        loop = asyncio.get_running_loop()
        self._watch_task = loop.create_task(_watcher())
        _log.info("管理工具文件监控已启动 (间隔=%ss)", interval)

    async def stop_file_watcher(self) -> None:
        """停止文件变化监控。"""
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError as e:
                _log.debug("__init__.stop_file_watcher: %s", e)
            self._watch_task = None
            _log.info("管理工具文件监控已停止")

    # ── 工作流结果格式化 ──

    @staticmethod
    def format_result(result: WorkflowResult, max_steps_show: int = 20) -> str:
        """将工作流执行结果格式化为人类可读的消息。

        Args:
            result: 执行结果
            max_steps_show: 最多显示几步

        Returns:
            格式化的字符串
        """
        icon = "✅" if result.success else "❌"
        lines = [
            f"{icon} 工作流: {result.workflow_name}",
            f"   耗时: {result.total_elapsed_ms:.0f}ms",
            f"   状态: {'全部成功' if result.success else '存在失败'}",
            "",
        ]

        steps = result.steps[:max_steps_show]
        for i, sr in enumerate(steps):
            mark = "✅" if sr.success else "❌"
            desc = sr.step.description or f"{sr.step.module}.{sr.step.method}"
            detail = f" ({sr.elapsed_ms:.0f}ms)"
            if not sr.success and sr.error:
                detail += f" — {sr.error[:80]}"
            lines.append(f"   {mark} 第{i+1}步: {desc}{detail}")

        if len(result.steps) > max_steps_show:
            lines.append(f"   ... 还有 {len(result.steps) - max_steps_show} 步")

        if result.rollback_performed:
            lines.append(f"\n   🔄 已回滚 {len(result.rollback_results)} 步:")
            for i, rr in enumerate(result.rollback_results[:10]):
                mark = "✅" if rr.success else "⚠️"
                lines.append(
                    f"      {mark} {rr.step.description}"
                    f"{'' if rr.success else f' — {rr.error[:60]}'}"
                )

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 内部工具函数
# ═══════════════════════════════════════════════════════════════

def _parse_fail_strategy(raw: str) -> FailStrategy:
    """解析失败策略字符串。"""
    mapping = {
        "stop_on_error": FailStrategy.STOP_ON_ERROR,
        "stop": FailStrategy.STOP_ON_ERROR,
        "continue_on_error": FailStrategy.CONTINUE_ON_ERROR,
        "continue": FailStrategy.CONTINUE_ON_ERROR,
        "ignore": FailStrategy.CONTINUE_ON_ERROR,
        "rollback_on_error": FailStrategy.ROLLBACK_ON_ERROR,
        "rollback": FailStrategy.ROLLBACK_ON_ERROR,
    }
    return mapping.get(raw.lower().replace("-", "_"), FailStrategy.STOP_ON_ERROR)


def _step_from_dict(data: Dict[str, Any]) -> WorkflowStep:
    """从字典创建 WorkflowStep。"""
    args = data.get("args")
    args_from_ctx = data.get("args_from_ctx", False)

    if args is not None and args_from_ctx:
        _log.warning("步骤同时设置了 args 和 args_from_ctx，优先使用 args_from_ctx")
        args = None

    return WorkflowStep(
        description=data.get("description", f"{data.get('module', '?')}.{data.get('method', '?')}"),
        module=data.get("module", ""),
        method=data.get("method", ""),
        args=args,
        args_from_ctx=args_from_ctx,
        rollback_module=data.get("rollback_module"),
        rollback_method=data.get("rollback_method"),
        rollback_args=data.get("rollback_args"),
        timeout=data.get("timeout", 30.0),
    )


def _derive_rollback_steps(
    steps: List[WorkflowStep],
    strategy: FailStrategy,
) -> List[WorkflowStep]:
    """从步骤列表推导回滚步骤（逆序，且要求步骤有 rollback 信息）。"""
    if strategy != FailStrategy.ROLLBACK_ON_ERROR:
        return []

    rollback_steps: List[WorkflowStep] = []
    for step in reversed(steps):
        if step.rollback_method:
            rb = WorkflowStep(
                description=f"回滚: {step.description}",
                module=step.rollback_module or step.module,
                method=step.rollback_method,
                args=step.rollback_args,
                timeout=step.timeout,
            )
            rollback_steps.append(rb)

    return rollback_steps

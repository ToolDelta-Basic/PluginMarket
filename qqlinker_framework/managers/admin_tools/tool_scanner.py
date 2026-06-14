"""工具扫描 — 从 数据/管理工具/ 目录扫描 JSON 工作流定义并支持热加载

═══════════════════════════════════════════════════════════════════════════
 功能
═══════════════════════════════════════════════════════════════════════════
 · 扫描 数据/管理工具/*.json 工作流定义文件
 · 支持热加载 — 文件变化时自动重载（基于 FileWatcher 或定时扫描）
 · 文件校验 — JSON 格式、步骤完整性、模块存在性
 · 新旧工作流同步 — 删除文件自动注销对应工作流
 · 目录监听 — 基于 inotify 或轮询的文件变化监控

 使用:
   1. 将 JSON 工作流文件放入 数据/管理工具/ 目录
   2. FrameworkHost 启动时自动加载
   3. 运行时使用 管理工具.重载 命令手动热重载
   4. 启用 FileWatcher 时自动检测文件变化
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .admin_tools import AdminToolManager
from qqlinker_framework.managers.admin_tools.workflow_registry import WorkflowDefinition, WorkflowStep, FailStrategy

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# JSON 工作流校验
# ═══════════════════════════════════════════════════════════════

VALID_FAIL_STRATEGIES = {"stop_on_error", "stop", "continue_on_error", "continue", "ignore", "rollback_on_error", "rollback"}
VALID_TIERS = {"root", "kernel", "daemon", "service", "app", "nobody"}


class ValidationResult:
    """JSON 工作流校验结果。"""
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    @property
    def is_valid(self) -> bool:
        """是否验证通过。"""
        return len(self.errors) == 0

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """合并另一个验证结果。"""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.info.extend(other.info)
        return self

    def __repr__(self) -> str:
        return (
            f"ValidationResult(errors={len(self.errors)}, "
            f"warnings={len(self.warnings)}, info={len(self.info)})"
        )


def validate_workflow_json(data: Dict[str, Any], filename: str = "") -> ValidationResult:
    """校验 JSON 工作流定义的完整性和合法性。

    Args:
        data: 解析后的 JSON 字典
        filename: 文件名（用于错误消息）

    Returns:
        ValidationResult — 错误/警告/信息列表
    """
    result = ValidationResult()

    # ── 顶层校验 ──
    if not isinstance(data, dict):
        result.errors.append(f"根元素必须是 JSON 对象，当前为: {type(data).__name__}")
        return result

    # name
    name = data.get("name")
    if not name or not isinstance(name, str):
        result.errors.append("缺少 'name' 字段（工作流名称）")

    # description（可选）
    desc = data.get("description", "")
    if desc and not isinstance(desc, str):
        result.warnings.append("'description' 应为字符串")

    # fail_strategy（可选，默认 stop_on_error）
    fail_strategy = data.get("fail_strategy", "stop_on_error")
    if isinstance(fail_strategy, str) and fail_strategy.lower().replace("-", "_") not in VALID_FAIL_STRATEGIES:
        result.warnings.append(
            f"'fail_strategy' 无效值: '{fail_strategy}'，"
            f"将使用默认值 'stop_on_error'。有效值: {sorted(VALID_FAIL_STRATEGIES)}"
        )

    # require_confirm（可选）
    require_confirm = data.get("require_confirm", False)
    if not isinstance(require_confirm, (bool, type(None))):
        result.warnings.append(f"'require_confirm' 应为布尔值，当前为: {type(require_confirm).__name__}")

    # min_tier（可选，默认 daemon）
    min_tier = data.get("min_tier", "daemon")
    if isinstance(min_tier, str) and min_tier not in VALID_TIERS:
        result.warnings.append(
            f"'min_tier' 无效值: '{min_tier}'，"
            f"将使用默认值 'daemon'。有效值: {sorted(VALID_TIERS)}"
        )

    # ── 步骤校验 ──
    steps = data.get("steps")
    if not steps:
        result.errors.append("'steps' 字段不能为空（至少需要一个步骤）")
        return result

    if not isinstance(steps, list):
        result.errors.append(f"'steps' 必须是数组，当前为: {type(steps).__name__}")
        return result

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            result.errors.append(f"步骤[{i}] 必须是 JSON 对象")
            continue

        # module
        mod = step.get("module")
        if not mod or not isinstance(mod, str):
            result.errors.append(f"步骤[{i}] 缺少 'module' 字段（目标模块名）")

        # method
        meth = step.get("method")
        if not meth or not isinstance(meth, str):
            result.errors.append(f"步骤[{i}] 缺少 'method' 字段（目标方法名）")

        # description（可选但建议）
        step_desc = step.get("description")
        if not step_desc:
            result.info.append(
                f"步骤[{i}] 建议添加 'description' 字段（目前为 '{mod}.{meth}'）"
            )

        # args / args_from_ctx 互斥
        has_args = "args" in step
        has_args_from_ctx = step.get("args_from_ctx", False)
        if has_args and has_args_from_ctx:
            result.warnings.append(
                f"步骤[{i}] 同时设置了 'args' 和 'args_from_ctx=True'，"
                f"将优先使用 'args_from_ctx'"
            )

        # timeout（可选）
        timeout = step.get("timeout")
        if timeout is not None:
            if not isinstance(timeout, (int, float)):
                result.warnings.append(f"步骤[{i}] 'timeout' 应为数字")
            elif timeout <= 0:
                result.warnings.append(f"步骤[{i}] 'timeout' 应为正数")

        # rollback 一致性
        has_rollback_method = "rollback_method" in step
        if has_rollback_method and fail_strategy not in ("rollback_on_error", "rollback"):
            result.info.append(
                f"步骤[{i}] 定义了 'rollback_method'，"
                f"但 fail_strategy 不是 'rollback_on_error'，回滚方法不会生效"
            )

    return result


def validate_directory(
    scan_dir: str,
    host_module_mgr=None,
) -> Dict[str, ValidationResult]:
    """扫描并校验 数据/管理工具/ 目录中的所有 JSON 工作流文件。

    Args:
        scan_dir: 扫描目录路径
        host_module_mgr: 可选的 SourceManager 实例（用于校验模块存在性）

    Returns:
        {文件名: ValidationResult} 映射
    """
    results: Dict[str, ValidationResult] = {}

    if not os.path.isdir(scan_dir):
        _log.warning("管理工具目录不存在: %s", scan_dir)
        return results

    for fname in sorted(os.listdir(scan_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(scan_dir, fname)
        result = ValidationResult()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            result.errors.append(f"JSON 解析错误: {e}")
            results[fname] = result
            continue
        except IOError as e:
            result.errors.append(f"文件读取错误: {e}")
            results[fname] = result
            continue

        # 基本校验
        v = validate_workflow_json(data, fname)
        result.merge(v)

        # 模块存在性校验（需要 host module_mgr）
        if host_module_mgr and v.is_valid:
            loaded_modules = set(host_module_mgr.get_loaded_modules()) if hasattr(host_module_mgr, 'get_loaded_modules') else set()
            for i, step in enumerate(data.get("steps", [])):
                mod_name = step.get("module", "")
                if mod_name and mod_name not in loaded_modules:
                    result.warnings.append(
                        f"步骤[{i}] 模块 '{mod_name}' 当前未加载（运行时调用将失败）"
                    )

        results[fname] = result

    return results


# ═══════════════════════════════════════════════════════════════
# FileWatcher — 轻量级文件变化监控
# ═══════════════════════════════════════════════════════════════

class FileWatcher:
    """轻量级文件变化监控（轮询实现，零外部依赖）。

    监控指定目录下匹配模式的文件变化（新增/修改/删除），
    检测到变化时回调通知。
    """

    def __init__(
        self,
        watch_dir: str,
        pattern: str = "*.json",
        callback: Callable[[str, str], None] = None,
        interval: float = 5.0,
    ):
        """
        Args:
            watch_dir: 监控目录
            pattern: 文件名模式（glob 风格，仅支持 *.ext）
            callback: 变化回调 (filename, event_type)
            interval: 扫描间隔秒数
        """
        self._watch_dir = watch_dir
        self._pattern = pattern
        self._callback = callback
        self._interval = interval
        self._last_state: Dict[str, float] = {}  # filename → mtime
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _scan(self) -> Dict[str, float]:
        """扫描目录返回 {filename: mtime} 映射。"""
        state: Dict[str, float] = {}
        if not os.path.isdir(self._watch_dir):
            return state
        suffix = self._pattern.lstrip("*")
        for fname in os.listdir(self._watch_dir):
            if fname.endswith(suffix):
                path = os.path.join(self._watch_dir, fname)
                try:
                    state[fname] = os.path.getmtime(path)
                except OSError:
                    state[fname] = 0.0
        return state

    async def start(self) -> None:
        """启动文件监控循环。"""
        if self._running:
            return

        self._last_state = self._scan()
        self._running = True

        async def _loop():
            while self._running:
                try:
                    await asyncio.sleep(self._interval)
                    current = self._scan()

                    # 检测新增/修改
                    for fname, mtime in current.items():
                        prev = self._last_state.get(fname)
                        if prev is None:
                            self._notify(fname, "added")
                        elif mtime > prev:
                            self._notify(fname, "modified")

                    # 检测删除
                    for fname in self._last_state:
                        if fname not in current:
                            self._notify(fname, "removed")

                    self._last_state = current
                except asyncio.CancelledError:
                    break
                except Exception:
                    _log.exception("FileWatcher 循环异常")

        loop = asyncio.get_running_loop()
        self._task = loop.create_task(_loop())
        _log.info(
            "FileWatcher 已启动 (目录=%s, 模式=%s, 间隔=%ss)",
            self._watch_dir, self._pattern, self._interval,
        )

    async def stop(self) -> None:
        """停止文件监控。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        _log.info("FileWatcher 已停止")

    def _notify(self, filename: str, event_type: str) -> None:
        """通知回调函数。"""
        if self._callback:
            try:
                self._callback(filename, event_type)
            except Exception:
                _log.exception("FileWatcher 回调异常: %s %s", filename, event_type)
        _log.debug("FileWatcher: %s → %s", filename, event_type)


# ═══════════════════════════════════════════════════════════════
# 集成入口 — 连接 FileWatcher 到 AdminToolManager
# ═══════════════════════════════════════════════════════════════

async def setup_file_watcher(
    admin_tool: AdminToolManager,
    scan_dir: str,
    interval: float = 10.0,
) -> Optional[FileWatcher]:
    """为 AdminToolManager 设置文件监控。

    Args:
        admin_tool: AdminToolManager 实例
        scan_dir: 扫描目录
        interval: 扫描间隔秒数

    Returns:
        FileWatcher 实例（已启动），若目录不存在则返回 None
    """
    if not os.path.isdir(scan_dir):
        _log.warning("目录不存在，无法设置文件监控: %s", scan_dir)
        return None

    def on_file_change(filename: str, event_type: str):
        """文件变化回调 — 触发 JSON 工作流重载。"""
        _log.info("管理工具文件变化: %s → %s", filename, event_type)
        # 同步触发扫描（在事件循环中执行）
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_async_rescan(admin_tool, filename, event_type))
        except RuntimeError:
            # 没有运行中的事件循环，下次定时扫描会捡起
            pass

    watcher = FileWatcher(
        watch_dir=scan_dir,
        pattern="*.json",
        callback=on_file_change,
        interval=interval,
    )
    await watcher.start()
    return watcher


async def _async_rescan(
    admin_tool: AdminToolManager,
    filename: str,
    event_type: str,
) -> None:
    """异步重新扫描 JSON 工作流。"""
    try:
        count = await admin_tool.reload_json_workflows()
        _log.info(
            "文件变化 (%s: %s) 触发热重载，当前 %d 个工作流",
            event_type, filename, count,
        )
    except Exception:
        _log.exception("热重载异常: %s", filename)

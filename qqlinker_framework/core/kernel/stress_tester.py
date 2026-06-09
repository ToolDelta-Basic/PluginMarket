"""自动压力测试器 (StressTester)

启动后在后台线程运行（不阻塞主循环），对已加载模块执行基础压力测试：
  - 对每个已注册命令执行 1 次空参数调用
  - 对每个事件处理器模拟空事件
  - 记录执行时间、内存增量、是否异常
  - 输出报告到 data/stress_report.json

测试时间窗口: 启动后 90-120s 内完成
只测试 UID≥300 的模块（用户模块），不测内核命令
"""
import asyncio
import json
import logging
import os
import sys
import threading
import time
import traceback as _traceback
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

# ── 测试配置 ──

STRESS_MIN_DELAY = 90   # 启动后至少等 N 秒才开始
STRESS_MAX_DELAY = 120  # 最晚开始时间
STRESS_CMD_TIMEOUT = 3.0   # 每个命令调用的最大超时（秒）
STRESS_EVENT_TIMEOUT = 3.0
MIN_UID_FOR_TEST = 300     # 只测试 uid >= 300 的用户模块


class StressTester:
    """自动压力测试器。

    在后台线程中运行，不阻塞主循环。对每个已载入的用户模块
    （uid ≥ 300）的已注册命令和事件处理器执行一次空调用。

    报告格式:
      {
        "timestamp": "ISO 8601",
        "duration_sec": 12.3,
        "modules_tested": 5,
        "modules_skipped": 2,
        "results": [ ... ]
      }
    """

    def __init__(self, host, data_path: str = "."):
        self._host = host
        self._data_path = data_path
        self._thread: Optional[threading.Thread] = None
        self._started = False

    def start(self):
        """启动后台压力测试线程（非阻塞）。"""
        if self._started:
            _log.debug("StressTester 已启动，跳过重复启动")
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="stress-tester"
        )
        self._thread.start()
        _log.info("StressTester 后台线程已启动 (延迟 %ds～%ds)", STRESS_MIN_DELAY, STRESS_MAX_DELAY)

    def _run(self, skip_delay: bool = False):
        """压力测试主循环（后台线程）。

        Args:
            skip_delay: 跳过随机延迟（测试用）。
        """
        if not skip_delay:
            import random
            delay = random.uniform(STRESS_MIN_DELAY, STRESS_MAX_DELAY)
            _log.debug("StressTester 将在 %.1fs 后开始测试", delay)
            time.sleep(delay)

        start_ts = time.time()
        results: List[Dict[str, Any]] = []
        modules_tested = 0
        modules_skipped = 0

        try:
            modules = getattr(self._host, '_modules', [])
            if not modules:
                _log.warning("StressTester: 未发现已加载模块，跳过测试")
                self._write_report(start_ts, start_ts, 0, 0, [])
                return

            for mod in modules:
                mod_uid = getattr(mod, 'uid', 400)

                if mod_uid < MIN_UID_FOR_TEST:
                    _log.debug("StressTester: 跳过内核模块 '%s' (uid=%d)", mod.name, mod_uid)
                    modules_skipped += 1
                    continue

                mod_results = self._test_module(mod)
                results.extend(mod_results)
                modules_tested += 1

        except Exception as e:
            _log.error("StressTester 运行异常: %s", e)

        end_ts = time.time()
        self._write_report(start_ts, end_ts, modules_tested, modules_skipped, results)
        _log.info(
            "StressTester 完成: 测试了 %d 个模块，%d 个用例，耗时 %.2fs",
            modules_tested, len(results), end_ts - start_ts,
        )

    def _test_module(self, mod) -> List[Dict[str, Any]]:
        """对单个模块执行压力测试，返回结果列表。"""
        results: List[Dict[str, Any]] = []
        mod_name = getattr(mod, 'name', 'unknown')

        # ── 1. 测试已注册命令 ──
        commands = getattr(mod, '_commands', {})
        for trigger, cmd_info in commands.items():
            result = self._test_command(mod, mod_name, trigger, cmd_info)
            results.append(result)

        # ── 2. 测试事件处理器 ──
        handlers = getattr(mod, '_event_handlers', [])
        for event_type, handler, priority in handlers:
            result = self._test_event_handler(mod, mod_name, event_type, handler)
            results.append(result)

        return results

    def _test_command(self, mod, mod_name: str, trigger: str, cmd_info: dict) -> dict:
        """测试单个命令：用空参数调用一次，记录结果。"""
        callback = cmd_info.get('callback')
        result = {
            "module": mod_name,
            "type": "command",
            "target": trigger,
            "passed": False,
            "error": None,
            "elapsed_ms": 0.0,
            "memory_delta_bytes": 0,
        }

        if callback is None:
            result["error"] = "callback is None"
            return result

        # 测量内存（粗略，跨线程限制）
        try:
            import tracemalloc
            mem_before = 0
            if tracemalloc.is_tracing():
                mem_before = tracemalloc.get_traced_memory()[0]
        except Exception:
            mem_before = 0

        start = time.time()
        try:
            # 尝试在事件循环中运行异步回调
            loop = getattr(self._host, '_main_loop', None)
            if loop and loop.is_running():
                if asyncio.iscoroutinefunction(callback):
                    # 构造一个空的命令上下文
                    ctx = self._make_empty_ctx(trigger)
                    future = asyncio.run_coroutine_threadsafe(
                        self._safe_call_async(callback, ctx), loop
                    )
                    try:
                        future.result(timeout=STRESS_CMD_TIMEOUT)
                    except asyncio.TimeoutError:
                        result["error"] = f"超时 ({STRESS_CMD_TIMEOUT}s)"
                    except Exception as e:
                        result["error"] = f"{type(e).__name__}: {e}"
                else:
                    # 同步回调：在线程池中执行
                    try:
                        ctx = self._make_empty_ctx(trigger)
                        callback(ctx)
                    except Exception as e:
                        result["error"] = f"{type(e).__name__}: {e}"
            else:
                # 无运行中的事件循环，同步测试
                if not asyncio.iscoroutinefunction(callback):
                    try:
                        ctx = self._make_empty_ctx(trigger)
                        callback(ctx)
                    except Exception as e:
                        result["error"] = f"{type(e).__name__}: {e}"
                else:
                    result["error"] = "无法测试异步回调（无事件循环）"
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"

        result["elapsed_ms"] = round((time.time() - start) * 1000, 2)

        try:
            import tracemalloc
            if tracemalloc.is_tracing():
                mem_after = tracemalloc.get_traced_memory()[0]
                result["memory_delta_bytes"] = max(0, mem_after - mem_before)
        except Exception:
            pass

        if result["error"] is None:
            result["passed"] = True

        return result

    def _test_event_handler(self, mod, mod_name: str, event_type: str, handler) -> dict:
        """测试单个事件处理器：模拟空事件调用。"""
        result = {
            "module": mod_name,
            "type": "event",
            "target": f"{event_type}:{getattr(handler, '__name__', 'unknown')}",
            "passed": False,
            "error": None,
            "elapsed_ms": 0.0,
            "memory_delta_bytes": 0,
        }

        start = time.time()
        try:
            loop = getattr(self._host, '_main_loop', None)
            if loop and loop.is_running():
                if asyncio.iscoroutinefunction(handler):
                    # 模拟空事件
                    mock_event = self._make_empty_event(event_type)
                    future = asyncio.run_coroutine_threadsafe(
                        self._safe_call_async(handler, mock_event), loop
                    )
                    try:
                        future.result(timeout=STRESS_EVENT_TIMEOUT)
                    except asyncio.TimeoutError:
                        result["error"] = f"超时 ({STRESS_EVENT_TIMEOUT}s)"
                    except Exception as e:
                        result["error"] = f"{type(e).__name__}: {e}"
                else:
                    mock_event = self._make_empty_event(event_type)
                    try:
                        handler(mock_event)
                    except Exception as e:
                        result["error"] = f"{type(e).__name__}: {e}"
            else:
                if not asyncio.iscoroutinefunction(handler):
                    try:
                        mock_event = self._make_empty_event(event_type)
                        handler(mock_event)
                    except Exception as e:
                        result["error"] = f"{type(e).__name__}: {e}"
                else:
                    result["error"] = "无法测试异步处理器（无事件循环）"
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"

        result["elapsed_ms"] = round((time.time() - start) * 1000, 2)

        if result["error"] is None:
            result["passed"] = True

        return result

    @staticmethod
    async def _safe_call_async(callback, *args):
        """安全异步调用，捕获异常。"""
        try:
            await callback(*args)
        except Exception:
            # 测试中的异常不传播，已记录在 result.error 中
            raise

    @staticmethod
    def _make_empty_ctx(trigger: str) -> object:
        """构造一个空的命令上下文对象。"""
        class _EmptyCtx:
            user_id = 0
            group_id = 0
            message = ""
            raw_data = {}
            args = []
            trigger = ""
            sender_uid = 300
            nickname = "StressTester"
            sender_nickname = "StressTester"
            sender_card = "StressTester"

        ctx = _EmptyCtx()
        ctx.trigger = trigger
        return ctx

    @staticmethod
    def _make_empty_event(event_type: str) -> object:
        """构造模拟事件对象。"""
        class _EmptyEvent:
            user_id = 0
            group_id = 0
            message = ""
            raw_data = {}
            player_name = "StressTester"
            player_uuid = "00000000-0000-0000-0000-000000000000"

        return _EmptyEvent()

    def _write_report(self, start_ts, end_ts, modules_tested, modules_skipped, results):
        """将压力测试报告写入 JSON 文件。"""
        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        failed = total - passed

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "duration_sec": round(end_ts - start_ts, 2),
            "modules_tested": modules_tested,
            "modules_skipped": modules_skipped,
            "total_cases": total,
            "passed": passed,
            "failed": failed,
            "results": results,
        }

        report_path = os.path.join(self._data_path, "stress_report.json")
        try:
            os.makedirs(os.path.dirname(report_path) or self._data_path, exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            _log.info("压力测试报告已写入: %s", report_path)
        except Exception as e:
            _log.error("写入压力测试报告失败: %s", e)

    def get_last_report(self) -> Optional[dict]:
        """读取最近一次压力测试报告。"""
        report_path = os.path.join(self._data_path, "stress_report.json")
        if os.path.isfile(report_path):
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

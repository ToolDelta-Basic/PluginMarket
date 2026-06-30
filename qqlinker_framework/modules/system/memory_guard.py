import asyncio
import gc
import logging
import os
import time
import sys
import traceback
from datetime import datetime, timedelta
from typing import Optional

from ...core.module import Module, ScheduledTask
from ...core.kernel.decorators import command

_log = logging.getLogger(__name__)

# ── 内存状态枚举 ──
class MemState:
    """内存状态枚举。"""
    OK = "ok"
    WARNING = "warning"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class MemoryGuard(Module):
    """内存守护 — 监控系统内存 + 智能重启策略。

    background=True: 预加载模块，持续运行。
    uid=100 (daemon): 框架级守护服务。
    """

    name: str = "memory_guard"
    mid: int = 100  # daemon
    uid: int = 100  # deprecated, use mid
    version: tuple = (1, 0, 0)
    background: bool = True

    dependencies: list[str] = []

    default_config: dict = {
        "内存守护": {
            "是否启用": True,
            "检查间隔_秒": 120,
            "警告阈值_RSS_MB": 800,
            "退化触发_内存占用比例": 0.85,
            "夜间安全重启": True,
            "夜间窗口_起始时": 2,
            "夜间窗口_结束时": 6,
            "长命令判定_分钟": 5,
            "重启前广播_秒": 30,
            "重启冷却_小时": 2.0,
            "重启后等待_秒": 10,
            "N小时高水位_小时": 0,
            "高水位阈值_RSS_MB": 1200,
            "定期重启_模式": "每天",
            "每天重启_时间": "04:00",
            "每周重启_星期几": 0,
            "每周重启_时间": "04:00",
            "通知群号": 0,
            "广播消息模板": "🔧 框架将在 {countdown} 秒后自动重启（内存守护），重启需要约 {wait} 秒，请稍候。",
        }
    }

    config_schema: dict = {
        "guard_enabled": ("内存守护.是否启用", True),
        "check_interval": ("内存守护.检查间隔_秒", 120),
        "warn_mb": ("内存守护.警告阈值_RSS_MB", 800),
        "degrade_ratio": ("内存守护.退化触发_内存占用比例", 0.85),
        "night_restart": ("内存守护.夜间安全重启", True),
        "night_start": ("内存守护.夜间窗口_起始时", 2),
        "night_end": ("内存守护.夜间窗口_结束时", 6),
        "long_cmd_min": ("内存守护.长命令判定_分钟", 5),
        "broadcast_sec": ("内存守护.重启前广播_秒", 30),
        "cooldown_hours": ("内存守护.重启冷却_小时", 2.0),
        "wait_sec": ("内存守护.重启后等待_秒", 10),
        "high_water_hours": ("内存守护.N小时高水位_小时", 0),
        "high_water_mb": ("内存守护.高水位阈值_RSS_MB", 1200),
        "schedule_mode": ("内存守护.定期重启_模式", "每天"),
        "daily_time": ("内存守护.每天重启_时间", "04:00"),
        "weekly_day": ("内存守护.每周重启_星期几", 0),
        "weekly_time": ("内存守护.每周重启_时间", "04:00"),
        "notify_group": ("内存守护.通知群号", 0),
        "broadcast_tpl": ("内存守护.广播消息模板", ""),
    }

    # ── @every 装饰器: 定时检查 ──

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = MemState.OK
        self._last_restart_at: float = 0.0
        self._restart_lock = asyncio.Lock()
        self._rss_history: list[tuple[float, float]] = []  # [(ts, rss_mb), ...]
        self._high_water_since: Optional[float] = None
        self._long_cmd_start: Optional[float] = None
        self._scheduled_restart_task: Optional[asyncio.Task] = None

    async def on_init(self):
        if not self.config.get("内存守护.是否启用", True):
            _log.info("内存守护已禁用")
            return

        _log.info("内存守护已启动 (检查间隔=%ds, 警告=%dMB, 夜间=%s)",
                  self.cfg_check_interval, self.cfg_warn_mb,
                  "启用" if self.cfg_night_restart else "禁用")

        # 注册 .内存状态 命令
        self.register_command(
            ".内存状态", self._cmd_mem_status,
            description="查看当前内存使用情况",
        )

        # 启动定期重启调度器
        await self._start_scheduled_restart()

    # ── 定时检查: @every 装饰器 ──

    @command(".内存状态")
    async def _cmd_mem_status(self, ctx):
        """查看当前内存使用详情。"""
        try:
            rss_mb = self._get_rss_mb()
            sys_mem = self._get_system_memory()
            uptime = self._get_uptime()
            state_emoji = {"ok": "✅", "warning": "⚠️", "degraded": "🔶", "critical": "🔴"}
            emoji = state_emoji.get(self._state, "❓")

            lines = [
                f"{emoji} 内存守护状态",
                f"状态: {self._state}",
                f"进程 RSS: {rss_mb:.1f} MB",
                f"系统可用: {sys_mem.get('available_gb', 0):.1f} GB / {sys_mem.get('total_gb', 0):.1f} GB",
                f"运行时长: {uptime}",
            ]
            if self._last_restart_at > 0:
                ago = time.time() - self._last_restart_at
                lines.append(f"上次重启: {ago/3600:.1f} 小时前")
            await ctx.reply("\n".join(lines))
        except Exception as e:
            await ctx.reply(f"查询失败: {e}")

    # ── 核心监控逻辑 ──

    async def _memory_check(self):
        """定时内存检查 — 由 @every 装饰器驱动。"""
        try:
            rss_mb = self._get_rss_mb()
            sys_mem = self._get_system_memory()
            now = time.time()

            # ── v5.2: 周期性清理过期命令（每 10 次检查 = 每 20 分钟）──
            self._orphan_cleanup_count = getattr(self, '_orphan_cleanup_count', 0) + 1
            if self._orphan_cleanup_count >= 10:
                self._orphan_cleanup_count = 0
                try:
                    host = self.services.try_get("host")
                    if host and hasattr(host, 'module_mgr'):
                        cleaned = await host.module_mgr.cleanup_orphan_commands()
                        if cleaned:
                            _log.info("清理 %d 条过期命令", cleaned)
                except Exception as e:
                    _log.debug("memory_guard._memory_check: %s", e)

            # 记录历史
            self._rss_history.append((now, rss_mb))
            # 只保留最近 24 小时
            cutoff = now - 86400
            self._rss_history = [(ts, v) for ts, v in self._rss_history if ts > cutoff]

            # 高水位追踪
            if self.cfg_high_water_hours > 0 and rss_mb >= self.cfg_high_water_mb:
                if self._high_water_since is None:
                    self._high_water_since = now
                    _log.warning("RSS 进入高水位: %.1f MB (阈值=%d MB, 开始追踪)",
                                 rss_mb, self.cfg_high_water_mb)
                else:
                    duration_h = (now - self._high_water_since) / 3600
                    if duration_h >= self.cfg_high_water_hours:
                        _log.critical(
                            "RSS 持续高水位 %.1f 小时 (%.1f MB)，触发紧急重启",
                            duration_h, rss_mb,
                        )
                        await self._trigger_restart(reason=f"持续高水位 {duration_h:.1f}h")
                        return
            else:
                self._high_water_since = None

            # 多级阈值判断
            ratio = sys_mem.get("used_ratio", 0)
            if ratio >= self.cfg_degrade_ratio:
                await self._on_critical(rss_mb, ratio, sys_mem)
            elif rss_mb >= self.cfg_warn_mb:
                await self._on_warning(rss_mb)
            else:
                if self._state != MemState.OK:
                    _log.info("内存状态恢复: %.1f MB (比例=%.1f%%)", rss_mb, ratio * 100)
                self._state = MemState.OK

            # debug: 定期输出
            _log.debug("内存检查: RSS=%.1fMB, 系统=%.1f%%, 状态=%s",
                       rss_mb, ratio * 100, self._state)

        except Exception:
            _log.error("内存检查异常: %s", traceback.format_exc())

    async def _on_warning(self, rss_mb: float):
        """警告: RSS 超过阈值，但系统内存充足。"""
        if self._state != MemState.WARNING:
            self._state = MemState.WARNING
            _log.warning("RSS 超过警告阈值: %.1f MB (阈值=%d MB)", rss_mb, self.cfg_warn_mb)
            # 主动 gc
            collected = gc.collect()
            _log.info("触发 gc.collect(), 回收 %d 个对象", collected)

    async def _on_critical(self, rss_mb: float, ratio: float, sys_mem: dict):
        """系统内存紧张。"""
        if self._state == MemState.CRITICAL:
            return

        self._state = MemState.CRITICAL
        _log.warning("系统内存紧张: RSS=%.1fMB, 使用率=%.1f%%, 可用=%.1fGB",
                     rss_mb, ratio * 100, sys_mem.get("available_gb", 0))

        # 判断是否触发重启
        should_restart = False
        reason = ""

        # 夜间窗口内 → 允许静默重启
        if self.cfg_night_restart and self._is_night_window():
            if await self._has_long_running_command():
                _log.info("夜间窗口内但不重启: 检测到活跃的长命令")
            else:
                should_restart = True
                reason = "夜间窗口 + 内存紧张"
        else:
            # 非夜间: 退化但不重启
            _log.warning("非夜间窗口，执行退化。可用内存=%.1fGB", sys_mem.get("available_gb", 0))
            # 通知管理员
            await self._notify(
                f"⚠️ 内存告警: RSS={rss_mb:.0f}MB, 系统使用率={ratio*100:.0f}%, "
                f"可用={sys_mem.get('available_gb',0):.1f}GB。"
                f"非夜间窗口仅执行 gc 退化，不触发重启。"
            )

        if should_restart:
            await self._trigger_restart(reason=reason)

    async def _trigger_restart(self, reason: str = "内存策略"):
        """执行重启流程。

        1. 检查冷却
        2. 广播通知
        3. 等待倒计时
        4. 保存状态
        5. 退出
        """
        async with self._restart_lock:
            # 冷却检查
            now = time.time()
            if self._last_restart_at > 0:
                elapsed_h = (now - self._last_restart_at) / 3600
                if elapsed_h < self.cfg_cooldown_hours:
                    _log.info("重启冷却中 (%.1f/%.1f 小时)，跳过", elapsed_h, self.cfg_cooldown_hours)
                    return

            self._last_restart_at = now

            _log.warning("⚠️ 触发重启: %s", reason)
            broadcast_sec = self.cfg_broadcast_sec

            # 广播
            tpl = self.config.get("内存守护.广播消息模板", "")
            if not tpl:
                tpl = "🔧 框架将在 {countdown} 秒后自动重启（{reason}），重启需要约 {wait} 秒，请稍候。"
            msg = tpl.format(countdown=broadcast_sec, reason=reason, wait=self.cfg_wait_sec)
            await self._broadcast(msg)

            # 倒计时
            if broadcast_sec > 0:
                _log.info("重启倒计时 %d 秒...", broadcast_sec)
                await asyncio.sleep(broadcast_sec)

            # 保存状态
            await self._save_state_before_restart()

            # 通知并尝试软重启
            await self._broadcast(
                f"🔄 框架正在软重启... 预计 {self.cfg_wait_sec} 秒后恢复。"
            )

            _log.warning("内存守护触发软重启 (reason=%s, rss=%.1fMB)", reason, self._get_rss_mb())

            # 短暂等待让消息发出
            await asyncio.sleep(2)

            # 尝试通过 framework_restart 服务进行软重启
            # 软重启不会杀进程，Minecraft/OneBot 不受影响
            restart_fn = self._root_services.try_get("framework_restart")
            if restart_fn:
                loop = asyncio.get_event_loop()
                # 需要在新任务中执行，因为当前协程会被停掉
                loop.create_task(restart_fn(reason))
            else:
                _log.error("framework_restart 服务不可用，无法软重启。降级为 gc.collect()")
                await self._broadcast(
                    "⚠️ 软重启服务不可用，仅执行内存回收。"
                )
                import gc
                gc.collect()

    # ── 定期重启调度 ──

    async def _start_scheduled_restart(self):
        """启动定期重启调度器（每天/每周）。"""
        mode = self.config.get("内存守护.定期重启_模式", "每天")
        if mode == "关闭":
            _log.info("定期计划重启已关闭")
            return

        _log.info("定期重启模式: %s", mode)
        self._scheduled_restart_task = asyncio.create_task(self._scheduled_restart_loop())

    async def _scheduled_restart_loop(self):
        """定期重启主循环 — 每分钟检查一次是否到计划时间。"""
        while True:
            try:
                await asyncio.sleep(60)
                if await self._should_scheduled_restart():
                    await self._trigger_restart(reason="定期计划重启")
            except asyncio.CancelledError:
                break
            except Exception:
                _log.error("定期重启检查异常: %s", traceback.format_exc())

    async def _should_scheduled_restart(self) -> bool:
        """检查是否到了计划重启时间。"""
        mode = self.config.get("内存守护.定期重启_模式", "每天")
        now = datetime.now()

        if mode == "每天":
            target = self.config.get("内存守护.每天重启_时间", "04:00")
            current = now.strftime("%H:%M")
            return current == target and now.minute == int(target.split(":")[1])

        elif mode == "每周":
            target_day = self.config.get("内存守护.每周重启_星期几", 0)
            target = self.config.get("内存守护.每周重启_时间", "04:00")
            if now.weekday() != target_day:
                return False
            current = now.strftime("%H:%M")
            return current == target and now.minute == int(target.split(":")[1])

        return False

    # ── 工具方法 ──

    @staticmethod
    def _get_rss_mb() -> float:
        """获取当前进程 RSS (MB)，纯 Python 实现无需 psutil。"""
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb_val = int(line.split(":")[1].strip().split()[0])
                        return kb_val / 1024.0
        except Exception as e:
            _log.debug("memory_guard._get_rss_mb: %s", e)
        return 0.0

    @staticmethod
    def _get_system_memory() -> dict:
        """读取系统内存信息（Linux /proc/meminfo）。"""
        try:
            meminfo = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        meminfo[key.strip()] = int(val.strip().split()[0])
            total_kb = meminfo.get("MemTotal", 0)
            available_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            total_gb = total_kb / (1024 * 1024)
            available_gb = available_kb / (1024 * 1024)
            used_ratio = (total_kb - available_kb) / max(total_kb, 1)
            return {
                "total_gb": total_gb,
                "available_gb": available_gb,
                "used_ratio": used_ratio,
            }
        except Exception:
            return {"total_gb": 0, "available_gb": 0, "used_ratio": 0}

    @staticmethod
    def _get_uptime() -> str:
        """获取进程运行时长。"""
        try:
            # Linux: /proc/self 启动时间
            start_ts = os.path.getctime("/proc/self")
            elapsed = time.time() - start_ts
            if elapsed < 3600:
                return f"{elapsed/60:.0f} 分钟"
            elif elapsed < 86400:
                return f"{elapsed/3600:.1f} 小时"
            else:
                return f"{elapsed/86400:.1f} 天"
        except Exception:
            return "未知"

    def _is_night_window(self) -> bool:
        """判断当前是否在夜间窗口内。"""
        now = datetime.now()
        start = self.config.get("内存守护.夜间窗口_起始时", 2)
        end = self.config.get("内存守护.夜间窗口_结束时", 6)
        hour = now.hour
        if start <= end:
            return start <= hour < end
        else:
            # 跨天窗口 (如 22-6)
            return hour >= start or hour < end

    async def _has_long_running_command(self) -> bool:
        """检查是否有超过阈值的活跃长命令。

        通过 host 的命令执行时间追踪判断。
        """
        # 留空 — 子类或后续集成可以接入 host 的命令执行追踪
        # 目前保守返回 False，即夜间窗口内只要有内存压力就允许重启
        return False

    async def _save_state_before_restart(self):
        """重启前保存所有模块状态。"""
        try:
            # 触发 gc 释放内存
            gc.collect()
            _log.info("已执行 gc.collect()")
        except Exception as e:
            _log.debug("memory_guard._save_state_before_restart: %s", e)

    async def _notify(self, msg: str):
        """发送通知到配置的群号。"""
        group_id = self.config.get("内存守护.通知群号", 0)
        if group_id and group_id > 0:
            try:
                await self.qq.send_group(group_id, msg)
            except Exception:
                _log.debug("发送通知失败: %s", traceback.format_exc())

    async def _broadcast(self, msg: str):
        """广播消息到通知群。"""
        await self._notify(msg)

    # ── 生命周期 ──

    async def on_start(self):
        """启动后开始定时检查。"""
        if not self.config.get("内存守护.是否启用", True):
            return

        # 使用 @every 替代手动任务: 更简洁
        interval = self.config.get("内存守护.检查间隔_秒", 120)

        async def _check_wrapper():
            await self._memory_check()

        # 直接创建定时检查任务（不走 ScheduledTask 装饰器，
        # 因为 on_init 里没有 @every 可用在这个上下文中）
        self._check_task = asyncio.create_task(self._run_check_loop(interval))

    async def _run_check_loop(self, interval: int):
        """内存检查循环。"""
        # 首次延迟 30 秒，让其他模块先完成初始化
        await asyncio.sleep(30)
        _log.info("内存守护开始定时检查 (间隔=%ds)", interval)
        while True:
            try:
                await self._memory_check()
            except asyncio.CancelledError:
                break
            except Exception:
                _log.error("内存检查异常: %s", traceback.format_exc())
            await asyncio.sleep(interval)

    async def on_stop(self):
        """模块卸载。"""
        if hasattr(self, '_check_task'):
            self._check_task.cancel()
        if self._scheduled_restart_task:
            self._scheduled_restart_task.cancel()
        _log.info("内存守护已停止")

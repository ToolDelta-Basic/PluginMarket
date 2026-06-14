"""命令路由中间件（权限检查 + 角色系统 + 冷却控制 + 群级模块过滤 + 友好错误提示）。

v2.0: 新增 per-user asyncio.Lock 映射 — 同一用户消息串行处理。
v3.0: 新增模块级熔断器 — 60s 内连续 3 次失败自动熔断 120s。
"""
import asyncio
import time
import logging
from typing import Dict, List, Optional

from ...core.kernel.error_hints import hint
from ..kernel.context import CommandContext
from ..kernel.audit_trail import AuditTrail

# 默认 per-user 锁获取超时（秒）
USER_LOCK_TIMEOUT = 30.0

# ── v3.0 熔断器常量 ──
CIRCUIT_BREAKER_WINDOW = 60.0      # 60 秒故障窗口
CIRCUIT_BREAKER_THRESHOLD = 3       # 窗口内 3 次连续失败触发熔断
CIRCUIT_BREAKER_COOLDOWN = 120.0    # 熔断 120 秒后尝试恢复


class CommandRouter:
    """将 GroupMessageEvent 分发给匹配的命令，进行权限校验和冷却控制。

    v2.0 改进:
      - 按 user_id 加锁（同一用户消息串行处理），防止帮助翻页消息和
        被路由的命令同时执行导致竞态。
      - _user_locks 使用 asyncio.Lock 映射，2h 未使用的锁自动清理。
    """

    def __init__(
        self,
        command_mgr,  # : CommandManager
        adapter,
        config_mgr,
        message_mgr,
        group_filter=None,
        loaded_modules: dict = None,
        uid_lookup=None,
        audit_trail: Optional[AuditTrail] = None,
        source_mgr=None,
    ):
        self.command_mgr = command_mgr
        self.adapter = adapter
        self.config_mgr = config_mgr
        self.message_mgr = message_mgr
        self.group_filter = group_filter
        self.loaded_modules = loaded_modules or {}
        self.source_mgr = source_mgr
        self.uid_lookup = uid_lookup
        self.audit_trail = audit_trail
        self._cooldowns: dict[str, dict[int, float]] = {}
        self._cooldown_check_count = 0

        # Layer 2: per-user 串行锁
        self._user_locks: Dict[int, asyncio.Lock] = {}
        self._user_locks_lock = asyncio.Lock()  # 保护 _user_locks 本身
        self._user_lock_last_used: Dict[int, float] = {}
        self._user_lock_cleanup_count = 0

        # Layer 3: v3.0 模块级熔断器（60s/3次/120s）
        # _circuit_breakers[module_name] = {
        #     "failures": [(timestamp, error_type), ...],  # 窗口内失败记录
        #     "open_since": timestamp or 0,               # 熔断开启时间
        #     "total_failures": int,                        # 总故障数（监控用）
        # }
        self._circuit_breakers: Dict[str, dict] = {}
        self._circuit_breaker_lock = asyncio.Lock()
        self._cb_cleanup_count = 0

    async def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        """获取或创建 per-user 锁（线程安全）。"""
        async with self._user_locks_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = asyncio.Lock()
            self._user_lock_last_used[user_id] = time.monotonic()
            return self._user_locks[user_id]

    async def _get_guardian(self):
        """安全获取资源守护者服务。"""
        try:
            from ..host import FrameworkHost
            host = None
            # 通过 uid_lookup 的 closure 反向查找（weak pattern）
            # fallback: 检查 services container
            if hasattr(self, '_host_ref'):
                host = self._host_ref
            if host and hasattr(host, 'guardian'):
                return host.guardian
        except Exception:
            pass
        return None

    # ═══════════════════════════════════════════════════════════
    # v3.0: 模块级熔断器
    # ═══════════════════════════════════════════════════════════

    async def _check_circuit_breaker(self, module_name: str) -> bool:
        """检查模块熔断器是否开启。返回 True 表示熔断中（拒绝执行）。"""
        async with self._circuit_breaker_lock:
            cb = self._circuit_breakers.get(module_name)
            if cb is None:
                return False
            # 熔断已开启
            if cb.get("open_since", 0) > 0:
                elapsed = time.time() - cb["open_since"]
                if elapsed < CIRCUIT_BREAKER_COOLDOWN:
                    # 仍在熔断期
                    remain = CIRCUIT_BREAKER_COOLDOWN - elapsed
                    logging.getLogger(__name__).warning(
                        "熔断器: 模块 '%s' 已熔断 (剩余 %.0fs)",
                        module_name, remain,
                    )
                    return True
                else:
                    # 熔断期结束，尝试半开（half-open）恢复
                    cb["open_since"] = 0.0
                    # 保留 failures 记录以便半开状态跟踪
                    logging.getLogger(__name__).info(
                        "熔断器: 模块 '%s' 进入半开恢复状态", module_name,
                    )
                    return False
            return False

    async def _resolve_callback(self, cmd_info: dict, module_name: str):
        """解析命令回调 — 懒加载模块先激活后返回方法引用。

        对于已加载模块（background=True），直接返回 callback（绑定方法）。
        对于懒加载模块（background=False），通过 SourceManager 激活后获取方法。
        """
        callback = cmd_info.get("callback")
        if callback is not None:
            return callback

        # 懒加载模块未激活：通过 SourceManager 激活
        if self.source_mgr is None:
            return None

        module = await self.source_mgr._activate_lazy_module(module_name)
        if module is None:
            return None

        # 从新激活的模块获取方法
        method_name = cmd_info.get("method")
        if method_name:
            return getattr(module, method_name, None)
        return None

    async def _record_circuit_failure(self, module_name: str, error: str = "") -> None:
        """记录模块命令执行失败，超过阈值则熔断。"""
        now = time.time()
        async with self._circuit_breaker_lock:
            if module_name not in self._circuit_breakers:
                self._circuit_breakers[module_name] = {
                    "failures": [],
                    "open_since": 0.0,
                    "total_failures": 0,
                }
            cb = self._circuit_breakers[module_name]

            # 只保留窗口内的失败记录
            recent = [f for f in cb["failures"] if now - f[0] < CIRCUIT_BREAKER_WINDOW]
            recent.append((now, error[:100] if error else "unknown"))
            cb["failures"] = recent
            cb["total_failures"] += 1

            if len(recent) >= CIRCUIT_BREAKER_THRESHOLD:
                # 触发熔断
                cb["open_since"] = now
                logging.getLogger(__name__).error(
                    "⚡ 熔断器触发: 模块 '%s' 在 %.0fs 内连续 %d 次失败，"
                    "已熔断 %ds",
                    module_name, CIRCUIT_BREAKER_WINDOW,
                    CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_COOLDOWN,
                )
                # 通知降级引擎
                try:
                    degradation = self.services.try_get("degradation") if hasattr(self, 'services') else None
                    if degradation:
                        degradation.on_service_fail(
                            f"module:{module_name}",
                            f"circuit_breaker_open: {len(recent)} failures in {CIRCUIT_BREAKER_WINDOW}s",
                        )
                except Exception:
                    pass

    async def _reset_circuit_breaker(self, module_name: str) -> None:
        """命令执行成功后重置熔断器（半开恢复确认）。"""
        async with self._circuit_breaker_lock:
            if module_name in self._circuit_breakers:
                cb = self._circuit_breakers[module_name]
                if cb.get("open_since", 0) == 0.0 and len(cb.get("failures", [])) > 0:
                    # 半开状态成功执行 → 完全恢复
                    cb["failures"] = []
                    logging.getLogger(__name__).info(
                        "熔断器: 模块 '%s' 已恢复 (半开确认)", module_name,
                    )
                    # 清除降级状态
                    try:
                        degradation = self.services.try_get("degradation") if hasattr(self, 'services') else None
                        if degradation:
                            degradation.clear_degraded(f"module:{module_name}")
                    except Exception:
                        pass

    def get_circuit_breaker_status(self) -> Dict[str, dict]:
        """返回所有熔断器状态（供监控/控制台查询）。"""
        return {
            name: {
                "open": cb.get("open_since", 0) > 0,
                "open_since": cb.get("open_since", 0),
                "recent_failures": len(cb.get("failures", [])),
                "total_failures": cb.get("total_failures", 0),
                "cooldown_remaining": max(0, CIRCUIT_BREAKER_COOLDOWN - (time.time() - cb.get("open_since", 0)))
                    if cb.get("open_since", 0) > 0 else 0,
            }
            for name, cb in self._circuit_breakers.items()
        }

    async def handle_message(self, event):
        """处理群消息事件，查找匹配命令并执行。

        v6 增强: 检查交互式会话约定 — 若用户处于交互式会话且
        capture_command=True，跳过所有命令匹配。
        """
        # ── v6 交互式会话拦截 ──
        tracker = None
        try:
            tracker = self.source_mgr.host.services.try_get("session_tracker")
        except Exception:
            pass
        if tracker is not None:
            session = tracker.get_session(event.user_id) if hasattr(tracker, 'get_session') else None
            if session and session.get("capture_command", True):
                # 更新时间戳
                if hasattr(tracker, 'touch'):
                    tracker.touch(event.user_id)
                # 不过滤事件 — 模块的 @listen 处理器仍然能收到 GroupMessageEvent
                # 但不走命令路由
                return False

        return await self._handle_message_impl(event)

    async def _handle_message_impl(self, event):
        """命令路由内部实现（调用方已持有 per-user 锁）。"""
        msg = (event.message or "").strip()
        if not msg:
            return False
        for cmd_info in self.command_mgr.get_group_commands():
            trigger = cmd_info["trigger"]
            if not msg.startswith(trigger):
                continue

            # ── 群级模块/命令过滤 (root不受隔离) ──
            if self.group_filter:
                module_name = cmd_info.get("plugin", "core")
                caller_uid = self.uid_lookup(event.user_id) if self.uid_lookup else 400
                if not self.group_filter.is_command_enabled(
                    event.group_id, module_name, trigger, caller_uid=caller_uid
                ):
                    _log = logging.getLogger(__name__)
                    _log.debug(
                        "命令被群过滤拦截: trigger=%s module=%s group=%d user=%d",
                        trigger, module_name, event.group_id, event.user_id,
                    )
                    return False  # 静默忽略，不给提示

            # ── 冷却检查 ──
            cooldown = cmd_info.get("cooldown", 0)
            if cooldown > 0:
                now = time.time()
                # 定期清理过期条目（每 100 次检查触发一次）
                if self._cooldown_check_count >= 100:
                    self._cleanup_cooldowns(now)
                    self._cooldown_check_count = 0
                self._cooldown_check_count += 1
                user_cd = self._cooldowns.setdefault(trigger, {})
                last = user_cd.get(event.user_id, 0)
                if now - last < cooldown:
                    remain = cooldown - (now - last)
                    ctx = CommandContext(
                        user_id=event.user_id,
                        group_id=event.group_id,
                        nickname=event.nickname,
                        message=event.message,
                        args=[],
                        adapter=self.adapter,
                        message_mgr=self.message_mgr,
                    )
                    await ctx.reply(
                        f"⏳ 命令冷却中，请 {remain:.0f} 秒后再试。{hint['COMMAND_COOLDOWN']}"
                    )
                    event.handled = True
                    return True

            # ── 权限检查 ──
            # v5.1 修复: daemon 用户 (uid ≤ 100) 自动拥有 op/role 权限
            authorized = True
            if cmd_info.get("op_only", False):
                daemon_ok = (
                    self.uid_lookup is not None
                    and self.uid_lookup(event.user_id) <= 100
                )
                authorized = daemon_ok or self.adapter.is_user_admin(
                    event.user_id, self.config_mgr
                )
            elif required_role := cmd_info.get("required_role"):
                daemon_ok = (
                    self.uid_lookup is not None
                    and self.uid_lookup(event.user_id) <= 100
                )
                authorized = daemon_ok or self._check_role(
                    required_role, event.user_id
                )

            if not authorized:
                ctx = CommandContext(
                    user_id=event.user_id,
                    group_id=event.group_id,
                    nickname=event.nickname,
                    message=event.message,
                    args=[],
                    adapter=self.adapter,
                    message_mgr=self.message_mgr,
                )
                await ctx.reply(
                    f"🔒 权限不足，该命令仅管理员可用。{hint['COMMAND_PERMISSION_DENIED']}"
                )
                logging.getLogger(__name__).warning(
                    "用户 %s 尝试越权执行命令 %s", str(event.user_id), trigger,
                )
                event.handled = True
                return True

            # ── UID 等级检查 ──
            min_uid = cmd_info.get("min_uid", 400)
            if self.uid_lookup and min_uid >= 0:
                user_uid = self.uid_lookup(event.user_id)
                if user_uid > 0 and user_uid > min_uid:
                    logging.getLogger(__name__).warning(
                        "用户 %s (uid=%s) 尝试执行需要 min_uid=%s 的命令 %s",
                        str(event.user_id), str(user_uid), str(min_uid), trigger,
                    )
                    ctx = CommandContext(
                        user_id=event.user_id,
                        group_id=event.group_id,
                        nickname=event.nickname,
                        message=event.message,
                        args=[],
                        adapter=self.adapter,
                        message_mgr=self.message_mgr,
                    )
                    await ctx.reply(
                        f"\U0001f512 你的 UID ({user_uid}) 不足，"
                        f"该命令需要 UID <= {min_uid}"
                    )
                    event.handled = True
                    return True

            args_str = msg[len(trigger):].strip()
            args = args_str.split() if args_str else []
            ctx = CommandContext(
                user_id=event.user_id,
                group_id=event.group_id,
                nickname=event.nickname,
                message=event.message,
                args=args,
                adapter=self.adapter,
                message_mgr=self.message_mgr,
            )

            # ── v3.0 熔断器检查 ──
            module_name = cmd_info.get("plugin", "core")
            if await self._check_circuit_breaker(module_name):
                await ctx.reply(
                    "⚡ 该模块暂时不可用（故障熔断中），请稍后再试。"
                )
                event.handled = True
                return True

            # ── 审计追溯: 记录开始时间 ──
            user_uid = self.uid_lookup(event.user_id) if self.uid_lookup else 4009
            cmd_start = time.time()
            cmd_success = True
            cmd_error = ""

            try:
                # ── 资源守护者: 频率检查 + 命令超时包装 ──
                guardian = await self._get_guardian()

                if guardian:
                    # v5: 命令调用频率检查（每分钟上限）
                    if guardian.config.enabled:
                        cmd_rate_ok = await guardian.check_command_rate(module_name)
                        if not cmd_rate_ok:
                            await ctx.reply(
                                "⏳ 该模块调用过于频繁，请稍后再试"
                            )
                            event.handled = True
                            return True
                    # 频率检查
                    rate_ok = await guardian.check_rate(module_name, user_uid)
                    if not rate_ok:
                        await ctx.reply(
                            "⚠️ 模块繁忙，请稍后再试。"
                        )
                        event.handled = True
                        return True
                    # 命令超时包装
                    callback = await self._resolve_callback(cmd_info, module_name)
                    if callback is None:
                        await ctx.reply("⚠️ 模块不可用，请稍后重试")
                        event.handled = True
                        return True
                    await guardian.guard(
                        callback(ctx),
                        user_uid,
                        module_name,
                    )
                else:
                    callback = await self._resolve_callback(cmd_info, module_name)
                    if callback is None:
                        await ctx.reply("⚠️ 模块不可用，请稍后重试")
                        event.handled = True
                        return True
                    await callback(ctx)

                event.handled = True
                # 执行成功后才记录冷却
                if cooldown > 0:
                    user_cd[event.user_id] = now

                # ── v3.0 熔断器恢复确认 ──
                await self._reset_circuit_breaker(module_name)

            except asyncio.TimeoutError:
                cmd_success = False
                cmd_error = "TimeoutError"
                logging.getLogger(__name__).warning(
                    "命令 %s 执行超时 (模块: %s)",
                    trigger, module_name,
                )
                await self._record_circuit_failure(module_name, "TimeoutError")
                try:
                    await ctx.reply(
                        "⏰ 命令执行超时，请稍后再试。"
                    )
                except Exception:
                    pass
                # ── v5: 通知健康评分器（失败）──
                await self._notify_health_scorer(module_name, success=False,
                                                  elapsed_ms=3000, exception=None)
            except Exception as e:
                cmd_success = False
                cmd_error = f"{type(e).__name__}: {e}"
                logging.getLogger(__name__).error(
                    "命令 %s 执行异常: %s。%s",
                    trigger, e, hint['COMMAND_EXEC_FAILED'],
                )
                await self._record_circuit_failure(module_name, type(e).__name__)
                try:
                    await ctx.reply(
                        f"❌ 命令执行出错。{hint['COMMAND_EXEC_FAILED']}"
                    )
                except Exception:
                    pass
                # ── v5: 通知健康评分器（失败）──
                await self._notify_health_scorer(module_name, success=False,
                                                  exception=e)
            finally:
                # ── v5: 通知健康评分器（成功）──
                if cmd_success:
                    elapsed_ms = (time.time() - cmd_start) * 1000
                    await self._notify_health_scorer(module_name, success=True,
                                                      elapsed_ms=elapsed_ms)
                # ── 审计追溯: 记录执行摘要 ──
                if self.audit_trail:
                    elapsed_ms = (time.time() - cmd_start) * 1000
                    self.audit_trail.record(
                        user_id=event.user_id,
                        group_id=event.group_id,
                        nickname=event.nickname,
                        command=trigger,
                        args=args,
                        module=module_name,
                        uid_level=user_uid,
                        success=cmd_success,
                        error=cmd_error,
                        elapsed_ms=elapsed_ms,
                    )
            return True
        return False

    def _cleanup_cooldowns(self, now: float):
        """清理过期的冷却条目。"""
        for trigger in list(self._cooldowns):
            user_cd = self._cooldowns[trigger]
            expired = [uid for uid, t in user_cd.items() if now - t > 120]
            for uid in expired:
                del user_cd[uid]
            if not user_cd:
                del self._cooldowns[trigger]

    def _cleanup_user_locks(self):
        """清理 2 小时内未使用的 per-user 锁。"""
        cutoff = time.monotonic() - 7200  # 2 hours
        stale = [
            uid for uid, ts in self._user_lock_last_used.items()
            if ts < cutoff
        ]
        for uid in stale:
            self._user_locks.pop(uid, None)
            self._user_lock_last_used.pop(uid, None)

    async def _notify_health_scorer(self, module_name: str, success: bool,
                                     elapsed_ms: float = 0,
                                     exception: Optional[Exception] = None):
        """通知健康评分器命令执行结果。"""
        try:
            from ..host import FrameworkHost
            host = None
            if hasattr(self, '_host_ref'):
                host = self._host_ref
            if host and hasattr(host, 'health_scorer'):
                scorer = host.health_scorer
                if success:
                    scorer.on_command_success(module_name, elapsed_ms)
                else:
                    scorer.on_command_failure(module_name, elapsed_ms, exception)
        except Exception:
            pass  # 健康评分非关键，静默降级

    def _check_role(self, role: str, user_id: int) -> bool:
        """检查用户是否属于指定角色（兼容字符串和整数 user_id）。"""
        roles = self.config_mgr.get("权限管理.角色", {}, requester_uid=0)
        if not isinstance(roles, dict):
            return False
        allowed = roles.get(role, [])
        if not isinstance(allowed, list):
            return False
        uid_int = int(user_id) if not isinstance(user_id, int) else user_id
        if uid_int in [int(q) for q in allowed if q]:
            return True
        logging.getLogger(__name__).warning(
            "用户 %s 无角色 '%s' 权限", str(user_id), role
        )
        return False

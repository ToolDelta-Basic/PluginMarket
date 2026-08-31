import asyncio
import collections
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Optional, Set, Tuple

_log = logging.getLogger(__name__)

# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_CMD_TIMEOUT = 3.0          # 命令执行软超时（秒）
DEFAULT_FREQ_SOFT_LIMIT = 20       # 每分钟软限制次数
DEFAULT_FREQ_HARD_LIMIT = 30       # 每分钟硬限制次数
DEFAULT_MSG_PER_HOUR = 100         # 每小时消息上限
MAX_VIOLATIONS_BEFORE_KILL = 3     # 窗口内违规 N 次 → 杀死
MAX_VIOLATIONS_BEFORE_BAN = 6      # 总量违规 N 次 → 永久禁用
VIOLATION_WINDOW = 600             # 违规计数窗口（10分钟）
FREQ_WINDOW = 60                   # 频率滑动窗口（秒）

# 文件沙箱白名单 — 非 root 模块可访问的目录前缀
SANDBOX_ALLOWED_PREFIXES = ("data/", "模块/", "日志/", "配置/",
                            "工具/", "第三方库/")


# ── 枚举 ────────────────────────────────────────────────

class GuardAction(IntEnum):
    """资源守护者执行动作级别"""
    LOG_ONLY = 0    # 仅日志警告
    THROTTLE = 1    # 节流（降低该模块的调用频率）
    ISOLATE = 2     # 隔离（触发 _rollback_module 卸载）
    BAN = 3         # 永久禁用（写入 persist 黑名单）


class ResourceViolation(IntEnum):
    """违规类型枚举"""
    CPU_TIMEOUT = 1       # 单次命令执行超时
    CALL_RATE = 5         # 调用速率超限
    MESSAGE_RATE = 6      # 消息发送速率超限
    FILE_ACCESS = 7       # 非法文件访问


# ── 数据结构 ────────────────────────────────────────────

@dataclass
class GuardianConfig:
    """守护者全局配置"""
    enabled: bool = True
    root_exempt: bool = True              # uid=0 模块不受限制

    cmd_timeout: float = DEFAULT_CMD_TIMEOUT
    freq_soft_limit: int = DEFAULT_FREQ_SOFT_LIMIT
    freq_hard_limit: int = DEFAULT_FREQ_HARD_LIMIT
    freq_window: float = FREQ_WINDOW

    msg_per_hour: int = DEFAULT_MSG_PER_HOUR

    violation_window: float = VIOLATION_WINDOW
    max_violations_before_kill: int = MAX_VIOLATIONS_BEFORE_KILL
    max_violations_before_ban: int = MAX_VIOLATIONS_BEFORE_BAN

    # 命令调用频率限制（独立于通用频率检查）
    max_commands_per_minute: int = 30          # 每分钟最多命令调用次数
    enforce_command_rate: bool = True          # 是否强制执行命令频率限制

    blacklist_path: str = "data/resource_blacklist.json"


@dataclass
class ModuleProfile:
    """单个模块的运行画像"""
    module_name: str
    module_uid: int

    # 违规计数
    violation_count: int = 0              # 总量
    violation_events: list = field(default_factory=list)  # [(ts, type), ...]
    killed: bool = False
    banned: bool = False
    throttle_factor: float = 1.0


# ── H3 修复: 独立模块身份验证 frozenset ─────────────────
# 不依赖可变的 uid 参数，而是通过模块路径验证是否为框架内核/守护。
# 防止 C1 提权（_tier=0）后连带绕过 ResourceGuardian。

_VERIFIED_ROOT_MODULES: frozenset = frozenset({
    "qqlinker_framework.core.host", "qqlinker_framework.libraries.channel_host",
    "qqlinker_framework.__init__",
    "qqlinker_framework.managers",
    "qqlinker_framework.modules.security.orion",
    "qqlinker_framework.modules.ai",
})


# ── 核心类 ──────────────────────────────────────────────

class ResourceGuardian:
    """资源守护者 — 运行时对非 root 模块的资源消耗实时监控与执行动作"""

    # ── H3 修复: 已验证的 root 模块名集合 ──
    _verified_root_modules: frozenset = _VERIFIED_ROOT_MODULES

    def __init__(
        self,
        config: GuardianConfig = None,
        kill_callback: Any = None,
        host_ref: Any = None,
    ):
        self.config = config or GuardianConfig()
        self._kill_callback = kill_callback   # async def(name) → kill module
        self._host_ref = host_ref             # FrameworkHost 引用

        # Per-module profiles
        self._profiles: Dict[str, ModuleProfile] = {}

        # 滑动窗口频率计数器: module_name → deque((timestamp,), ...)
        self._freq_windows: Dict[str, collections.deque] = {}

        # 消息发送计数器: module_name → {"hour": hour_int, "count": N}
        self._msg_counters: Dict[str, Dict[str, int]] = {}

        # 命令调用时间戳: module_name → list[float]（1分钟滑动窗口）
        self._command_timestamps: Dict[str, list] = {}

        # 黑名单持久化
        self._blacklist: Set[str] = set()
        self._load_blacklist()

    # ── 生命周期 ──

    async def start(self) -> None:
        """启动资源守护者（从磁盘加载黑名单）。"""
        _log.info("资源守护者已启动 (cmd_timeout=%.1fs, freq=%d/%d/min, "
                  "msg=%d/h)",
                  self.config.cmd_timeout,
                  self.config.freq_soft_limit,
                  self.config.freq_hard_limit,
                  self.config.msg_per_hour)

    async def stop(self) -> None:
        """优雅停止资源守护者。"""
        _log.info("资源守护者已停止")
        self._save_blacklist()

    # ── 模块追踪 ──

    def track_module(self, module_name: str, uid: int) -> None:
        """开始追踪一个模块。"""
        if module_name not in self._profiles:
            self._profiles[module_name] = ModuleProfile(
                module_name=module_name, module_uid=uid,
            )
        if module_name not in self._freq_windows:
            self._freq_windows[module_name] = collections.deque()

    def untrack_module(self, module_name: str) -> None:
        """停止追踪一个模块。"""
        self._profiles.pop(module_name, None)
        self._freq_windows.pop(module_name, None)
        self._msg_counters.pop(module_name, None)
        self._command_timestamps.pop(module_name, None)

    def is_banned(self, module_name: str) -> bool:
        """检查模块是否在黑名单中。"""
        return module_name in self._blacklist

    # ── 守卫钩子 ──

    def _is_root_module(self, uid: int, module_name: str) -> bool:
        """H3 修复: 独立模块身份验证，不依赖可变的 uid 参数。

        仅同时满足以下条件才认定为 root:
        1. uid == 0
        2. module_name 在 _verified_root_modules 中

        修复前仅检查 uid==0，C1 提权后可伪造为 0 完全绕过。
        """
        if not self.config.root_exempt:
            return False
        if uid != 0:
            return False
        if not module_name or module_name not in self._verified_root_modules:
            return False
        return True

    async def guard(
        self,
        command_co,
        uid: int,
        module_name: str,
        timeout: float = None,
    ) -> Any:
        """包装命令执行，添加超时保护。

        Args:
            command_co: 协程对象（如 cmd_info['callback'](ctx) 的返回值）
            uid: 模块 UID
            module_name: 模块名称
            timeout: 超时秒数（None=使用默认值）

        Returns:
            协程的返回值

        Raises:
            asyncio.TimeoutError: 命令超时（上层已捕获）
        """
        # root 豁免 (H3: 独立身份验证)
        if self._is_root_module(uid, module_name):
            return await command_co

        t = timeout if timeout is not None else self.config.cmd_timeout

        try:
            return await asyncio.wait_for(command_co, timeout=t)
        except asyncio.TimeoutError:
            _log.warning(
                "模块 '%s' (uid=%d) 命令执行超时 (%.1fs)，"
                "记录违规 #%d",
                module_name, uid, t,
                self._profiles.get(module_name, ModuleProfile(module_name, uid)).violation_count + 1,
            )
            await self._handle_violation(
                module_name, uid, ResourceViolation.CPU_TIMEOUT,
                f"命令执行超时 ({t}s)",
            )
            raise

    async def check_rate(self, module_name: str, uid: int) -> bool:
        """检查模块调用频率，返回是否允许执行。

        - 软限制超限 → 警告
        - 硬限制超限 → 杀死模块

        Returns:
            True 允许，False 拒绝（硬限制超限）
        """
        if self._is_root_module(uid, module_name):
            return True

        now = time.monotonic()
        window = self._freq_windows.get(module_name)
        if window is None:
            window = collections.deque()
            self._freq_windows[module_name] = window

        # 清理窗口外条目
        cutoff = now - self.config.freq_window
        while window and window[0] < cutoff:
            window.popleft()

        window.append(now)
        count = len(window)

        if count >= self.config.freq_hard_limit:
            _log.warning(
                "模块 '%s' (uid=%d) 调用频率超硬限制 (%d次/%ds)，触发隔离",
                module_name, uid, count, int(self.config.freq_window),
            )
            await self._handle_violation(
                module_name, uid, ResourceViolation.CALL_RATE,
                f"频率硬限制超限 ({count}次/{int(self.config.freq_window)}s)",
            )
            return False

        if count >= self.config.freq_soft_limit:
            _log.info(
                "模块 '%s' (uid=%d) 调用频率超软限制 (%d次/%ds)",
                module_name, uid, count, int(self.config.freq_window),
            )

        return True

    async def check_command_rate(self, module_name: str) -> bool:
        """检查模块在最近1分钟内的命令调用次数。

        独立于通用 check_rate，专门用于命令路由的频率限制。
        基于自我维护的 _command_timestamps 滑动窗口。

        Returns:
            True 允许执行，False 超过 max_commands_per_minute 限制。
        """
        if not self.config.enforce_command_rate:
            return True

        now = time.monotonic()

        # 获取或初始化该模块的时间戳列表
        if module_name not in self._command_timestamps:
            self._command_timestamps[module_name] = []

        timestamps = self._command_timestamps[module_name]

        # 清理 1 分钟窗口外的过期时间戳
        cutoff = now - 60.0
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        count = len(timestamps)

        if count >= self.config.max_commands_per_minute:
            _log.warning(
                "模块 '%s' 命令调用频率超限 (%d次/分钟, 上限 %d)，已拒绝",
                module_name, count, self.config.max_commands_per_minute,
            )
            # 记录违规
            await self._handle_violation(
                module_name, 0, ResourceViolation.CALL_RATE,
                f"命令调用频率超限 ({count}次/分钟, 上限 {self.config.max_commands_per_minute})",
            )
            return False

        # 记录本次调用时间戳
        timestamps.append(now)
        return True

    async def check_msg_send(self, uid: int, module_name: str = "") -> bool:
        """检查消息发送频率（小时级配额）。

        Returns:
            True 允许发送，False 配额耗尽
        """
        if self._is_root_module(uid, module_name):
            return True

        # 使用 module_name 作为计数键（fallback uid）
        key = module_name or str(uid)
        now = time.localtime()
        current_hour = now.tm_hour + now.tm_yday * 24

        counter = self._msg_counters.get(key)
        if counter is None or counter.get("hour") != current_hour:
            self._msg_counters[key] = {"hour": current_hour, "count": 0}
            return True

        if counter["count"] >= self.config.msg_per_hour:
            _log.warning(
                "模块 '%s' (uid=%d) 消息发送配额耗尽 (%d/%d小时)",
                key, uid, counter["count"], self.config.msg_per_hour,
            )
            await self._handle_violation(
                key, uid, ResourceViolation.MESSAGE_RATE,
                f"消息配额耗尽 ({counter['count']}/{self.config.msg_per_hour}h)",
            )
            return False

        counter["count"] += 1
        return True

    def check_file_access(self, path: str, uid: int, mode: str = "r", module_name: str = "") -> bool:
        """文件访问沙箱检查。

        非 root (uid≠0) 模块只能读写 data/ 和配置/ 下的文件。

        Returns:
            True 允许访问，False 拒绝。
        """
        if self._is_root_module(uid, module_name):
            return True

        # 规范化路径
        norm = os.path.normpath(path)

        # 检查是否在白名单前缀内
        for prefix in SANDBOX_ALLOWED_PREFIXES:
            if norm.startswith(prefix) or norm.startswith("./" + prefix):
                return True

        # 也检查绝对路径
        for prefix in SANDBOX_ALLOWED_PREFIXES:
            abs_prefix = os.path.abspath(prefix)
            if os.path.abspath(norm).startswith(abs_prefix):
                return True

        _log.warning(
            "模块 (uid=%d) 尝试访问沙箱外文件: '%s' (mode=%s)，已拒绝",
            uid, norm, mode,
        )
        return False

    # ── 违规处理 ──

    async def _handle_violation(
        self,
        module_name: str,
        uid: int,
        violation_type: ResourceViolation,
        detail: str,
    ) -> None:
        """统一的违规处理入口。"""
        profile = self._profiles.get(module_name)
        if profile is None:
            profile = ModuleProfile(module_name=module_name, module_uid=uid)
            self._profiles[module_name] = profile

        now = time.monotonic()
        profile.violation_count += 1

        # 清理窗口外违事件
        cutoff = now - self.config.violation_window
        profile.violation_events = [
            (ts, vt) for ts, vt in profile.violation_events
            if ts > cutoff
        ]
        profile.violation_events.append((now, violation_type))

        window_count = len(profile.violation_events)

        _log.info(
            "模块 '%s' 违规: %s — %s (窗口内 %d, 总计 %d)",
            module_name, violation_type.name, detail,
            window_count, profile.violation_count,
        )

        # 审计日志
        try:
            from .audit import audit_log, AuditLevel
            audit_log(
                sender="guardian",
                action=f"violation.{violation_type.name}",
                target=module_name,
                detail=detail,
                level=AuditLevel.WARNING,
            )
        except ImportError as e:
            _log.warning("resource_guardian.resource_guardian: %s", e)

        # ── v5: 通知健康评分器（违规）──
        self._notify_health_scorer(module_name)

        # 决策树
        if profile.violation_count >= self.config.max_violations_before_ban:
            await self._ban_module(module_name, detail)
            self._notify_health_scorer_degradation(module_name)
        elif window_count >= self.config.max_violations_before_kill:
            await self._isolate_module(module_name, detail)
            self._notify_health_scorer_degradation(module_name)
        elif window_count >= 2:
            await self._throttle_module(module_name)

    # ── 执行动作 ──

    async def _throttle_module(self, module_name: str) -> None:
        """节流模块：记录日志，标记节流状态。"""
        profile = self._profiles.get(module_name)
        if profile is None:
            return
        if not profile.throttle_factor or profile.throttle_factor > 0.1:
            profile.throttle_factor = 0.1
            _log.info(
                "模块 '%s' 已进入节流模式 (factor=%.1f)",
                module_name, profile.throttle_factor,
            )

    async def _isolate_module(self, module_name: str, detail: str = "") -> None:
        """隔离模块：调用 kill_callback 杀死模块。"""
        profile = self._profiles.get(module_name)
        if profile is None:
            return
        if profile.killed:
            return
        profile.killed = True
        _log.warning("模块 '%s' 已被资源守护者隔离（杀死）", module_name)

        if self._kill_callback:
            try:
                await self._kill_callback(module_name)
            except Exception as e:
                _log.error("隔离回调失败 '%s': %s", module_name, e)

    async def _ban_module(self, module_name: str, reason: str) -> None:
        """永久禁用模块：写入黑名单持久化。"""
        if module_name in self._blacklist:
            return
        self._blacklist.add(module_name)
        _log.critical(
            "模块 '%s' 已被永久禁用: %s", module_name, reason,
        )
        self._save_blacklist()

        # 同时隔离
        await self._isolate_module(module_name)

    # ── 黑名单持久化 ──

    def _load_blacklist(self) -> None:
        """从磁盘加载黑名单。"""
        path = self.config.blacklist_path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._blacklist = set(data.get("banned_modules", []))
                _log.info(
                    "已加载资源黑名单: %d 个模块",
                    len(self._blacklist),
                )
            except (json.JSONDecodeError, IOError) as e:
                _log.warning("加载黑名单失败: %s", e)
                self._blacklist = set()

    def _save_blacklist(self) -> None:
        """持久化黑名单到磁盘。"""
        path = self.config.blacklist_path
        try:
            dirname = os.path.dirname(path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {"banned_modules": sorted(self._blacklist)},
                    f, ensure_ascii=False, indent=2,
                )
        except IOError as e:
            _log.error("保存黑名单失败: %s", e)

    # ── v5: 健康评分通知 ──

    def _notify_health_scorer(self, module_name: str):
        """通知健康评分器：违规事件。"""
        try:
            if self._host_ref and hasattr(self._host_ref, 'health_scorer'):
                self._host_ref.health_scorer.on_violation(module_name)
        except Exception as e:
            _log.warning("resource_guardian._notify_health_scorer: %s", e)

    def _notify_health_scorer_degradation(self, module_name: str):
        """通知健康评分器：模块降级/隔离。"""
        try:
            if self._host_ref and hasattr(self._host_ref, 'health_scorer'):
                self._host_ref.health_scorer.on_degradation(module_name)
        except Exception as e:
            _log.warning("resource_guardian._notify_health_scorer_degradatio: %s", e)

    # ── 查询 API ──

    def get_profile(self, module_name: str) -> Optional[ModuleProfile]:
        """获取模块运行画像。"""
        return self._profiles.get(module_name)

    def get_blacklist(self) -> Set[str]:
        """获取当前黑名单（只读副本）。"""
        return set(self._blacklist)

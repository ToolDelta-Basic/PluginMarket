from __future__ import annotations

import time
import threading
from bisect import bisect_left
from collections.abc import Callable
from typing import ClassVar

from tooldelta import Plugin, plugin_entry, utils, cfg, Config
from tooldelta.internal.types import FrameExit, Packet_CommandOutput


def _unpatched_placeholder(*_args, **_kwargs):
    """原始方法引用的占位符：在原始方法被捕获前调用即抛错"""
    raise RuntimeError("原始命令方法引用未初始化")


class CommandFrequencyMonitor(Plugin):
    """指令频率监测插件：统计并限制所有插件发送指令的频率"""

    name = "指令频率监测"
    author = "Mono"
    description = "指令频率监测插件，统计并限制所有插件发送指令的频率"
    version = (0, 0, 5)

    # 类级别的原始方法引用，防止插件重载时重复包装
    _originals_stored: ClassVar[bool] = False
    _original_sendaicmd_ref: ClassVar[Callable] = _unpatched_placeholder
    _original_sendaicmdonly_ref: ClassVar[Callable] = _unpatched_placeholder
    _original_sendcmd_ref: ClassVar[Callable] = _unpatched_placeholder
    _original_sendwocmd_ref: ClassVar[Callable] = _unpatched_placeholder
    _original_sendwscmd_ref: ClassVar[Callable] = _unpatched_placeholder

    # 默认配置（使用英文蛇形命名）
    DEFAULT_CONFIG: ClassVar[dict[str, float | bool]] = {
        # 频率限制配置：当指定时间内平均频率超过阈值时，阻止后续指令发送指定秒数
        "freq_limit_5s_threshold": 10.0,
        "freq_limit_5s_block_duration": 5.0,
        "freq_limit_10s_threshold": 8.0,
        "freq_limit_10s_block_duration": 10.0,
        "freq_limit_30s_threshold": 5.0,
        "freq_limit_30s_block_duration": 30.0,
        "freq_limit_60s_threshold": 3.0,
        "freq_limit_60s_block_duration": 60.0,
        "freq_limit_600s_threshold": 2.0,
        "freq_limit_600s_block_duration": 300.0,
        # 警告阈值配置：达到最高限制的百分比时触发警告
        "warning_50pct_enable": True,
        "warning_70pct_enable": True,
        "warning_90pct_enable": True,
        "warning_120pct_force_exit": True,
        # 最高限制（用于计算百分比阈值）
        "max_freq_limit": 20.0,
    }

    # 配置类型校验
    CONFIG_SCHEMA: ClassVar[dict[str, type]] = {
        "freq_limit_5s_threshold": Config.PNumber,
        "freq_limit_5s_block_duration": Config.PNumber,
        "freq_limit_10s_threshold": Config.PNumber,
        "freq_limit_10s_block_duration": Config.PNumber,
        "freq_limit_30s_threshold": Config.PNumber,
        "freq_limit_30s_block_duration": Config.PNumber,
        "freq_limit_60s_threshold": Config.PNumber,
        "freq_limit_60s_block_duration": Config.PNumber,
        "freq_limit_600s_threshold": Config.PNumber,
        "freq_limit_600s_block_duration": Config.PNumber,
        "warning_50pct_enable": bool,
        "warning_70pct_enable": bool,
        "warning_90pct_enable": bool,
        "warning_120pct_force_exit": bool,
        "max_freq_limit": Config.PNumber,
    }

    # 统计时间窗口配置（秒）
    TIME_WINDOWS: ClassVar[list[int]] = [5, 10, 30, 60, 600]

    # 窗口名称映射
    WINDOW_NAMES: ClassVar[dict[int, str]] = {
        5: "5秒",
        10: "10秒",
        30: "30秒",
        60: "1分钟",
        600: "10分钟",
    }

    # 警告阈值配置映射
    WARNING_CONFIG_MAP: ClassVar[dict[int, str]] = {
        50: "warning_50pct_enable",
        70: "warning_70pct_enable",
        90: "warning_90pct_enable",
        120: "warning_120pct_force_exit",
    }

    # 频率限制配置映射（窗口秒数 -> (阈值键, 阻止时长键)）
    FREQ_LIMIT_CONFIG_MAP: ClassVar[dict[int, tuple[str, str]]] = {
        5: ("freq_limit_5s_threshold", "freq_limit_5s_block_duration"),
        10: ("freq_limit_10s_threshold", "freq_limit_10s_block_duration"),
        30: ("freq_limit_30s_threshold", "freq_limit_30s_block_duration"),
        60: ("freq_limit_60s_threshold", "freq_limit_60s_block_duration"),
        600: ("freq_limit_600s_threshold", "freq_limit_600s_block_duration"),
    }

    def __init__(self, frame):
        super().__init__(frame)

        # 加载配置
        self.config, _ = self.get_config_and_version(
            self.CONFIG_SCHEMA, self.DEFAULT_CONFIG
        )
        self._ensure_config_defaults()

        # 保存原始命令方法引用（类级别，防止重复包装）
        if not CommandFrequencyMonitor._originals_stored:
            CommandFrequencyMonitor._original_sendaicmd_ref = self.game_ctrl.sendaicmd
            CommandFrequencyMonitor._original_sendaicmdonly_ref = (
                self.game_ctrl.sendaicmdonly
            )
            CommandFrequencyMonitor._original_sendcmd_ref = self.game_ctrl.sendcmd
            CommandFrequencyMonitor._original_sendwocmd_ref = self.game_ctrl.sendwocmd
            CommandFrequencyMonitor._original_sendwscmd_ref = self.game_ctrl.sendwscmd
            CommandFrequencyMonitor._originals_stored = True

        # 实例级别引用（方便调用）
        self._original_sendaicmd = CommandFrequencyMonitor._original_sendaicmd_ref
        self._original_sendaicmdonly = (
            CommandFrequencyMonitor._original_sendaicmdonly_ref
        )
        self._original_sendcmd = CommandFrequencyMonitor._original_sendcmd_ref
        self._original_sendwocmd = CommandFrequencyMonitor._original_sendwocmd_ref
        self._original_sendwscmd = CommandFrequencyMonitor._original_sendwscmd_ref

        # 命令时间戳记录（线程安全）- 使用list配合bisect进行二分查找
        # 时间戳按插入顺序递增，天然有序
        self._cmd_timestamps: list[float] = []
        # 单个锁保护所有操作：检查阻止状态、记录命令、查询频率、清理过期数据
        self._lock = threading.Lock()

        # 阻止发送状态（在_lock内保护）
        self._blocked_until = 0.0

        # 警告状态记录（避免重复警告）- 仅由监控线程访问，无需加锁
        self._warning_states = {50: False, 70: False, 90: False, 120: False}

        # 退出事件
        self._stop_event = threading.Event()

        # 是否需要强制退出（在_lock内保护）
        self._force_exit_triggered = False

        # 退出日志是否已写入（避免重复写入）
        self._exit_log_written = False

        # 重写命令发送方法
        self._patch_game_ctrl_methods()

        # 启动监测线程
        utils.createThread(self._monitor_loop, usage="指令频率监测线程")

        # 监听框架退出事件
        self.ListenFrameExit(self.on_frame_exit)

        # 注册控制台命令
        self.frame.add_console_cmd_trigger(
            ["指令频率"],
            None,
            "查看当前指令频率统计信息",
            self._on_console_cmd,
        )

    def _patch_game_ctrl_methods(self):
        """重写命令发送方法"""
        self.game_ctrl.sendaicmd = self.sendaicmd
        self.game_ctrl.sendaicmdonly = self.sendaicmdonly
        self.game_ctrl.sendcmd = self.sendcmd
        self.game_ctrl.sendwocmd = self.sendwocmd
        self.game_ctrl.sendwscmd = self.sendwscmd

    def _restore_game_ctrl_methods(self):
        """恢复命令发送方法为原始方法"""
        if CommandFrequencyMonitor._originals_stored:
            self.game_ctrl.sendaicmd = CommandFrequencyMonitor._original_sendaicmd_ref
            self.game_ctrl.sendaicmdonly = (
                CommandFrequencyMonitor._original_sendaicmdonly_ref
            )
            self.game_ctrl.sendcmd = CommandFrequencyMonitor._original_sendcmd_ref
            self.game_ctrl.sendwocmd = CommandFrequencyMonitor._original_sendwocmd_ref
            self.game_ctrl.sendwscmd = CommandFrequencyMonitor._original_sendwscmd_ref
            # 重置标志，允许下次插件重载时重新捕获原始方法
            CommandFrequencyMonitor._originals_stored = False

    def _on_console_cmd(self, args: list[str]):
        """控制台命令回调：显示指令频率统计信息"""
        frequencies = self.get_all_frequencies()
        self.print_inf("===== 指令频率统计 =====")
        for window, freq in frequencies.items():
            self.print_inf(f"  {window}: {freq:.2f} 条/秒")
        self.print_inf(f"  命令总数: {self.get_command_count()}")
        if self.is_blocked():
            self.print_war(
                f"  当前状态: 已阻止 ({self.get_block_remaining_time():.1f}秒后恢复)"
            )
        else:
            self.print_suc("  当前状态: 正常")

    def _ensure_config_defaults(self):
        """确保配置文件包含所有必要的默认值"""
        changed = any(k not in self.config for k in self.DEFAULT_CONFIG)
        if changed:
            self.config = {**self.DEFAULT_CONFIG, **self.config}
            cfg.upgrade_plugin_config(self.name, self.config, self.version)

    def _record_command(self, now: float):
        """记录命令发送时间戳（内部方法，需在锁内调用）"""
        self._cmd_timestamps.append(now)
        # 清理过期的时间戳（只保留最近10分钟的）
        cutoff = now - 600
        idx = bisect_left(self._cmd_timestamps, cutoff)
        if idx > 0:
            self._cmd_timestamps = self._cmd_timestamps[idx:]

    def _get_frequency(self, window_seconds: int) -> float:
        """获取指定时间窗口内的指令频率（条/秒）"""
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            # 使用二分查找快速定位起始位置
            idx = bisect_left(self._cmd_timestamps, cutoff)
            count = len(self._cmd_timestamps) - idx
        return count / window_seconds if window_seconds > 0 else 0.0

    def _is_blocked(self) -> bool:
        """检查当前是否被阻止发送指令"""
        now = time.time()
        with self._lock:
            return now < self._blocked_until

    def _check_block_and_record(self) -> bool:
        """检查是否被阻止，如果未被阻止则记录命令并返回True，否则返回False

        使用单个锁保护整个检查+记录流程，确保原子性。
        IO操作（print_war）已移到锁外，避免阻塞全局锁。
        """
        now = time.time()
        blocked_reason = ""

        with self._lock:
            # 检查阻止状态
            if now < self._blocked_until:
                blocked_reason = "blocked"
            elif self._force_exit_triggered:
                blocked_reason = "exiting"
            else:
                # 记录命令并清理过期数据（在同一锁内完成）
                self._record_command(now)
                return True

        # IO操作移到锁外
        if blocked_reason == "blocked":
            self.print_war("指令发送被阻止，当前处于频率限制期间")
        elif blocked_reason == "exiting":
            self.print_war("指令发送被阻止，程序即将退出")

        return False

    def _check_warnings(self) -> bool:
        """检查并触发警告阈值

        _warning_states 仅由监控线程访问，故无需加锁。

        Returns:
            bool: 是否需要强制退出
        """
        max_limit = self.config["max_freq_limit"]
        current_freq = self._get_frequency(5)  # 使用5秒窗口作为参考

        # 计算当前频率占最高限制的百分比
        percentage = (current_freq / max_limit) * 100 if max_limit > 0 else 0

        # 检查各个阈值阶段（使用配置映射消除重复代码）
        for threshold in [50, 70, 90, 120]:
            config_key = self.WARNING_CONFIG_MAP[threshold]
            if percentage >= threshold and not self._warning_states[threshold]:
                self._warning_states[threshold] = True
                if self.config[config_key]:
                    if threshold == 120:
                        self.print_err(
                            f"指令频率超过最高限制的{threshold}% ({current_freq:.2f}条/秒)，强制退出程序"
                        )
                        return True  # 需要强制退出
                    self.print_war(
                        f"指令频率达到最高限制的{threshold}% ({current_freq:.2f}条/秒)"
                    )

        # 重置警告状态（当频率下降到阈值以下时）
        for threshold in [50, 70, 90, 120]:
            if percentage < threshold * 0.8 and self._warning_states[threshold]:
                self._warning_states[threshold] = False

        return False

    def _monitor_loop(self):
        """监测线程主循环"""
        while not self._stop_event.is_set():
            time.sleep(0.5)  # 每0.5秒检查一次

            # 检查警告阈值（_warning_states仅由监控线程访问，无需加锁）
            if self._check_warnings():
                # 在锁内标记已触发强制退出
                with self._lock:
                    self._force_exit_triggered = True

                # 停止监测循环
                self._stop_event.set()

                # 记录退出日志（只写一次）
                self._write_exit_log()

                # 尝试调用框架退出API
                try:
                    if hasattr(self.frame, "exit"):
                        self.frame.exit()  # type: ignore
                    elif hasattr(self.frame.launcher, "update_status"):
                        from tooldelta.constants import SysStatus

                        self.frame.launcher.update_status(SysStatus.NORMAL_EXIT)
                except Exception as e:
                    self.print_err(f"触发框架退出时出错: {e}")
                return

            # 检查频率限制：获取一次锁，统一计算所有窗口频率（快照一致性）
            with self._lock:
                now = time.time()

                # 如果未被阻止，检查是否需要阻止
                if now >= self._blocked_until:
                    # 计算所有窗口的频率（同一时刻的快照）
                    frequencies = {}
                    for window in self.FREQ_LIMIT_CONFIG_MAP:
                        cutoff = now - window
                        idx = bisect_left(self._cmd_timestamps, cutoff)
                        frequencies[window] = (len(self._cmd_timestamps) - idx) / window

                    # 检查各窗口频率是否超过阈值
                    for window in self.FREQ_LIMIT_CONFIG_MAP:
                        freq = frequencies[window]
                        threshold_key, duration_key = self.FREQ_LIMIT_CONFIG_MAP[window]
                        if freq > self.config[threshold_key]:
                            duration = self.config[duration_key]
                            self._blocked_until = now + duration
                            window_name = self.WINDOW_NAMES[window]
                            # IO操作在锁外执行
                            self._schedule_warning(
                                f"{window_name}内指令频率({freq:.2f}条/秒)超过阈值，阻止发送{duration}秒"
                            )
                            break

    def _schedule_warning(self, message: str):
        """在锁外执行警告消息输出"""
        self.print_war(message)

    def sendaicmd(
        self, cmd: str, waitForResp: bool = False, timeout: float = 30
    ) -> Packet_CommandOutput | None:
        """
        发送魔法命令（被重写以监测频率）。

        Args:
            cmd: Minecraft 命令
            waitForResp: 是否等待返回。默认为 False（参数名遵循框架原始接口）
            timeout: 超时时间，超时则引发 TimeoutError

        Returns:
            Packet_CommandOutput | None: 命令返回结果或None
        """
        if not self._check_block_and_record():
            return None
        return self._original_sendaicmd(cmd, waitForResp, timeout)

    def sendaicmdonly(self, cmd: str) -> None:
        """
        仅发送魔法命令，不获取返回（被重写以监测频率）。

        Args:
            cmd: Minecraft 命令
        """
        if not self._check_block_and_record():
            return
        self._original_sendaicmdonly(cmd)

    def sendcmd(
        self, cmd: str, waitForResp: bool = False, timeout: float = 30
    ) -> Packet_CommandOutput | None:
        """
        发送命令（被重写以监测频率）。

        Args:
            cmd: Minecraft 命令
            waitForResp: 是否等待返回。默认为 False（参数名遵循框架原始接口）
            timeout: 超时时间，超时则引发 TimeoutError

        Returns:
            Packet_CommandOutput | None: 命令返回结果或None
        """
        if not self._check_block_and_record():
            return None
        return self._original_sendcmd(cmd, waitForResp, timeout)

    def sendwocmd(self, cmd: str) -> None:
        """
        发送无返回命令（被重写以监测频率）。

        Args:
            cmd: Minecraft 命令
        """
        if not self._check_block_and_record():
            return
        self._original_sendwocmd(cmd)

    def sendwscmd(
        self, cmd: str, waitForResp: bool = False, timeout: float = 30
    ) -> Packet_CommandOutput | None:
        """
        以 WebSocket 身份发送命令（被重写以监测频率）。

        Args:
            cmd: Minecraft 命令
            waitForResp: 是否等待返回。默认为 False（参数名遵循框架原始接口）
            timeout: 超时时间，超时则引发 TimeoutError

        Returns:
            Packet_CommandOutput | None: 命令返回结果或None
        """
        if not self._check_block_and_record():
            return None
        return self._original_sendwscmd(cmd, waitForResp, timeout)

    def get_frequency(self, window_seconds: int) -> float:
        """
        获取指定时间窗口内的指令发送频率（API方法）。

        Args:
            window_seconds: 时间窗口（秒），支持的值：5, 10, 30, 60, 600

        Returns:
            float: 指令频率（条/秒）
        """
        if window_seconds not in self.TIME_WINDOWS:
            self.print_war(f"不支持的时间窗口: {window_seconds}秒，使用5秒窗口")
            window_seconds = 5
        return self._get_frequency(window_seconds)

    def get_all_frequencies(self) -> dict[str, float]:
        """
        获取所有时间窗口内的指令发送频率（API方法）。

        Returns:
            dict[str, float]: 各时间窗口的频率字典
        """
        return {
            self.WINDOW_NAMES[window]: self._get_frequency(window)
            for window in self.TIME_WINDOWS
        }

    def get_command_count(self) -> int:
        """
        获取当前记录的命令总数（API方法）。

        Returns:
            int: 命令总数
        """
        with self._lock:
            return len(self._cmd_timestamps)

    def is_blocked(self) -> bool:
        """
        检查当前是否被阻止发送指令（API方法）。

        Returns:
            bool: 是否被阻止
        """
        return self._is_blocked()

    def get_block_remaining_time(self) -> float:
        """
        获取阻止发送的剩余时间（API方法）。

        Returns:
            float: 剩余阻止时间（秒），未被阻止时返回0
        """
        now = time.time()
        with self._lock:
            remaining = max(0.0, self._blocked_until - now)
        return remaining

    def on_frame_exit(self, _: FrameExit):
        """框架退出时清理资源并记录日志"""
        self._stop_event.set()

        # 恢复原始方法引用
        self._restore_game_ctrl_methods()

        # 记录退出日志（只写一次）
        self._write_exit_log()

        self.print_inf("指令频率监测插件已停止")

    def _write_exit_log(self):
        """将指令频率统计信息写入日志文件（只写一次）"""
        if self._exit_log_written:
            return

        self._exit_log_written = True

        import datetime

        now = datetime.datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d_%H-%M-%S")

        # 确保目录存在
        self.data_path.mkdir(parents=True, exist_ok=True)

        # 日志文件名
        log_file = self.data_path / f"exit_log_{timestamp_str}.txt"

        # 构建日志内容
        frequencies = self.get_all_frequencies()
        log_lines = [
            "=" * 50,
            "指令频率监测 - 退出日志",
            f"退出时间: {now.strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 50,
            "",
            "【频率统计】",
        ]

        for window, freq in frequencies.items():
            log_lines.append(f"  {window}: {freq:.2f} 条/秒")

        log_lines.extend(
            [
                "",
                "【其他统计】",
                f"  命令总数: {self.get_command_count()}",
                "",
                "【配置信息】",
            ]
        )

        for key, value in self.config.items():
            log_lines.append(f"  {key}: {value}")

        log_lines.extend(
            [
                "",
                "=" * 50,
            ]
        )

        # 写入日志文件
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(log_lines))
            self.print_suc(f"指令频率日志已保存到: {log_file}")
        except Exception as e:
            self.print_err(f"保存指令频率日志失败: {e}")


entry = plugin_entry(CommandFrequencyMonitor, "指令频率监测")

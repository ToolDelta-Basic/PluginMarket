import json
import logging
import os
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────

_DEFAULT_RETENTION_DAYS = 30


class AuditTrail:
    """命令审计追溯系统。

    每条记录包含:
      - user_id: QQ 号
      - group_id: 群号
      - nickname: 用户昵称
      - command: 命令名 (trigger)
      - args: 参数列表
      - triggered_at: ISO 时间戳
      - triggered_at_unix: unix 时间戳
      - elapsed_ms: 执行耗时（毫秒）
      - success: 是否成功
      - error: 错误信息（失败时）
      - uid_level: 当时 UID 等级
      - module: 模块名
    """

    def __init__(
        self,
        data_dir: str,
        retention_days: int = _DEFAULT_RETENTION_DAYS,
    ) -> None:
        """初始化审计追溯器。

        Args:
            data_dir: 数据目录路径（日志文件存放在其 audit_trail/ 子目录）。
            retention_days: 日志保留天数，默认 30。
        """
        self._data_dir = os.path.join(data_dir, "审计追溯")
        self._retention_days = max(retention_days, 1)
        self._lock = threading.Lock()
        self._initialized = False
        os.makedirs(self._data_dir, exist_ok=True)
        self._current_date: str = ""
        self._current_fp: Optional[str] = None
        self._initialized = True
        # 启动时清理过期文件
        self._cleanup_old_files()

    # ── 文件管理 ──────────────────────────────────────────

    def _get_log_path(self, dt: Optional[datetime] = None) -> str:
        """获取指定日期的日志文件路径。

        Args:
            dt: 日期，默认当天。
        """
        if dt is None:
            dt = datetime.now()
        return os.path.join(self._data_dir, f"audit_trail_{dt.strftime('%Y%m%d')}.jsonl")

    def _ensure_file(self) -> str:
        """确保当天的日志文件存在，返回路径。"""
        today = datetime.now()
        date_str = today.strftime("%Y%m%d")
        if self._current_date != date_str:
            self._current_date = date_str
            self._current_fp = self._get_log_path(today)
            # 确保文件存在
            if not os.path.exists(self._current_fp):
                with open(self._current_fp, "a", encoding="utf-8") as _:
                    pass
            # 日期切换时清理过期文件
            self._cleanup_old_files()
        return self._current_fp

    def _cleanup_old_files(self) -> None:
        """删除超过保留天数的旧日志文件。"""
        try:
            cutoff = datetime.now() - timedelta(days=self._retention_days)
            cutoff_str = cutoff.strftime("%Y%m%d")
            for fname in os.listdir(self._data_dir):
                if not fname.startswith("audit_trail_") or not fname.endswith(".jsonl"):
                    continue
                # 提取日期部分: audit_trail_YYYYMMDD.jsonl
                date_part = fname[len("audit_trail_"):-len(".jsonl")]
                if len(date_part) == 8 and date_part.isdigit():
                    if date_part < cutoff_str:
                        fp = os.path.join(self._data_dir, fname)
                        try:
                            os.remove(fp)
                            _log.info("清理过期审计日志: %s", fname)
                        except OSError as e:
                            _log.warning("audit_trail._cleanup_old_files: %s", e)
        except OSError as e:
            _log.warning("审计日志过期清理失败: %s", e)

    # ── 写入 ──────────────────────────────────────────────

    def record(
        self,
        user_id: int,
        group_id: int,
        nickname: str,
        command: str,
        args: List[str],
        module: str,
        uid_level: int,
        success: bool = True,
        error: str = "",
        elapsed_ms: float = 0.0,
    ) -> None:
        """记录一条命令执行记录。

        Args:
            user_id: QQ 号。
            group_id: 群号。
            nickname: 用户昵称。
            command: 命令触发词。
            args: 参数列表。
            module: 模块名。
            uid_level: 调用者 UID 等级。
            success: 执行是否成功。
            error: 失败时的错误信息。
            elapsed_ms: 执行耗时（毫秒）。
        """
        now = time.time()
        ts = datetime.fromtimestamp(now).isoformat()

        entry = json.dumps(
            {
                "user_id": user_id,
                "group_id": group_id,
                "nickname": nickname,
                "command": command,
                "args": args,
                "triggered_at": ts,
                "triggered_at_unix": int(now),
                "elapsed_ms": round(elapsed_ms, 2),
                "success": success,
                "error": error[:500] if error else "",
                "uid_level": uid_level,
                "module": module,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

        with self._lock:
            try:
                fp = self._ensure_file()
                with open(fp, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except OSError as e:
                _log.error("审计追溯写入失败: %s", e)

    # ── 查询 ──────────────────────────────────────────────

    def _read_all_entries(self) -> List[Dict[str, Any]]:
        """读取所有保留文件中的记录（最近优先）。"""
        entries: List[Dict[str, Any]] = []
        try:
            files = sorted(
                [f for f in os.listdir(self._data_dir)
                 if f.startswith("audit_trail_") and f.endswith(".jsonl")],
                reverse=True,
            )
            for fname in files:
                fp = os.path.join(self._data_dir, fname)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    entries.append(json.loads(line))
                                except json.JSONDecodeError as e:
                                    _log.warning("audit_trail._read_all_entries: %s", e)
                except OSError as e:
                    _log.warning("audit_trail._read_all_entries: %s", e)
        except OSError as e:
            _log.warning("audit_trail._read_all_entries: %s", e)
        return entries

    def get_by_user(
        self,
        user_id: int,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """按用户查询命令记录。

        Args:
            user_id: QQ 号。
            limit: 最大返回条数。

        Returns:
            按时间倒序排列的记录列表。
        """
        entries = self._read_all_entries()
        matched = [e for e in entries if e.get("user_id") == user_id]
        return matched[:limit]

    def get_by_module(
        self,
        module: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """按模块查询命令记录。

        Args:
            module: 模块名。
            limit: 最大返回条数。

        Returns:
            按时间倒序排列的记录列表。
        """
        entries = self._read_all_entries()
        matched = [e for e in entries if e.get("module") == module]
        return matched[:limit]

    def get_by_time(
        self,
        start: float,
        end: float,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """按时间范围查询命令记录。

        Args:
            start: 起始 unix 时间戳。
            end: 结束 unix 时间戳。
            limit: 最大返回条数。

        Returns:
            在时间范围内的记录列表。
        """
        entries = self._read_all_entries()
        matched = [
            e for e in entries
            if start <= e.get("triggered_at_unix", 0) <= end
        ][:limit]
        return matched

    def get_hotspots(self, top_n: int = 10) -> List[Tuple[str, int]]:
        """获取最常用命令排名（Top N）。

        Args:
            top_n: 返回前 N 个。

        Returns:
            [(命令名, 次数), ...] 按次数降序排列。
        """
        entries = self._read_all_entries()
        counter: Counter = Counter()
        for e in entries:
            cmd = e.get("command", "")
            if cmd:
                counter[cmd] += 1
        return counter.most_common(top_n)

    def get_hot_users(self, top_n: int = 10) -> List[Tuple[int, int]]:
        """获取最活跃用户排名（Top N）。

        Args:
            top_n: 返回前 N 个。

        Returns:
            [(user_id, 次数), ...] 按次数降序排列。
        """
        entries = self._read_all_entries()
        counter: Counter = Counter()
        for e in entries:
            uid = e.get("user_id", 0)
            if uid:
                counter[uid] += 1
        return counter.most_common(top_n)

    def get_stats(self) -> Dict[str, Any]:
        """获取审计统计摘要。

        Returns:
            字典: total_commands, success_rate, unique_users, unique_modules 等。
        """
        entries = self._read_all_entries()
        total = len(entries)
        if not total:
            return {
                "total_commands": 0,
                "success_rate": 0.0,
                "unique_users": 0,
                "unique_modules": 0,
                "avg_elapsed_ms": 0.0,
            }
        succeeded = sum(1 for e in entries if e.get("success"))
        users = set(e.get("user_id") for e in entries)
        modules = set(e.get("module") for e in entries)
        elapsed_vals = [e.get("elapsed_ms", 0) for e in entries if e.get("elapsed_ms", 0) > 0]
        avg_elapsed = sum(elapsed_vals) / len(elapsed_vals) if elapsed_vals else 0.0
        return {
            "total_commands": total,
            "success_rate": round(succeeded / total, 4),
            "unique_users": len(users),
            "unique_modules": len(modules),
            "avg_elapsed_ms": round(avg_elapsed, 2),
        }

    # ── 管理 ──────────────────────────────────────────────

    def get_file_count(self) -> int:
        """获取当前保留的日志文件数。"""
        try:
            return len([
                f for f in os.listdir(self._data_dir)
                if f.startswith("audit_trail_") and f.endswith(".jsonl")
            ])
        except OSError:
            return 0

    def clear(self) -> None:
        """清除所有审计日志文件（危险操作）。"""
        with self._lock:
            try:
                for fname in os.listdir(self._data_dir):
                    fp = os.path.join(self._data_dir, fname)
                    if os.path.isfile(fp):
                        os.remove(fp)
            except OSError as e:
                _log.error("清除审计日志失败: %s", e)

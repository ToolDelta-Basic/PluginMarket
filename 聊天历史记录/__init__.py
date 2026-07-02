from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from tooldelta import Player, Plugin, plugin_entry
from tooldelta.constants import PacketIDS
from tooldelta.utils import packet_transition


DAY_LOG_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})\.log$")
MONTH_DIR_RE = re.compile(r"^(\d{4})年(\d{1,2})月$")
TIME_PREFIX_RE = re.compile(r"^(?P<month>\d{2})-(?P<day>\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) ")


class ChatbarHistory(Plugin):
    name = "聊天历史记录"
    author = "ToolDelta & Mono"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenPacket(PacketIDS.Text, self.parse_text)
        self.make_data_path()
        self.migrate_legacy_logs()

    def on_player_join(self, player: Player):
        self.log(f"{player.name} (XUID:{player.xuid}) 进入游戏")

    def on_player_leave(self, player: Player):
        self.log(f"{player.name} 退出游戏")

    def parse_text(self, pk: dict):
        playername, msg, can_be_trusted = (
            packet_transition.get_playername_and_msg_from_text_packet(self.frame, pk)
        )
        if playername is None:
            # 忽略 tellraw 等消息
            return False
        if can_be_trusted:
            self.log(f"{playername}: {msg}")
        else:
            self.log(f"{playername} (可能为伪造消息) 发送了消息: {msg}")
        return False

    def log(self, line: str):
        now = datetime.now()
        safe_line = self.escape_log_text(line)
        log_path = self.data_path / f"{now.year}-{now.month:02d}-{now.day:02d}.log"
        record = f"{now.strftime('%m-%d %H:%M:%S')} {safe_line}\n"
        with log_path.open("a", encoding="utf-8") as fp:
            fp.write(record)

    @staticmethod
    def escape_log_text(line: str) -> str:
        escaped = (
            line.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return "".join(
            f"\\x{ord(ch):02x}" if ord(ch) < 32 or ord(ch) == 127 else ch
            for ch in escaped
        )

    def migrate_legacy_logs(self):
        now = datetime.now()
        self._migrate_legacy_single_log(now)
        self._archive_daily_logs(now)
        self._merge_root_month_directories()
        self._archive_month_directories(now)

    def _migrate_legacy_single_log(self, now: datetime):
        legacy_path = self.data_path / "聊天记录.log"
        if not legacy_path.is_file():
            return

        target_year = now.year
        target_month = now.month
        target_day = now.day
        try:
            stat = legacy_path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime)
            target_year = modified.year
            target_month = modified.month
            target_day = modified.day
        except OSError:
            pass

        day_buckets: dict[tuple[int, int, int], list[tuple[str, str]]] = {}
        try:
            with legacy_path.open("r", encoding="utf-8") as fp:
                for raw_line in fp:
                    line = raw_line.rstrip("\n")
                    if not line:
                        day_buckets.setdefault(
                            (target_year, target_month, target_day), []
                        ).append(
                            (
                                f"{target_month:02d}-{target_day:02d} 00:00:00",
                                "",
                            )
                        )
                        continue

                    matched = TIME_PREFIX_RE.match(line)
                    if matched:
                        month = int(matched.group("month"))
                        day = int(matched.group("day"))
                        timestamp = (
                            f"{matched.group('month')}-{matched.group('day')} "
                            f"{matched.group('time')}"
                        )
                        content = line[matched.end() :]
                        day_buckets.setdefault((target_year, month, day), []).append(
                            (timestamp, self.escape_log_text(content))
                        )
                    else:
                        day_buckets.setdefault(
                            (target_year, target_month, target_day), []
                        ).append(
                            (
                                f"{target_month:02d}-{target_day:02d} 00:00:00",
                                self.escape_log_text(line),
                            )
                        )
        except OSError:
            return

        for (year, month, day), lines in sorted(day_buckets.items()):
            daily_path = self.data_path / f"{year}-{month:02d}-{day:02d}.log"
            with daily_path.open("a", encoding="utf-8") as fp:
                for timestamp, content in lines:
                    fp.write(f"{timestamp} {content}\n")

        legacy_path.unlink(missing_ok=True)

    def _archive_daily_logs(self, now: datetime):
        month_groups: dict[tuple[int, int], list[Path]] = {}
        for entry in self.data_path.iterdir():
            if not entry.is_file():
                continue
            matched = DAY_LOG_RE.fullmatch(entry.name)
            if not matched:
                continue
            year = int(matched.group(1))
            month = int(matched.group(2))
            if (year, month) >= (now.year, now.month):
                continue
            month_groups.setdefault((year, month), []).append(entry)

        for (year, month), files in sorted(month_groups.items()):
            month_dir = self.data_path / f"{year}年{month}月"
            month_dir.mkdir(exist_ok=True)
            for file_path in sorted(files, key=lambda p: p.name):
                target_path = month_dir / file_path.name
                if target_path.exists():
                    self._append_file_contents(file_path, target_path)
                    file_path.unlink(missing_ok=True)
                else:
                    shutil.move(str(file_path), str(target_path))
            self._merge_month_directory(month_dir, year, month)

    def _merge_root_month_directories(self):
        for entry in sorted(self.data_path.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            matched = MONTH_DIR_RE.fullmatch(entry.name)
            if matched is None:
                continue
            year = int(matched.group(1))
            month = int(matched.group(2))
            self._merge_month_directory(entry, year, month)

    def _archive_month_directories(self, now: datetime):
        for entry in sorted(self.data_path.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            matched = MONTH_DIR_RE.fullmatch(entry.name)
            if not matched:
                continue
            year = int(matched.group(1))
            if year >= now.year:
                continue
            year_dir = self.data_path / f"{year}年"
            year_dir.mkdir(exist_ok=True)
            target_dir = year_dir / entry.name
            if target_dir.exists():
                self._merge_existing_month_dir(entry, target_dir)
                self._merge_month_directory(target_dir, year, int(matched.group(2)))
                shutil.rmtree(entry, ignore_errors=True)
            else:
                shutil.move(str(entry), str(target_dir))

    def _merge_month_directory(self, month_dir: Path, year: int, month: int):
        day_files = [
            path
            for path in month_dir.iterdir()
            if path.is_file() and DAY_LOG_RE.fullmatch(path.name)
        ]
        month_log_path = month_dir / f"{year}年{month}月.log"
        if not day_files:
            return

        chunks: list[str] = []

        if month_log_path.exists():
            try:
                existing_text = month_log_path.read_text(encoding="utf-8")
            except OSError:
                existing_text = ""
            if existing_text:
                chunks.append(existing_text.rstrip("\n"))

        for day_file in sorted(day_files, key=lambda p: p.name):
            matched = DAY_LOG_RE.fullmatch(day_file.name)
            if matched is None:
                continue
            day = int(matched.group(3))
            try:
                content = day_file.read_text(encoding="utf-8")
            except OSError:
                content = ""
            header = f"====={year}年{month}月{day}日=====\n\n\n"
            content = content.rstrip("\n")
            block = f"{header}{content}"
            if chunks:
                chunks.append(f"\n\n\n{block}")
            else:
                chunks.append(block)

        merged_content = "".join(chunks)
        with month_log_path.open("w", encoding="utf-8") as fp:
            fp.write(merged_content)
            if merged_content:
                fp.write("\n")

        for day_file in day_files:
            day_file.unlink(missing_ok=True)

    def _merge_existing_month_dir(self, source_dir: Path, target_dir: Path):
        target_dir.mkdir(exist_ok=True)
        for item in sorted(source_dir.iterdir(), key=lambda p: p.name):
            target_item = target_dir / item.name
            if item.is_file():
                if target_item.exists():
                    self._append_file_contents(item, target_item)
                    item.unlink(missing_ok=True)
                else:
                    shutil.move(str(item), str(target_item))
            elif item.is_dir():
                if target_item.exists():
                    self._merge_existing_month_dir(item, target_item)
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    shutil.move(str(item), str(target_item))

    @staticmethod
    def _append_file_contents(source: Path, target: Path):
        try:
            content = source.read_text(encoding="utf-8")
        except OSError:
            content = ""
        if content:
            with target.open("a", encoding="utf-8") as fp:
                fp.write(content)


entry = plugin_entry(ChatbarHistory)

"""Console records and game events with independent, resumable cursors."""

import json
import logging
import re
import time
from collections import deque
from datetime import date as calendar_date
from datetime import datetime
from pathlib import Path
from threading import Condition

COLOR = re.compile(r"§.|\x1b\[[0-9;]*[a-zA-Z]")
HEADER = re.compile(
    rb"^\[(\d\d:\d\d:\d\d)\] \[([^\]\r\n]{1,64})\] ", re.MULTILINE
)
LEVELS = {"成功": "success", "加载": "loading", "警告": "warning", "报错": "error",
          "信息": "info", "warn": "warning"}
TEXT_LIMIT = 8192
HISTORY_WINDOW = 2 * 1024 * 1024


def level_name(level):
    return LEVELS.get(level, level.casefold())


def log_data(level, message):
    return {"level": level_name(level), "raw": message[:TEXT_LIMIT],
            "text": COLOR.sub("", message[:TEXT_LIMIT]), "truncated": len(message) > TEXT_LIMIT}


def matches(item, kind, level, contains):
    if kind and item.get("kind") != kind or level and item.get("level") != level:
        return False
    if not contains:
        return True
    body = item.get("text")
    if body is None:
        body = json.dumps(item.get("data"), ensure_ascii=False)
    return contains.casefold() in body.casefold()


class Stream:
    def __init__(self, session, capacity):
        self.session = session
        self.rows = deque(maxlen=capacity)
        self.cursor = 0
        self.closed = False
        self.changed = Condition()

    def append(self, row):
        with self.changed:
            if not self.closed:
                self.cursor += 1
                self.rows.append({**row, "cursor": self.cursor,
                                  "time": datetime.now().astimezone().isoformat()})
                self.changed.notify_all()

    def close(self):
        with self.changed:
            self.closed = True
            self.changed.notify_all()

    def read(self, after=None, limit=50, session="", timeout=0, kind="", level="",
             contains="", future=False):
        deadline = time.monotonic() + timeout
        with self.changed:
            first = self.rows[0]["cursor"] if self.rows else self.cursor + 1
            if session and session != self.session or after is not None and after > self.cursor:
                return {"session": self.session, "next_cursor": first - 1, "items": [],
                        "reset": True, "gap": True}
            recent = after is None and not future
            start = self.cursor if after is None and future else (after or 0)
            gap = after is not None and after < first - 1
            while True:
                if self.rows and not recent and start < self.rows[0]["cursor"] - 1:
                    gap = True
                found = [r for r in self.rows if r["cursor"] > start
                         and matches(r, kind, level_name(level), contains)]
                batch = found[-limit:] if recent else found[:limit]
                more = not recent and len(found) > limit
                remaining = deadline - time.monotonic()
                if batch or self.closed or remaining <= 0:
                    return {"session": self.session, "items": batch, "gap": gap,
                            "next_cursor": batch[-1]["cursor"] if more else self.cursor,
                            "has_more": more, "closed": self.closed,
                            "timed_out": bool(timeout and not batch and not self.closed)}
                start = self.cursor
                recent = False
                self.changed.wait(remaining)


class Capture(logging.Filter):
    def __init__(self, stream):
        super().__init__()
        self.stream = stream

    def filter(self, record):
        try:
            data = log_data(record.levelname, record.getMessage())
            self.stream.append({**data, "logger": record.name})
        except (TypeError, ValueError):
            pass
        return True


def history(root: Path, date, after=None, limit=50, level="", contains="", session=""):
    if calendar_date.fromisoformat(date).isoformat() != date:
        raise ValueError("日期格式为 YYYY-MM-DD")
    path = (root / (date + ".log")).resolve()
    if path.parent != root.resolve() or not path.is_file():
        raise ValueError("找不到该日期的日志")
    file_session = "log:" + date
    with path.open("rb") as fp:
        size = fp.seek(0, 2)
        if session and session != file_session or after is not None and after > size:
            return {"session": file_session, "next_cursor": 0, "reset": True, "gap": True, "items": []}
        start = max(0, size - HISTORY_WINDOW) if after is None else after
        stop = min(size, start + HISTORY_WINDOW)
        # The preceding byte identifies real line starts. The lookahead lets a
        # timestamp straddling the window boundary close the preceding entry.
        base = max(0, start - 1)
        fp.seek(base)
        block = fp.read(min(size, stop + 96) - base)

    rows = deque(maxlen=limit)
    sought_level = level_name(level)

    def finish(header, end, partial=False):
        body_start = header.end()
        body_end = min(end, body_start + 4 * (TEXT_LIMIT + 1))
        text = block[body_start:body_end].decode("utf-8", "replace")
        text = text.replace("\r\n", "\n").removesuffix("\n")
        data = log_data(header[2].decode("utf-8", "replace"), text)
        data["truncated"] |= partial or body_end < end
        if matches(data, "", sought_level, contains):
            rows.append({**data, "time": date + "T" + header[1].decode("ascii"),
                         "cursor": base + end})

    cursor = stop
    gap = False
    current = None
    for header in HEADER.finditer(block, start - base):
        position = base + header.start()
        if position > stop:
            break
        if current is None:
            gap = position != start
        else:
            finish(current, header.start())
            if after is not None and len(rows) >= limit:
                cursor = position
                current = None
                break
        if position == stop:
            current = None
            break
        current = header
    if current is not None:
        if stop == size:
            finish(current, stop - base)
        elif base + current.start() > start:
            # Start the next page at this record so its continuation stays with it.
            cursor = base + current.start()
        else:
            # A single entry fills the whole window. Return a bounded preview and
            # advance, even when its next newline is several windows away.
            finish(current, stop - base, partial=True)
            gap = True
    elif not rows and start < stop and not HEADER.match(block, start - base):
        gap = True
    return {"session": file_session, "items": list(rows), "next_cursor": cursor,
            "has_more": cursor < size, "earlier_available": after is None and start > 0,
            "gap": gap}

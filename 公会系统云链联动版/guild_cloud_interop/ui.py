"""Orion-style UI helpers for the guild cloud interop plugin."""

from __future__ import annotations

import re
from typing import Iterable, Sequence


ORION_BORDER = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
TITLE_PREFIX = "§l§d❐§f"
OPTION_PREFIX = "§l§b[ §e{}§b ] §r§e{}"
INFO_PREFIX = "§a❀ §r"
WARN_PREFIX = "§6❀ "
ERROR_PREFIX = "§c❀ "
SUCCESS_PREFIX = "§a❀ "
MAX_CHAT_MESSAGE_CHARS = 240


def split_chat_chunks(
        text: str,
        max_chars: int = MAX_CHAT_MESSAGE_CHARS) -> list[str]:
    """Split rich-text chat output into line-preserving chunks for rental servers."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in str(text).splitlines():
        line_len = len(line)
        separator_len = 1 if current else 0
        if current and current_len + separator_len + line_len > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_len = 0

        if line_len > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for start in range(0, line_len, max_chars):
                chunks.append(line[start:start + max_chars])
            continue

        current.append(line)
        current_len += separator_len + line_len

    if current:
        chunks.append("\n".join(current))

    return chunks or [""]


class OrionPlayerView:
    """Player proxy that renders plugin messages in the Orion panel style."""

    def __init__(self, player):
        self._player = player

    def __getattr__(self, name):
        return getattr(self._player, name)

    def show(self, text):
        """Implement the show operation."""
        for chunk in split_chat_chunks(format_message(str(text))):
            self._player.show(chunk)


def wrap_player(player):
    """Implement the wrap player operation."""
    if isinstance(player, OrionPlayerView):
        return player
    return OrionPlayerView(player)


def strip_reset(text: str) -> str:
    """Implement the strip reset operation."""
    return text.replace("§r", "")


def normalize_inline(text: str) -> str:
    """Implement the normalize inline operation."""
    text = strip_reset(text)
    text = text.replace("§l§a公会仓库 §d>> ", "")
    text = text.replace("§l§a公会任务 §d>> ", "")
    text = text.replace("§l§a任务管理 §d>> ", "")
    text = text.replace("§l§a创建任务 §d>> ", "")
    text = text.replace("§l§a公会 §d>> ", "")
    text = text.replace("§r§7>> ", "")
    text = text.replace("§7>> ", "")
    text = text.replace(">>>", "-")
    return text.strip()


def classify_prefix(text: str) -> str:  # skipcq: PY-R1000
    """Implement the classify prefix operation."""
    if "错误" in text or "失败" in text or "无效" in text or "不足" in text or "权限不足" in text:
        return ERROR_PREFIX
    if "警告" in text or "超时" in text or "已满" in text or "不存在" in text or "未找到" in text:
        return WARN_PREFIX
    if "成功" in text or "已创建" in text or "已加入" in text or "已退出" in text or "已更新" in text:
        return SUCCESS_PREFIX
    return INFO_PREFIX


def format_option(line: str) -> str | None:
    """Implement the format option operation."""
    clean = normalize_inline(line)

    match = re.match(r"^(?:§[0-9a-frlomnk])*([0-9]+)[.．、]\s*(.*)$", clean)
    if match:
        return OPTION_PREFIX.format(match.group(1), match.group(2).strip())

    match = re.match(
        r"^(?:§[0-9a-frlomnk])*●\s*(.+?)(?:\s*§7[-—]\s*|\s+-\s+)(.+)$", clean)
    if match:
        return f"§l§b[ §e-§b ] §r§e{match.group(1).strip()} §7- §f{match.group(2).strip()}"

    match = re.match(r"^([^\s]+)\s+§7[-—]\s*(.+)$", clean)
    if match:
        return f"§l§b[ §e-§b ] §r§e{match.group(1).strip()} §7- §f{match.group(2).strip()}"

    return None


def format_title(title: str) -> str:
    """Implement the format title operation."""
    title = normalize_inline(title)
    title = title.replace("§a", "§6").replace("§c", "§c")
    return (
        f"{ORION_BORDER}\n"
        f"{TITLE_PREFIX} 『§6公会系统 §d云链联动版§f』 §b{title}§d\n"
        f"{ORION_BORDER}"
    )


def format_message(text: str) -> str:  # skipcq: PY-R1000
    """Implement the format message operation."""
    lines = str(text).splitlines()
    rendered: list[str] = []

    for raw_line in lines:
        if raw_line == "":
            rendered.append("")
            continue

        line = raw_line.strip()
        if (
            line == ORION_BORDER
            or line.startswith("§d✧✦")
            or line.startswith(TITLE_PREFIX)
            or line.startswith("§l§b[")
            or line.startswith("§e>§g>§6>")
            or "❀" in line
        ):
            rendered.append(line)
            continue

        title_match = re.match(r"^(?:§r)?=+\s*§a(.+?)§r?\s*=+", line)
        if title_match:
            rendered.append(format_title(title_match.group(1)))
            continue

        if re.fullmatch(r"=+", strip_reset(line)):
            rendered.append(ORION_BORDER)
            continue

        option = format_option(line)
        if option is not None:
            rendered.append(option)
            continue

        clean = normalize_inline(line)
        if not clean:
            rendered.append("")
            continue

        if clean.startswith("§c"):
            rendered.append(ERROR_PREFIX + clean[2:])
        elif clean.startswith("§6"):
            rendered.append(WARN_PREFIX + clean[2:])
        elif clean.startswith("§a"):
            rendered.append(SUCCESS_PREFIX + clean[2:])
        elif clean.startswith("§7"):
            rendered.append(INFO_PREFIX + clean[2:])
        elif clean.startswith("§e"):
            rendered.append(INFO_PREFIX + clean[2:])
        else:
            rendered.append(classify_prefix(clean) + clean)

    return "\n".join(rendered)


def format_panel(
    title: str,
    options: Sequence[tuple[str, str]] = (),
    *,
    subtitle: str = "",
    footer: str = "",
    lines: Iterable[str] = (),
) -> str:
    """Implement the format panel operation."""
    output = [
        ORION_BORDER,
        f"{TITLE_PREFIX} 『§6公会系统 §d云链联动版§f』 §b{title}§d",
    ]
    if subtitle:
        output.append(f"§e>§g>§6>§f{subtitle}")
    output.append(ORION_BORDER)
    for index, (label, description) in enumerate(options, start=1):
        output.append(
            OPTION_PREFIX.format(
                index,
                f"{label} §7- §f{description}"))
    for line in lines:
        output.append(format_message(line))
    if footer:
        output.append(format_message(footer))
    return "\n".join(output)


def format_page_footer(
        page: int,
        total_pages: int,
        start: int,
        end: int,
        allow_selection: bool) -> str:
    """Implement the format page footer operation."""
    lines = [
        ORION_BORDER,
        f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} §f◀§l§b下页 §a[ §e+ §a]",
    ]
    if allow_selection:
        lines.append(f"{INFO_PREFIX}输入 §e[{start}-{end}]§r 之间的数字以选择")
    lines.append(f"{INFO_PREFIX}输入 §d-§e 上一页 §r| §d+§e 下一页 §r| §cq§r 退出")
    return "\n".join(lines)

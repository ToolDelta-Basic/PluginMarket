"""『Lyra-天琴座』统一控制台入口与任务生命周期"""

import os
import re
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tooldelta import fmts, utils

from . import handlers
from .lyra_loader.common.dimensions import Dimension, source_dimension, target_dimension

if TYPE_CHECKING:
    from .__init__ import LyraSystem

SEPARATOR = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
FILES_PER_PAGE = 20
FORMATS = {
    ".bdx": "BDX",
    ".litematic": "Litematic",
    ".mcstructure": "MCStructure",
    ".mcworld": "MCWorld",
    ".schem": "Schem",
    ".schematic": "Schematic",
}


@dataclass(frozen=True)
class FileChoice:
    path: str
    extension: str
    display_name: str
    size_bytes: int = 0


def format_file_size(size_bytes: int) -> str:
    size = float(size_bytes)
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{size:.1f} {unit}"


class Basic:
    def __init__(self, plugin: "LyraSystem") -> None:
        self.plugin = plugin
        self.cfg = plugin.config_mgr
        self.data_path = plugin.data_path
        self.running_mutex = threading.Lock()

    def entry(self) -> None:
        self.plugin.frame.add_console_cmd_trigger(
            self.cfg.CONSOLE_TRIGGERS, None, "『Lyra-天琴座』ToolDelta导入器", self.main
        )

    def main(self, _: list[str]) -> None:
        files = self.get_files()
        if not files:
            fmts.print_inf(
                f"§c❀ 未发现支持的建筑或存档文件! 请前往 {self.data_path} 上传文件! "
                "§7(支持: bdx, litematic, mcstructure, mcworld, schem, schematic)"
            )
            return
        choice = self.select_file(files)
        if choice is None:
            return
        fmts.print_inf(f"\n§a❀ 已选择文件: §e{os.path.basename(choice.path)}")
        source: handlers.MCWorldSelection | None = None
        if choice.extension == ".mcworld":
            source = self.get_mcworld_source()
            if source is None:
                return
        target = self.get_target()
        if target is None:
            return
        self.import_thread(choice, target, source)

    def get_files(self) -> list[FileChoice]:
        result: list[FileChoice] = []
        for filename in sorted(os.listdir(self.data_path)):
            extension = os.path.splitext(filename)[1].lower()
            if display := FORMATS.get(extension):
                result.append(
                    FileChoice(
                        os.path.join(self.data_path, filename),
                        extension,
                        display,
                        os.path.getsize(os.path.join(self.data_path, filename)),
                    )
                )
        return result

    def select_file(self, files: list[FileChoice]) -> FileChoice | None:
        search = ""
        page = 1
        while True:
            normalized_search = search.replace("\\", "")
            matched = [
                item
                for item in files
                if normalized_search in os.path.basename(item.path)
            ]
            if not matched:
                fmts.print_inf("§c❀ 找不到对应建筑或存档文件, 已退出")
                return None

            total_pages = (len(matched) + FILES_PER_PAGE - 1) // FILES_PER_PAGE
            start = (page - 1) * FILES_PER_PAGE
            end = min(start + FILES_PER_PAGE, len(matched))
            fmts.print_inf("\n§a❀ 已发现以下建筑或存档文件~")
            fmts.print_inf(SEPARATOR)
            fmts.print_inf(
                "§l§b[ §a序号§b ] §r§a格式 §f- §a文件名称 §f- §a文件大小"
            )
            for index in range(start, end):
                item = matched[index]
                filename = os.path.basename(item.path)
                if normalized_search:
                    filename = filename.replace(
                        normalized_search, f"§b{normalized_search}§e"
                    )
                fmts.print_inf(
                    f"§l§b[ §e{index + 1}§b ] §r§d{item.display_name} §f- §e{filename} "
                    f"§f- §7{format_file_size(item.size_bytes)}"
                )
            fmts.print_inf(
                f"{SEPARATOR}\n"
                f"§l§a[ §e-§a ] §b上页§r§f▶ §7{page}/{total_pages} "
                "§f◀§l§b下页 §a[ §e+ §a]\n"
                f"§a❀ §b输入 §e[{start + 1}-{end}]§b 之间的数字选择需要导入的文件\n"
                "§a❀ §b输入 §d- §e转到上一页\n"
                "§a❀ §b输入 §d+ §e转到下一页\n"
                "§a❀ §b输入 §d正整数+页 §e转到对应页\n"
                "§a❀ §b输入 §e文件名或部分文件名 §b可尝试搜索\n"
                "§a❀ §b搜索纯数字或数字+页形式的文件名时, 请在最前面添加反斜杠\\"
            )
            user_input = input(fmts.fmt_info("§a❀ §b输入 §c. §b退出"))
            if user_input in (".", "。"):
                fmts.print_inf("§a❀ 已退出文件选择")
                return None
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    fmts.print_inf("§6❀ 已经是第一页啦~")
            elif user_input == "+":
                if page < total_pages:
                    page += 1
                else:
                    fmts.print_inf("§6❀ 已经是最后一页啦~")
            elif match := re.fullmatch(r"^([1-9]\d*)页$", user_input):
                target_page = int(match.group(1))
                if 1 <= target_page <= total_pages:
                    page = target_page
                else:
                    fmts.print_inf(f"§6❀ 不存在第{target_page}页！请重新输入！")
            else:
                try:
                    selected = int(user_input)
                    if start + 1 <= selected <= end:
                        return matched[selected - 1]
                    fmts.print_inf("§c❀ 您输入的内容无效, 已退出")
                    return None
                except ValueError:
                    for item in files:
                        if user_input == os.path.basename(item.path):
                            return item
                    search = user_input
                    page = 1

    @classmethod
    def get_target(cls) -> tuple[Dimension, tuple[int, int, int]] | None:
        dimension = cls._read_dimension("目标服务器", allow_dm=True)
        if dimension is None:
            return None
        position = cls._read_position(f"目标服务器{dimension.display_name}的起始")
        return None if position is None else (dimension, position)

    @classmethod
    def get_mcworld_source(cls) -> handlers.MCWorldSelection | None:
        dimension = cls._read_dimension("所选MCWorld文件中的", allow_dm=False)
        if dimension is None:
            return None
        start = cls._read_position(f"所选MCWorld文件中的{dimension.display_name}的开始")
        if start is None:
            return None
        end = cls._read_position(f"所选MCWorld文件中的{dimension.display_name}的终止")
        if end is None:
            return None
        return handlers.MCWorldSelection(dimension.number, start, end)

    @staticmethod
    def _read_dimension(label: str, *, allow_dm: bool) -> Dimension | None:
        limit = 20 if allow_dm else 2
        fmts.print_inf(f"\n§a❀ §b请选择{label}维度 §e(输入0-{limit}之间的整数)")
        fmts.print_inf("§6· §f0 §e- 主世界")
        fmts.print_inf("§6· §f1 §e- 下界")
        fmts.print_inf("§6· §f2 §e- 末地")
        if allow_dm:
            fmts.print_inf("§6· §fN §e- dmN §7(3≤N≤20)")
        try:
            value = int(input(fmts.fmt_info("§a❀ §b输入 §c其他内容 §b退出")))
            return target_dimension(value) if allow_dm else source_dimension(value)
        except ValueError:
            fmts.print_inf("§c❀ 您输入的内容无效, 已退出")
            return None

    @staticmethod
    def _read_position(label: str) -> tuple[int, int, int] | None:
        values: list[int] = []
        for axis in "XYZ":
            fmts.print_inf(f"\n§a❀ §b请输入{label}{axis}坐标 §e(输入整数)")
            try:
                values.append(int(input(fmts.fmt_info("§a❀ §b输入 §c其他内容 §b退出"))))
            except ValueError:
                fmts.print_inf("§c❀ 您输入的内容无效, 已退出")
                return None
        return values[0], values[1], values[2]

    @utils.thread_func("天琴座统一导入进程")
    def import_thread(
        self,
        choice: FileChoice,
        target: tuple[Dimension, tuple[int, int, int]],
        source: handlers.MCWorldSelection | None,
    ) -> None:
        if not self.running_mutex.acquire(blocking=False):
            fmts.print_inf("§c❀ 警告: 同一时刻最多处理一个导入任务!")
            return
        try:
            handlers.run(self.plugin, choice.path, choice.extension, target, source)
        except Exception as error:
            fmts.print_inf(f"§c❀ 警告: 解析或导入文件时出现异常: {error}")
        finally:
            self.running_mutex.release()

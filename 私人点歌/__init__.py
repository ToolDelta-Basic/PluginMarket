"""私人点歌插件。

免费点歌，只对点歌人播放；支持本地曲库的分页与模糊搜索，
以及通过 MIDI 中转服务（midishow）搜索并下载曲目。

网络歌源（2026-10-19 起）：
    主链路为自建中转服务 ``https://midishow.tdgzs.top``，三步走：
    ``/api/search`` 搜索 -> ``/api/fetch`` 取签名直链 -> ``GET <url>`` 下文件。
    历史链路（midishow 直连搜索 + midi.fxdby.net 下载）已废弃但保留在
    废弃链路已挪到 ``legacy.py``，网络客户端在 ``network.py``。
"""

import os
import re
import threading
from typing import Any

from tooldelta import Player, Plugin, cfg, plugin_entry, utils

try:
    from .legacy import LegacyMixin
    from .network import NETWORK_DEFAULT_BASE, NetworkMixin
except ImportError:  # pragma: no cover
    from legacy import LegacyMixin  # type: ignore
    from network import NETWORK_DEFAULT_BASE, NetworkMixin  # type: ignore

MENU_TIMEOUT = 300

# Windows 保留文件名（即使用作主名 + 扩展名，系统也会拒绝）
WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
CFG_STD = {
    "本地歌曲点歌每页显示多少歌曲": cfg.PInt,
    "是否启用网络点歌": bool,
    "网络点歌冷却秒数": cfg.NNInt,
    "网络点歌每日上限": cfg.NNInt,
    "网络点歌搜索结果每页显示": cfg.PInt,
    "是否保留原始 MIDI": bool,
    "播放时是否公告": bool,
    "网络请求间隔秒数": cfg.NNNumber,
    "网络请求超时秒数": cfg.PInt,
    "网络请求失败重试次数": cfg.NNInt,
    "网络点歌服务地址": str,
    "网络点歌客户端标识": str,
}

CFG_DEFAULT = {
    "本地歌曲点歌每页显示多少歌曲": 10,
    "是否启用网络点歌": True,
    "网络点歌冷却秒数": 30,
    "网络点歌每日上限": 0,
    "网络点歌搜索结果每页显示": 10,
    "是否保留原始 MIDI": True,
    "播放时是否公告": False,
    "网络请求间隔秒数": 1.0,
    "网络请求超时秒数": 15,
    "网络请求失败重试次数": 1,
    "网络点歌服务地址": NETWORK_DEFAULT_BASE,
    "网络点歌客户端标识": "",
}


class PersonalSongRequest(NetworkMixin, LegacyMixin, Plugin):
    """私人点歌主插件类。"""

    name = "私人点歌"
    author = "小六神"
    version = (0, 2, 0)
    description = (
        "免费点歌，只对点歌人播放；支持本地曲库分页与模糊搜索，"
        "以及通过 MIDI 中转服务（midishow）搜索并下载曲目。"
    )

    def __init__(self, frame):
        """初始化配置、数据目录与运行时状态。"""
        super().__init__(frame)
        self.load_config()
        self.make_data_path()
        self.music_dir = self.format_data_path("音乐列表")
        os.makedirs(self.music_dir, exist_ok=True)

        # 本地曲库：曲名列表 + 已载入播放器的 mtime 缓存
        self.local_songs: list[str] = []
        self.loaded_songs: dict[str, float] = {}
        # 网络曲库索引：本地曲名 -> {"id": 作品ID, "title": 原始曲名}
        self.network_index: dict[str, dict[str, Any]] = {}
        # 播放状态：玩家名 -> MIDI播放器线程 ID
        self.playing_threads: dict[str, int] = {}
        # 网络点歌限流：冷却时间戳 / (日期, 当日次数)
        self.network_cooldowns: dict[str, float] = {}
        self.network_daily: dict[str, tuple[str, int]] = {}

        # 网络请求全局串行锁：避免多玩家同时打第三方服务触发限流
        self.network_lock = threading.Lock()
        self.network_last_request = 0.0

        self.chatbar = None
        self.midiplayer = None
        self.requests = None
        self.urllib3 = None
        self.etree = None  # 仅废弃链路使用

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenFrameExit(self.on_frame_exit)

    # ------------------------------------------------------------------
    # 配置与生命周期
    # ------------------------------------------------------------------
    def load_config(self):
        """读取配置；插件升级后自动补齐新增键，再做一次严格类型校验。"""
        self.cfg, cfg_ver = cfg.get_plugin_config_and_version(
            self.name, {}, CFG_DEFAULT, self.version
        )
        if cfg_ver < self.version:
            added = [key for key in CFG_DEFAULT if key not in self.cfg]
            for key in added:
                self.cfg[key] = CFG_DEFAULT[key]
            if added:
                cfg.upgrade_plugin_config(self.name, self.cfg, self.version)
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, CFG_STD, CFG_DEFAULT, self.version
        )

    @property
    def page_size(self) -> int:
        """本地曲库每页显示的曲目数。"""
        return max(1, int(self.cfg["本地歌曲点歌每页显示多少歌曲"]))

    def on_preload(self):
        """前置阶段：取前置插件 API、装依赖、载入本地曲库与网络索引。"""
        self.prepare_plugin_apis()
        self.prepare_network_dependencies()
        self.network_index = self.load_network_index()
        self.refresh_library(force=True)

    def on_active(self):
        """激活阶段：注册聊天栏触发词与控制台命令。"""
        self.chatbar.add_new_trigger(
            [".点歌", ".song"],
            [],
            "打开私人点歌菜单",
            self.on_song_command,
        )
        self.chatbar.add_new_trigger(
            [".停止点歌", ".stopsong"],
            [],
            "停止你当前播放的歌曲",
            self.stop_current_song,
        )
        self.chatbar.add_new_trigger(
            [".重载曲库", ".reloadsongs"],
            [],
            "重新扫描私人点歌的本地曲库",
            self.reload_library_command,
            op_only=True,
        )
        self.frame.add_console_cmd_trigger(
            ["重载私人点歌曲库"],
            None,
            "强制重新扫描私人点歌的本地曲库",
            self.on_console_reload,
        )

    def on_player_leave(self, player: Player):
        """玩家离线：停掉他的播放线程并清理冷却记录。

        注意：ToolDelta 的玩家进/离事件是靠解析聊天栏里的
        ``%multiplayer.player.left`` 文本触发的，玩家掉线重连、短暂抖动、
        甚至换维度时都可能收到这条文本。所以这里用 ``online`` 做二次确认，
        避免把还在听歌的玩家误判成已离开而中断播放。
        """
        name = getattr(player, "name", None)
        if not name:
            return
        if getattr(player, "online", None):
            return
        self.stop_song_thread(name)
        self.network_cooldowns.pop(name, None)

    def on_frame_exit(self, _):
        """框架退出：停掉所有仍在播放的线程。"""
        for player_name in list(self.playing_threads):
            self.stop_song_thread(player_name)

    def prepare_plugin_apis(self):
        """获取前置插件 API 并声明第三方 Python 依赖。"""
        pip = self.GetPluginAPI("pip")
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.midiplayer = self.GetPluginAPI("MIDI播放器")
        pip.require(
            {
                "lxml": "lxml",
                "requests": "requests",
                "urllib3": "urllib3",
            }
        )

    # ------------------------------------------------------------------
    # 玩家提示与菜单骨架
    # ------------------------------------------------------------------

    @staticmethod
    def show_info(player: Player, text: str):
        """向玩家输出普通提示。"""
        player.show(f"§f❀ {text}")

    @staticmethod
    def show_success(player: Player, text: str):
        """向玩家输出成功提示。"""
        player.show(f"§a❀ {text}")

    @staticmethod
    def show_warn(player: Player, text: str):
        """向玩家输出警告提示。"""
        player.show(f"§6❀ {text}")

    @staticmethod
    def show_error(player: Player, text: str):
        """向玩家输出错误提示。"""
        player.show(f"§c❀ {text}")

    @staticmethod
    def menu_header(title: str, with_rule: bool = True) -> str:
        """菜单顶部装饰条。

        Args:
            title: 菜单标题。
            with_rule: 是否附带下方的分隔装饰线。像「网络搜索点歌」这种
                标题下面紧跟 ``menu_footer`` 的纯提示菜单要传 False，
                否则两条装饰线会叠在一起，看着像重复了一条。
        """
        header = f"§l§e>§a>§6> §7「§b{title}§7」\n"
        if not with_rule:
            return header
        return (
            header
            + "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧\n"
        )

    @staticmethod
    def menu_footer(page_label: str, body: str) -> str:
        """菜单底部装饰条与操作提示。"""
        return (
            f"§l§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓 §r§7[ §b{page_label} §7] "
            "§l§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧\n"
            f"§r{body}"
        )

    def prompt_player(self, player: Player, prompt: str) -> str | None:
        """向玩家索取一次输入，超时返回 None 并提示。"""
        response = player.input(prompt, timeout=MENU_TIMEOUT)
        if response is None:
            self.show_error(player, "操作超时，已退出")
            return None
        return response.strip()

    @staticmethod
    def get_page_items(
        items: list[Any], current_page: int, page_size: int
    ) -> tuple[list[Any], int, int]:
        """按页大小切分列表，并把页码夹到合法范围内。"""
        total_pages = max(1, (len(items) + page_size - 1) // page_size)
        current_page = max(0, min(current_page, total_pages - 1))
        start = current_page * page_size
        end = min(start + page_size, len(items))
        return items[start:end], current_page, total_pages

    def next_page(self, player: Player, current_page: int, total_pages: int) -> int:
        """翻到下一页；已是最后一页则提示并原地不动。"""
        if current_page + 1 < total_pages:
            return current_page + 1
        self.show_warn(player, "已经是最后一页")
        return current_page

    def previous_page(self, player: Player, current_page: int) -> int:
        """翻到上一页；已是第一页则提示并原地不动。"""
        if current_page > 0:
            return current_page - 1
        self.show_warn(player, "已经是第一页")
        return current_page

    def select_indexed_item(self, player: Player, response: str, items: list[Any]):
        """把玩家输入的序号翻译成列表项；无效输入返回 None 并提示。"""
        choice = utils.try_int(response)
        if choice is None:
            self.show_error(player, "输入无效，请输入序号、q、+、- 或 s")
            return None
        if choice not in range(1, len(items) + 1):
            self.show_error(player, "序号超出当前页范围")
            return None
        return items[choice - 1]

    # ------------------------------------------------------------------
    # 本地曲库：扫描 / 转换 / 增量载入
    # ------------------------------------------------------------------
    def refresh_library(self, force: bool = False) -> int:
        """刷新本地曲库（按 mtime 增量处理，不重复做重活）。

        Args:
            force: 为 True 时忽略 mtime 缓存，全部重新载入。

        Returns:
            本次新载入的曲目数。
        """
        self.sync_seq_files()
        return self.load_local_song_library(force=force)

    def sync_seq_files(self) -> int:
        """把比同名 .midseq 更新的 .mid 转换成 .midseq。

        Returns:
            实际转换的文件数。
        """
        try:
            filenames = os.listdir(self.music_dir)
        except OSError as err:
            self.print_err(f"读取曲库目录失败: {err}")
            return 0
        converted = 0
        for filename in filenames:
            root, ext = os.path.splitext(filename)
            if ext.lower() != ".mid":
                continue
            midi_path = os.path.join(self.music_dir, filename)
            seq_path = os.path.join(self.music_dir, root + ".midseq")
            try:
                if os.path.isfile(seq_path):
                    stale = os.path.getmtime(midi_path) > os.path.getmtime(seq_path)
                else:
                    stale = True
            except OSError:
                stale = True
            if not stale:
                continue
            try:
                self.midiplayer.translate_midi_to_seq_file(midi_path, seq_path)
            except (Exception, SystemExit) as err:
                # MIDI播放器内部失败时会 raise SystemExit，它不属于 Exception
                self.print_err(f"转换 MIDI 失败: {filename} -> {err}")
                continue
            converted += 1
        return converted

    def load_local_song_library(self, force: bool = False) -> int:
        """把曲库目录下的 .midseq 增量载入 MIDI 播放器。

        Args:
            force: 为 True 时忽略 mtime 缓存，全部重新载入。

        Returns:
            本次新载入的曲目数。
        """
        try:
            filenames = sorted(os.listdir(self.music_dir), key=str.lower)
        except OSError as err:
            self.print_err(f"读取曲库目录失败: {err}")
            return 0
        found: list[str] = []
        loaded = 0
        for filename in filenames:
            root, ext = os.path.splitext(filename)
            if ext.lower() != ".midseq":
                continue
            seq_path = os.path.join(self.music_dir, filename)
            try:
                mtime = os.path.getmtime(seq_path)
            except OSError:
                continue
            found.append(root)
            if not force and self.loaded_songs.get(root) == mtime:
                continue
            try:
                self.midiplayer.load_sound_seq_file(seq_path, root)
            except (Exception, SystemExit) as err:
                # 损坏的序列文件同样会 raise SystemExit，必须显式吞掉
                self.print_err(f"载入音乐序列失败: {filename} -> {err}")
                continue
            self.loaded_songs[root] = mtime
            loaded += 1
        for gone in set(self.loaded_songs) - set(found):
            self.loaded_songs.pop(gone, None)
        self.local_songs = found
        return loaded

    def on_console_reload(self, _):
        """控制台命令：强制重载曲库与网络索引。"""
        self.network_index = self.load_network_index()
        self.refresh_library(force=True)

    # ------------------------------------------------------------------
    # 命令入口
    # ------------------------------------------------------------------
    def on_song_command(self, player: Player, _args: tuple):
        """聊天栏入口 ``.点歌``：打开主菜单。

        这里刻意声明 ``argument_hint=[]``（不接受参数）。实测部分版本的
        聊天栏菜单前置会把 ``...``（任意参数）理解为「必须补参数」，
        于是玩家只发 ``.点歌`` 时被前置插件反问 ``请输入：``。
        带歌名直达改由菜单内的输入兜底，见 ``open_song_menu`` 末尾分支。
        """
        self.open_song_menu(player, ())

    def search_and_play(self, player: Player, keyword: str):
        """先匹配本地曲库；本地没有则询问是否转向网络搜索。"""
        self.refresh_library()
        matches = [
            name for name in self.local_songs if self.is_fuzzy_match(name, keyword)
        ]
        if len(matches) == 1:
            self.play_song_for_player(player, matches[0])
            return
        if matches:
            chosen = self.choose_local_song(
                player, matches, f"本地歌曲点歌 - 匹配: {keyword}"
            )
            if chosen is not None:
                self.play_song_for_player(player, chosen)
            return
        if not self.cfg["是否启用网络点歌"]:
            self.show_error(player, f"本地没有包含 §6{keyword}§c 的歌曲。")
            return
        self.show_warn(player, f"本地没有包含 §6{keyword}§c 的歌曲。")
        answer = self.prompt_player(player, "§a是否从网络搜索？输入 §ey§a 继续：")
        if answer is None:
            return
        if answer.strip().lower() not in ("y", "yes", "是", "好"):
            self.show_info(player, "已取消网络搜索")
            return
        self.handle_network_search(player, keyword)

    def stop_current_song(self, player: Player, _):
        """聊天栏入口 ``.停止点歌``。"""
        if self.stop_song_thread(player.name):
            self.show_success(player, "已停止你当前播放的歌曲")
        else:
            self.show_warn(player, "你当前没有正在播放的歌曲")

    def reload_library_command(self, player: Player, _):
        """聊天栏入口 ``.重载曲库``（仅 OP 在菜单中可见）。"""
        if not player.is_op():
            self.show_error(player, "只有 OP 可以重载曲库")
            return
        loaded = self.refresh_library(force=True)
        self.show_success(
            player,
            f"曲库已重载：共 {len(self.local_songs)} 首，本次载入 {loaded} 首",
        )

    # ------------------------------------------------------------------
    # 菜单流程
    # ------------------------------------------------------------------
    def open_song_menu(self, player: Player, _):
        """``.点歌`` 的主菜单。"""
        self.refresh_library()
        if not self.cfg["是否启用网络点歌"]:
            self.handle_local_song_menu(player)
            return
        # 逐行发送，避免整块多行文本在某些接入点下渲染成一行而被玩家忽略
        player.show(self.menu_header("私人点歌"))
        player.show("§l§b[ §e1 §b] §f- §7本地点歌")
        player.show("§l§b[ §e2 §b] §f- §7网络搜索点歌")
        player.show(
            self.menu_footer(
                "MENU",
                "§a❀ §b输入 §e1 §b进入本地点歌\n"
                "§a❀ §b输入 §e2 §b进入网络搜索\n"
                "§a❀ §b输入 §6q §r§b退出菜单",
            )
        )
        # 操作提示已经写在页脚，输入提示留空，避免屏幕上多一行重复文本
        choice = self.prompt_player(player, "")
        if choice is None:
            return
        lowered = choice.strip().lower()
        if not lowered:
            # 没有输入提示行，玩家可能直接回车退出；空输入不当作歌名处理
            return
        if lowered == "q":
            self.show_error(player, "已退出点歌菜单")
            return
        if lowered == "1":
            self.handle_local_song_menu(player)
            return
        if lowered == "2":
            self.handle_network_song_menu(player)
            return
        # 既不是选项也不是退出指令，就按歌名处理，省得玩家再输一遍
        self.show_info(player, f"未选择模式，按歌名查找：§f{choice}§f")
        self.search_and_play(player, choice)

    def handle_local_song_menu(self, player: Player):
        """进入本地曲库选择流程。"""
        if not self.local_songs:
            self.show_error(
                player,
                f"本地曲库为空，请把 .mid 或 .midseq 放入 "
                f"§6插件数据文件/{self.name}/音乐列表§c。",
            )
            return
        selected_song = self.choose_local_song(player)
        if selected_song is not None:
            self.play_song_for_player(player, selected_song)

    def choose_local_song(
        self,
        player: Player,
        source_songs: list[str] | None = None,
        title: str | None = None,
    ) -> str | None:
        """分页展示本地歌曲并让玩家选择，支持模糊搜索。

        Args:
            player: 选择的玩家。
            source_songs: 候选曲名；默认使用整个本地曲库。
            title: 自定义菜单标题；留空时按是否有搜索关键词自动生成。

        Returns:
            选中的曲名；退出或超时返回 None。
        """
        source = list(source_songs if source_songs is not None else self.local_songs)
        songs = list(source)
        keyword = ""
        current_page = 0

        while True:
            if not songs:
                if keyword:
                    self.show_error(player, f"没有找到包含 §6{keyword}§c 的歌曲。")
                    songs = list(source)
                    keyword = ""
                    current_page = 0
                else:
                    self.show_error(player, "本地曲库为空。")
                    return None

            page_songs, current_page, total_pages = self.get_page_items(
                songs, current_page, self.page_size
            )
            header = title or (
                "本地歌曲点歌" if not keyword else f"本地歌曲点歌 - 搜索: {keyword}"
            )
            player.show(self.menu_header(header))
            for index, song_name in enumerate(page_songs, start=1):
                player.show(f"§l§b[ §e{index} §b] §f- §7{song_name}")
            player.show(
                self.menu_footer(
                    f"{current_page + 1}/{total_pages}",
                    "§f输入当前页歌名前序号点歌\n"
                    "输入 §l§b+ §7/ §c- §r§f翻页\n"
                    "输入 §l§6q §r§f退出菜单\n"
                    "输入 §l§es§r§f 搜索",
                )
            )

            response = self.prompt_player(player, "§a请输入操作：")
            if response is None:
                return None
            lowered = response.lower()
            if lowered == "q":
                self.show_error(player, "已退出点歌菜单")
                return None
            if response == "+":
                current_page = self.next_page(player, current_page, total_pages)
                continue
            if response == "-":
                current_page = self.previous_page(player, current_page)
                continue
            if lowered == "s":
                songs, keyword, current_page = self.search_local_songs(player, source)
                continue

            selected_song = self.select_indexed_item(player, response, page_songs)
            if selected_song is not None:
                return selected_song

    def search_local_songs(
        self, player: Player, source_songs: list[str]
    ) -> tuple[list[str], str, int]:
        """向玩家索取关键词并按模糊规则过滤本地曲库。

        Args:
            player: 搜索的玩家。
            source_songs: 完整候选列表。

        Returns:
            (过滤后的列表, 关键词, 页码)。
        """
        keyword_input = self.prompt_player(
            player, "§a请输入搜索关键词，留空返回完整列表："
        )
        if keyword_input is None:
            self.show_error(player, "搜索超时，保持当前列表")
            return list(source_songs), "", 0
        if not keyword_input:
            return list(source_songs), "", 0
        filtered = [
            name for name in source_songs if self.is_fuzzy_match(name, keyword_input)
        ]
        if not filtered:
            self.show_error(player, f"没有找到包含 §6{keyword_input}§c 的歌曲")
            return list(source_songs), "", 0
        return filtered, keyword_input, 0

    def is_fuzzy_match(self, song_name: str, keyword: str) -> bool:
        """判断歌曲名是否模糊命中关键词（顺序无关的多词匹配）。"""
        normalized_song = self.normalize_text(song_name)
        normalized_keyword = self.normalize_text(keyword)
        if not normalized_keyword:
            return True
        if normalized_keyword in normalized_song:
            return True
        return all(part in normalized_song for part in normalized_keyword.split())

    @staticmethod
    def normalize_text(text: str) -> str:
        """把文本统一成小写、单空格分隔的形式用于比较。"""
        return "".join(ch.lower() if not ch.isspace() else " " for ch in text).strip()

    # ------------------------------------------------------------------
    # 播放控制
    # ------------------------------------------------------------------
    def play_song_for_player(self, player: Player, song_name: str):
        """停掉该玩家当前播放，再为他播放指定曲目。"""
        self.stop_song_thread(player.name)
        target = utils.to_player_selector(player.name)
        thread_id = self.midiplayer.playsound_at_target(song_name, target)
        if not thread_id:
            self.show_error(player, f"播放失败：无法播放 §6{song_name}§c。")
            return
        self.playing_threads[player.name] = thread_id
        self.show_success(player, f"开始为你播放：§f「 §b{song_name} §f」")

    def is_song_playing(self, player_name: str) -> bool:
        """判断该玩家此刻是否真的在播放。

        MIDI播放器的播放线程结束时会在内部删除自己的记录，
        这里同步清理过期映射，避免 ``.停止点歌`` 出现假阳性。
        """
        thread_id = self.playing_threads.get(player_name)
        if thread_id is None:
            return False
        if self.midiplayer.playsound_threads.get(thread_id) is None:
            self.playing_threads.pop(player_name, None)
            return False
        return True

    def stop_song_thread(self, player_name: str) -> bool:
        """停止该玩家正在播放的歌曲。

        Args:
            player_name: 玩家名。

        Returns:
            是否真的停掉了一首正在播放的曲子。
        """
        thread_id = self.playing_threads.pop(player_name, None)
        if thread_id is None:
            return False
        if self.midiplayer.playsound_threads.get(thread_id) is None:
            return False
        self.midiplayer.stop_playing(thread_id)
        return True

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def remove_file_quietly(path: str):
        """删除文件；不存在或删除失败时静默忽略。"""
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

    @staticmethod
    def make_safe_song_name(title: str) -> str:
        """把任意标题清洗成可安全落盘的文件名。

        Args:
            title: 原始标题。

        Returns:
            清洗后的文件名（不含扩展名）。
        """
        cleaned = (title or "").strip() or "未命名歌曲"
        cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", cleaned)
        cleaned = cleaned[:80].rstrip(". ")
        if not cleaned:
            # 形如 ".." / "..." 的标题，rstrip 之后会变成空串
            return "未命名歌曲"
        if cleaned.upper() in WINDOWS_RESERVED_NAMES:
            return f"_{cleaned}"
        return cleaned


entry = plugin_entry(PersonalSongRequest)

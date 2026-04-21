import base64
import os
import re
from dataclasses import dataclass
from typing import Any

from tooldelta import Player, Plugin, cfg, plugin_entry, utils

MENU_TIMEOUT = 300


@dataclass
class SongSearchResult:
    title: str
    link: str
    download_count: str = "?"
    rating: str = "?"
    duration: str = "?"


class PersonalSongRequest(Plugin):
    name = "私人点歌"
    author = "小六神"
    version = (0, 0, 1)
    description = "免费点歌，只对点歌人播放，支持本地歌曲分页与模糊搜索，以及网络搜索下载。"

    def __init__(self, frame):
        super().__init__(frame)
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name,
            {"本地歌曲点歌每页显示多少歌曲": cfg.PInt},
            {"本地歌曲点歌每页显示多少歌曲": 10},
            self.version,
        )

        self.make_data_path()
        self.music_dir = self.format_data_path("音乐列表")
        os.makedirs(self.music_dir, exist_ok=True)

        self.local_songs: list[str] = []
        self.playing_threads: dict[str, int] = {}
        self.chatbar = None
        self.midiplayer = None
        self.requests = None
        self.urllib3 = None
        self.etree = None

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_frame_exit)

    @property
    def page_size(self) -> int:
        return max(1, int(self.cfg["本地歌曲点歌每页显示多少歌曲"]))

    def on_preload(self):
        self.prepare_plugin_apis()
        self.prepare_network_dependencies()
        self.reload_local_songs()

    def on_active(self):
        self.chatbar.add_new_trigger(
            [".点歌", ".song"],
            [],
            "打开私人点歌菜单",
            self.open_song_menu,
        )
        self.chatbar.add_new_trigger(
            [".停止点歌", ".stopsong"],
            [],
            "停止你当前播放的歌曲",
            self.stop_current_song,
        )

    def prepare_plugin_apis(self):
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

    def prepare_network_dependencies(self):
        from lxml import etree  # type: ignore
        import requests  # type: ignore
        import urllib3  # type: ignore

        self.etree = etree
        self.requests = requests
        self.urllib3 = urllib3

    def show_info(self, player: Player, text: str):
        player.show(f"§f❀ {text}")

    def show_success(self, player: Player, text: str):
        player.show(f"§a❀ {text}")

    def show_warn(self, player: Player, text: str):
        player.show(f"§6❀ {text}")

    def show_error(self, player: Player, text: str):
        player.show(f"§c❀ {text}")

    @staticmethod
    def menu_header(title: str) -> str:
        return (
            f"§l§e>§g>§6> §7「§b{title}§7」\n"
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧\n"
        )

    @staticmethod
    def menu_footer(page_label: str, body: str) -> str:
        return (
            f"§l§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓 §r§7[ §b{page_label} §7] "
            "§l§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧\n"
            f"§r{body}"
        )

    def prompt_player(self, player: Player, prompt: str) -> str | None:
        response = player.input(prompt, timeout=MENU_TIMEOUT)
        if response is None:
            self.show_error(player, "操作超时，已退出")
            return None
        return response.strip()

    def reload_local_songs(self):
        self.sync_seq_files()
        self.local_songs = self.load_local_song_library()

    def sync_seq_files(self):
        for filename in os.listdir(self.music_dir):
            root, ext = os.path.splitext(filename)
            if ext.lower() != ".mid":
                continue
            midi_path = os.path.join(self.music_dir, filename)
            seq_path = os.path.join(self.music_dir, root + ".midseq")
            try:
                if not os.path.isfile(seq_path) or (
                    os.path.getmtime(midi_path) > os.path.getmtime(seq_path)
                ):
                    self.midiplayer.translate_midi_to_seq_file(midi_path, seq_path)
            except Exception as err:
                self.print_err(f"转换 MIDI 失败: {filename} -> {err}")

    def load_local_song_library(self) -> list[str]:
        loaded_names: list[str] = []
        for filename in sorted(os.listdir(self.music_dir), key=str.lower):
            root, ext = os.path.splitext(filename)
            if ext.lower() != ".midseq":
                continue
            seq_path = os.path.join(self.music_dir, filename)
            try:
                self.midiplayer.load_sound_seq_file(seq_path, root)
            except Exception as err:
                self.print_err(f"载入音乐序列失败: {filename} -> {err}")
                continue
            loaded_names.append(root)
        return loaded_names

    def open_song_menu(self, player: Player, _):
        self.reload_local_songs()
        player.show(
            self.menu_header("私人点歌")
            + "§l§b[ §e1 §b] §f- §7本地点歌\n"
            + "§l§b[ §e2 §b] §f- §7网络搜索点歌\n"
            + self.menu_footer(
                "MENU",
                "§a❀ §b输入 §e1 或 2 §b选择点歌模式\n"
                "§a❀ §b输入 §6q §r§b退出菜单",
            )
        )
        choice = self.prompt_player(player, "§a请输入操作：")
        if choice is None:
            return
        lowered = choice.lower()
        if lowered == "q":
            self.show_error(player, "已退出点歌菜单")
            return
        if choice == "1":
            self.handle_local_song_menu(player)
            return
        if choice == "2":
            self.handle_network_song_menu(player)
            return
        self.show_error(player, "输入无效，请输入 1、2 或 q")

    def handle_local_song_menu(self, player: Player):
        if not self.local_songs:
            self.show_error(
                player,
                f"本地曲库为空，请将 .mid 或 .midseq 文件放入 §6插件数据文件/{self.name}/音乐列表§c。",
            )
            return
        selected_song = self.choose_local_song(player)
        if selected_song is not None:
            self.play_song_for_player(player, selected_song)

    def choose_local_song(self, player: Player) -> str | None:
        source_songs = list(self.local_songs)
        songs = list(source_songs)
        keyword = ""
        current_page = 0

        while True:
            if not songs:
                if keyword:
                    self.show_error(player, f"没有找到包含 §6{keyword}§c 的歌曲。")
                    songs = list(source_songs)
                    keyword = ""
                    current_page = 0
                else:
                    self.show_error(player, "本地曲库为空。")
                    return None

            page_songs, current_page, total_pages = self.get_page_items(songs, current_page)
            title = "本地歌曲点歌" if not keyword else f"本地歌曲点歌 - 搜索: {keyword}"
            player.show(self.menu_header(title))
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
                songs, keyword, current_page = self.search_local_songs(
                    player,
                    source_songs,
                )
                continue

            selected_song = self.select_indexed_item(player, response, page_songs)
            if selected_song is not None:
                return selected_song

    def search_local_songs(
        self,
        player: Player,
        source_songs: list[str],
    ) -> tuple[list[str], str, int]:
        keyword_input = self.prompt_player(
            player,
            "§a请输入搜索关键词，留空返回完整列表：",
        )
        if keyword_input is None:
            self.show_error(player, "搜索超时，保持当前列表")
            return source_songs, "", 0
        if not keyword_input:
            return source_songs, "", 0
        filtered = [
            song_name
            for song_name in source_songs
            if self.is_fuzzy_match(song_name, keyword_input)
        ]
        if not filtered:
            self.show_error(player, f"没有找到包含 §6{keyword_input}§c 的歌曲")
            return source_songs, "", 0
        return filtered, keyword_input, 0

    def get_page_items(self, items: list[Any], current_page: int) -> tuple[list[Any], int, int]:
        total_pages = max(1, (len(items) + self.page_size - 1) // self.page_size)
        current_page = max(0, min(current_page, total_pages - 1))
        start = current_page * self.page_size
        end = min(start + self.page_size, len(items))
        return items[start:end], current_page, total_pages

    def next_page(self, player: Player, current_page: int, total_pages: int) -> int:
        if current_page + 1 < total_pages:
            return current_page + 1
        self.show_warn(player, "已经是最后一页")
        return current_page

    def previous_page(self, player: Player, current_page: int) -> int:
        if current_page > 0:
            return current_page - 1
        self.show_warn(player, "已经是第一页")
        return current_page

    def select_indexed_item(self, player: Player, response: str, items: list[Any]):
        choice = utils.try_int(response)
        if choice is None:
            self.show_error(player, "输入无效，请输入序号、q、+、- 或 s")
            return None
        if choice not in range(1, len(items) + 1):
            self.show_error(player, "序号超出当前页范围")
            return None
        return items[choice - 1]

    def is_fuzzy_match(self, song_name: str, keyword: str) -> bool:
        normalized_song = self.normalize_text(song_name)
        normalized_keyword = self.normalize_text(keyword)
        if not normalized_keyword:
            return True
        if normalized_keyword in normalized_song:
            return True
        return all(part in normalized_song for part in normalized_keyword.split())

    @staticmethod
    def normalize_text(text: str) -> str:
        return "".join(ch.lower() if not ch.isspace() else " " for ch in text).strip()

    def play_song_for_player(self, player: Player, song_name: str):
        self.stop_song_thread(player.name)
        target = utils.to_player_selector(player.name)
        thread_id = self.midiplayer.playsound_at_target(song_name, target)
        if not thread_id:
            self.show_error(player, f"播放失败：无法播放 §6{song_name}§c。")
            return
        self.playing_threads[player.name] = thread_id
        self.show_success(player, f"开始为你播放：§f「 §b{song_name} §f」")

    def stop_current_song(self, player: Player, _):
        if self.stop_song_thread(player.name):
            self.show_success(player, "已停止你当前播放的歌曲")
        else:
            self.show_warn(player, "你当前没有正在播放的歌曲")

    def stop_song_thread(self, player_name: str) -> bool:
        thread_id = self.playing_threads.pop(player_name, None)
        if thread_id is None:
            return False
        self.midiplayer.stop_playing(thread_id)
        return True

    def on_frame_exit(self, _):
        for player_name in list(self.playing_threads):
            self.stop_song_thread(player_name)

    def handle_network_song_menu(self, player: Player):
        player.show(
            self.menu_header("网络搜索点歌")
            + self.menu_footer(
                "网络点歌",
                "§a❀ §b输入歌曲名开始搜索\n"
                "§a❀ §b输入 §l§6q §r§b退出菜单",
            )
        )
        keyword = self.prompt_player(player, "§a请输入要搜索的歌曲名称：")
        if keyword is None:
            return
        keyword = keyword.strip()
        if not keyword or keyword.lower() == "q":
            self.show_error(player, "已退出网络点歌")
            return

        music_items = self.search_music(keyword, player)
        if not music_items:
            return

        selected_song = self.display_search_results(music_items, player, keyword)
        if selected_song is None:
            return

        self.show_info(player, f"正在下载歌曲：§f「 §b{selected_song.title} §f」")
        api_data = self.download_midi(selected_song.link)
        if not api_data:
            self.show_error(player, "下载失败，请稍后再试")
            return

        song_name = self.process_downloaded_midi(api_data, selected_song.title, player)
        if song_name is not None:
            self.play_song_for_player(player, song_name)

    def search_music(self, music_name: str, player: Player) -> list[SongSearchResult] | None:
        self.urllib3.disable_warnings(self.urllib3.exceptions.InsecureRequestWarning)
        search_url = f"https://www.midishow.com/search/result?q={music_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.midishow.com/",
        }
        try:
            self.show_info(player, "正在搜索网络歌曲，请稍候…")
            response = self.requests.get(
                search_url,
                headers=headers,
                verify=False,
                timeout=10,
            )
            response.raise_for_status()
        except Exception as err:
            self.show_error(player, f"搜索失败：{err}")
            return None
        tree = self.etree.HTML(response.text)
        nodes = tree.xpath(
            '//div[@id="search-result"]/div/a[@class="d-block border-bottom pb-5 mb-5 position-relative"]'
        )
        return [self.parse_search_result(node) for node in nodes]

    def parse_search_result(self, node) -> SongSearchResult:
        title = (
            node.xpath(".//h3")[0].xpath("string()").strip()
            if node.xpath(".//h3")
            else "未知标题"
        )
        info_text = (
            node.xpath('.//div[@class="small text-muted"]')[0].xpath("string()").strip()
            if node.xpath('.//div[@class="small text-muted"]')
            else ""
        )
        file_info_text = (
            node.xpath('.//div[@class="row small text-muted pl-0 pl-md-9"]')[0]
            .xpath("string()")
            .strip()
            if node.xpath('.//div[@class="row small text-muted pl-0 pl-md-9"]')
            else ""
        )
        download_match = re.search(r"(\d+)次下载", info_text)
        rating_match = re.search(r"(\d+\.\d+)\(\d+人打分\)", file_info_text)
        duration_match = re.search(r"(\d+:\d+)", file_info_text)
        return SongSearchResult(
            title=title,
            link=node.get("href") or "",
            download_count=download_match.group(1) if download_match else "?",
            rating=rating_match.group(1) if rating_match else "?",
            duration=duration_match.group(1) if duration_match else "?",
        )

    def display_search_results(
        self,
        music_items: list[SongSearchResult],
        player: Player,
        keyword: str,
    ) -> SongSearchResult | None:
        if not music_items:
            self.show_error(player, "没有找到相关歌曲")
            return None

        current_page = 0
        while True:
            page_items, current_page, total_pages = self.get_page_items(
                music_items,
                current_page,
            )
            player.show(self.menu_header(f"网络搜索点歌 - 搜索: {keyword}"))
            for index, item in enumerate(page_items, start=1):
                player.show(
                    f"§l§b[ §e{index} §b] §f- §7{item.title} "
                    f"§8(下载:{item.download_count} 评分:{item.rating} 时长:{item.duration})"
                )
            player.show(
                self.menu_footer(
                    f"{current_page + 1}/{total_pages}",
                    "§f输入当前页序号选择歌曲\n"
                    "输入 §l§b+ §7/ §c- §r§f翻页\n"
                    "输入 §l§6q §r§f退出菜单",
                )
            )

            response = self.prompt_player(player, "§a请输入操作：")
            if response is None:
                return None
            lowered = response.lower()
            if lowered == "q":
                self.show_error(player, "已退出网络点歌")
                return None
            if response == "+":
                current_page = self.next_page(player, current_page, total_pages)
                continue
            if response == "-":
                current_page = self.previous_page(player, current_page)
                continue
            selected_song = self.select_indexed_item(player, response, page_items)
            if isinstance(selected_song, SongSearchResult):
                if not selected_song.link:
                    self.show_error(player, "无法获取歌曲链接")
                    return None
                return selected_song

    def download_midi(self, selected_link: str) -> dict[str, Any] | None:
        self.urllib3.disable_warnings(self.urllib3.exceptions.InsecureRequestWarning)
        try:
            api_response = self.requests.post(
                "https://midi.fxdby.net/api/download_midi",
                json={"url": selected_link},
                verify=False,
                timeout=15,
            )
            api_response.raise_for_status()
            return api_response.json()
        except Exception as err:
            self.print_err(f"网络 MIDI 下载失败: {err}")
            return None

    def process_downloaded_midi(
        self,
        api_data: dict[str, Any],
        fallback_title: str,
        player: Player,
    ) -> str | None:
        if not api_data.get("success"):
            self.show_error(player, f"下载失败：{api_data.get('message', '未知错误')}")
            return None

        data = api_data.get("data", {})
        midi_file = data.get("file")
        if not midi_file:
            self.show_error(player, "下载结果缺少音乐数据")
            return None

        safe_title = self.make_safe_song_name(data.get("title", fallback_title))
        midi_path = os.path.join(self.music_dir, safe_title + ".mid")
        seq_path = os.path.join(self.music_dir, safe_title + ".midseq")
        try:
            self.show_info(player, f"正在载入歌曲：§f「 §b{safe_title} §f」")
            with open(midi_path, "wb") as file:
                file.write(base64.b64decode(midi_file))
            self.midiplayer.translate_midi_to_seq_file(midi_path, seq_path)
            if os.path.isfile(midi_path):
                os.remove(midi_path)
            self.midiplayer.load_sound_seq_file(seq_path, safe_title)
        except Exception as err:
            self.print_err(f"处理下载的 MIDI 失败: {err}")
            self.show_error(player, f"载入失败：{err}")
            return None

        if safe_title not in self.local_songs:
            self.local_songs.append(safe_title)
            self.local_songs.sort(key=str.lower)
        self.show_success(player, f"网络歌曲已载入：§f「 §b{safe_title} §f」")
        return safe_title

    @staticmethod
    def make_safe_song_name(title: str) -> str:
        cleaned_title = (title or "").strip() or "未命名歌曲"
        cleaned_title = re.sub(r'[\\\\/:*?"<>|]+', "_", cleaned_title)
        return cleaned_title[:80].rstrip(". ")


entry = plugin_entry(PersonalSongRequest)

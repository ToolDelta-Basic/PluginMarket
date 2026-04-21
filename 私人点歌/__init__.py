import os
import re
import base64
from typing import TYPE_CHECKING

from tooldelta import Plugin, Player, cfg, plugin_entry, utils


class PersonalSongRequest(Plugin):
    name = "私人点歌"
    author = "OpenAI"
    version = (0, 0, 1)
    description = "免费点歌，只对点歌人播放，支持本地歌曲分页与模糊搜索，以及网络搜索下载。"

    def __init__(self, frame):
        super().__init__(frame)
        cfg_default = {
            "本地歌曲点歌每页显示多少歌曲": 10,
        }
        cfg_std = {
            "本地歌曲点歌每页显示多少歌曲": cfg.PInt,
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name,
            cfg_std,
            cfg_default,
            self.version,
        )

        self.make_data_path()
        self.music_dir = self.format_data_path("音乐列表")
        os.makedirs(self.music_dir, exist_ok=True)

        self.local_songs: list[str] = []
        self.playing_threads: dict[str, int] = {}

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_frame_exit)

    def on_preload(self):
        pip = self.GetPluginAPI("pip")
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.midiplayer = self.GetPluginAPI("MIDI播放器")
        if TYPE_CHECKING:
            from pip模块支持 import PipSupport
            from 前置_MIDI播放器 import ToolMidiMixer
            from 前置_聊天栏菜单 import ChatbarMenu

            pip: PipSupport
            self.midiplayer: ToolMidiMixer
            self.chatbar: ChatbarMenu
        pip.require(
            {
                "lxml": "lxml",
                "requests": "requests",
                "urllib3": "urllib3",
            }
        )
        global etree, requests, urllib3
        from lxml import etree  # type: ignore
        import requests  # type: ignore
        import urllib3  # type: ignore
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

    def reload_local_songs(self):
        for filename in os.listdir(self.music_dir):
            root, ext = os.path.splitext(filename)
            if ext.lower() != ".mid":
                continue
            midi_path = os.path.join(self.music_dir, filename)
            seq_path = os.path.join(
                self.music_dir,
                root + ".midseq",
            )
            try:
                if (not os.path.isfile(seq_path)) or (
                    os.path.getmtime(midi_path) > os.path.getmtime(seq_path)
                ):
                    self.midiplayer.translate_midi_to_seq_file(midi_path, seq_path)
            except Exception as err:
                self.print_err(f"转换 MIDI 失败: {filename} -> {err}")

        loaded_names: list[str] = []
        for filename in sorted(os.listdir(self.music_dir), key=str.lower):
            root, ext = os.path.splitext(filename)
            if ext.lower() != ".midseq":
                continue
            seq_path = os.path.join(self.music_dir, filename)
            song_name = root
            try:
                self.midiplayer.load_sound_seq_file(seq_path, song_name)
            except Exception as err:
                self.print_err(f"载入音乐序列失败: {filename} -> {err}")
                continue
            loaded_names.append(song_name)
        self.local_songs = loaded_names

    def open_song_menu(self, player: Player, _):
        self.reload_local_songs()
        player.show(
            self.menu_header("私人点歌")
            +
            "§l§b[ §e1 §b] §f- §7本地点歌\n"
            "§l§b[ §e2 §b] §f- §7网络搜索点歌\n"
            + self.menu_footer(
                "MENU",
                "§a❀ §b输入 §e1 或 2 §b选择点歌模式\n"
                "§a❀ §b输入 §6q §r§b退出菜单",
            )
        )
        choice = player.input("§a请输入操作：", timeout=300)
        if choice is None:
            self.show_error(player, "操作超时，已退出")
            return
        choice = choice.strip().lower()
        if choice == "q":
            self.show_error(player, "已退出点歌菜单")
            return
        if choice == "1":
            if not self.local_songs:
                self.show_error(
                    player,
                    f"本地曲库为空，请将 .mid 或 .midseq 文件放入 §6插件数据文件/{self.name}/音乐列表§c。",
                )
                return
            selected_song = self.choose_local_song(player)
            if selected_song is None:
                return
            self.play_song_for_player(player, selected_song)
            return
        if choice == "2":
            self.network_song_menu(player)
            return
        self.show_error(player, "输入无效，请输入 1、2 或 q")

    def choose_local_song(self, player: Player) -> str | None:
        page_size = max(1, int(self.cfg["本地歌曲点歌每页显示多少歌曲"]))
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

            total_pages = max(1, (len(songs) + page_size - 1) // page_size)
            current_page = max(0, min(current_page, total_pages - 1))
            start = current_page * page_size
            end = min(start + page_size, len(songs))
            page_songs = songs[start:end]

            title = "本地歌曲点歌"
            if keyword:
                title += f" - 搜索: {keyword}"
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

            response = player.input("§a请输入操作：", timeout=300)
            if response is None:
                self.show_error(player, "操作超时，已退出")
                return None

            response = response.strip()
            if not response:
                continue

            lowered = response.lower()
            if lowered == "q":
                self.show_error(player, "已退出点歌菜单")
                return None
            if response == "+":
                if current_page + 1 < total_pages:
                    current_page += 1
                else:
                    self.show_warn(player, "已经是最后一页")
                continue
            if response == "-":
                if current_page > 0:
                    current_page -= 1
                else:
                    self.show_warn(player, "已经是第一页")
                continue
            if lowered == "s":
                keyword_input = player.input(
                    "§a请输入搜索关键词，留空返回完整列表：",
                    timeout=300,
                )
                if keyword_input is None:
                    self.show_error(player, "搜索超时，保持当前列表")
                    continue
                keyword_input = keyword_input.strip()
                if not keyword_input:
                    songs = list(source_songs)
                    keyword = ""
                    current_page = 0
                    continue
                filtered = [
                    song_name
                    for song_name in source_songs
                    if self.is_fuzzy_match(song_name, keyword_input)
                ]
                if not filtered:
                    self.show_error(player, f"没有找到包含 §6{keyword_input}§c 的歌曲")
                    continue
                songs = filtered
                keyword = keyword_input
                current_page = 0
                continue

            choice = utils.try_int(response)
            if choice is None:
                self.show_error(player, "输入无效，请输入序号、q、+、- 或 s")
                continue
            if choice not in range(1, len(page_songs) + 1):
                self.show_error(player, "序号超出当前页范围")
                continue
            return page_songs[choice - 1]

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

    def network_song_menu(self, player: Player):
        player.show(
            self.menu_header("网络搜索点歌")
            + self.menu_footer(
                "网络点歌",
                "§a❀ §b输入歌曲名开始搜索\n"
                "§a❀ §b输入 §l§6q §r§b退出菜单",
            )
        )
        keyword = player.input("§a请输入要搜索的歌曲名称：", timeout=300)
        if keyword is None:
            self.show_error(player, "操作超时，已退出")
            return
        keyword = keyword.strip()
        if not keyword or keyword.lower() == "q":
            self.show_error(player, "已退出网络点歌")
            return

        music_items = self.search_music(keyword, player)
        if not music_items:
            return

        selected_link, selected_title = self.display_search_results(
            music_items,
            player,
            keyword,
        )
        if not selected_link or not selected_title:
            return

        self.show_info(player, f"正在下载歌曲：§f「 §b{selected_title} §f」")
        api_data = self.download_midi(selected_link)
        if not api_data:
            self.show_error(player, "下载失败，请稍后再试")
            return

        song_name = self.process_downloaded_midi(api_data, selected_title, player)
        if not song_name:
            return
        self.play_song_for_player(player, song_name)

    def search_music(self, music_name: str, player: Player):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        search_url = f"https://www.midishow.com/search/result?q={music_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.midishow.com/",
        }
        try:
            self.show_info(player, "正在搜索网络歌曲，请稍候…")
            response = requests.get(search_url, headers=headers, verify=False, timeout=10)
            response.raise_for_status()
            tree = etree.HTML(response.text)
            return tree.xpath(
                '//div[@id="search-result"]/div/a[@class="d-block border-bottom pb-5 mb-5 position-relative"]'
            )
        except Exception as err:
            self.show_error(player, f"搜索失败：{err}")
            return None

    def display_search_results(
        self,
        music_items,
        player: Player,
        keyword: str,
    ):
        if not music_items:
            self.show_error(player, "没有找到相关歌曲")
            return None, None

        page_size = max(1, int(self.cfg["本地歌曲点歌每页显示多少歌曲"]))
        current_page = 0

        while True:
            total_pages = max(1, (len(music_items) + page_size - 1) // page_size)
            current_page = max(0, min(current_page, total_pages - 1))
            start = current_page * page_size
            end = min(start + page_size, len(music_items))
            page_items = music_items[start:end]

            player.show(self.menu_header(f"网络搜索点歌 - 搜索: {keyword}"))
            for index, item in enumerate(page_items, start=1):
                title = (
                    item.xpath(".//h3")[0].xpath("string()").strip()
                    if item.xpath(".//h3")
                    else "未知标题"
                )
                info_text = (
                    item.xpath('.//div[@class="small text-muted"]')[0].xpath("string()").strip()
                    if item.xpath('.//div[@class="small text-muted"]')
                    else ""
                )
                file_info_text = (
                    item.xpath('.//div[@class="row small text-muted pl-0 pl-md-9"]')[0].xpath("string()").strip()
                    if item.xpath('.//div[@class="row small text-muted pl-0 pl-md-9"]')
                    else ""
                )
                download_match = re.search(r"(\d+)次下载", info_text)
                rating_match = re.search(r"(\d+\.\d+)\(\d+人打分\)", file_info_text)
                duration_match = re.search(r"(\d+:\d+)", file_info_text)
                download_count = download_match.group(1) if download_match else "?"
                rating = rating_match.group(1) if rating_match else "?"
                duration = duration_match.group(1) if duration_match else "?"
                player.show(
                    f"§l§b[ §e{index} §b] §f- §7{title} §8(下载:{download_count} 评分:{rating} 时长:{duration})"
                )
            player.show(
                self.menu_footer(
                    f"{current_page + 1}/{total_pages}",
                    "§f输入当前页序号选择歌曲\n"
                    "输入 §l§b+ §7/ §c- §r§f翻页\n"
                    "输入 §l§6q §r§f退出菜单",
                )
            )

            resp = player.input("§a请输入操作：", timeout=300)
            if resp is None:
                self.show_error(player, "操作超时，已退出")
                return None, None
            resp = resp.strip().lower()
            if resp == "q":
                self.show_error(player, "已退出网络点歌")
                return None, None
            if resp == "+":
                if current_page + 1 < total_pages:
                    current_page += 1
                else:
                    self.show_warn(player, "已经是最后一页")
                continue
            if resp == "-":
                if current_page > 0:
                    current_page -= 1
                else:
                    self.show_warn(player, "已经是第一页")
                continue
            choice = utils.try_int(resp)
            if choice is None or choice not in range(1, len(page_items) + 1):
                self.show_error(player, "输入无效，请输入当前页序号、q、+ 或 -")
                continue
            selected_item = page_items[choice - 1]
            selected_title = (
                selected_item.xpath(".//h3")[0].xpath("string()").strip()
                if selected_item.xpath(".//h3")
                else "未知标题"
            )
            selected_link = selected_item.get("href")
            if not selected_link:
                self.show_error(player, "无法获取歌曲链接")
                return None, None
            return selected_link, selected_title

    def download_midi(self, selected_link: str):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            api_response = requests.post(
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
        api_data,
        selected_title: str,
        player: Player,
    ) -> str | None:
        if not api_data.get("success"):
            message = api_data.get("message", "未知错误")
            self.show_error(player, f"下载失败：{message}")
            return None
        midi_file = api_data.get("data", {}).get("file")
        if not midi_file:
            self.show_error(player, "下载结果缺少音乐数据")
            return None

        resolved_title = api_data.get("data", {}).get("title", selected_title)
        safe_title = self.make_safe_song_name(resolved_title)
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
            if safe_title not in self.local_songs:
                self.local_songs.append(safe_title)
                self.local_songs.sort(key=str.lower)
            self.show_success(player, f"网络歌曲已载入：§f「 §b{safe_title} §f」")
            return safe_title
        except Exception as err:
            self.print_err(f"处理下载的 MIDI 失败: {err}")
            self.show_error(player, f"载入失败：{err}")
            return None

    @staticmethod
    def make_safe_song_name(title: str) -> str:
        title = title.strip() or "未命名歌曲"
        title = re.sub(r'[\\\\/:*?"<>|]+', "_", title)
        return title[:80].rstrip(". ")


entry = plugin_entry(PersonalSongRequest)

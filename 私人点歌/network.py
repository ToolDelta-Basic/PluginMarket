"""私人点歌：网络点歌客户端（MIDI 中转服务）。

从 ``__init__.py`` 拆出，避免单文件过长。这里只放网络相关的常量、
数据结构与 mixin 方法，实际插件类在 ``__init__.py`` 里组合它们。
"""

import importlib
import json
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from tooldelta import Player

# ---------------------------------------------------------------------------
# MIDI 中转服务常量
#
# 服务端自己去 midishow 拉曲并缓存
# ---------------------------------------------------------------------------
NETWORK_DEFAULT_BASE = "https://midishow.tdgzs.top"

NETWORK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class NetworkSong:
    """中转服务返回的一首曲目（即 ``/api/search`` 的 results 单项）。

    Attributes:
        song_id: 作品 ID，``/api/fetch`` 用它换取下载直链。
        title: 曲名。
        author: 上传者。
        duration: 时长文本，形如 ``04:19``；服务端缺失时回落为 ``?``。
        downloads: 站点下载量。
        size_text: 文件大小文本，形如 ``25.42 KB``。
        tracks: 轨道数。
    """

    song_id: str
    title: str
    author: str = ""
    duration: str = "?"
    downloads: int = 0
    size_text: str = ""
    tracks: int = 0


class NetworkMixin:
    """网络点歌相关方法集合，由主插件类继承使用。"""

    @property
    def network_base(self) -> str:
        """网络点歌服务地址（去掉末尾斜杠；留空则回落默认地址）。"""
        base = str(self.cfg.get("网络点歌服务地址") or "").strip()
        return (base or NETWORK_DEFAULT_BASE).rstrip("/")

    @property
    def network_page_size(self) -> int:
        """网络搜索结果每页显示条数。"""
        return max(1, int(self.cfg["网络点歌搜索结果每页显示"]))

    def prepare_network_dependencies(self):
        """导入网络依赖并关闭证书告警（pip.require 已保证装好）。

        这里用 ``importlib`` 而不是函数内的 ``import``：既保留「等 pip.require
        装完再导入」的时序，也避免触发 import-outside-toplevel 这类风格检查。
        """
        self.etree = importlib.import_module("lxml.etree")
        self.requests = importlib.import_module("requests")
        self.urllib3 = importlib.import_module("urllib3")
        self.urllib3.disable_warnings(self.urllib3.exceptions.InsecureRequestWarning)

    # ------------------------------------------------------------------
    # 网络曲库索引
    # ------------------------------------------------------------------
    def load_network_index(self) -> dict[str, dict[str, Any]]:
        """读取网络曲库索引（记录已下载曲目对应的中转服务作品 ID）。"""
        path = self.format_data_path("网络曲库索引.json")
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as err:
            self.print_err(f"读取网络曲库索引失败: {err}")
            return {}
        if isinstance(data, dict):
            return data
        return {}

    def save_network_index(self):
        """原子写入网络曲库索引。"""
        path = self.format_data_path("网络曲库索引.json")
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as file:
                json.dump(self.network_index, file, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except OSError as err:
            self.print_err(f"写入网络曲库索引失败: {err}")
            self.remove_file_quietly(tmp_path)

    def resolve_local_name(self, song: NetworkSong) -> str:
        """决定本地文件名，避免同名不同曲互相覆盖。

        Args:
            song: 已拿到作品 ID 的曲目。

        Returns:
            可安全用作文件名的本地曲名。
        """
        base = self.make_safe_song_name(song.title)
        # 变量名避开模块级的 entry（插件入口），否则会遮蔽外层同名
        index_entry = self.network_index.get(base)
        if index_entry is not None and str(index_entry.get("id")) == song.song_id:
            return base
        if index_entry is None and base not in self.local_songs:
            return base
        short = self.make_safe_song_name(song.title[:60])
        return self.make_safe_song_name(f"{short}_{song.song_id[-6:]}")
    # ------------------------------------------------------------------
    # 网络点歌客户端（搜索 / 取直链 / 下载）
    # ------------------------------------------------------------------

    def network_headers(self, with_json: bool = False) -> dict[str, str]:
        """构造请求头。

        服务端前面挂着 WAF，``User-Agent`` 必须是浏览器 UA，否则直接 403。
        配置了客户端标识时一并带上，让服务端按「客户端」而不是「IP」计配额。
        """
        headers = {
            "User-Agent": NETWORK_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }
        if with_json:
            headers["Content-Type"] = "application/json"
        client_id = str(self.cfg.get("网络点歌客户端标识") or "").strip()
        if client_id:
            headers["X-Client-Id"] = client_id
        return headers

    def network_api(
        self, path: str, payload: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """调用一次中转服务 JSON 接口：全局串行 + 限速 + 重试。

        Args:
            path: 以 ``/`` 开头的接口路径，或者完整 URL。
            payload: 非 None 时改用 POST 发送该 JSON。

        Returns:
            ``(响应字典, 错误文本)``；成功时错误文本为空串。

        Note:
            服务端用 429 表示「该作品今日下载次数已用完」，但响应体仍是
            合法 JSON（``error`` / ``used`` / ``limit``）。所以这里先解析
            JSON 再看状态码，好把这类业务错误原样翻译给玩家。
        """
        attempts = max(1, int(self.cfg["网络请求失败重试次数"]) + 1)
        timeout = max(1, int(self.cfg["网络请求超时秒数"]))
        interval = max(0.0, float(self.cfg["网络请求间隔秒数"]))
        url = path if path.startswith("http") else self.network_base + path
        is_post = payload is not None

        last_err = "未知错误"
        with self.network_lock:
            for attempt in range(attempts):
                wait = interval - (time.time() - self.network_last_request)
                if wait > 0:
                    time.sleep(wait)
                try:
                    if is_post:
                        response = self.requests.post(
                            url,
                            json=payload,
                            headers=self.network_headers(with_json=True),
                            timeout=timeout,
                            verify=False,
                            allow_redirects=True,
                        )
                    else:
                        response = self.requests.get(
                            url,
                            headers=self.network_headers(),
                            timeout=timeout,
                            verify=False,
                            allow_redirects=True,
                        )
                except Exception as err:
                    self.network_last_request = time.time()
                    last_err = f"{type(err).__name__}: {err}"
                else:
                    self.network_last_request = time.time()
                    try:
                        data = response.json()
                    except ValueError:
                        data = None
                    if isinstance(data, dict):
                        return data, ""
                    last_err = f"HTTP {response.status_code}"
                    # 4xx 是调用方问题（参数 / 配额 / UA），重试没有意义
                    if 400 <= response.status_code < 500:
                        return None, last_err
                if attempt + 1 < attempts:
                    time.sleep(min(max(interval, 0.5), 3.0))
        self.print_err(f"网络请求失败 {url} -> {last_err}")
        return None, last_err

    def network_get_bytes(self, url: str) -> bytes | None:
        """按签名直链取文件字节。

        ``?t=`` 签名只有 15 分钟且绑定客户端，拿到就该立刻用掉。

        Args:
            url: ``/api/fetch`` 返回的完整直链。

        Returns:
            文件内容；失败返回 None。
        """
        timeout = max(1, int(self.cfg["网络请求超时秒数"]))
        # ?t= 签名绑定客户端：这里必须与 /api/fetch 用同一套请求头，
        # 否则配置了「网络点歌客户端标识」时直链会直接 403。
        try:
            response = self.requests.get(
                url,
                headers=self.network_headers(),
                timeout=timeout,
                verify=False,
                allow_redirects=True,
            )
        except Exception as err:
            self.print_err(f"下载失败 {url} -> {type(err).__name__}: {err}")
            return None
        if response.status_code != 200:
            self.print_err(f"下载失败 {url} -> HTTP {response.status_code}")
            return None
        return response.content

    def network_search(self, keyword: str) -> list[NetworkSong]:
        """在 MIDI 中转服务上搜索曲目。

        Args:
            keyword: 搜索关键词。

        Returns:
            搜索结果列表；失败返回空列表。
        """
        path = "/api/search?q=" + urllib.parse.quote(keyword) + "&page=1"
        data, err = self.network_api(path)
        if data is None:
            self.print_err(f"搜索失败 {keyword} -> {err}")
            return []
        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            self.print_err(f"搜索返回结构异常: {str(data)[:200]}")
            return []
        songs: list[NetworkSong] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            song_id = str(item.get("id") or "").strip()
            if not song_id:
                continue
            songs.append(
                NetworkSong(
                    song_id=song_id,
                    title=str(item.get("title") or "").strip() or "未命名歌曲",
                    author=str(item.get("author") or "").strip(),
                    duration=str(item.get("duration") or "?") or "?",
                    downloads=int(item.get("downloads") or 0),
                    size_text=str(item.get("size") or ""),
                    tracks=int(item.get("tracks") or 0),
                )
            )
        return songs

    def network_fetch_url(self, song: NetworkSong) -> tuple[str, str]:
        """用作品 ID 换一次下载直链。

        Args:
            song: 玩家选中的曲目。

        Returns:
            ``(下载直链, 错误文本)``；成功时错误文本为空串。
        """
        data, err = self.network_api("/api/fetch", {"id": song.song_id})
        if data is None:
            return "", err
        url = str(data.get("url") or "").strip()
        if not url:
            return "", str(data.get("error") or "服务端未返回下载地址")
        if url.startswith("/"):
            url = self.network_base + url
        return url, ""

    def network_download(self, url: str) -> bytes | None:
        """下载曲目文件并校验 MIDI 头。

        Args:
            url: 服务端签发的签名直链。

        Returns:
            MIDI 二进制内容；失败返回 None。
        """
        data = self.network_get_bytes(url)
        if data is None:
            return None
        if data[:4] != b"MThd":
            self.print_err(f"下载内容不是 MIDI（前 8 字节 {data[:8]!r}）")
            return None
        return data

    def install_network_song(self, song: NetworkSong, data: bytes) -> str | None:
        """把下载到的 MIDI 落盘、转换、载入曲库并登记索引。

        Args:
            song: 已下载的曲目。
            data: MIDI 二进制内容。

        Returns:
            本地曲名；失败返回 None。
        """
        local_name = self.resolve_local_name(song)
        midi_path = os.path.join(self.music_dir, local_name + ".mid")
        seq_path = os.path.join(self.music_dir, local_name + ".midseq")
        try:
            with open(midi_path, "wb") as file:
                file.write(data)
            self.midiplayer.translate_midi_to_seq_file(midi_path, seq_path)
        except (Exception, SystemExit) as err:
            self.print_err(f"写入或转换下载的 MIDI 失败: {local_name} -> {err}")
            self.remove_file_quietly(midi_path)
            self.remove_file_quietly(seq_path)
            return None
        if not self.cfg["是否保留原始 MIDI"]:
            self.remove_file_quietly(midi_path)
        self.load_local_song_library()
        self.network_index[local_name] = {
            "id": song.song_id,
            "title": song.title,
        }
        self.save_network_index()
        return local_name

    def check_network_cooldown(self, player: Player) -> bool:
        """检查网络点歌冷却，通过则记录本次时间。

        Args:
            player: 发起点歌的玩家。

        Returns:
            允许继续则为 True。
        """
        cooldown = max(0, int(self.cfg["网络点歌冷却秒数"]))
        now = time.time()
        last = self.network_cooldowns.get(player.name)
        if cooldown > 0 and last is not None:
            remain = cooldown - (now - last)
            if remain > 0:
                self.show_warn(player, f"网络点歌冷却中，请 {int(remain) + 1} 秒后再试")
                return False
        self.network_cooldowns[player.name] = now
        return True

    def check_network_daily_limit(self, player: Player) -> bool:
        """检查并消耗当日网络点歌额度（在真正下载成功时调用）。

        Args:
            player: 发起点歌的玩家。

        Returns:
            未超限则为 True。
        """
        limit = max(0, int(self.cfg["网络点歌每日上限"]))
        if limit <= 0:
            return True
        today = time.strftime("%Y-%m-%d")
        record = self.network_daily.get(player.name)
        if record is None or record[0] != today:
            record = (today, 0)
        if record[1] >= limit:
            self.network_daily[player.name] = record
            self.show_warn(player, f"今天的网络点歌次数已用完（上限 {limit} 首）")
            return False
        self.network_daily[player.name] = (record[0], record[1] + 1)
        return True

    # ------------------------------------------------------------------
    # 网络点歌流程
    # ------------------------------------------------------------------
    def handle_network_song_menu(self, player: Player):
        """网络点歌入口：询问歌名后走中转服务搜索。"""
        # 这个菜单没有条目列表，标题下直接是页脚装饰线，
        # 所以不画顶部那条装饰线，否则两条线会紧挨着重复。
        player.show(
            self.menu_header("网络搜索点歌", with_rule=False)
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
        self.handle_network_search(player, keyword)

    def handle_network_search(self, player: Player, keyword: str):
        """搜索中转服务，展示结果并走下载播放流程。"""
        if not self.check_network_cooldown(player):
            return
        self.show_info(player, f"正在搜索 §f{keyword}§f …")
        results = self.network_search(keyword)
        if not results:
            self.show_error(player, f"没有搜到 §6{keyword}§c。")
            return
        selected = self.display_network_results(results, player, keyword)
        if selected is None:
            return
        self.download_and_play_network(player, selected)

    def display_network_results(
        self, results: list[NetworkSong], player: Player, keyword: str
    ) -> NetworkSong | None:
        """分页展示网络搜索结果并让玩家选一首。

        每个条目的时长与下载量固定用 §f 白色展示，标题用 §7 灰，
        这样一眼就能把「歌名」和「时长 / 下载量」分开。

        Args:
            results: 搜索结果。
            player: 选择的玩家。
            keyword: 关键词，仅用于标题展示。

        Returns:
            选中的曲目；退出或超时返回 None。
        """
        current_page = 0
        while True:
            page_items, current_page, total_pages = self.get_page_items(
                results, current_page, self.network_page_size
            )
            player.show(self.menu_header(f"网络搜索 - {keyword}"))
            for index, item in enumerate(page_items, start=1):
                player.show(
                    f"§l§b[ §e{index} §b] §f- §7{item.title}"
                    f" §8| §f时长 {item.duration}"
                    f" §8| §f下载 {item.downloads}"
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
            selected = self.select_indexed_item(player, response, page_items)
            if isinstance(selected, NetworkSong):
                return selected

    def download_and_play_network(self, player: Player, song: NetworkSong):
        """取直链 -> 下载 -> 入库 -> 为玩家播放。"""
        if not self.check_network_daily_limit(player):
            return
        self.show_info(player, f"正在获取 §f{song.title}§f 的下载地址 …")
        url, err = self.network_fetch_url(song)
        if not url:
            self.show_error(player, err or "获取下载地址失败，请稍后再试")
            return
        self.show_info(player, f"正在下载 §f{song.title}§f …")
        data = self.network_download(url)
        if data is None:
            self.show_error(player, "下载失败，请稍后再试")
            return
        local_name = self.install_network_song(song, data)
        if local_name is None:
            self.show_error(player, "曲子已下载但无法载入，可能是文件格式问题")
            return
        self.show_success(player, f"已存入曲库：§f「 §b{local_name} §f」")
        self.play_song_for_player(player, local_name)
        if self.cfg["播放时是否公告"]:
            self.game_ctrl.say_to("@a", f"§b{song.title} §7正在播放中")

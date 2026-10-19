"""私人点歌：已废弃的旧歌源链路（midishow 直连 + midi.fxdby.net）。

从 ``__init__.py`` 拆出，仅作留档与回滚参考，不参与任何调用路径。
"""

import base64
import os
import re
from dataclasses import dataclass

from tooldelta import Player


@dataclass
class SongSearchResult:
    """midishow 搜索结果条目（仅废弃链路使用）。"""

    title: str
    link: str
    download_count: str = "?"
    rating: str = "?"
    duration: str = "?"


class LegacyMixin:
    """已废弃的旧歌源方法集合，仅作留档与回滚参考。"""

    # ==================================================================
    # 废弃链路（LEGACY）：midishow 搜索 + midi.fxdby.net 下载
    #
    # 已废弃，不参与任何调用路径，仅作留档与回滚参考。
    # 废弃原因（2026-10-17 实测）：
    #   1. midi.fxdby.net/api/download_midi 返回 404，域名根是 MCSManager
    #      Daemon 默认页 —— 该第三方中转服务已下线；
    #   2. midishow 无公开 API，GET /midi/download?id= 要求登录且每首消耗
    #      3 积分（注册验证邮箱仅送 5 分）；
    #   3. midishow 全站 Cloudflare，连续约 5 次请求即 403 且 100 秒不恢复；
    #   4. 试听直链带短期 token，过期即 403，无法稳定复用。
    # 若上述服务将来恢复，可参考本分区低成本回滚（P0 修复已一并同步）。
    # ==================================================================
    def legacy_search_midishow(self, music_name: str, player: Player):
        """[废弃] 在 midishow 搜索曲目，返回 xpath 节点列表。"""
        search_url = "https://www.midishow.com/search/result"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.midishow.com/",
        }
        self.show_info(player, "正在搜索网络歌曲，请稍候…")
        try:
            response = self.requests.get(
                search_url,
                headers=headers,
                params={"q": music_name},
                verify=False,
                timeout=10,
            )
            response.raise_for_status()
        except Exception as err:
            self.show_error(player, f"搜索失败：{err}")
            return None
        tree = self.etree.HTML(response.text)
        return tree.xpath(
            '//div[@id="search-result"]'
            '/div/a[@class="d-block border-bottom pb-5 mb-5 position-relative"]'
        )

    @staticmethod
    def legacy_parse_search_result(node) -> SongSearchResult:
        """[废弃] 把 midishow 搜索结果节点解析成 SongSearchResult。"""
        title = (
            node.xpath(".//h3")[0].xpath("string()").strip()
            if node.xpath(".//h3")
            else "未知标题"
        )
        node_muted = node.xpath('.//div[@class="small text-muted"]')
        info_text = node_muted[0].xpath("string()").strip() if node_muted else ""
        node_file = node.xpath('.//div[@class="row small text-muted pl-0 pl-md-9"]')
        file_info = node_file[0].xpath("string()").strip() if node_file else ""
        download_match = re.search(r"(\d+)次下载", info_text)
        rating_match = re.search(r"(\d+\.\d+)\(\d+人打分\)", file_info)
        duration_match = re.search(r"(\d+:\d+)", file_info)
        return SongSearchResult(
            title=title,
            link=node.get("href") or "",
            download_count=download_match.group(1) if download_match else "?",
            rating=rating_match.group(1) if rating_match else "?",
            duration=duration_match.group(1) if duration_match else "?",
        )

    def legacy_display_search_results(
        self, music_items: list, player: Player, keyword: str
    ):
        """[废弃] 分页展示 midishow 搜索结果并让玩家选择。"""
        if not music_items:
            self.show_error(player, "没有找到相关歌曲")
            return None
        current_page = 0
        while True:
            page_items, current_page, total_pages = self.get_page_items(
                music_items, current_page, self.page_size
            )
            player.show(self.menu_header(f"网络搜索点歌 - 搜索: {keyword}"))
            for index, node in enumerate(page_items, start=1):
                item = self.legacy_parse_search_result(node)
                player.show(
                    f"§l§b[ §e{index} §b] §f- §7{item.title} "
                    f"§8(下载:{item.download_count} 评分:{item.rating} "
                    f"时长:{item.duration})"
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
            if selected is not None:
                return selected

    def legacy_download_from_fxdby(self, selected_link: str):
        """[废弃] 调 midi.fxdby.net 中转接口下载 MIDI（该服务已 404）。"""
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

    def legacy_process_downloaded_midi(
        self, api_data: dict, fallback_title: str, player: Player
    ) -> str | None:
        """[废弃] 解析 fxdby 返回的 base64 MIDI 并落盘播放。"""
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
        except (Exception, SystemExit) as err:
            self.print_err(f"处理下载的 MIDI 失败: {err}")
            self.show_error(player, f"载入失败：{err}")
            return None
        if not self.cfg["是否保留原始 MIDI"]:
            self.remove_file_quietly(midi_path)
        self.load_local_song_library()
        self.show_success(player, f"网络歌曲已载入：§f「 §b{safe_title} §f」")
        return safe_title

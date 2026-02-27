from typing import TYPE_CHECKING
from tooldelta import utils, Plugin, Player, plugin_entry
import requests
import urllib3
import re
import base64

class DJTable(Plugin):
    author = "SuperScript & Zhonger-Yuansi"
    name = "点歌台"
    version = (1, 0, 0)

    MAX_SONGS_QUEUED = 6
    can_stop = False

    def __init__(self, frame):
        self.musics_list: list[tuple[str, Player]] = []
        super().__init__(frame)
        (self.data_path / "音乐列表").mkdir(exist_ok=True)

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        pip = self.GetPluginAPI("pip")
        if TYPE_CHECKING:
            from pip模块支持 import PipSupport
            pip: PipSupport
        pip.require({"lxml": "lxml"})
        
        global etree
        from lxml import etree # type: ignore
        
        self.midiplayer = self.GetPluginAPI("MIDI播放器")
        self.chatmenu = self.GetPluginAPI("聊天栏菜单")
        midi_names: list[str] = []
        if TYPE_CHECKING:
            from 前置_MIDI播放器 import ToolMidiMixer
            from 前置_聊天栏菜单 import ChatbarMenu

            self.midiplayer: ToolMidiMixer
            self.chatmenu: ChatbarMenu
        mdir = self.data_path / "音乐列表"
        for i in mdir.iterdir():
            if i.name.endswith(".mid"):
                self.midiplayer.translate_midi_to_seq_file(
                    str(i),
                    str(mdir / i.name.replace(".mid", ".midseq")),
                )
                i.unlink()
        for i in mdir.iterdir():
            if i.name.endswith(".midseq"):
                self.midiplayer.load_sound_seq_file(
                    str(i), i.name.replace(".midseq", "")
                )
                midi_names.append(i.name.replace(".midseq", ""))
        self.midis_list = midi_names
        

    def on_inject(self):
        self.game_ctrl.sendwocmd("/scoreboard objectives add song_point dummy 音乐点")
        self.game_ctrl.sendwocmd("/scoreboard players add @a song_point 0")
        self.chatmenu.add_new_trigger(
            ["点歌列表"], [], "查看点歌台点歌列表", self.lookup_songs_list
        )
        self.chatmenu.add_new_trigger(
            ["点歌"], [], "点歌", self.choose_menu
        )
        self.chatmenu.add_new_trigger(
            ["停止当前曲目"],
            [],
            "停止当前点歌曲目",
            self.force_stop_current,
            op_only=True,
        )
        self.choose_music_thread()


    
    def search_music(self, music_name, player):
        """搜索音乐并返回结果"""
        
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # 构建搜索 URL
        search_url = f"https://www.midishow.com/search/result?q={music_name}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Connection': 'keep-alive',
            'Host': 'www.midishow.com',
            'Referer': 'https://www.midishow.com/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'sec-ch-ua': '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        
        try:
            player.show("§e点歌§f>> §a正在搜索歌曲...")
            
            response = requests.get(search_url, headers=headers, verify=False, timeout=10)
            response.raise_for_status()
            
            # 解析 HTML 并提取音乐信息
            tree = etree.HTML(response.text)
            
            # 查找所有音乐项
            music_items = tree.xpath('//div[@id="search-result"]/div/a[@class="d-block border-bottom pb-5 mb-5 position-relative"]')
            
            return music_items
        except Exception as e:
            player.show(f"§e点歌§f>> §c搜索失败：{str(e)}")
            return None
    
    def display_search_results(self, music_items, player):
        """显示搜索结果并让玩家选择"""
        if not music_items:
            player.show("§e点歌§f>> §c网络搜索未找到相关歌曲")
            return None, None
        
        player.show("§e点歌§f>> §a网络搜索到以下结果：")
        
        # 提取并显示关键信息
        for i, item in enumerate(music_items[:10]):
            # 提取标题
            title = item.xpath('.//h3')[0].xpath('string()').strip() if item.xpath('.//h3') else "未知标题"
            
            # 提取信息（包含下载次数）
            info_text = item.xpath('.//div[@class="small text-muted"]')[0].xpath('string()').strip() if item.xpath('.//div[@class="small text-muted"]') else ""
            
            # 提取文件信息（包含打分、时长）
            file_info_text = item.xpath('.//div[@class="row small text-muted pl-0 pl-md-9"]')[0].xpath('string()').strip() if item.xpath('.//div[@class="row small text-muted pl-0 pl-md-9"]') else ""
            
            # 提取下载次数
            download_count = ""
            download_match = re.search(r'(\d+)次下载', info_text)
            if download_match:
                download_count = download_match.group(1)
            
            # 提取打分
            rating = ""
            rating_match = re.search(r'(\d+\.\d+)\(\d+人打分\)', file_info_text)
            if rating_match:
                rating = rating_match.group(1)
            
            # 提取时长
            duration = ""
            duration_match = re.search(r'(\d+:\d+)', file_info_text)
            if duration_match:
                duration = duration_match.group(1)
            
            # 显示简化信息
            player.show(f"§e点歌§f>> §b{i+1}. §f{title} §7[下载: {download_count}次, 评分: {rating}, 时长: {duration}]")
        
        # 让玩家选择
        resp = player.input(
            "§e点歌§f>> §a请输入序号选择歌曲，或输入'取消'退出：",
            timeout=300,
        )
        
        if resp is None:
            player.show("§e点歌§f>> §c操作超时")
            return None, None
        
        resp = resp.strip()
        if resp == "取消":
            player.show("§e点歌§f>> §7已取消操作")
            return None, None
        
        # 验证输入
        try:
            choice = int(resp)
            if 1 <= choice <= len(music_items[:10]):
                selected_item = music_items[choice-1]
                
                # 提取选中歌曲的标题
                selected_title = selected_item.xpath('.//h3')[0].xpath('string()').strip() if selected_item.xpath('.//h3') else "未知标题"
                
                player.show(f"§e点歌§f>> §a您选择了：{selected_title}")
                
                # 提取选中歌曲的链接
                selected_link = selected_item.get('href')
                if selected_link:
                    return selected_link, selected_title
                else:
                    player.show("§e点歌§f>> §c无法获取歌曲链接")
                    return None, None
            else:
                player.show("§e点歌§f>> §c选择无效，请输入正确的序号")
                return None, None
        except ValueError:
            player.show("§e点歌§f>> §c输入无效，请输入数字序号")
            return None, None
    
    def download_midi(self, selected_link, selected_title):
        """下载 MIDI 文件"""
        try:
            api_url = "https://midi.fxdby.net/api/download_midi"
            payload = {'url': selected_link}
            
            # 下载时无需 header
            api_response = requests.post(api_url, json=payload, verify=False, timeout=10)
            api_response.raise_for_status()
            
            # 解析响应
            api_data = api_response.json()
            return api_data
        except Exception as e:
            return None
    
    def process_midi(self, player, api_data, selected_title):
        """处理下载的 MIDI 文件"""

        
        message = api_data.get('message', '未知消息')
        player.show(f"§e点歌§f>> §a{message}")
        
        # 检查是否成功
        if api_data.get('success') and api_data.get('data', {}).get('file'):
            midi_file = api_data['data']['file']
            title = api_data['data'].get('title', selected_title)
            
            # 检查音乐点数
            try:
                if player.getScore("song_point") <= 0:
                    player.show("§e点歌§f>> §c音乐点数不足，点歌一次需消耗§e1§c点")
                    return False
            except Exception as e:
                player.show("§e点歌§f>> §c计分板项不存在或您在此计分板没有分数")
                self.print(f"搜索失败: {str(e)}")
                return False
            
            # 检查等待列表是否已满
            if len(self.musics_list) >= self.MAX_SONGS_QUEUED:
                self.game_ctrl.say_to("@a", "§e点歌§f>> §c等待列表已满，请等待这首歌播放完")
                return False
            
            # 保存 MIDI 文件到本地
            midi_file_path = self.data_path / "音乐列表" / f"{title}.mid"
            try:
                with open(midi_file_path, 'wb') as f:
                    f.write(base64.b64decode(midi_file))
            except Exception as e:
                self.print_err(f"保存 MIDI 文件失败: {e}")
                return False
            
            # 转换为 midseq 文件
            midseq_path = self.data_path / "音乐列表" / f"{title}.midseq"
            self.midiplayer.translate_midi_to_seq_file(str(midi_file_path), str(midseq_path))
            midi_file_path.unlink()
            
            # 加载到播放器
            self.midiplayer.load_sound_seq_file(str(midseq_path), title)
            
            # 添加到播放列表
            self.musics_list.append((title, player))
            player.show("§e点歌§f>> §a点歌成功， 消耗1点音乐点")
            self.game_ctrl.sendwocmd(
                f"scoreboard players remove @a[name=\"{player.safe_name}\"] song_point 1"
            )
            self.game_ctrl.say_to(
                "@a", f"§e点歌§f>> §e{player.name}§a成功点歌:{title}"
            )
            return True
        else:
            return False
    
    def display_local_songs(self, player: Player):
        """显示本地歌曲列表，支持翻页"""
        total_songs = len(self.midis_list)
        if total_songs == 0:
            player.show("§e点歌§f>> §c本地仓库中没有歌曲")
            return None
        
        page_size = 15
        total_pages = (total_songs + page_size - 1) // page_size
        current_page = 1
        
        while True:
            # 计算当前页的歌曲范围
            start_idx = (current_page - 1) * page_size
            end_idx = min(start_idx + page_size, total_songs)
            page_songs = self.midis_list[start_idx:end_idx]
            
            # 显示当前页的歌曲
            player.show(f"§e点歌§f>> §a本地仓库 (第 {current_page}/{total_pages} 页):")
            for i, song in enumerate(page_songs, start=start_idx + 1):
                player.show(f"§e点歌§f>> §b{i}. §f{song}")
            
            # 显示操作选项（固定序号）
            player.show("§e点歌§f>> §a操作选项：")
            if current_page > 1:
                player.show("§e点歌§f>> §b16. §f上一页")
            if current_page < total_pages:
                player.show("§e点歌§f>> §b17. §f下一页")
            player.show("§e点歌§f>> §b18. §f取消")
            
            # 让玩家输入序号
            resp = player.input(
                "§e点歌§f>> §a请输入歌曲序号或操作序号：",
                timeout=300,
            )
            
            if resp is None:
                player.show("§c操作超时")
                return None
            resp = resp.strip()
            
            try:
                choice = int(resp)
                if 1 <= choice <= total_songs:
                    # 选择了歌曲
                    selected_song = self.midis_list[choice - 1]
                    player.show(f"§e点歌§f>> §a您选择了：{selected_song}")
                    return selected_song
                elif choice == 16 and current_page > 1:
                    # 上一页
                    current_page -= 1
                elif choice == 17 and current_page < total_pages:
                    # 下一页
                    current_page += 1
                elif choice == 18:
                    # 取消
                    player.show("§e点歌§f>> §7已取消操作")
                    return None
                else:
                    player.show("§e点歌§f>> §c输入的序号超出范围")
            except ValueError:
                player.show("§e点歌§f>> §c输入无效，请输入数字序号")
    
    def choose_menu(self, player: Player, args: tuple):
        """点歌菜单主函数"""
        # 询问玩家选择来源
        resp = player.input(
            "§e点歌§f>> §a请选择歌曲来源：\n§b1. §f本地仓库\n§b2. §f网络源 - 来源于 MidiShow\n§b3. §f取消",
            timeout=300,
        )
        if resp is None:
            player.show("§c操作超时")
            return
        resp = resp.strip()
        
        # 处理玩家选择
        if resp == "3" or resp == "取消":
            player.show("§e点歌§f>> §7已取消操作")
            return
        elif resp == "1":
            # 本地仓库
            selected_song = self.display_local_songs(player)
            if not selected_song:
                return
            music_name = selected_song
        elif resp == "2":
            # 网络源
            resp = player.input(
                "§a请输入您要点的歌曲曲目名称：",
                timeout=300,
            )
            if resp is None:
                player.show("§c操作超时")
                return
            music_name = resp.strip()
            if not music_name:
                player.show("§c曲目名称不能为空")
                return
            
            # 打印输入的曲目给玩家
            player.show(f"§e点歌§f>> §a您输入的曲目是：{music_name}")
            
            # 直接从网络搜索，不检查本地
            player.show("§e点歌§f>> §a正在从网络搜索...(需要花费较长时间)")
            
            try:
                # 搜索音乐
                music_items = self.search_music(music_name, player)
                if not music_items:
                    return
                
                # 显示搜索结果并让玩家选择
                selected_link, selected_title = self.display_search_results(music_items, player)
                if not selected_link or not selected_title:
                    return
                
                # 下载 MIDI 文件
                api_data = self.download_midi(selected_link, selected_title)
                if not api_data:
                    player.show(f"§e点歌§f>> §c下载失败")
                    return
                
                # 处理 MIDI 文件
                self.process_midi(player, api_data, selected_title)
                
            except Exception as e:
                self.print(f"搜索失败: {e}")
                player.show("§e点歌§f>> §c网络搜索失败，请检查网络连接或曲目名称")
            return
        else:
            player.show("§e点歌§f>> §c选择无效，请输入正确的序号")
            return
        
        # 检查音乐点数
        try:
            if player.getScore("song_point") <= 0:
                player.show("§e点歌§f>> §c音乐点数不足，点歌一次需消耗§e1§c点")
                return
        except Exception as e:
            player.show("§e点歌§f>> §c计分板项不存在或您在此计分板没有分数")
            self.print(f"搜索失败: {str(e)}")
            return
        
        # 检查等待列表是否已满
        if len(self.musics_list) >= self.MAX_SONGS_QUEUED:
            self.game_ctrl.say_to("@a", "§e点歌§f>> §c等待列表已满，请等待这首歌播放完")
            return
        
        # 减少音乐点数并添加到播放队列
        self.musics_list.append((music_name, player))
        player.show("§e点歌§f>> §a点歌成功， 消耗1点音乐点")
        self.game_ctrl.sendwocmd(
            f"scoreboard players remove @a[name=\"{player.safe_name}\"] song_point 1"
        )
        self.game_ctrl.say_to(
            "@a", f"§e点歌§f>> §e{player.name}§a成功点歌:{music_name}"
        )

    def lookup_songs_list(self, player: Player, _):
        if not self.musics_list == []:
            player.show("§b◎§e当前点歌♬等待列表:")
            for i, j in enumerate(self.musics_list):
                player.show(f"§a{i + 1}§f. {j[0]} §7点歌: {j[1]}")
        else:
            player.show("§a♬§f列表空空如也啦! ")

    def force_stop_current(self, player, _):
        if self.can_stop:
            self.main_thread.stop()
            self.game_ctrl.say_to("@a", "§e点歌§f>> §6管理员已停止当前点歌曲目")
        else:
            player.show("§e点歌§f>> §6当前没有在播放曲目啦！")

    def play_music(self, song_name, player: Player):
        self.game_ctrl.say_to(
            "@a",
            f"§e点歌§f>> §7开始播放§f{song_name}§7，点歌者:§f{player.name}",
        )
        try:
            self.midiplayer.playsound_at_target_sync(song_name, "@a")
        except SystemExit:
            self.game_ctrl.say_to("@a", "§e点歌§f>> §7准备播放下一首")
        if self.musics_list == []:
            self.game_ctrl.say_to("@a", "§e点歌§f>> §7点歌列表已空!")
        self.can_stop = False

    @utils.timer_event(10, "点歌台切歌")
    def choose_music_thread(self):
        if self.musics_list != [] and not self.can_stop:
            self.can_stop = True
            song_name, player = self.musics_list.pop(0)
            self.main_thread = utils.createThread(
                self.play_music, args=(song_name, player)
            )

entry = plugin_entry(DJTable)

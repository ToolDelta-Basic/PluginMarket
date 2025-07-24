import os
from typing import TYPE_CHECKING
from GetFile import get_github_repo_files
from tooldelta import utils, Plugin, Player, plugin_entry


class DJTable(Plugin):
    author = "SuperScript & Zhonger-Yuansi"
    name = "点歌台"
    version = (0, 2, 5)
    MAX_SONGS_QUEUED = 6
    can_stop = False

    def __init__(self, frame):
        self.musics_list: list[tuple[str, Player]] = []
        super().__init__(frame)
        os.makedirs(self.data_path, exist_ok=True)
        os.makedirs(os.path.join(self.data_path, "音乐列表"), exist_ok=True)
        self.mdir_external = os.path.join(self.data_path, "远程缓存")
        os.makedirs(self.mdir_external, exist_ok=True)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)

    def on_def(self):
        self.midiplayer = self.GetPluginAPI("MIDI播放器")
        self.chatmenu = self.GetPluginAPI("聊天栏菜单")
        midi_names: list[str] = []
        if TYPE_CHECKING:
            from 前置_MIDI播放器 import ToolMidiMixer
            from 前置_聊天栏菜单 import ChatbarMenu

            self.midiplayer: ToolMidiMixer
            self.chatmenu: ChatbarMenu
        mdir = os.path.join(self.data_path, "音乐列表")
        for i in os.listdir(mdir):
            if i.endswith(".mid"):
                self.midiplayer.translate_midi_to_seq_file(
                    os.path.join(mdir, i),
                    os.path.join(mdir, i.replace(".mid", ".midseq")),
                )
                os.remove(os.path.join(mdir, i))
        for i in os.listdir(mdir):
            if i.endswith(".midseq"):
                self.midiplayer.load_sound_seq_file(
                    os.path.join(mdir, i), i.replace(".midseq", "")
                )
                midi_names.append(i.replace(".midseq", ""))
        self.midis_list = midi_names
        self.repo_url = "Zhonger-Yuansi/Midi-Repositories"
        try:
            repo_url = self.repo_url
            remote_data = get_github_repo_files(repo_url)
            original_list, self.repo_message = remote_data
            self.remote_midis_list = [
                name for name in original_list if name.lower() != "message"
            ]
        except Exception:
            self.remote_midis_list = []
            self.repo_message = None

    def on_inject(self):
        self.game_ctrl.sendwocmd("/scoreboard objectives add song_point dummy 音乐点")
        self.game_ctrl.sendwocmd("/scoreboard players add @a song_point 0")
        self.chatmenu.add_new_trigger(
            ["点歌列表"], [], "查看点歌台点歌列表", self.lookup_songs_list
        )
        self.chatmenu.add_new_trigger(
            ["点歌"], [("歌名", str, "")], "点歌", self.choose_menu
        )
        self.chatmenu.add_new_trigger(
            ["停止当前曲目"],
            [],
            "停止当前点歌曲目",
            self.force_stop_current,
            op_only=True,
        )
        self.choose_music_thread()

    def on_player_join(self, player: Player):
        self.game_ctrl.sendcmd("/scoreboard players add @a song_point 0")

    def choose_menu(self, player: Player, args: tuple):
        song_list = self.midis_list
        choose_song_name: str = args[0]
        if choose_song_name == "":
            total_songs = len(song_list)
            total_remote = len(getattr(self, "remote_midis_list", []))
            if total_songs == 0 and total_remote == 0:
                player.show("§6曲目列表空空如也...")
                return

            combined_list = song_list + getattr(self, "remote_midis_list", [])
            page_size = 10
            max_page = (len(combined_list) + page_size - 1) // page_size
            current_page = 0

            while True:
                start = current_page * page_size
                end = start + page_size
                page_songs = combined_list[start:end]

                player.show(f"§a当前曲目列表 (第 {current_page + 1} / {max_page} 页)：")
                for i, j in enumerate(page_songs):
                    index = start + i + 1
                    is_remote = index > len(song_list)
                    suffix = " §7(远程)" if is_remote else ""
                    player.show(f" §b{index} §f{j}{suffix}")

                if hasattr(self, "repo_message"):
                    if self.repo_message:
                        player.show(f"§7远程仓库: {self.repo_message}")
                    else:
                        player.show("§7远程仓库: 当前暂无公告内容")

                resp = player.input("§a请输入序号选择曲目 \n§e+ §f下一页\n§e- §f上一页\n§e退出 §f退出菜单", timeout=300)
                if resp is None:
                    player.show("§c操作超时")
                    return
                resp = resp.strip()
                if resp == "+":
                    current_page = min(current_page + 1, max_page - 1)
                    continue
                elif resp == "-":
                    current_page = max(current_page - 1, 0)
                    continue
                elif resp == "退出":
                    player.show("§7已退出点歌菜单")
                    return

                if (resp_int := utils.try_int(resp)) is None:
                    player.show("§c选项无效")
                    continue

                total_options = len(combined_list)
                if resp_int < 1 or resp_int > total_options:
                    player.show("§c选项不在范围内")
                    continue

                if resp_int <= len(song_list):
                    music_name = song_list[resp_int - 1].removesuffix(".midseq")
                else:
                    remote_index = resp_int - len(song_list) - 1
                    music_name = self.remote_midis_list[remote_index]
                    if player.getScore("song_point") <= 0:
                        player.show("§e点歌§f>> §c音乐点数不足，点歌一次需消耗§e1§c点")
                    else:
                        self.game_ctrl.sendwocmd(
                            f"/scoreboard players remove {player.getSelector()} song_point 1")
                        player.show("§e点歌§f>> §7正在下载并处理远程曲目，消耗1点音乐，请稍候...")
                        self._download_process(player, music_name)
                    return
                break
        else:
            for song_name in song_list:
                if song_name.removesuffix(".midseq") == choose_song_name:
                    music_name = song_name.removesuffix(".midseq")
                    break
            else:
                player.show("§c没有找到音乐")
                return

        if len(self.musics_list) >= self.MAX_SONGS_QUEUED:
            self.game_ctrl.say_to("@a", "§e点歌§f>> §c等待列表已满，请等待这首歌播放完")
        elif player.getScore("song_point") <= 0:
            player.show("§e点歌§f>> §c音乐点数不足，点歌一次需消耗§e1§c点")
        else:
            self.musics_list.append((music_name, player))
            player.show("§e点歌§f>> §a点歌成功， 消耗1点音乐点")
            self.game_ctrl.sendwocmd(
                f"/scoreboard players remove {player.getSelector()} song_point 1"
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

    def _download_process(self, player: Player, music_name: str, **kwargs):
        """下载远程音乐并完成转换及播放入队"""
        try:
            import requests
            from urllib3.exceptions import InsecureRequestWarning

            #requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

            """
            
            清空外部缓存文件夹
            可能这会给面板带来一点流量占用
            但是MIDI仓库的主人不一定获取到MIDI作者的授权
            所以这一步至关重要

            """
            for file in os.listdir(self.mdir_external):
                try:
                    os.remove(os.path.join(self.mdir_external, file))
                except Exception as e:
                    pass

            url = f"https://ghproxy.net/https://raw.githubusercontent.com/{self.repo_url}/main/{music_name}.mid"
            response = requests.get(url)

            if response.status_code == 200:
                midi_path = os.path.join(self.mdir_external, f"{music_name}.mid")
                with open(midi_path, "wb") as file:
                    file.write(response.content)

            midseq_path = os.path.join(self.mdir_external, f"{music_name}.midseq")
            self.midiplayer.translate_midi_to_seq_file(midi_path, midseq_path)
            os.remove(midi_path)

            self.midiplayer.load_sound_seq_file(midseq_path, music_name)
            self.musics_list.append((music_name, player))
            player.show("§e点歌§f>> §a远程曲目已加入播放队列！")

        except Exception as e:
            # self.logger.error(f"处理远程音乐异常: {e}")
            player.show(f"§c处理远程曲目失败: {str(e)}")

entry = plugin_entry(DJTable)

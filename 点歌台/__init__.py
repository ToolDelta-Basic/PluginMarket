import os
import time
from typing import TYPE_CHECKING

from tooldelta import Builtins, Plugin, plugins
from tooldelta.frame import ToolDelta
from tooldelta.game_utils import getScore


@plugins.add_plugin
class DJTable(Plugin):
    author = "Sup3rScr1pt"
    name = "点歌台"
    version = (0, 1, 4)

    musics_list = []
    MAX_SONGS_QUEUED = 6
    can_stop = None

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        os.makedirs(self.data_path, exist_ok=True)
        os.makedirs(os.path.join(self.data_path, "音乐列表"), exist_ok=True)

    def on_def(self):
        self.midiplayer = plugins.get_plugin_api("MIDI播放器")
        self.chatmenu = plugins.get_plugin_api("聊天栏菜单")
        if TYPE_CHECKING:
            from 前置_MIDI播放器 import ToolMidiMixer
            from 前置_聊天栏菜单 import ChatbarMenu

            self.midiplayer = plugins.instant_plugin_api(ToolMidiMixer)
            self.chatmenu = plugins.instant_plugin_api(ChatbarMenu)
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

    def on_inject(self):
        self.game_ctrl.sendcmd("/scoreboard objectives add song_point dummy 音乐点")
        self.game_ctrl.sendcmd("/scoreboard players add @a song_point 0")
        self.main_thread = Builtins.createThread(self.choose_music_thread)
        self.chatmenu.add_trigger(
            ["点歌列表"], None, "查看点歌台点歌列表", self.lookup_songs_list
        )
        self.chatmenu.add_trigger(
            ["点歌"], "[歌名]", "点歌", self.choose_menu, lambda x: x > 0
        )
        self.chatmenu.add_trigger(
            ["停止当前曲目"],
            None,
            "停止当前点歌曲目",
            self.force_stop_current,
            op_only=True,
        )

    def on_player_join(self, _):
        self.game_ctrl.sendcmd("/scoreboard players add @a song_point 0")

    def choose_menu(self, player: str, args: list[str]):
        music_name = " ".join(args).replace(".midseq", "")
        music_path = os.path.join(self.data_path, "音乐列表", (music_name + ".midseq"))
        if not os.path.isfile(music_path):
            self.game_ctrl.say_to("@a", "§e点歌§f>> §c此音乐未被收录")
        elif len(self.musics_list) >= self.MAX_SONGS_QUEUED:
            self.game_ctrl.say_to("@a", "§e点歌§f>> §c等待列表已满，请等待这首歌播放完")
        elif getScore("song_point", player) <= 0:
            self.game_ctrl.say_to(
                player, "§e点歌§f>> §c音乐点数不足，点歌一次需消耗§e1§c点"
            )
        else:
            self.musics_list.append((music_name, player))
            self.game_ctrl.say_to(player, "§e点歌§f>> §a点歌成功，消耗1点音乐点")
            self.game_ctrl.sendwocmd(
                f"/scoreboard players remove {player} song_point 1"
            )
            self.game_ctrl.say_to(
                "@a", "§e点歌§f>> §e%s§a成功点歌:%s" % (player, music_name)
            )

    def lookup_songs_list(self, player: str, _):
        if not self.musics_list == []:
            self.game_ctrl.say_to(player, "§b◎§e当前点歌♬等待列表:")
            for i, j in enumerate(self.musics_list):
                self.game_ctrl.say_to(
                    player, "§a%d§f. %s §7点歌: %s" % (i + 1, j[0], j)
                )
        else:
            self.game_ctrl.say_to(player, "§a♬§f列表空空如也啦! ")

    def force_stop_current(self, player, _):
        if self.can_stop:
            self.main_thread.stop()
            self.game_ctrl.say_to("@a", "§e点歌§f>> §6管理员已停止当前点歌曲目")
        else:
            self.game_ctrl.say_to(player, "§e点歌§f>> §6当前没有在播放曲目啦！")

    def choose_music_thread(self):
        counter = 0
        while 1:
            time.sleep(1)
            counter += 1
            if counter > 4:
                if self.musics_list != []:
                    self.can_stop = True
                    music_data = self.musics_list.pop(0)
                    self.game_ctrl.say_to(
                        "@a",
                        "§e点歌§f>> §7开始播放§f%s§7，点歌者:§f%s"
                        % (music_data[0], music_data[1]),
                    )
                    try:
                        self.midiplayer.playsound_at_target_sync(music_data[0], "@a")
                    except SystemExit:
                        self.game_ctrl.say_to("@a", "§e点歌§f>> §7下一首")
                    if self.musics_list == []:
                        self.game_ctrl.say_to("@a", "§e点歌§f>> §7点歌列表已空!")
                else:
                    self.can_stop = False

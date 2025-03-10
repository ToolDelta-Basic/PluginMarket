import os
from typing import TYPE_CHECKING, ClassVar
from tooldelta import utils, Plugin, Player, plugin_entry

from tooldelta.game_utils import getScore, waitMsg


class DJTable(Plugin):
    author = "Sup3rScr1pt"
    name = "点歌台"
    version = (0, 1, 7)

    musics_list: ClassVar[list] = []
    MAX_SONGS_QUEUED = 6
    can_stop = False

    def __init__(self, frame):
        super().__init__(frame)
        os.makedirs(self.data_path, exist_ok=True)
        os.makedirs(os.path.join(self.data_path, "音乐列表"), exist_ok=True)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)

    def on_def(self):
        self.midiplayer = self.GetPluginAPI("MIDI播放器")
        self.chatmenu = self.GetPluginAPI("聊天栏菜单")
        midi_names = []
        if TYPE_CHECKING:
            from 前置_MIDI播放器 import ToolMidiMixer
            from 前置_聊天栏菜单 import ChatbarMenu

            self.midiplayer = self.get_typecheck_plugin_api(ToolMidiMixer)
            self.chatmenu = self.get_typecheck_plugin_api(ChatbarMenu)
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

    def on_inject(self):
        self.game_ctrl.sendcmd("/scoreboard objectives add song_point dummy 音乐点")
        self.game_ctrl.sendcmd("/scoreboard players add @a song_point 0")
        self.chatmenu.add_trigger(
            ["点歌列表"], None, "查看点歌台点歌列表", self.lookup_songs_list
        )
        self.chatmenu.add_trigger(["点歌"], "", "点歌", self.choose_menu)
        self.chatmenu.add_trigger(
            ["停止当前曲目"],
            None,
            "停止当前点歌曲目",
            self.force_stop_current,
            op_only=True,
        )
        self.choose_music_thread()

    def on_player_join(self, player: Player):
        _ = player.name
        self.game_ctrl.sendcmd("/scoreboard players add @a song_point 0")

    def choose_menu(self, player: str, _):
        song_list = self.midis_list
        if song_list == []:
            self.game_ctrl.say_to(player, "§6曲目列表空空如也...")
            return
        self.game_ctrl.say_to(player, "§a当前曲目列表：")
        for i, j in enumerate(song_list):
            self.game_ctrl.say_to(player, f" §b{i + 1} §f{j}")
        self.game_ctrl.say_to(player, "§a请输入序号选择曲目：")
        if (resp := utils.try_int(waitMsg(player))) is None:
            self.game_ctrl.say_to(player, "§c选项无效")
            return
        elif resp not in range(1, len(song_list) + 1):
            self.game_ctrl.say_to(player, "§c选项不在范围内")
            return
        music_name = song_list[resp - 1].replace(".midseq", "")
        if len(self.musics_list) >= self.MAX_SONGS_QUEUED:
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
            self.game_ctrl.say_to("@a", f"§e点歌§f>> §e{player}§a成功点歌:{music_name}")

    def lookup_songs_list(self, player: str, _):
        if not self.musics_list == []:
            self.game_ctrl.say_to(player, "§b◎§e当前点歌♬等待列表:")
            for i, j in enumerate(self.musics_list):
                self.game_ctrl.say_to(player, f"§a{i + 1}§f. {j[0]} §7点歌: {j[1]}")
        else:
            self.game_ctrl.say_to(player, "§a♬§f列表空空如也啦! ")

    def force_stop_current(self, player, _):
        if self.can_stop:
            self.main_thread.stop()
            self.game_ctrl.say_to("@a", "§e点歌§f>> §6管理员已停止当前点歌曲目")
        else:
            self.game_ctrl.say_to(player, "§e点歌§f>> §6当前没有在播放曲目啦！")

    def play_music(self, song_name, player):
        self.game_ctrl.say_to(
            "@a",
            f"§e点歌§f>> §7开始播放§f{song_name}§7，点歌者:§f{player}",
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

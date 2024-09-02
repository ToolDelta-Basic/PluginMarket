import os
import time
import tooldelta
import tooldelta.game_utils
from dataclasses import dataclass


@dataclass
class PlayerMusicStatus:
    name: str
    now: float
    duration: float
    is_stop: bool
    thread: tooldelta.Utils.ToolDeltaThread


@tooldelta.plugins.add_plugin
class MusicPlayer(tooldelta.Plugin):
    name = "音乐播放器"
    author = "SuperScript"
    version = (0, 0, 10)

    def __init__(self, frame: tooldelta.ToolDelta):
        super().__init__(frame)
        CFG_DEFAULT = {
            "音乐播放条格式": "§e[歌曲名] §f[当前播放时长] §7/ [总播放时长] [播放符号]\n[播放条]",
            "限制最大的音乐同时播放数": 4,
            "播放音乐、暂停和继续播放的触发词": [
                "music play",
                "播放",
                "music pause",
                "暂停",
            ],
            "停止播放的触发词": ["music stop", "停止播放"],
            "查询曲目列表触发词": ["music list", "音乐列表"],
            "是否仅OP可播放音乐": False,
        }
        CFG_STD = tooldelta.Config.auto_to_std(CFG_DEFAULT)
        self.cfg, _ = tooldelta.Config.get_plugin_config_and_version(
            self.name, CFG_STD, CFG_DEFAULT, self.version
        )
        _ = self.data_path
        self.thread_num = 0
        self.players_thread: dict[str, PlayerMusicStatus] = {}
        self.public_showbar_thread_awaked = False
        self.fmt = self.cfg["音乐播放条格式"]
        os.makedirs(os.path.join(self.data_path, "midi_backup"), exist_ok=True)

    def on_def(self):
        self.midiplayer = tooldelta.plugins.get_plugin_api("MIDI播放器", (0, 2, 5))
        self.chatbar = tooldelta.plugins.get_plugin_api("聊天栏菜单", (0, 2, 3))
        self.song_list = []
        if tooldelta.TYPE_CHECKING:
            from 前置_MIDI播放器 import ToolMidiMixer
            from 前置_聊天栏菜单 import ChatbarMenu

            self.midiplayer = tooldelta.plugins.instant_plugin_api(ToolMidiMixer)
            self.chatbar = tooldelta.plugins.instant_plugin_api(ChatbarMenu)
        for i in os.listdir(self.data_path):
            if i.endswith(".mid"):
                self.midiplayer.translate_midi_to_seq_file(
                    os.path.join(self.data_path, i),
                    os.path.join(self.data_path, i.replace(".mid", ".midseq")),
                )
                new_dir = os.path.join(self.data_path, "midi_backup", i)
                if not os.path.isfile(new_dir):
                    os.rename(os.path.join(self.data_path, i), new_dir)
        for i in os.listdir(self.data_path):
            if i.endswith(".midseq"):
                name = i.replace(".midseq", "")
                self.midiplayer.load_sound_seq_file(
                    os.path.join(self.data_path, i), name
                )
                self.song_list.append(name)

    def on_inject(self):
        self.chatbar.add_trigger(
            self.cfg["播放音乐、暂停和继续播放的触发词"],
            None,
            "播放歌曲， 或停止或继续播放音乐",
            self.play_music_menu,
            op_only=self.cfg["是否仅OP可播放音乐"],
        )
        self.chatbar.add_trigger(
            self.cfg["停止播放的触发词"],
            "[曲目名]",
            "播放歌曲或停止或继续播放音乐",
            self.stop_song,
            op_only=self.cfg["是否仅OP可播放音乐"],
        )
        self.chatbar.add_trigger(
            self.cfg["查询曲目列表触发词"],
            "[曲目名]",
            "播放歌曲或停止或继续播放音乐",
            self.list_songs,
        )

    def list_songs(self, player: str, _):
        self.game_ctrl.say_to(player, "§e♬ §d曲目列表：")
        if self.song_list == []:
            self.game_ctrl.say_to(player, "  §7空空如也...")
            self.game_ctrl.say_to(
                player, "  §7将MIDI音乐文件放入 §f插件数据文件/音乐播放器 §7文件夹中吧"
            )
            return
        for i, name in enumerate(self.song_list):
            self.game_ctrl.say_to(player, f" §f{i + 1} §7- §f{name}")

    def play_music_menu(self, player: str, args: list[str]):
        if player in self.players_thread.keys():
            self.pause_or_play(player)
        else:
            if self.song_list == []:
                self.game_ctrl.say_to(player, "§6曲目列表空空如也...")
                return
            self.game_ctrl.say_to(player, "§a当前曲目列表：")
            for i, j in enumerate(self.song_list):
                self.game_ctrl.say_to(player, f" §b{i+1} §f{j}")
            self.game_ctrl.say_to(player, "§a请输入序号选择曲目：")
            if (resp := tooldelta.Utils.try_int(tooldelta.game_utils.waitMsg(player))) is None:
                self.game_ctrl.say_to(player, "§c选项无效")
                return
            elif resp not in range(1, len(self.song_list) + 1):
                self.game_ctrl.say_to(player, "§c选项不在范围内")
                return
            song_name = self.song_list[resp - 1]
            if self.thread_num > self.cfg["限制最大的音乐同时播放数"]:
                self.game_ctrl.say_to(player, "§c目前游戏内同时播放音乐数达上限")
            elif self.players_thread.get(player):
                self.game_ctrl.say_to(player, "§c你正在播放音乐, 请停止")
            else:
                status = PlayerMusicStatus(
                    song_name,
                    0,
                    self.midiplayer.midi_seqs[song_name].duration,
                    False,
                    None,  # type: ignore
                )
                thread = tooldelta.Utils.ToolDeltaThread(
                    self.playmusic_thread, (player, song_name, status)
                )
                status.thread = thread
                self.players_thread[player] = status
            self.wake_showbar_thread()

    def stop_song(self, player: str, _):
        if not self.players_thread.get(player):
            self.game_ctrl.say_to(player, "§c当前你没有正在播放的音乐")
        else:
            self.players_thread[player].thread.stop()
            del self.players_thread[player]

    def pause_or_play(self, player: str):
        if not self.players_thread.get(player):
            self.game_ctrl.say_to(player, "§c当前你没有正在播放的音乐")
        else:
            self.players_thread[player].is_stop = not self.players_thread[
                player
            ].is_stop

    def playmusic_thread(self, target: str, music_name: str, parent: PlayerMusicStatus):
        scmd = self.game_ctrl.sendwocmd
        self.thread_num += 1
        now_play = 0
        parent.duration = self.midiplayer.midi_seqs[music_name].duration
        try:
            for instrument, vol, pitch, delay in self.midiplayer.iter_playsound(
                music_name
            ):
                time.sleep(delay)
                scmd(
                    f"/execute as {target} at @s run playsound {instrument} @s ~~~ {vol} {pitch}"
                )
                print(vol)
                now_play += delay
                parent.now = now_play
                if parent.is_stop:
                    while parent.is_stop:
                        ...
        finally:
            self.thread_num -= 1
            if target in self.players_thread.keys():
                del self.players_thread[target]

    def make_playbar(self, current, total):
        TOTAL_BAR = 30
        prg = int(TOTAL_BAR * current / total)
        return "§b" + "=" * prg + "§f§l|§r§f" + "=" * (TOTAL_BAR - prg)

    def wake_showbar_thread(self):
        if not self.public_showbar_thread_awaked:
            self.public_showbar_thread()

    def format_time(self, sec: float):
        sec = int(sec)
        return "%.2d:%.2d" % (sec // 60, sec % 60)

    @tooldelta.Utils.thread_func("音乐播放器显示播放模块")
    def public_showbar_thread(self):
        self.public_showbar_thread_awaked = True
        while self.players_thread:
            for player, status in self.players_thread.items():
                self.game_ctrl.player_actionbar(
                    player,
                    tooldelta.Utils.SimpleFmt(
                        {
                            "[歌曲名]": status.name,
                            "[播放符号]": ("∥", "▶")[status.is_stop],
                            "[当前播放时长]": self.format_time(status.now),
                            "[总播放时长]": self.format_time(status.duration),
                            "[播放条]": self.make_playbar(status.now, status.duration),
                        },
                        self.fmt,
                    ),
                )
            time.sleep(1)
        self.public_showbar_thread_awaked = False

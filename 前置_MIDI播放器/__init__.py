import time
import os
from typing import ClassVar
import Musicreater
from Musicreater.constants import MM_INSTRUMENT_DEVIATION_TABLE
from tooldelta import Plugin, utils, fmts, plugin_entry


# API 名: MIDI播放器
def seq_chunk_split(s: bytes, chunk_size: int = 4):
    res = []
    while s != b"":
        res.append(s[:chunk_size])
        s = s[chunk_size:]
    return res


def read_midi_and_dump_to_seq(midipath: str):
    mid = Musicreater.MidiConvert.from_midi_file(midipath)
    lst = mid.to_sequence()
    return ToolSoundSequence(lst)


class ToolSoundSequence:
    def __init__(self, seq: bytes | list):
        if isinstance(seq, bytes):
            try:
                instruments_bt, noteseq = seq.split(b"SEQ:\x00")
                instruments_bts = instruments_bt.split(b"\xff")
                instruments = [i.decode("ascii") for i in instruments_bts]
                self.instruments = instruments
                self.noteseq = noteseq
                self._duration = 0
            except IndexError:
                raise Exception("解码失败: 音符表错误")
        elif isinstance(seq, list):
            instrument_indexes: list[str] = []
            bt = b""
            newb = []
            duration = 0
            for instrument, vol, pitch, delay_ticks in seq:
                if instrument not in instrument_indexes:
                    instrument_indexes.append(instrument)
                    duration += delay_ticks / 20
                instrument_index = instrument_indexes.index(instrument)
                if pitch < 0:
                    pitch = 0
                if pitch not in range(256):
                    fmts.print_err(
                        f"音高超出转换预期: {pitch} (当前乐器: {instrument})"
                    )
                # 有些音符间隔很长
                while delay_ticks >= 256:
                    newb.append(bytes([instrument_index, 0, 60, min(delay_ticks, 255)]))
                    delay_ticks -= 255
                newb.append(
                    bytes([instrument_index, vol, pitch, min(delay_ticks, 127)])
                )
            bt += b"\xfe".join(newb)
            self.instruments = instrument_indexes
            self.noteseq = bt
            self._duration = duration

    def __iter__(self):
        seq = self.noteseq
        instruments = self.instruments
        for ind in seq.split(b"\xfe"):
            instrument_index, volume, note_pitch_shift, note_delay = ind
            instrument: str = instruments[instrument_index]
            pitch_modifier = MM_INSTRUMENT_DEVIATION_TABLE.get(instrument)
            if pitch_modifier is None:
                pitch_modifier = 6
                fmts.print_war(f"modifier: instrument {instrument} is invalid")
            pitch_resized = note_pitch_shift - pitch_modifier
            vol = volume / 100
            pitch = (
                1
                if instrument in ("note.snare", "note.bd", "note.hat")
                else 2 ** ((pitch_resized - 60) / 12)
            )
            delay = note_delay
            yield instrument, vol, pitch, delay

    @property
    def duration(self):
        if self._duration == 0:
            duration = 0
            for i in self.noteseq.split(b"\xfe"):
                duration += i[3] / 20
            self._duration = duration
        return self._duration

    def dump_seq(self):
        instruments = self.instruments
        bt = b"\xff".join(i.encode("ascii") for i in instruments)
        bt += b"SEQ:\x00" + self.noteseq
        return bt


class ToolMidiMixer(Plugin):
    author = "SuperScript"
    name = "库-MIDI播放器"
    version = (0, 2, 7)
    midi_seqs: ClassVar[dict[str, ToolSoundSequence]] = {}
    playsound_threads: ClassVar[dict[int, utils.createThread]] = {}
    _id_counter = 0

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.on_inject)

    # ---------------- API ---------------------
    def load_midi_file(self, path: str, as_name: str):
        "读取MIDI文件并解析为序列载入(慢)."
        self.midi_seqs[as_name] = read_midi_and_dump_to_seq(path)

    def load_sound_seq_file(self, path: str, as_name: str):
        "读取ToolSound声音文件解析为序列载入(快)."
        with open(path, "rb") as f:
            try:
                self.midi_seqs[as_name] = ToolSoundSequence(f.read())
            except Exception as err:
                fmts.print_err(f"读取音乐序列 {path} 失败: {err}")
                raise SystemExit

    def translate_midi_to_seq_file(self, path: str, path1: str):
        "将MIDI文件转换为ToolSound序列文件."
        try:
            seq = read_midi_and_dump_to_seq(path)
        except Exception as err:
            import traceback

            traceback.print_exc()
            fmts.print_err(f"转换音乐 {path} 失败: {err}")
            raise SystemExit
        with open(path1, "wb") as f:
            f.write(seq.dump_seq())

    def read_midi_file_to_sequence(self, path: str):
        "读取MIDI序列文件, 将其转换为序列并返回"
        try:
            return read_midi_and_dump_to_seq(path)
        except Exception as err:
            fmts.print_err(f"转换音乐 {path} 失败: {err}")
            raise SystemExit

    def playsound_at_target(self, name_or_seq: str | ToolSoundSequence, target: str):
        "创建播放器线程并返回线程ID, 失败则返回0, 以便使用 stop_playing() 停止线程"
        self._id_counter += 1
        if isinstance(name_or_seq, str) and name_or_seq not in self.midi_seqs.keys():
            return 0
        self.playsound_threads[self._id_counter] = utils.createThread(
            self._playsound_at_target_thread, (name_or_seq, target, self._id_counter)
        )
        return self._id_counter

    def stop_playing(self, idc: int):
        "终止播放器播放线程"
        thr = self.playsound_threads.get(idc)
        if thr is not None:
            thr.stop()
            return True
        return False

    def playsound_at_target_sync(
        self, name_or_seq: str | ToolSoundSequence, target: str
    ):
        if isinstance(name_or_seq, ToolSoundSequence):
            seq = name_or_seq
        else:
            seq = self.midi_seqs[name_or_seq]
        scmd = self.game_ctrl.sendwocmd
        for instrument, vol, pitch, delay in seq:
            time.sleep(delay / 20)
            scmd(
                f"/execute as {target} at @s run playsound {instrument} @s ~~~ {vol} {pitch}"
            )

    def iter_playsound(self, name_or_seq: str | ToolSoundSequence):
        """
        获取一个音乐播放遍历器
        Args:
            name_or_seq (str | ToolSoundSequence): 已导入的音乐名或音乐序列
        Yields:
            Iterator (str, float, float, float): 返回遍历器, 包括乐器类型, 音量, 音高, 延迟(s)
        """
        if isinstance(name_or_seq, ToolSoundSequence):
            seq = name_or_seq
        else:
            seq = self.midi_seqs[name_or_seq]
        for instrument, vol, pitch, delay in seq:
            yield instrument, vol, pitch, delay / 20

    # ------------------------------------------
    def _playsound_at_target_thread(
        self, name_or_seq: str | ToolSoundSequence, target: str, idc: int
    ):
        if isinstance(name_or_seq, ToolSoundSequence):
            seq = name_or_seq
        else:
            seq = self.midi_seqs[name_or_seq]
        scmd = self.game_ctrl.sendwocmd
        try:
            for instrument, vol, pitch, delay in seq:
                time.sleep(delay / 20)
                scmd(
                    f"/execute as {target} at @s run playsound {instrument} @s ~~~ {vol} {pitch}"
                )
        finally:
            del self.playsound_threads[idc]

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["播放测试"], None, "测试声乐合成器", self.play_test
        )
        self.frame.add_console_cmd_trigger(
            ["停止所有播放"], None, "停止正在播放的所有音乐", self.stop_all
        )

    def play_test(self, *_):
        for i in os.listdir():
            if i.endswith(".mid"):
                fmts.print_suc(f"已找到用于示例播放的midi文件: {i}")
                self.load_midi_file(i, "example")
                fmts.print_suc(f"开始播放: {i}")
                self.playsound_at_target("example", "@a")
                break
        else:
            fmts.print_war(
                "没有找到用于示例播放的任何midi文件(ToolDelta目录下), 已忽略"
            )

    def stop_all(self, *_):
        for k in self.playsound_threads.copy().keys():
            res = self.stop_playing(k)
            fmts.print_inf(f"停止音乐 {k} 的播放: " + ["失败", "成功"][res] + ".")


entry = plugin_entry(ToolMidiMixer, "MIDI播放器")

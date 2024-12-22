# -*- coding: utf-8 -*-


"""
音·创 (Musicreater)
一款免费开源的针对《我的世界》音乐的支持库
Musicreater (音·创)
A free open source library used for **Minecraft** musics.

版权所有 © 2024 音·创 开发者
Copyright © 2024 all the developers of Musicreater

开源相关声明请见 仓库根目录下的 License.md
Terms & Conditions: License.md in the root directory
"""

# 音·创 开发交流群 861684859
# Email TriM-Organization@hotmail.com
# 若需转载或借鉴 许可声明请查看仓库根目录下的 License.md


# BUG退散！BUG退散！                  BUG退散！BUG退散！                   BUG retreat! BUG retreat!
# 异常与错误作乱之时                   異常、誤りが、困った時は               Abnormalities and errors are causing chaos
# 二六字组！万国码合！二六字组！万国码合！ グループ！コード＃！グループ！コード＃！  Words combine! Unicode unite!
# 赶快呼叫 程序员！Let's Go！          直ぐに呼びましょプログラマ レッツゴー！  Hurry to call the programmer! Let's Go!

import math
import os

import mido

from .constants import *
from .exceptions import *
from .subclass import *
from .types import *
from .utils import *

"""
学习笔记：
tempo:  microseconds per quarter note 毫秒每四分音符，换句话说就是一拍占多少毫秒
tick:  midi帧
ticks_per_beat:  帧每拍，即一拍多少帧

那么：

tick / ticks_per_beat => amount_of_beats 拍数(四分音符数)

tempo * amount_of_beats => 毫秒数

所以：

tempo * tick / ticks_per_beat => 毫秒数

###########

seconds per tick:
(tempo / 1000000.0) / ticks_per_beat

seconds:
tick * tempo / 1000000.0 / ticks_per_beat

microseconds:
tick * tempo / 1000.0 / ticks_per_beat

gameticks:
tick * tempo / 1000000.0 / ticks_per_beat * 一秒多少游戏刻


"""


@dataclass(init=False)
class MusicSequence:
    """
    音乐曲谱序列存储类
    """

    music_name: str
    """乐曲名"""

    channels: MineNoteChannelType
    """频道信息字典"""

    total_note_count: int
    """音符总数"""

    note_count_per_instrument: Dict[str, int]
    """所使用的乐器"""

    minimum_volume: float
    """乐曲最小音量"""

    music_deviation: float
    """全曲音调偏移"""

    def __init__(
        self,
        name_of_music: str,
        channels_of_notes: MineNoteChannelType,
        music_note_count: Optional[int] = None,
        note_used_per_instrument: Optional[Dict[str, int]] = None,
        minimum_volume_of_music: float = 0.1,
        deviation_value: Optional[float] = None,
    ) -> None:
        """
        音符序列类

        Paramaters
        ==========
        name_of_music: str
            乐曲名称
        channels_of_notes: MineNoteChannelType
            音乐音轨
        music_note_count: int
            总音符数
        note_used_per_instrument: Dict[str, int]
            全曲乐器使用统计
        minimum_volume_of_music: float
            音乐最小音量(0,1]
        deviation_value: float
            全曲音调偏移值
        """

        if minimum_volume_of_music > 1 or minimum_volume_of_music <= 0:
            raise IllegalMinimumVolumeError(
                "自订的最小音量参数错误：{}，应在 (0,1] 范围内。".format(
                    minimum_volume_of_music
                )
            )
        # max_volume = 1 if max_volume > 1 else (0.001 if max_volume <= 0 else max_volume)

        self.music_name = name_of_music
        self.channels = channels_of_notes
        self.minimum_volume = minimum_volume_of_music

        if (note_used_per_instrument is None) or (music_note_count is None):
            kp = [i.sound_name for j in self.channels.values() for i in j]
            self.total_note_count = (
                len(kp) if music_note_count is None else music_note_count
            )
            self.note_count_per_instrument = (
                dict([(it, kp.count(it)) for it in set(kp)])
                if note_used_per_instrument is None
                else note_used_per_instrument
            )
        else:
            self.total_note_count = music_note_count
            self.note_count_per_instrument = note_used_per_instrument

        self.music_deviation = 0 if deviation_value is None else deviation_value

    @classmethod
    def from_mido(
        cls,
        mido_file: mido.MidiFile,
        midi_music_name: str,
        mismatch_error_ignorance: bool = True,
        speed_multiplier: float = 1,
        default_tempo: int = mido.midifiles.midifiles.DEFAULT_TEMPO,
        pitched_note_referance_table: MidiInstrumentTableType = MM_TOUCH_PITCHED_INSTRUMENT_TABLE,
        percussion_note_referance_table: MidiInstrumentTableType = MM_TOUCH_PERCUSSION_INSTRUMENT_TABLE,
        minimum_vol: float = 0.1,
        volume_processing_function: FittingFunctionType = natural_curve,
        deviation: float = 0,
    ):
        """
        自mido对象导入一个音符序列类

        Paramaters
        ==========
        mido_file: mido.MidiFile 对象
            需要处理的midi对象
        midi_music_name: str
            音乐名称
        mismatch_error_ignorance bool
            是否在导入时忽略音符不匹配错误
        speed_multiplier: float
            音乐播放速度倍数
        default_tempo: int
            默认的MIDI TEMPO值
        pitched_note_referance_table: Dict[int, Tuple[str, int]]
            乐音乐器Midi-MC对照表
        percussion_note_referance_table: Dict[int, Tuple[str, int]]
            打击乐器Midi-MC对照表
        minimum_vol: float
            播放的最小音量 应为 (0,1] 范围内的小数
        volume_processing_function: Callable[[float], float]
            声像偏移拟合函数
        deviation: float
            全曲音调偏移值
        """
        (
            note_channels,
            note_count_total,
            inst_note_count,
        ) = cls.to_music_note_channels(
            midi=mido_file,
            speed=speed_multiplier,
            pitched_note_rtable=pitched_note_referance_table,
            percussion_note_rtable=percussion_note_referance_table,
            default_tempo_value=default_tempo,
            vol_processing_function=volume_processing_function,
            ignore_mismatch_error=mismatch_error_ignorance,
        )
        return cls(
            name_of_music=midi_music_name,
            channels_of_notes=note_channels,
            music_note_count=note_count_total,
            note_used_per_instrument=inst_note_count,
            minimum_volume_of_music=minimum_vol,
            deviation_value=deviation,
        )

    @classmethod
    def load_decode(
        cls,
        bytes_buffer_in: bytes,
    ):
        """从字节码导入音乐序列"""

        group_1 = int.from_bytes(bytes_buffer_in[4:6], "big")
        music_name_ = bytes_buffer_in[8 : (stt_index := 8 + (group_1 >> 10))].decode(
            "utf-8"
        )
        channels_: MineNoteChannelType = empty_midi_channels(staff=[])
        for channel_index in channels_.keys():
            for i in range(
                int.from_bytes(
                    bytes_buffer_in[stt_index : (stt_index := stt_index + 4)], "big"
                )
            ):
                try:
                    end_index = stt_index + 14 + (bytes_buffer_in[stt_index] >> 2)
                    channels_[channel_index].append(
                        MineNote.decode(bytes_buffer_in[stt_index:end_index])
                    )
                    stt_index = end_index
                except:
                    print(channels_)
                    raise

        return cls(
            name_of_music=music_name_,
            channels_of_notes=channels_,
            minimum_volume_of_music=(group_1 & 0b1111111111) / 1000,
            deviation_value=int.from_bytes(bytes_buffer_in[6:8], "big", signed=True)
            / 1000,
        )

    def encode_dump(
        self,
    ) -> bytes:
        """将音乐序列转为二进制字节码"""

        # 音乐名称长度 6 位 支持到 63
        # 最小音量 minimum_volume 10 位 最大支持 1023 即三位小数
        # 共 16 位 合 2 字节
        # +++
        # 总音调偏移 music_deviation 16 位 最大支持 -32768 ~ 32767 即 三位小数
        # 共 16 位 合 2 字节
        # +++
        # 音乐名称 music_name 长度最多63 支持到 21 个中文字符 或 63 个西文字符
        bytes_buffer = (
            b"MSQ#"
            + (
                (len(r := self.music_name.encode("utf-8")) << 10)
                + round(self.minimum_volume * 1000)
            ).to_bytes(2, "big")
            + round(self.music_deviation * 1000).to_bytes(2, "big", signed=True)
            + r
        )

        for channel_index, note_list in self.channels.items():
            bytes_buffer += len(note_list).to_bytes(4, "big")
            for note_ in note_list:
                bytes_buffer += note_.encode()

        return bytes_buffer

    def set_min_volume(self, volume_value: int):
        """重新设置全曲最小音量"""
        if volume_value > 1 or volume_value <= 0:
            raise IllegalMinimumVolumeError(
                "自订的最小音量参数错误：{}，应在 (0,1] 范围内。".format(volume_value)
            )
        self.minimum_volume = volume_value

    def set_deviation(self, deviation_value: int):
        """重新设置全曲音调偏移"""
        self.music_deviation = deviation_value

    def rename_music(self, new_name: str):
        """重命名此音乐"""
        self.music_name = new_name

    def add_note(self, channel_no: int, note: MineNote, is_sort: bool = False):
        """在指定通道添加一个音符"""
        self.channels[channel_no].append(note)
        self.total_note_count += 1
        if note.sound_name in self.note_count_per_instrument.keys():
            self.note_count_per_instrument[note.sound_name] += 1
        else:
            self.note_count_per_instrument[note.sound_name] = 1
        if is_sort:
            self.channels[channel_no].sort(key=lambda note: note.start_tick)

    @staticmethod
    def guess_deviation_wasted(
        total_note_count: int,
        total_instrument_count: int,
        note_count_per_instrument: Optional[Dict[str, int]] = None,
        qualified_note_count_per_instrument: Optional[Dict[str, int]] = None,
        music_channels: Optional[MineNoteChannelType] = None,
    ) -> float:
        """已废弃"""
        if (
            note_count_per_instrument is None
            or qualified_note_count_per_instrument is None
        ):
            if music_channels is None:
                raise ValueError("参数不足，算逑！")
            note_count_per_instrument = {}
            qualified_note_count_per_instrument = {}
            for this_note in [k for j in music_channels.values() for k in j]:
                if this_note.sound_name in note_count_per_instrument.keys():
                    note_count_per_instrument[this_note.sound_name] += 1
                    qualified_note_count_per_instrument[this_note.sound_name] += (
                        is_note_in_diapason(this_note)
                    )
                else:
                    note_count_per_instrument[this_note.sound_name] = 1
                    qualified_note_count_per_instrument[this_note.sound_name] = int(
                        is_note_in_diapason(this_note)
                    )
        return (
            sum(
                [
                    (
                        (
                            MM_INSTRUMENT_RANGE_TABLE[inst][-1]
                            * note_count
                            / total_note_count
                            - MM_INSTRUMENT_RANGE_TABLE[inst][-1]
                        )
                        * (note_count - qualified_note_count_per_instrument[inst])
                    )
                    for inst, note_count in note_count_per_instrument.items()
                ]
            )
            / total_instrument_count
            / total_note_count
        )

    @staticmethod
    def to_music_note_channels(
        midi: mido.MidiFile,
        ignore_mismatch_error: bool = True,
        speed: float = 1.0,
        default_tempo_value: int = mido.midifiles.midifiles.DEFAULT_TEMPO,
        pitched_note_rtable: MidiInstrumentTableType = MM_TOUCH_PITCHED_INSTRUMENT_TABLE,
        percussion_note_rtable: MidiInstrumentTableType = MM_TOUCH_PERCUSSION_INSTRUMENT_TABLE,
        vol_processing_function: FittingFunctionType = natural_curve,
    ) -> Tuple[MineNoteChannelType, int, Dict[str, int]]:
        """
        将midi解析并转换为频道音符字典

        Parameters
        ----------
        midi: mido.MidiFile 对象
            需要处理的midi对象
        ignore_mismatch_error： bool
            是否在导入时忽略音符不匹配错误
        speed: float
            音乐播放速度倍数
        default_tempo_value: int
            默认的MIDI TEMPO值
        pitched_note_rtable: Dict[int, Tuple[str, int]]
            乐音乐器Midi-MC对照表
        percussion_note_rtable: Dict[int, Tuple[str, int]]
            打击乐器Midi-MC对照表
        vol_processing_function: Callable[[float], float]
            声像偏移拟合函数

        Returns
        -------
        以频道作为分割的Midi音符列表字典, 音符总数, 乐器使用统计:
        Tuple[MineNoteChannelType, int, Dict[str, int]]
        """

        if speed == 0:
            raise ZeroSpeedError("播放速度为 0 ，其需要(0,1]范围内的实数。")

        # 一个midi中仅有16个通道 我们通过通道来识别而不是音轨
        midi_channels: MineNoteChannelType = empty_midi_channels(staff=[])
        tempo = default_tempo_value
        note_count = 0
        note_count_per_instrument: Dict[str, int] = {}

        # 我们来用通道统计音乐信息
        # 但是是用分轨的思路的
        for track_no, track in enumerate(midi.tracks):
            microseconds = 0
            if not track:
                continue

            note_queue_A: Dict[
                int,
                List[
                    Tuple[
                        int,
                        int,
                    ]
                ],
            ] = empty_midi_channels(staff=[])
            note_queue_B: Dict[
                int,
                List[
                    Tuple[
                        int,
                        int,
                    ]
                ],
            ] = empty_midi_channels(staff=[])

            channel_program: Dict[int, int] = empty_midi_channels(staff=-1)

            for msg in track:
                if msg.time != 0:
                    microseconds += msg.time * tempo / midi.ticks_per_beat / 1000

                if msg.is_meta:
                    if msg.type == "set_tempo":
                        tempo = msg.tempo
                else:
                    if msg.type == "program_change":
                        channel_program[msg.channel] = msg.program

                    elif msg.type == "note_on" and msg.velocity != 0:
                        note_queue_A[msg.channel].append(
                            (msg.note, channel_program[msg.channel])
                        )
                        note_queue_B[msg.channel].append((msg.velocity, microseconds))

                    elif (msg.type == "note_off") or (
                        msg.type == "note_on" and msg.velocity == 0
                    ):
                        if (msg.note, channel_program[msg.channel]) in note_queue_A[
                            msg.channel
                        ]:
                            _velocity, _ms = note_queue_B[msg.channel][
                                note_queue_A[msg.channel].index(
                                    (msg.note, channel_program[msg.channel])
                                )
                            ]
                            note_queue_A[msg.channel].remove(
                                (msg.note, channel_program[msg.channel])
                            )
                            note_queue_B[msg.channel].remove((_velocity, _ms))

                            midi_channels[msg.channel].append(
                                that_note := midi_msgs_to_minenote(
                                    inst_=(
                                        msg.note
                                        if msg.channel == 9
                                        else channel_program[msg.channel]
                                    ),
                                    note_=(
                                        channel_program[msg.channel]
                                        if msg.channel == 9
                                        else msg.note
                                    ),
                                    velocity_=_velocity,
                                    start_time_=_ms,
                                    duration_=microseconds - _ms,
                                    track_no_=track_no,
                                    percussive_=(msg.channel == 9),
                                    play_speed=speed,
                                    midi_reference_table=(
                                        percussion_note_rtable
                                        if msg.channel == 9
                                        else pitched_note_rtable
                                    ),
                                    volume_processing_method_=vol_processing_function,
                                )
                            )
                            note_count += 1
                            if that_note.sound_name in note_count_per_instrument.keys():
                                note_count_per_instrument[that_note.sound_name] += 1
                            else:
                                note_count_per_instrument[that_note.sound_name] = 1
                        else:
                            if ignore_mismatch_error:
                                pass
                                # print(
                                #    "[WARRING] MIDI格式错误 音符不匹配 {} 无法在上文中找到与之匹配的音符开音消息".format(
                                #        msg
                                #    )
                                # )
                            else:
                                raise NoteOnOffMismatchError(
                                    "当前的MIDI很可能有损坏之嫌……",
                                    msg,
                                    "无法在上文中找到与之匹配的音符开音消息。",
                                )

        """整合后的音乐通道格式
        每个通道包括若干消息元素其中逃不过这三种：

        1 切换乐器消息
        ("PgmC", 切换后的乐器ID: int, 距离演奏开始的毫秒)

        2 音符开始消息
        ("NoteS", 开始的音符ID, 力度（响度）, 距离演奏开始的毫秒)

        3 音符结束消息
        ("NoteE", 结束的音符ID, 距离演奏开始的毫秒)"""
        del tempo
        channels = dict(
            [
                (channel_no, sorted(channel_notes, key=lambda note: note.start_tick))
                for channel_no, channel_notes in midi_channels.items()
            ]
        )

        return (
            channels,
            note_count,
            note_count_per_instrument,
        )


class MidiConvert(MusicSequence):
    """
    将Midi文件转换为我的世界内容
    """

    enable_old_exe_format: bool
    """是否启用旧版execute指令格式"""

    execute_cmd_head: str
    """execute指令头部"""

    music_command_list: List[MineCommand]
    """音乐指令列表"""

    progress_bar_command: List[MineCommand]
    """进度条指令列表"""

    @classmethod
    def from_mido_obj(
        cls,
        midi_obj: mido.MidiFile,
        midi_name: str,
        ignore_mismatch_error: bool = True,
        playment_speed: float = 1,
        default_tempo_value: int = mido.midifiles.midifiles.DEFAULT_TEMPO,
        pitched_note_rtable: MidiInstrumentTableType = MM_TOUCH_PITCHED_INSTRUMENT_TABLE,
        percussion_note_rtable: MidiInstrumentTableType = MM_TOUCH_PERCUSSION_INSTRUMENT_TABLE,
        enable_old_exe_format: bool = False,
        minimum_volume: float = 0.1,
        vol_processing_function: FittingFunctionType = natural_curve,
    ):
        """
        简单的midi转换类，将midi对象转换为我的世界结构或者包

        Parameters
        ----------
        midi_obj: mido.MidiFile 对象
            需要处理的midi对象
        midi_name: str
            此音乐之名称
        ignore_mismatch_error： bool
            是否在导入时忽略音符不匹配错误
        playment_speed: float
            音乐播放速度倍数
        default_tempo_value: int
            默认的MIDI TEMPO值
        pitched_note_rtable: Dict[int, Tuple[str, int]]
            乐音乐器Midi-MC对照表
        percussion_note_rtable: Dict[int, Tuple[str, int]]
            打击乐器Midi-MC对照表
        enable_old_exe_format: bool
            是否启用旧版(≤1.19)指令格式，默认为否
        minimum_volume: float
            最小播放音量
        vol_processing_function: Callable[[float], float]
            声像偏移拟合函数
        """

        cls.enable_old_exe_format: bool = enable_old_exe_format

        cls.execute_cmd_head = (
            "execute {} ~ ~ ~ "
            if enable_old_exe_format
            else "execute as {} at @s positioned ~ ~ ~ run "
        )

        cls.progress_bar_command = cls.music_command_list = []
        cls.channels = {}

        return cls.from_mido(
            mido_file=midi_obj,
            midi_music_name=midi_name,
            speed_multiplier=playment_speed,
            pitched_note_referance_table=pitched_note_rtable,
            percussion_note_referance_table=percussion_note_rtable,
            minimum_vol=minimum_volume,
            volume_processing_function=vol_processing_function,
            default_tempo=default_tempo_value,
            mismatch_error_ignorance=ignore_mismatch_error,
        )

    @classmethod
    def from_midi_file(
        cls,
        midi_file_path: str,
        mismatch_error_ignorance: bool = True,
        play_speed: float = 1,
        default_tempo: int = mido.midifiles.midifiles.DEFAULT_TEMPO,
        pitched_note_table: MidiInstrumentTableType = MM_TOUCH_PITCHED_INSTRUMENT_TABLE,
        percussion_note_table: MidiInstrumentTableType = MM_TOUCH_PERCUSSION_INSTRUMENT_TABLE,
        old_exe_format: bool = False,
        min_volume: float = 0.1,
        vol_processing_func: FittingFunctionType = natural_curve,
    ):
        """
        直接输入文件地址，将midi文件读入

        Parameters
        ----------
        midi_file_path: str
            midi文件地址
        mismatch_error_ignorance bool
            是否在导入时忽略音符不匹配错误
        play_speed: float
            音乐播放速度倍数
        default_tempo: int
            默认的MIDI TEMPO值
        pitched_note_table: Dict[int, Tuple[str, int]]
            乐音乐器Midi-MC对照表
        percussion_note_table: Dict[int, Tuple[str, int]]
            打击乐器Midi-MC对照表
        old_exe_format: bool
            是否启用旧版(≤1.19)指令格式，默认为否
        min_volume: float
            最小播放音量
        vol_processing_func: Callable[[float], float]
            声像偏移拟合函数
        """

        midi_music_name = os.path.splitext(os.path.basename(midi_file_path))[0].replace(
            " ", "_"
        )
        """文件名，不含路径且不含后缀"""

        try:
            return cls.from_mido_obj(
                midi_obj=mido.MidiFile(
                    midi_file_path,
                    clip=True,
                ),
                midi_name=midi_music_name,
                ignore_mismatch_error=mismatch_error_ignorance,
                playment_speed=play_speed,
                default_tempo_value=default_tempo,
                pitched_note_rtable=pitched_note_table,
                percussion_note_rtable=percussion_note_table,
                enable_old_exe_format=old_exe_format,
                minimum_volume=min_volume,
                vol_processing_function=vol_processing_func,
            )
        except (ValueError, TypeError) as E:
            raise MidiDestroyedError(f"文件{midi_file_path}可能损坏：{E}")
        except FileNotFoundError as E:
            raise FileNotFoundError(f"文件{midi_file_path}不存在：{E}")

    def to_sequence(self):
        "Created by ToolDelta"
        notes_list: List[MineNote] = sorted(
            [i for j in self.channels.values() for i in j],
            key=lambda note: note.start_tick,
        )
        res_list: list[tuple[str, int, int, int]] = []
        delaytime_previous = 0
        for note in notes_list:
            tickdelay = note.start_tick - delaytime_previous
            delaytime_previous = note.start_tick
            # 响度 / 127
            # 音调 2 ** (f1 / 12)
            res_list.append(
                (
                    note.sound_name,
                    round(note.velocity / 127 * 100),
                    note.note_pitch,
                    tickdelay,
                )
            )
        return res_list

    def copy_important(self):
        dst = MidiConvert.from_mido_obj(
            midi_obj=mido.MidiFile(),
            midi_name=self.music_name,
            enable_old_exe_format=self.enable_old_exe_format,
            pitched_note_rtable={},
            percussion_note_rtable={},
            vol_processing_function=lambda a: a,
        )
        dst.music_command_list = [i.copy() for i in self.music_command_list]
        dst.progress_bar_command = [i.copy() for i in self.progress_bar_command]
        return dst

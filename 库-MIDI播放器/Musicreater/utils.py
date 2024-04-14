# -*- coding: utf-8 -*-
"""
存放主程序所必须的功能性内容
"""

"""
版权所有 © 2024 音·创 开发者
Copyright © 2024 all the developers of Musicreater

开源相关声明请见 仓库根目录下的 License.md
Terms & Conditions: License.md in the root directory
"""

# 睿乐组织 开发交流群 861684859
# Email TriM-Organization@hotmail.com
# 若需转载或借鉴 许可声明请查看仓库目录下的 License.md

import math
import random

from .constants import (
    MC_INSTRUMENT_BLOCKS_TABLE,
    MM_INSTRUMENT_DEVIATION_TABLE,
    MC_PITCHED_INSTRUMENT_LIST,
    MM_INSTRUMENT_RANGE_TABLE,
)
from .subclass import SingleNote, MineNote

from .types import (
    Any,
    Dict,
    Tuple,
    Optional,
    Callable,
    Literal,
    Union,
    MidiInstrumentTableType,
)


def mctick2timestr(mc_tick: int) -> str:
    """
    将《我的世界》的游戏刻计转为表示时间的字符串
    """
    return str(int(int(mc_tick / 20) / 60)) + ":" + str(int(int(mc_tick / 20) % 60))


def empty_midi_channels(channel_count: int = 17, staff: Any = {}) -> Dict[int, Any]:
    """
    空MIDI通道字典
    """

    return dict(
        (
            i,
            (staff.copy() if isinstance(staff, (dict, list)) else staff),
        )  # 这告诉我们，你不能忽略任何一个复制的序列，因为它真的，我哭死，折磨我一整天，全在这个bug上了
        for i in range(channel_count)
    )


def inst_to_sould_with_deviation(
    instrumentID: int,
    reference_table: MidiInstrumentTableType,
    default_instrument: str = "note.flute",
) -> Tuple[str, int]:
    """
    返回midi的乐器ID对应的我的世界乐器名，对于音域转换算法，如下：
    2**( ( msg.note - 60 - X ) / 12 ) 即为MC的音高

    Parameters
    ----------
    instrumentID: int
        midi的乐器ID
    reference_table: Dict[int, Tuple[str, int]]
        转换乐器参照表
    default_instrument: str
        查无此乐器时的替换乐器

    Returns
    -------
    tuple(str我的世界乐器名, int转换算法中的偏移量)
    """
    sound_id = midi_inst_to_mc_sound(
        instrumentID=instrumentID,
        reference_table=reference_table,
        default_instrument=default_instrument,
    )
    return sound_id, MM_INSTRUMENT_DEVIATION_TABLE.get(
        sound_id,
        MM_INSTRUMENT_DEVIATION_TABLE.get(
            default_instrument, 6 if sound_id in MC_PITCHED_INSTRUMENT_LIST else -1
        ),
    )


def midi_inst_to_mc_sound(
    instrumentID: int,
    reference_table: MidiInstrumentTableType,
    default_instrument: str = "note.flute",
) -> str:
    """
    返回midi的乐器ID对应的我的世界乐器名

    Parameters
    ----------
    instrumentID: int
        midi的乐器ID
    reference_table: Dict[int, Tuple[str, int]]
        转换乐器参照表
    default_instrument: str
        查无此乐器时的替换乐器

    Returns
    -------
    str我的世界乐器名
    """
    return reference_table.get(
        instrumentID,
        default_instrument,
    )


def natural_curve(
    vol: float,
) -> float:
    """
    midi力度值拟合成的距离函数

    Parameters
    ----------
    vol: int
        midi音符力度值

    Returns
    -------
    float播放中心到玩家的距离
    """
    return (
        -8.081720684086314
        * math.log(
            vol + 14.579508825070013,
        )
        + 37.65806375944386
        if vol < 60.64
        else 0.2721359356095803 * ((vol + 2592.272889454798) ** 1.358571233418649)
        + -6.313841334963396 * (vol + 2592.272889454798)
        + 4558.496367823575
    )


def straight_line(vol: float) -> float:
    """
    midi力度值拟合成的距离函数

    Parameters
    ----------
    vol: int
        midi音符力度值

    Returns
    -------
    float播放中心到玩家的距离
    """
    return vol / -8 + 16


def minenote_to_command_paramaters(
    note_: MineNote,
    pitch_deviation: float = 0,
) -> Tuple[
    str,
    Tuple[float, float, float],
    float,
    Union[float, Literal[None]],
]:
    """
    将MineNote对象转为《我的世界》音符播放所需之参数
    :param note_:MineNote 音符对象
    :param deviation:float 音调偏移量

    :return str[我的世界音符ID], Tuple[float,float,float]播放视角坐标, float[指令音量参数], float[指令音调参数]
    """

    return (
        note_.sound_name,
        note_.position_displacement,
        note_.velocity / 127,
        (
            None
            if note_.percussive
            else (
                2
                ** (
                    (
                        note_.note_pitch
                        - 60
                        - MM_INSTRUMENT_DEVIATION_TABLE.get(note_.sound_name, 6)
                        + pitch_deviation
                    )
                    / 12
                )
            )
        ),
    )


def single_note_to_command_parameters(
    note_: SingleNote,
    reference_table: MidiInstrumentTableType,
    deviation: float = 0,
    volume_processing_method: Callable[[float], float] = natural_curve,
) -> Tuple[
    str,
    Tuple[float, float, float],
    float,
    Union[float, Literal[None]],
]:
    """
    将音符转为播放的指令之参数
    :param note_:int 音符对象
    :param reference_table:Dict[int, str] 转换对照表
    :param deviation:float 音调偏移量
    :param volume_proccessing_method:Callable[[float], float] 音量处理函数

    :return str[我的世界音符ID], Tuple[float,float,float]播放视角坐标, float[指令音量参数], float[指令音调参数]
    """

    mc_sound_ID, _X = inst_to_sould_with_deviation(
        note_.inst,
        reference_table,
        "note.bd" if note_.percussive else "note.flute",
    )

    mc_distance_volume = volume_processing_method(note_.velocity)

    return (
        mc_sound_ID,
        (0, mc_distance_volume, 0),
        note_.velocity / 127,
        None if note_.percussive else 2 ** ((note_.pitch - 60 - _X + deviation) / 12),
    )


def midi_msgs_to_minenote(
    inst_: int,  # 乐器编号
    note_: int,
    percussive_: bool,  # 是否作为打击乐器启用
    velocity_: int,
    start_time_: int,
    duration_: int,
    track_no_: int,
    play_speed: float,
    midi_reference_table: MidiInstrumentTableType,
    volume_processing_method_: Callable[[float], float],
) -> MineNote:
    """
    将Midi信息转为我的世界音符对象
    :param inst_: int 乐器编号
    :param note_: int 音高编号（音符编号）
    :param percussive_: bool 是否作为打击乐器启用
    :param velocity_: int 力度(响度)
    :param start_time_: int 音符起始时间（毫秒数）
    :param duration_: int 音符持续时间（毫秒数）
    :param track_no_: int 音符所处音轨
    :param play_speed: float 曲目播放速度
    :param midi_reference_table: Dict[int, str] 转换对照表
    :param volume_proccessing_method_: Callable[[float], float] 音量处理函数

    :return MineNote我的世界音符对象
    """
    mc_sound_ID = midi_inst_to_mc_sound(
        inst_,
        midi_reference_table,
        "note.bd" if percussive_ else "note.flute",
    )

    mc_distance_volume = volume_processing_method_(velocity_)

    return MineNote(
        mc_sound_name=mc_sound_ID,
        midi_pitch=note_,
        midi_velocity=velocity_,
        start_time=round(start_time_ / float(play_speed) / 50),
        last_time=round(duration_ / float(play_speed) / 50),
        track_number=track_no_,
        is_percussion=percussive_,
        displacement=(0, mc_distance_volume, 0),
    )


def single_note_to_minenote(
    note_: SingleNote,
    reference_table: MidiInstrumentTableType,
    play_speed: float = 0,
    volume_processing_method: Callable[[float], float] = natural_curve,
) -> MineNote:
    """
    将音符转为我的世界音符对象
    :param note_:SingleNote 音符对象
    :param reference_table:Dict[int, str] 转换对照表
    :param play_speed:float 播放速度
    :param volume_proccessing_method:Callable[[float], float] 音量处理函数

    :return MineNote我的世界音符对象
    """
    mc_sound_ID = midi_inst_to_mc_sound(
        note_.inst,
        reference_table,
        "note.bd" if note_.percussive else "note.flute",
    )

    mc_distance_volume = volume_processing_method(note_.velocity)

    return MineNote(
        mc_sound_ID,
        note_.pitch,
        note_.velocity,
        round(note_.start_time / float(play_speed) / 50),
        round(note_.duration / float(play_speed) / 50),
        note_.track_no,
        note_.percussive,
        (0, mc_distance_volume, 0),
        note_.extra_info,
    )


def is_in_diapason(note_pitch: int, instrument: str) -> bool:
    note_range = MM_INSTRUMENT_RANGE_TABLE.get(instrument, ((-1, 128), 0))[0]
    return note_pitch >= note_range[0] and note_pitch <= note_range[1]


def is_note_in_diapason(note_: MineNote) -> bool:
    note_range = MM_INSTRUMENT_RANGE_TABLE.get(note_.sound_name, ((-1, 128), 0))[0]
    return note_.note_pitch >= note_range[0] and note_.note_pitch <= note_range[1]


def note_to_redstone_block(
    note_: MineNote, random_select: bool = False, default_block: str = "air"
):
    """
    将我的世界乐器名改作音符盒所需的对应方块名称

    Parameters
    ----------
    note_: SingleNote
        音符类
    random_select: bool
        是否随机选取对应方块
    default_block: str
        查表查不到怎么办？默认一个！

    Returns
    -------
    str方块名称
    """
    pass
    # return SingleNoteBox()  # TO-DO


@staticmethod
def soundID_to_blockID(
    sound_id: str, random_select: bool = False, default_block: str = "air"
) -> str:
    """
    将我的世界乐器名改作音符盒所需的对应方块名称

    Parameters
    ----------
    sound_id: str
        将我的世界乐器名
    random_select: bool
        是否随机选取对应方块
    default_block: str
        查表查不到怎么办？默认一个！

    Returns
    -------
    str方块名称
    """
    if random_select:
        return random.choice(MC_INSTRUMENT_BLOCKS_TABLE.get(sound_id, (default_block,)))
    else:
        return MC_INSTRUMENT_BLOCKS_TABLE.get(sound_id, (default_block,))[0]

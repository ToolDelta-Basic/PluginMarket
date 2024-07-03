# -*- coding: utf-8 -*-

"""
存储音·创附属子类
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


from dataclasses import dataclass
from .types import Optional, Any, List, Mapping, Tuple, Union

from .constants import MC_PERCUSSION_INSTRUMENT_LIST


@dataclass(init=False)
class MineNote:
    """存储单个音符的类"""

    sound_name: str
    """乐器ID"""

    note_pitch: int
    """midi音高"""

    velocity: int
    """响度(力度)"""

    start_tick: int
    """开始之时 命令刻"""

    duration: int
    """音符持续时间 命令刻"""

    track_no: int
    """音符所处的音轨"""

    percussive: bool
    """是否作为打击乐器启用"""

    position_displacement: Tuple[float, float, float]
    """声像位移"""

    extra_info: Any
    """你觉得放什么好？"""

    def __init__(
        self,
        mc_sound_name: str,
        midi_pitch: Optional[int],
        midi_velocity: int,
        start_time: int,
        last_time: int,
        track_number: int = 0,
        is_percussion: Optional[bool] = None,
        displacement: Optional[Tuple[float, float, float]] = None,
        extra_information: Optional[Any] = None,
    ):
        """用于存储单个音符的类
        :param mc_sound_name:`str` 《我的世界》声音ID
        :param midi_pitch:`int` midi音高
        :param midi_velocity:`int` midi响度(力度)
        :param start_time:`int` 开始之时(命令刻)
            注：此处的时间是用从乐曲开始到当前的毫秒数
        :param last_time:`int` 音符延续时间(命令刻)
        :param track_number:`int` 音轨编号
        :param is_percussion:`bool` 是否作为打击乐器
        :param displacement:`tuple[int,int,int]` 声像位移
        :param extra_information:`Any` 附加信息"""
        self.sound_name: str = mc_sound_name
        """乐器ID"""
        self.note_pitch: int = 66 if midi_pitch is None else midi_pitch
        """midi音高"""
        self.velocity: int = midi_velocity
        """响度(力度)"""
        self.start_tick: int = start_time
        """开始之时 tick"""
        self.duration: int = last_time
        """音符持续时间 tick"""
        self.track_no: int = track_number
        """音符所处的音轨"""

        self.percussive = (
            (mc_sound_name in MC_PERCUSSION_INSTRUMENT_LIST)
            if (is_percussion is None)
            else is_percussion
        )
        """是否为打击乐器"""

        self.position_displacement = (
            (0, 0, 0) if (displacement is None) else displacement
        )
        """声像位移"""

        self.extra_info = extra_information

    @classmethod
    def decode(cls, code_buffer: bytes):
        """自字节码析出MineNote类"""
        group_1 = int.from_bytes(code_buffer[:6], "big")
        percussive_ = bool(group_1 & 0b1)
        duration_ = (group_1 := group_1 >> 1) & 0b11111111111111111
        start_tick_ = (group_1 := group_1 >> 17) & 0b11111111111111111
        note_pitch_ = (group_1 := group_1 >> 17) & 0b1111111
        sound_name_length = group_1 >> 7

        if code_buffer[6] & 0b1:
            position_displacement_ = (
                int.from_bytes(
                    code_buffer[8 + sound_name_length : 10 + sound_name_length],
                    "big",
                )
                / 1000,
                int.from_bytes(
                    code_buffer[10 + sound_name_length : 12 + sound_name_length],
                    "big",
                )
                / 1000,
                int.from_bytes(
                    code_buffer[12 + sound_name_length : 14 + sound_name_length],
                    "big",
                )
                / 1000,
            )
        else:
            position_displacement_ = (0, 0, 0)

        try:
            return cls(
                mc_sound_name=code_buffer[8 : 8 + sound_name_length].decode(
                    encoding="utf-8"
                ),
                midi_pitch=note_pitch_,
                midi_velocity=code_buffer[6] >> 1,
                start_time=start_tick_,
                last_time=duration_,
                track_number=code_buffer[7],
                is_percussion=percussive_,
                displacement=position_displacement_,
            )
        except:
            print(code_buffer, "\n", code_buffer[8 : 8 + sound_name_length])
            raise

    def encode(self, is_displacement_included: bool = True) -> bytes:
        """
        将数据打包为字节码
        
        :param is_displacement_included:`bool` 是否包含声像偏移数据，默认为**是**

        :return bytes 打包好的字节码
        """

        # 字符串长度 6 位 支持到 63
        # note_pitch 7 位 支持到 127
        # start_tick 17 位 支持到 131071 即 109.22583 分钟 合 1.8204305 小时
        # duration 17 位 支持到 131071 即 109.22583 分钟 合 1.8204305 小时
        # percussive 长度 1 位 支持到 1
        # 共 48 位 合 6 字节
        # +++
        # velocity 长度 7 位 支持到 127
        # is_displacement_included 长度 1 位 支持到 1
        # 共 8 位 合 1 字节
        # +++
        # track_no 长度 8 位 支持到 255 合 1 字节
        # +++
        # sound_name 长度最多63 支持到 21 个中文字符 或 63 个西文字符
        # +++
        # position_displacement 每个元素长 16 位 合 2 字节
        # 共 48 位 合 6 字节 支持存储三位小数和两位整数，其值必须在 [0, 65.535] 之间

        return (
            (
                (
                    (
                        (
                            (
                                (
                                    (
                                        (
                                            len(
                                                r := self.sound_name.encode(
                                                    encoding="utf-8"
                                                )
                                            )
                                            << 7
                                        )
                                        + self.note_pitch
                                    )
                                    << 17
                                )
                                + self.start_tick
                            )
                            << 17
                        )
                        + self.duration
                    )
                    << 1
                )
                + self.percussive
            ).to_bytes(6, "big")
            + ((self.velocity << 1) + is_displacement_included).to_bytes(1, "big")
            + self.track_no.to_bytes(1, "big")
            + r
            + (
                (
                    round(self.position_displacement[0] * 1000).to_bytes(2, "big")
                    + round(self.position_displacement[1] * 1000).to_bytes(2, "big")
                    + round(self.position_displacement[2] * 1000).to_bytes(2, "big")
                )
                if is_displacement_included
                else b""
            )
        )

    def set_info(self, sth: Any):
        """设置附加信息"""
        self.extra_info = sth

    def __str__(self, is_displacement: bool = False, is_track: bool = False):
        return "{}Note(Instrument = {}, {}Velocity = {}, StartTick = {}, Duration = {}{}{})".format(
            "Percussive" if self.percussive else "",
            self.sound_name,
            "" if self.percussive else "NotePitch = {}, ".format(self.note_pitch),
            self.velocity,
            self.start_tick,
            self.duration,
            ", Track = {}".format(self.track_no) if is_track else "",
            (
                ", PositionDisplacement = {}".format(self.position_displacement)
                if is_displacement
                else ""
            ),
        )

    def tuplize(self, is_displacement: bool = False, is_track: bool = False):
        tuplized = self.__tuple__()
        return (
            tuplized[:-2]
            + ((tuplized[-2],) if is_track else ())
            + ((tuplized[-1],) if is_displacement else ())
        )

    def __list__(self) -> List:
        return (
            [
                self.percussive,
                self.sound_name,
                self.velocity,
                self.start_tick,
                self.duration,
                self.track_no,
                self.position_displacement,
            ]
            if self.percussive
            else [
                self.percussive,
                self.sound_name,
                self.note_pitch,
                self.velocity,
                self.start_tick,
                self.duration,
                self.track_no,
                self.position_displacement,
            ]
        )

    def __tuple__(
        self,
    ) -> Union[
        Tuple[bool, str, int, int, int, int, int, Tuple[float, float, float]],
        Tuple[bool, str, int, int, int, int, Tuple[float, float, float]],
    ]:
        return (
            (
                self.percussive,
                self.sound_name,
                self.velocity,
                self.start_tick,
                self.duration,
                self.track_no,
                self.position_displacement,
            )
            if self.percussive
            else (
                self.percussive,
                self.sound_name,
                self.note_pitch,
                self.velocity,
                self.start_tick,
                self.duration,
                self.track_no,
                self.position_displacement,
            )
        )

    def __dict__(self):
        return (
            {
                "Percussive": self.percussive,
                "Instrument": self.sound_name,
                "Velocity": self.velocity,
                "StartTick": self.start_tick,
                "Duration": self.duration,
                "Track": self.track_no,
                "PositionDisplacement": self.position_displacement,
            }
            if self.percussive
            else {
                "Percussive": self.percussive,
                "Instrument": self.sound_name,
                "Pitch": self.note_pitch,
                "Velocity": self.velocity,
                "StartTick": self.start_tick,
                "Duration": self.duration,
                "Track": self.track_no,
                "PositionDisplacement": self.position_displacement,
            }
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.tuplize() == other.tuplize()


@dataclass(init=False)
class SingleNote:
    """存储单个音符的类"""

    instrument: int
    """乐器编号"""

    note: int
    """音符编号"""

    velocity: int
    """力度/响度"""

    start_time: int
    """开始之时 ms"""

    duration: int
    """音符持续时间 ms"""

    track_no: int
    """音符所处的音轨"""

    percussive: bool
    """是否为打击乐器"""

    extra_info: Any
    """你觉得放什么好？"""

    def __init__(
        self,
        instrument: int,
        pitch: int,
        velocity: int,
        startime: int,
        lastime: int,
        is_percussion: bool,
        track_number: int = 0,
        extra_information: Any = None,
    ):
        """用于存储单个音符的类
        :param instrument 乐器编号
        :param pitch 音符编号
        :param velocity 力度/响度
        :param startTime 开始之时(ms)
            注：此处的时间是用从乐曲开始到当前的毫秒数
        :param lastTime 音符延续时间(ms)"""
        self.instrument: int = instrument
        """乐器编号"""
        self.note: int = pitch
        """音符编号"""
        self.velocity: int = velocity
        """力度/响度"""
        self.start_time: int = startime
        """开始之时 ms"""
        self.duration: int = lastime
        """音符持续时间 ms"""
        self.track_no: int = track_number
        """音符所处的音轨"""
        self.percussive: bool = is_percussion
        """是否为打击乐器"""

        self.extra_info = extra_information

    @property
    def inst(self) -> int:
        """乐器编号"""
        return self.instrument

    @inst.setter
    def inst(self, inst_: int):
        self.instrument = inst_

    @property
    def pitch(self) -> int:
        """音符编号"""
        return self.note

    # @property
    # def get_mc_pitch(self,table: Dict[int, Tuple[str, int]]) -> float:
    #     self.mc_sound_ID, _X =  inst_to_sould_with_deviation(self.inst,table,"note.bd" if self.percussive else "note.flute",)
    #     return -1 if self.percussive else 2 ** ((self.note - 60 - _X) / 12)

    def set_info(self, sth: Any):
        """设置附加信息"""
        self.extra_info = sth

    def __str__(self, is_track: bool = False):
        return "{}Note(Instrument = {}, {}Velocity = {}, StartTime = {}, Duration = {}{})".format(
            "Percussive" if self.percussive else "",
            self.inst,
            "" if self.percussive else "Pitch = {}, ".format(self.pitch),
            self.start_time,
            self.duration,
            ", Track = {}".format(self.track_no) if is_track else "",
        )

    def __tuple__(self):
        return (
            (
                self.percussive,
                self.inst,
                self.velocity,
                self.start_time,
                self.duration,
                self.track_no,
            )
            if self.percussive
            else (
                self.percussive,
                self.inst,
                self.note,
                self.velocity,
                self.start_time,
                self.duration,
                self.track_no,
            )
        )

    def __dict__(self):
        return (
            {
                "Percussive": self.percussive,
                "Instrument": self.inst,
                "Velocity": self.velocity,
                "StartTime": self.start_time,
                "Duration": self.duration,
                "Track": self.track_no,
            }
            if self.percussive
            else {
                "Percussive": self.percussive,
                "Instrument": self.inst,
                "Pitch": self.note,
                "Velocity": self.velocity,
                "StartTime": self.start_time,
                "Duration": self.duration,
                "Track": self.track_no,
            }
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.__str__() == other.__str__()


@dataclass(init=False)
class MineCommand:
    """存储单个指令的类"""

    command_text: str
    """指令文本"""

    conditional: bool
    """执行是否有条件"""

    delay: int
    """执行的延迟"""

    annotation_text: str
    """指令注释"""

    def __init__(
        self,
        command: str,
        condition: bool = False,
        tick_delay: int = 0,
        annotation: str = "",
    ):
        """
        存储单个指令的类

        Parameters
        ----------
        command: str
            指令
        condition: bool
            是否有条件
        tick_delay: int
            执行延时
        annotation: str
            注释
        """
        self.command_text = command
        self.conditional = condition
        self.delay = tick_delay
        self.annotation_text = annotation

    def copy(self):
        return MineCommand(
            command=self.command_text,
            condition=self.conditional,
            tick_delay=self.delay,
            annotation=self.annotation_text,
        )

    @property
    def cmd(self) -> str:
        """
        我的世界函数字符串（包含注释）
        """
        return self.__str__()

    def __str__(self) -> str:
        """
        转为我的世界函数文件格式（包含注释）
        """
        return "#[{cdt}]<{delay}> {ant}\n{cmd}".format(
            cdt="CDT" if self.conditional else "",
            delay=self.delay,
            ant=self.annotation_text,
            cmd=self.command_text,
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.__str__() == other.__str__()


@dataclass(init=False)
class SingleNoteBox:
    """存储单个音符盒"""

    instrument_block: str
    """乐器方块"""

    note_value: int
    """音符盒音高"""

    annotation_text: str
    """音符注释"""

    is_percussion: bool
    """是否为打击乐器"""

    def __init__(
        self,
        instrument_block_: str,
        note_value_: int,
        percussion: Optional[bool] = None,
        annotation: str = "",
    ):
        """用于存储单个音符盒的类
        :param instrument_block_ 音符盒演奏所使用的乐器方块
        :param note_value_ 音符盒的演奏音高
        :param percussion 此音符盒乐器是否作为打击乐处理
            注：若为空，则自动识别是否为打击乐器
        :param annotation 音符注释"""
        self.instrument_block = instrument_block_
        """乐器方块"""
        self.note_value = note_value_
        """音符盒音高"""
        self.annotation_text = annotation
        """音符注释"""
        if percussion is None:
            self.is_percussion = percussion in MC_PERCUSSION_INSTRUMENT_LIST
        else:
            self.is_percussion = percussion

    @property
    def inst(self) -> str:
        """获取音符盒下的乐器方块"""
        return self.instrument_block

    @inst.setter
    def inst(self, inst_):
        self.instrument_block = inst_

    @property
    def note(self) -> int:
        """获取音符盒音调特殊值"""
        return self.note_value

    @note.setter
    def note(self, note_):
        self.note_value = note_

    @property
    def annotation(self) -> str:
        """获取音符盒的备注"""
        return self.annotation_text

    @annotation.setter
    def annotation(self, annotation_):
        self.annotation_text = annotation_

    def copy(self):
        return SingleNoteBox(
            instrument_block_=self.instrument_block,
            note_value_=self.note_value,
            annotation=self.annotation_text,
        )

    def __str__(self) -> str:
        return f"Note(inst = {self.inst}, note = {self.note}, )"

    def __tuple__(self) -> tuple:
        return self.inst, self.note, self.annotation

    def __dict__(self) -> dict:
        return {
            "inst": self.inst,
            "note": self.note,
            "annotation": self.annotation,
        }

    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.__str__() == other.__str__()


@dataclass(init=False)
class ProgressBarStyle:
    """进度条样式类"""

    base_style: str
    """基础样式"""

    to_play_style: str
    """未播放之样式"""

    played_style: str
    """已播放之样式"""

    def __init__(self, base_s: str, to_play_s: str, played_s: str):
        """用于存储进度条样式的类
        :param base_s 基础样式，用以定义进度条整体
        :param to_play_s 进度条样式：尚未播放的样子
        :param played_s 已经播放的样子"""
        self.base_style = base_s
        self.to_play_style = to_play_s
        self.played_style = played_s

    @classmethod
    def from_tuple(cls, tuplized_style: Tuple[str, Tuple[str, str]]):
        """自旧版进度条元组表示法读入数据（已不建议使用）"""
        if isinstance(tuplized_style, tuple):
            if isinstance(tuplized_style[0], str) and isinstance(
                tuplized_style[1], tuple
            ):
                if isinstance(tuplized_style[1][0], str) and isinstance(
                    tuplized_style[1][1], str
                ):
                    return cls(
                        tuplized_style[0], tuplized_style[1][0], tuplized_style[1][1]
                    )
        raise ValueError(
            "元组表示的进度条样式组 {} 格式错误，已不建议使用此功能，请尽快更换。".format(
                tuplized_style
            )
        )

    def set_base_style(self, value: str):
        """设置基础样式"""
        self.base_style = value

    def set_to_play_style(self, value: str):
        """设置未播放之样式"""
        self.to_play_style = value

    def set_played_style(self, value: str):
        """设置已播放之样式"""
        self.played_style = value

    def copy(self):
        dst = ProgressBarStyle(self.base_style, self.to_play_style, self.played_style)
        return dst


DEFAULT_PROGRESSBAR_STYLE = ProgressBarStyle(
    r"▶ %%N [ %%s/%^s %%% __________ %%t|%^t ]",
    r"§e=§r",
    r"§7=§r",
)
"""
默认的进度条样式
"""

NoteChannelType = Mapping[
    int,
    List[SingleNote,],
]
"""
频道信息类型

Dict[int,Dict[int,List[SingleNote,],],]
"""


MineNoteChannelType = Mapping[
    int,
    List[MineNote,],
]
"""
我的世界频道信息类型

Dict[int,Dict[int,List[MineNote,],],]
"""

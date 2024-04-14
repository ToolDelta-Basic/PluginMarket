# -*- coding: utf-8 -*-

"""
存放一些报错类型
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


class MSCTBaseException(Exception):
    """音·创库版本的所有错误均继承于此"""

    def __init__(self, *args):
        """音·创库版本的所有错误均继承于此"""
        super().__init__(*args)

    def meow(
        self,
    ):
        for i in self.args:
            print(i + "喵！")

    def crash_it(self):
        raise self


class MidiFormatException(MSCTBaseException):
    """音·创库版本的所有MIDI格式错误均继承于此"""

    def __init__(self, *args):
        """音·创库版本的所有MIDI格式错误均继承于此"""
        super().__init__("MIDI格式错误", *args)


class MidiDestroyedError(MSCTBaseException):
    """Midi文件损坏"""

    def __init__(self, *args):
        """Midi文件损坏"""
        super().__init__("MIDI文件损坏：无法读取MIDI文件", *args)


# class MidiUnboundError(MSCTBaseException):
#     """未定义Midi对象（无用）"""

#     def __init__(self, *args):
#         """未绑定Midi对象"""
#         super().__init__("未定义MidiFile对象：你甚至没有对象就想要生孩子？", *args)
# 此错误在本版本内已经不再使用

class CommandFormatError(RuntimeError):
    """指令格式与目标格式不匹配而引起的错误"""

    def __init__(self, *args):
        """指令格式与目标格式不匹配而引起的错误"""
        super().__init__("指令格式不匹配", *args)


# class CrossNoteError(MidiFormatException):
#     """同通道下同音符交叉出现所产生的错误"""

#     def __init__(self, *args):
#         """同通道下同音符交叉出现所产生的错误"""
#         super().__init__("同通道下同音符交叉", *args)
# 这TM是什么错误？
# 我什么时候写的这玩意？
# 我哪知道这说的是啥？


class NotDefineTempoError(MidiFormatException):
    """没有Tempo设定导致时间无法计算的错误"""

    def __init__(self, *args):
        """没有Tempo设定导致时间无法计算的错误"""
        super().__init__("在曲目开始时没有声明Tempo（未指定拍长）", *args)


class ChannelOverFlowError(MidiFormatException):
    """一个midi中含有过多的通道"""

    def __init__(self, max_channel=16, *args):
        """一个midi中含有过多的通道"""
        super().__init__("含有过多的通道（数量应≤{}）".format(max_channel), *args)


class NotDefineProgramError(MidiFormatException):
    """没有Program设定导致没有乐器可以选择的错误"""

    def __init__(self, *args):
        """没有Program设定导致没有乐器可以选择的错误"""
        super().__init__("未指定演奏乐器", *args)


class NoteOnOffMismatchError(MidiFormatException):
    """音符开音和停止不匹配的错误"""

    def __init__(self, *args):
        """音符开音和停止不匹配的错误"""
        super().__init__("音符不匹配", *args)


class ZeroSpeedError(ZeroDivisionError):
    """以0作为播放速度的错误"""

    def __init__(self, *args):
        """以0作为播放速度的错误"""
        super().__init__("播放速度为0", *args)


class IllegalMinimumVolumeError(ValueError):
    """最小播放音量有误的错误"""

    def __init__(self, *args):
        """最小播放音量错误"""
        super().__init__("最小播放音量超出范围", *args)
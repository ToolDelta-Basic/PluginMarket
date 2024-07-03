# -*- coding: utf-8 -*-
"""一个简单的我的世界音频转换库
音·创 (Musicreater)
是一款免费开源的针对《我的世界》的midi音乐转换库
Musicreater(音·创)
A free open source library used for convert midi file into formats that is suitable for **Minecraft**.

版权所有 © 2024 音·创 开发者
Copyright © 2024 all the developers of Musicreater

开源相关声明请见 仓库根目录下的 License.md
Terms & Conditions: License.md in the root directory
"""

# 睿乐组织 开发交流群 861684859
# Email TriM-Organization@hotmail.com
# 若需转载或借鉴 许可声明请查看仓库目录下的 License.md


__version__ = "2.0.0"
__vername__ = "全新组织架构"
__author__ = (
    ("金羿", "Eilles Wan"),
    ("诸葛亮与八卦阵", "bgArray"),
    ("偷吃不是Touch", "Touch"),
    ("鱼旧梦", "ElapsingDreams"),
)
__all__ = [
    # 主要类
    "MusicSequence",
    "MidiConvert",
    # 附加类
    "SingleNote",
    "MineNote",
    "MineCommand",
    "SingleNoteBox",
    "ProgressBarStyle",
    # "TimeStamp", 未来功能
    # 默认值
    "DEFAULT_PROGRESSBAR_STYLE",
    "MM_INSTRUMENT_RANGE_TABLE",
    "MM_CLASSIC_PITCHED_INSTRUMENT_TABLE",
    "MM_CLASSIC_PERCUSSION_INSTRUMENT_TABLE",
    "MM_TOUCH_PITCHED_INSTRUMENT_TABLE",
    "MM_TOUCH_PERCUSSION_INSTRUMENT_TABLE",
]

from .main import *

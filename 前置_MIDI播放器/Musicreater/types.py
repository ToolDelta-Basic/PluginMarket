# -*- coding: utf-8 -*-

"""
存放数据类型的定义
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

from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
    Iterable,
    Sequence,
    Mapping,
    Callable,
)


MidiNoteNameTableType = Mapping[int, Tuple[str, ...]]
"""
Midi音符名称对照表类型
"""

MidiInstrumentTableType = Mapping[int, str]
"""
Midi乐器对照表类型
"""

FittingFunctionType = Callable[[float], float]
"""
声像偏移音量拟合函数类型
"""

ChannelType = Dict[
    int,
    Dict[
        int,
        List[
            Union[
                Tuple[Literal["PgmC"], int, int],
                Tuple[Literal["NoteS"], int, int, int],
                Tuple[Literal["NoteE"], int, int],
            ]
        ],
    ],
]
"""
以字典所标记的频道信息类型（已弃用）

Dict[int,Dict[int,List[Union[Tuple[Literal["PgmC"], int, int],Tuple[Literal["NoteS"], int, int, int],Tuple[Literal["NoteE"], int, int],]],],]
"""

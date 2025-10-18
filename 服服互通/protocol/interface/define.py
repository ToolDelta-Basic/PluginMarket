import json
from dataclasses import dataclass

_marshaler = json


@dataclass
class Data:
    # 数据类, 可以是发往服务端的信息或者服务端返回的信息
    type: str
    content: dict

    def marshal(self) -> bytes:
        return _marshaler.dumps({"Type": self.type, "Content": self.content})  # pyright: ignore[reportReturnType]


def format_data(type: str, content: dict):
    return Data(type, content)




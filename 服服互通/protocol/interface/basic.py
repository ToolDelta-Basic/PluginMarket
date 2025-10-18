from abc import ABCMeta, abstractmethod
from collections.abc import Callable
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ... import SuperLink


# PROTOCOL CLASSES 服服互通协议类
class BasicProtocol(metaclass=ABCMeta):
    # 所有服服互通协议的基类
    def __init__(self, frame: "SuperLink", ws_ip: str, cfgs: dict):
        self.frame = frame
        self.ws_ip = ws_ip
        self.cfgs = cfgs
        self.active = False
        self.listen_cbs = {}

    @abstractmethod
    def connect(self):
        # 开始连接
        raise NotImplementedError

    @abstractmethod
    def send(self, data: Any):
        # 发送数据
        raise NotImplementedError

    @abstractmethod
    def send_and_wait_req(self, data: Any) -> Any:
        # 向服务端请求数据
        raise NotImplementedError

    @abstractmethod
    def listen_for_data(self, data_type: str, cb: Callable[[Any], None]):
        raise NotImplementedError

    @abstractmethod
    def is_actived(self) -> bool:
        raise NotImplementedError

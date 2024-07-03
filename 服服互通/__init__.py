import websockets
import json
import time
import asyncio
import base64
import threading
from socket import gaierror
from dataclasses import dataclass
from typing import Any, Callable
from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import WebSocketClientProtocol
from tooldelta import Frame, plugins, Plugin, Config, Print, Utils

# CUSTOMIZE CLASSES AND FUNCS


@dataclass
class Data:
    # 数据类, 可以是发往服务端的信息或者服务端返回的信息
    type: str
    content: dict

    def marshal(self) -> str:
        return json.dumps({"Type": self.type, "Content": self.content})


def format_data(type: str, content: dict):
    return Data(type, content)


def new_result_getter():
    lock = threading.Lock()
    lock.acquire()
    resp: list[None | Data] = [None]

    def setter(result: Data):
        resp[0] = result
        lock.release()

    def getter(timeout: float = -1):
        lock.acquire(timeout=timeout)
        return resp[0]

    return setter, getter


# PROTOCOL CLASSES


class BasicProtocol:
    # 所有服服互通协议的基类
    def __init__(self, frame: Frame, ws_ip: str, cfgs: dict):
        self.frame = frame
        self.ws_ip = ws_ip
        self.cfgs = cfgs
        self.active = False
        self.listen_cbs = {}

    def start(self):
        # 开始连接
        raise NotImplementedError

    def send(self, data: Any):
        # 发送数据
        raise NotImplementedError

    def send_and_wait_req(self, data: Any) -> Any:
        # 向服务端请求数据
        raise NotImplementedError

    def listen_for_data(self, data_type: str, cb: Callable[[Any], None]):
        raise NotImplementedError


class SuperLinkProtocol(BasicProtocol):
    def __init__(self, frame: Frame, ws_ip: str, cfgs: dict):
        super().__init__(frame, ws_ip, cfgs)
        self.retryTime = 30
        self.retryCount = 0
        self.req_resps: dict[str, Callable[[Data], None]] = {}
        self.listen_cbs: dict[str, Callable[[Data], None]] = {}

    @Utils.thread_func("服服互通自动重连线程")
    def start(self):
        while 1:
            asyncio.run(self.start_ws_con())
            self.retryCount += 1
            if self.retryCount < 10:
                self.retryTime = self.retryCount * 10
            else:
                self.retryTime = 600
            Print.print_war(f"服服互通断开连接, 将在 {self.retryTime}s 后重连")
            time.sleep(self.retryTime)

    async def start_ws_con(self):
        try:
            async with websockets.connect(  # type: ignore
                self.ws_ip,
                extra_headers={
                    "Protocol": "SuperLink-v4@SuperScript",
                    "ServerName": base64.b64encode(
                        self.cfgs["此租赁服的公开显示名"].encode("utf-8")
                    ).decode("ascii"),
                    "ChannelName": base64.b64encode(
                        self.cfgs["登入后自动连接到的频道大区名"].encode("utf-8")
                    ).decode("ascii"),
                    "ChannelToken": base64.b64encode(
                        self.cfgs["频道密码"].encode("utf-8")
                    ).decode("ascii"),
                },
            ) as ws:
                self.ws: WebSocketClientProtocol = ws
                self.active = True
                login_resp_json = json.loads(await ws.recv())
                login_resp = format_data(
                    login_resp_json["Type"], login_resp_json["Content"]
                )
                if login_resp.type == "server.auth_failed":
                    Print.print_err(
                        f"§b服服互通: 中心服务器登录失败: {login_resp.content['Reason']}"
                    )
                elif login_resp.type == "server.auth_success":
                    Print.print_suc("服服互通: §f中心服务器登录成功")
                    self.retryCount = 0
                    while 1:
                        await self.handle(json.loads(await ws.recv()))

        except ConnectionClosed:
            Print.print_war(f"服服互通: 服务器断开连接")
        except gaierror as err:
            Print.print_err(
                f"服服互通: 中心服务器连接失败(IP解析异常): {self.ws_ip} - {err}"
            )
        except Exception as err:
            import traceback

            traceback.print_exc()
            Print.print_err(f"服服互通: 中心服务器连接失败: {err}")
        finally:
            self.active = False

    async def handle(self, recv_data: dict):
        data = format_data(recv_data["Type"], recv_data["Content"])
        if data.content.get("UUID") in self.req_resps.keys():
            self.req_resps[data.content["UUID"]](data)
        else:
            plugins.broadcastEvt("superlink.event", data)

    async def send(self, data: Data):
        await self.ws.send(data.marshal())

    @staticmethod
    def format_data(type: str, content: dict):
        return format_data(type, content)

    async def send_and_wait_req(self, data: Data, timeout=-1):
        await self.send(data)
        req_id = data.content["UUID"]
        s, g = new_result_getter()
        self.req_resps[req_id] = s
        res = g(timeout)
        return res

    def listen_for_data(self, data_type: str, cb: Callable[[Data], None]):
        self.listen_cbs[data_type] = cb


# PLUGIN MAIN


@plugins.add_plugin_as_api("服服互通")
class SuperLink(Plugin):
    name = "服服互通v4"
    author = "SuperScript"
    version = (0, 0, 5)

    def __init__(self, frame: Frame):
        super().__init__(frame)
        self.read_cfgs()
        self.init_funcs()

    def read_cfgs(self):
        CFG_DEFAULT = {
            "中心服务器IP": "ws://superlink.tblstudio.cn:24013",
            "服服互通协议": "SuperLink-v4@SuperScript",
            "协议附加配置": {
                "此租赁服的公开显示名": "???",
                "登入后自动连接到的频道大区名": "公共大区",
                "频道密码": "",
            },
            "基本互通配置": {
                "是否转发玩家发言": True,
                "转发聊天到本服格式": "<[服名]:[玩家名]> [消息]",
            },
        }
        CFG_STD = {
            "中心服务器IP": str,
            "服服互通协议": str,
            "协议附加配置": {
                "此租赁服的公开显示名": str,
                "登入后自动连接到的频道大区名": str,
                "频道密码": str,
            },
            "基本互通配置": {"是否转发玩家发言": bool, "转发聊天到本服格式": str},
        }
        self.cfg, _ = Config.get_plugin_config_and_version(
            self.name, CFG_STD, CFG_DEFAULT, self.version
        )
        use_protocol: type[BasicProtocol] | None = {
            "SuperLink-v4@SuperScript": SuperLinkProtocol
        }.get(self.cfg["服服互通协议"])
        if use_protocol is None:
            Print.print_err(f"协议不受支持: {self.cfg['服服互通协议']}")
            raise SystemExit
        self.active_protocol = use_protocol(
            self.frame, self.cfg["中心服务器IP"], self.cfg["协议附加配置"]
        )
        basic_link_cfg = self.cfg["基本互通配置"]
        self.enable_trans_chat = basic_link_cfg["是否转发玩家发言"]
        self.trans_fmt = basic_link_cfg["转发聊天到本服格式"]

    def init_funcs(self):
        # --------------- API -------------------
        self.send = self.active_protocol.send
        self.send_and_wait_req = self.active_protocol.send_and_wait_req
        self.listen_for_data = self.active_protocol.listen_for_data
        # ---------------------------------------

    def active(self):
        self.active_protocol.start()

    def on_inject(self):
        Print.print_inf("正在连接至服服互通..")
        self.active()

    @Utils.thread_func
    def on_player_message(self, player, msg):
        if self.enable_trans_chat and self.active:
            asyncio.run(
                self.send(format_data("chat.msg", {"ChatName": player, "Msg": msg}))
            )

    @plugins.add_broadcast_listener("superlink.event")
    def listen_chat(self, data: Data):
        if data.type == "chat.msg" and self.enable_trans_chat:
            self.game_ctrl.say_to(
                "@a",
                Utils.simple_fmt(
                    {
                        "[服名]": data.content["Sender"],
                        "[玩家名]": data.content["ChatName"],
                        "[消息]": data.content["Msg"],
                    },
                    self.cfg["基本互通配置"]["转发聊天到本服格式"],
                ),
            )
        return True

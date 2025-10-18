import asyncio
import time
import requests
import websockets
import base64
import json
from collections.abc import Callable
from socket import gaierror
from websockets.exceptions import ConnectionClosed
from tooldelta import utils, InternalBroadcast
from tooldelta.utils.cfg_meta import load_by_schema
from ..interface.basic import BasicProtocol
from ..interface.define import Data, format_data
from .define import SuperLinkConfig, MsgTypeEnum

class SuperLinkProtocol(BasicProtocol):
    def __init__(self, frame, ws_ip, cfgs):
        super().__init__(frame, ws_ip, cfgs)
        self.cfg = load_by_schema(cfgs, SuperLinkConfig)
        self.retryTime = 30
        self.retryCount = 0
        self.req_resps: dict[str, Callable[[Data], None]] = {}
        self.listen_cbs: dict[str, Callable[[Data], None]] = {}

    @utils.thread_func("服服互通自动重连线程")
    def connect(self):
        if self.ws_ip == "自动选择线路":
            name, self.ws_ip = self.find_default_ips()
            self.frame.print_suc(f"服服互通: 已自动选择线路 {name}")
        while True:
            asyncio.run(self.start_ws_con())
            self.retryCount += 1
            if self.retryCount < 10:
                self.retryTime = self.retryCount * 10
            else:
                self.retryTime = 600
            self.frame.print_war(f"服服互通断开连接, 将在 {self.retryTime}s 后重连")
            time.sleep(self.retryTime)

    def find_default_ips(self):
        self.frame.print_war("服服互通: 正在自动获取线路中..")
        try:
            resp = requests.get(
                "https://github.tooldelta.top/raw.githubusercontent.com/ToolDelta/SuperLink/main/source.json"
            )
            resp.raise_for_status()
            default_name, default_ip = next(iter(resp.json().items()))
            return default_name, default_ip
        except Exception as err:
            self.frame.print_err(f"服服互通: 无法自动获取线路: {err}; 此插件已禁用")
            raise SystemExit

    async def start_ws_con(self):
        serverName = base64.b64encode(self.cfg.display_name.encode("utf-8")).decode(
            "ascii"
        )
        channelName = base64.b64encode(self.cfg.channel_name.encode("utf-8")).decode(
            "ascii"
        )
        channelToken = base64.b64encode(
            self.cfg.channel_password.encode("utf-8")
        ).decode("ascii")
        protocol = base64.b64encode(b"SuperLink-v4@SuperScript").decode(
            "ascii"
        )
        try:
            async with websockets.connect(
                self.ws_ip
                + f"?Name={serverName}&Channel={channelName}&Token={channelToken}&ClientType=tooldelta&Protocol={protocol}"
                # extra_headers={
                #     "Protocol": "SuperLink-v4@SuperScript",
                #     "ServerName": base64.b64encode(
                #         self.cfg.display_name.encode("utf-8")
                #     ).decode("ascii"),
                #     "ChannelName": base64.b64encode(
                #         self.cfg.channel_name.encode("utf-8")
                #     ).decode("ascii"),
                #     "ChannelToken": base64.b64encode(
                #         self.cfg.channel_password.encode("utf-8")
                #     ).decode("ascii"),
                # },
            ) as ws:
                self.ws: websockets.WebSocketClientProtocol = ws
                self.active = True
                login_resp_json = json.loads(await ws.recv())
                login_resp = format_data(
                    login_resp_json["Type"], login_resp_json["Content"]
                )
                if login_resp.type == MsgTypeEnum.AUTH_FAILED:
                    self.frame.print_err(
                        f"§b服服互通: 中心服务器登录失败: {login_resp.content['Reason']}"
                    )
                elif login_resp.type == MsgTypeEnum.AUTH_SUCCESS:
                    self.frame.print_suc("服服互通: §f中心服务器登录成功")
                    self.retryCount = 0
                    while True:
                        await self.handle(json.loads(await ws.recv()))
        except ConnectionClosed:
            self.frame.print_war("服服互通: 服务器断开连接")
        except gaierror as err:
            self.frame.print_err(
                f"服服互通: 中心服务器连接失败(IP解析异常): {self.ws_ip} - {err}"
            )
        except Exception as err:
            import traceback

            self.frame.print_err(traceback.format_exc())
            self.frame.print_err(f"服服互通: 中心服务器 ({self.ws_ip}) 连接失败: {err}")
        finally:
            self.active = False

    async def handle(self, recv_data: dict):
        data = format_data(recv_data["Type"], recv_data["Content"])
        if data.content.get("UUID") in self.req_resps.keys():
            self.req_resps[data.content["UUID"]](data)
        else:
            self.frame.BroadcastEvent(InternalBroadcast("superlink.event", data))

    async def send(self, data: Data):
        await self.ws.send(data.marshal())

    @staticmethod
    def format_data(type: str, content: dict):
        return format_data(type, content)

    async def send_and_wait_req(self, data: Data, timeout=-1):
        await self.send(data)
        req_id = data.content["UUID"]
        g, s = utils.create_result_cb(Data)
        self.req_resps[req_id] = s
        res = g(timeout)
        return res

    def listen_for_data(self, data_type: str, cb: Callable[[Data], None]):
        self.listen_cbs[data_type] = cb

    def is_actived(self):
        return self.active

import asyncio
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ..channel_host import Library

_log = logging.getLogger(__name__)


class WsClient:
    """WebSocket 客户端（基于 websocket-client 库）。"""

    def __init__(self, url: str, token: str = "", reconnect_interval: float = 5.0):
        self._url = url
        self._token = token
        self._reconnect_interval = reconnect_interval
        self._ws = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._message_callback: Optional[Callable] = None
        self._connected = False

    @property
    def url(self) -> str:
        return self._url

    @property
    def connected(self) -> bool:
        return self._connected

    def set_message_callback(self, callback: Callable[[dict], Any]) -> None:
        """设置消息回调（收到 WS 消息时调用）。"""
        self._message_callback = callback

    def start(self) -> None:
        """启动 WS 连接线程。"""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止连接。"""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception as e:
                _log.warning("ws_client.stop: %s", e)

    def send(self, data: dict) -> bool:
        """发送 JSON 消息。"""
        if not self._ws or not self._connected:
            return False
        try:
            self._ws.send(json.dumps(data, ensure_ascii=False))
            return True
        except Exception as e:
            _log.error("WS 发送失败: %s", e)
            return False

    def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群消息（OneBot API）。"""
        return self.send({
            "action": "send_group_msg",
            "params": {"group_id": group_id, "message": message},
        })

    def send_private_msg(self, user_id: int, message: str) -> bool:
        """发送私聊消息（OneBot API）。"""
        return self.send({
            "action": "send_private_msg",
            "params": {"user_id": user_id, "message": message},
        })

    def _run(self) -> None:
        """WS 连接主循环（自动重连）。"""
        try:
            import websocket
            from websocket import WebSocketConnectionClosedException
        except ImportError:
            _log.error("websocket-client 未安装，WS 连接不可用")
            return

        connect_count = 0
        while self._running:
            try:
                if connect_count == 0:
                    _log.info("连接 WS: %s", self._url)
                else:
                    _log.debug("重连 WS (#%d): %s", connect_count, self._url)
                self._ws = websocket.WebSocket()
                # OneBot WS 认证: Authorization header
                headers = {}
                if self._token:
                    headers["Authorization"] = f"Bearer {self._token}"
                self._ws.connect(self._url, timeout=10, header=headers)
                self._connected = True
                if connect_count == 0:
                    _log.info("WS 连接成功")
                else:
                    _log.info("WS 重连成功 (#%d)", connect_count)
                connect_count += 1

                msg_count = 0
                while self._running:
                    try:
                        raw = self._ws.recv()
                    except WebSocketConnectionClosedException:
                        _log.warning("WS 断连原因: ConnectionClosed (已收 %d 条)", msg_count)
                        break
                    except Exception as e:
                        if self._running:
                            _log.warning("WS 断连原因: recv异常 %s: %s (已收 %d 条)",
                                         type(e).__name__, e, msg_count)
                        break

                    if raw is None:
                        _log.warning("WS 断连原因: recv返回None (已收 %d 条)", msg_count)
                        break

                    # 空帧跳过
                    if isinstance(raw, str) and raw.strip() == "":
                        continue
                    if isinstance(raw, bytes) and len(raw) == 0:
                        continue

                    msg_count += 1

                    # 解析 + 回调（回调异常不影响连接）
                    try:
                        data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode('utf-8'))
                    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
                        continue

                    if self._message_callback:
                        try:
                            self._message_callback(data)
                        except Exception as cb_err:
                            _log.debug("WS 回调异常(不断连): %s: %s",
                                       type(cb_err).__name__, cb_err)

            except Exception as e:
                if self._running:
                    _log.warning("WS 连接失败: %s (%.1fs 后重试)", e, self._reconnect_interval)
            finally:
                self._connected = False

            if self._running:
                time.sleep(self._reconnect_interval)


class WsClientLibrary(Library):
    """WebSocket 客户端库。"""

    name = "ws_client"
    version = "1.6.0"
    dependencies = ["config_store"]

    async def mount(self) -> None:
        config = self.services.get("config")
        url = config.get("网络连接.地址", "ws://127.0.0.1:3001")
        if not url:
            url = "ws://127.0.0.1:3001"
        token = config.get("网络连接.令牌", "") or ""

        client = WsClient(url, token=token)
        client.start()
        self.services.register("ws_client", client, mid=300)
        self._client = client

    async def unmount(self) -> None:
        if hasattr(self, "_client"):
            self._client.stop()

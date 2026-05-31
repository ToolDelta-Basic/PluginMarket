"""WebSocket 客户端服务，支持自动重连和 OneBot 消息收发。"""
import json
import threading
import time
import logging
from typing import Callable, Optional

try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False

from ..core.error_hints import hint


class WsClient:
    """WebSocket 客户端，负责连接 OneBot 实现端。"""

    def __init__(self, config: dict):
        """初始化 WebSocket 客户端。"""
        if not HAS_WEBSOCKET:
            raise ImportError(
                f"websocket-client 未安装，无法使用 WsClient。"
                f"请在控制台输入 qqdeps install 自动安装，"
                f"或手动执行: pip install websocket-client"
            )
        self.address = config.get("ws_address", "ws://127.0.0.1:8080")
        self.token = config.get("ws_token", "")
        self.ws: Optional[websocket.WebSocketApp] = None
        self.available = False
        self._on_message_callback: Optional[Callable[[dict], None]] = None
        self._reconnect = True
        self._thread: Optional[threading.Thread] = None
        self._initial_delay = 1
        self._max_delay = 60
        self._current_delay = self._initial_delay
        self._lock = threading.Lock()

        logging.getLogger("websocket").setLevel(logging.WARNING)

    def set_message_callback(self, callback: Callable[[dict], None]):
        """设置收到群消息时的回调函数。"""
        self._on_message_callback = callback

    def connect(self):
        """启动连接线程，自动重连。"""
        self._reconnect = True
        self._current_delay = self._initial_delay
        self._thread = threading.Thread(
            target=self._run_forever, daemon=True
        )
        self._thread.start()

    def disconnect(self):
        """关闭连接并停止重连（线程安全）。"""
        with self._lock:
            self._reconnect = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _run_forever(self):
        """后台线程：管理 WebSocket 连接与重连。"""
        logger = logging.getLogger(__name__)
        while True:
            with self._lock:
                if not self._reconnect:
                    break
            try:
                header = (
                    {"Authorization": f"Bearer {self.token}"}
                    if self.token
                    else None
                )
                self.ws = websocket.WebSocketApp(
                    self.address,
                    header=header,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.error(
                    "WebSocket 连接异常: %s → %s。%s",
                    type(e).__name__, e, hint.WS_CONNECT_FAILED,
                )
            self.available = False
            with self._lock:
                if not self._reconnect:
                    break
                delay = self._current_delay
                self._current_delay = min(
                    self._current_delay * 2, self._max_delay
                )
            # 首次失败给用户一个明确提示
            if delay == self._initial_delay:
                logger.warning(
                    "WebSocket 首次连接失败，将自动重试。%s",
                    hint.WS_CONNECT_FAILED,
                )
            logger.info("将在 %d 秒后重连...", delay)
            time.sleep(delay)

    def _on_open(self, ws):
        """连接建立回调。"""
        self.available = True
        with self._lock:
            self._current_delay = self._initial_delay
        logging.getLogger(__name__).info("已连接到 OneBot 服务器 (%s)", self.address)

    def _on_message(self, ws, message: str):
        """消息接收回调，只处理群消息并调用内部回调。"""
        try:
            data = json.loads(message)
        except Exception:
            return
        if (
            data.get("post_type") != "message"
            or data.get("message_type") != "group"
        ):
            return
        if self._on_message_callback:
            try:
                self._on_message_callback(data)
            except Exception as e:
                logging.getLogger(__name__).error(
                    "WS 消息回调异常: %s。%s",
                    e, hint.EVENT_HANDLER_FAILED,
                )

    @staticmethod
    def _on_error(ws, error):
        """错误回调。"""
        logging.getLogger(__name__).error(
            "WebSocket 传输错误: %s。可能是网络不稳定或 OneBot 服务异常。%s",
            error, hint.WS_CONNECT_FAILED,
        )

    def _on_close(self, ws, code, msg):
        """连接关闭回调。"""
        self.available = False
        self.ws = None
        logging.getLogger(__name__).info(
            "WebSocket 连接关闭 (code=%s, reason=%s)。%s",
            code or "?", (msg or "无")[:100],
            hint.WS_DISCONNECTED,
        )

    def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群消息（线程安全，防御 TOCTOU）。"""
        ws = self.ws
        if ws is None or not self.available:
            return False
        payload = json.dumps({
            "action": "send_group_msg",
            "params": {"group_id": group_id, "message": message},
        }).encode("utf-8")
        try:
            ws.send(payload)
            return True
        except Exception as e:
            logging.getLogger(__name__).error(
                "发送群消息失败 (group_id=%s): %s。%s",
                group_id, e, hint.WS_SEND_FAILED,
            )
            return False

    def send_private_msg(self, user_id: int, message: str) -> bool:
        """发送私聊消息（线程安全，防御 TOCTOU）。"""
        ws = self.ws
        if ws is None or not self.available:
            return False
        payload = json.dumps({
            "action": "send_private_msg",
            "params": {"user_id": user_id, "message": message},
        }).encode("utf-8")
        try:
            ws.send(payload)
            return True
        except Exception as e:
            logging.getLogger(__name__).error(
                "发送私聊消息失败 (user_id=%s): %s。%s",
                user_id, e, hint.WS_SEND_FAILED,
            )
            return False

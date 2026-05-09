# services/ws_client.py
"""WebSocket 客户端服务"""
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

class WsClient:
    def __init__(self, config: dict):
        if not HAS_WEBSOCKET:
            raise ImportError("websocket-client 未安装，无法使用 WsClient")
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

        # 关闭 websocket 库的调试日志
        logging.getLogger("websocket").setLevel(logging.WARNING)

    def set_message_callback(self, callback: Callable[[dict], None]):
        self._on_message_callback = callback

    def connect(self):
        self._reconnect = True
        self._current_delay = self._initial_delay
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def disconnect(self):
        self._reconnect = False
        if self.ws:
            self.ws.close()

    def _run_forever(self):
        logger = logging.getLogger(__name__)
        while self._reconnect:
            try:
                header = {"Authorization": f"Bearer {self.token}"} if self.token else None
                self.ws = websocket.WebSocketApp(
                    self.address,
                    header=header,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.error("连接异常: %s", e)
            self.available = False
            if not self._reconnect:
                break
            with self._lock:
                delay = self._current_delay
                self._current_delay = min(self._current_delay * 2, self._max_delay)
            logger.info("将在 %d 秒后重连...", delay)
            time.sleep(delay)

    def _on_open(self, ws):
        self.available = True
        with self._lock:
            self._current_delay = self._initial_delay
        logging.getLogger(__name__).info("已连接到 WS 服务器")

    def _on_message(self, ws, message: str):
        try:
            data = json.loads(message)
        except:
            return
        if data.get("post_type") != "message" or data.get("message_type") != "group":
            return
        if self._on_message_callback:
            self._on_message_callback(data)

    def _on_error(self, ws, error):
        logging.getLogger(__name__).error("WS 错误: %s", error)

    def _on_close(self, ws, code, msg):
        self.available = False
        logging.getLogger(__name__).info("WS 连接关闭")

    def send_group_msg(self, group_id: int, message: str) -> bool:
        logger = logging.getLogger(__name__)
        if not self.ws or not self.available:
            return False
        data = {
            "action": "send_group_msg",
            "params": {"group_id": group_id, "message": message}
        }
        try:
            self.ws.send(json.dumps(data).encode('utf-8'))
            return True
        except Exception as e:
            logger.error("发送群消息失败: %s", e)
            return False

    def send_private_msg(self, user_id: int, message: str) -> bool:
        logger = logging.getLogger(__name__)
        if not self.ws or not self.available:
            return False
        data = {
            "action": "send_private_msg",
            "params": {"user_id": user_id, "message": message}
        }
        try:
            self.ws.send(json.dumps(data).encode('utf-8'))
            return True
        except Exception as e:
            logger.error("发送私聊消息失败: %s", e)
            return False
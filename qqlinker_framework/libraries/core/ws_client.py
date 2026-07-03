import json
import logging
import random
import threading
import time
from typing import Any, Callable, Optional

from ..channel_host import Library

_log = logging.getLogger(__name__)

# 断路器参数
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RECOVERY_TIMEOUT = 30
CIRCUIT_PROBE_COUNT = 2


class WsClient:
    """WebSocket 客户端 — OneBot 双认证 + 心跳 + 断路器。

    对比 v1.6.0 修复：
      - ping/pong 心跳（WebSocketApp.run_forever ping_interval）
      - 双认证（Header + URL access_token）
      - 断路器 + 指数退避
      - recv 超时检测
    """

    def __init__(self, url: str, token: str = "", reconnect_interval: float = 5.0):
        self._url = url
        self._token = token
        self._reconnect_interval = reconnect_interval
        self._ws = None  # type: Optional["websocket.WebSocketApp"]
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._message_callback: Optional[Callable[[dict], Any]] = None
        self._connected = False

        # 断路器状态
        self._circuit_failures = 0
        self._circuit_opened_at: float = 0.0
        self._circuit_open = False
        self._circuit_half_open = False

        # 退避参数
        self._initial_delay = 1.0
        self._max_delay = 60.0
        self._current_delay = self._initial_delay
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        return self._url

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def circuit_open(self) -> bool:
        """查询断路器是否处于熔断状态。"""
        return self._circuit_open

    def set_message_callback(self, callback: Callable[[dict], Any]) -> None:
        """设置消息回调（收到 WS 消息时调用）。"""
        self._message_callback = callback

    def start(self) -> None:
        """启动 WS 连接线程。"""
        self._running = True
        self._circuit_failures = 0
        self._circuit_open = False
        self._circuit_half_open = False
        self._current_delay = self._initial_delay
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止连接。"""
        self._running = False
        ws = self._ws
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    def send(self, data: dict) -> bool:
        """发送 JSON 消息。"""
        if self._circuit_open:
            return False
        ws = self._ws
        if ws is None or not self._connected:
            return False
        try:
            ws.send(json.dumps(data, ensure_ascii=False))
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

    # ── 连接主循环 ──────────────────────────────────────────

    def _run(self) -> None:
        """连接主循环（WebSocketApp + 断路器 + 指数退避）。"""
        try:
            import websocket
        except ImportError:
            _log.error("websocket-client 未安装，WS 连接不可用")
            return

        while self._running:
            # ── 断路器：OPEN 时等待恢复窗口 ──
            if self._circuit_open:
                self._maybe_probe_recovery()
                if self._circuit_open:
                    time.sleep(5)
                    continue

            try:
                # ── 双认证：Header + URL access_token ──
                addr = self._url
                headers = {}
                if self._token:
                    headers["Authorization"] = f"Bearer {self._token}"
                    sep = "&" if "?" in addr else "?"
                    addr = f"{addr}{sep}access_token={self._token}"

                _log.info("连接 WS: %s", self._url)
                _log.debug("Token=%s", self._mask_token(self._token))

                ws_kwargs = {
                    "on_open": self._on_open,
                    "on_message": self._on_message,
                    "on_error": self._on_error,
                    "on_close": self._on_close,
                }
                if headers:
                    ws_kwargs["header"] = headers

                self._ws = websocket.WebSocketApp(addr, **ws_kwargs)
                self._ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10,
                    ping_payload="keepalive",
                )

            except Exception as e:
                if self._running:
                    _log.warning("WS 连接异常: %s (%.1fs 后重试)",
                                 e, self._reconnect_interval)

            self._connected = False
            self._on_failure()

            if self._running:
                delay = self._current_delay
                self._current_delay = min(
                    self._current_delay * 1.5, self._max_delay
                )
                # 25% 随机抖动，避免重连风暴
                jittered = delay + random.uniform(-delay * 0.25, delay * 0.25)
                time.sleep(jittered)

    # ── WebSocketApp 回调 ───────────────────────────────────

    def _on_open(self, ws) -> None:
        """连接成功。"""
        self._connected = True
        with self._lock:
            self._current_delay = self._initial_delay
        self._on_connect_success()
        _log.info("WS 连接成功 (%s)", self._url)

    def _on_message(self, ws, message: str) -> None:
        """消息接收。"""
        if not self._message_callback:
            return

        # 空帧跳过
        if isinstance(message, str) and message.strip() == "":
            return
        if isinstance(message, bytes) and len(message) == 0:
            return

        # 解析 JSON
        try:
            data = json.loads(message) if isinstance(message, str) else json.loads(message.decode("utf-8"))
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
            return

        # 回调（异常不断连）
        try:
            self._message_callback(data)
        except Exception as e:
            _log.debug("WS 回调异常(不断连): %s: %s",
                       type(e).__name__, e)

    @staticmethod
    def _on_error(ws, error) -> None:
        """错误回调。"""
        err_type = type(error).__name__
        err_msg = str(error)[:200] if error else "(无)"
        _log.error("WS 传输错误 (%s): %s", err_type, err_msg)

    def _on_close(self, ws, code, msg) -> None:
        """连接关闭回调。"""
        self._connected = False
        self._ws = None
        _log.info("WS 连接关闭 (code=%s, reason=%s)",
                  code or "?", (msg or "无")[:100])

    # ── 断路器逻辑 ──────────────────────────────────────────

    def _on_connect_success(self) -> None:
        """连接成功 → 重置断路器。"""
        if self._circuit_open or self._circuit_half_open:
            _log.info("断路器恢复 → CLOSED")
        self._circuit_failures = 0
        self._circuit_open = False
        self._circuit_half_open = False

    def _on_failure(self) -> None:
        """连接失败 → 累加失败计数。"""
        self._circuit_failures += 1
        if self._circuit_half_open:
            # 探测失败立即回 OPEN
            _log.warning("断路器探测失败，重新熔断 (尝试 %d/%d)",
                         self._circuit_failures, CIRCUIT_PROBE_COUNT)
            if self._circuit_failures >= CIRCUIT_PROBE_COUNT:
                self._circuit_open = True
                self._circuit_half_open = False
                self._circuit_opened_at = time.time()
        elif self._circuit_failures >= CIRCUIT_FAILURE_THRESHOLD:
            self._circuit_open = True
            self._circuit_opened_at = time.time()
            _log.warning(
                "⚡ WebSocket 断路器已熔断 (连续 %d 次失败)。"
                "将在 %d 秒后尝试探测恢复。",
                self._circuit_failures, CIRCUIT_RECOVERY_TIMEOUT,
            )

    def _maybe_probe_recovery(self) -> None:
        """熔断超时 → HALF_OPEN 探测。"""
        if not self._circuit_open:
            return
        elapsed = time.time() - self._circuit_opened_at
        if elapsed >= CIRCUIT_RECOVERY_TIMEOUT:
            _log.info("断路器探测中 (HALF_OPEN) — 尝试恢复...")
            self._circuit_open = False
            self._circuit_half_open = True
            self._circuit_failures = 0

    # ── 工具 ────────────────────────────────────────────────

    @staticmethod
    def _mask_token(token: str) -> str:
        if not token:
            return "(无)"
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}***{token[-4:]}"


class WsClientLibrary(Library):
    """WebSocket 客户端库。"""

    name = "ws_client"
    version = "1.6.1"
    dependencies = ["config_store"]

    async def mount(self) -> None:
        config = self.services.get("config")
        url = config.get("网络连接.地址", "ws://127.0.0.1:3001", requester_uid=0)
        if not url:
            url = "ws://127.0.0.1:3001"
        token = config.get("网络连接.令牌", "", requester_uid=0) or ""

        client = WsClient(url, token=token)
        client.start()
        self.services.register("ws_client", client, mid=300)
        self._client = client

    async def unmount(self) -> None:
        if hasattr(self, "_client"):
            self._client.stop()

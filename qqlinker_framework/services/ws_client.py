"""WebSocket 客户端服务，支持自动重连、断路器保护和 OneBot 消息收发。"""
import json
import random
import ssl
import threading
import time
import logging
import enum
import importlib
from typing import Callable, Optional

from ..core.kernel.error_hints import hint


def _get_websocket():
    """延迟导入 websocket 模块（确保 sys.path 已设置）。"""
    import websocket as _ws
    return _ws


def _json_depth(obj, _current=0):
    """递归计算 JSON 对象的最大嵌套深度。

    数组和字典均计入深度，防止深度嵌套数组绕过 DoS 保护。
    """
    if isinstance(obj, dict):
        if not obj:
            return _current
        return max(_json_depth(v, _current + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return _current
        return max(_json_depth(v, _current + 1) for v in obj)
    return _current


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class WsClient:
    """WebSocket 客户端，连接 OneBot 实现端。

    内建断路器模式：连续失败 N 次后熔断，定时探测恢复。
    """

    # 断路器参数
    CIRCUIT_FAILURE_THRESHOLD = 5      # 连续失败多少次后熔断
    CIRCUIT_RECOVERY_TIMEOUT = 30      # 熔断后多少秒尝试探测
    CIRCUIT_PROBE_COUNT = 2            # 探测阶段允许的尝试次数

    # 消息安全限制
    MAX_MESSAGE_BYTES = 1024 * 1024    # 单条消息最大 1MB
    MAX_JSON_DEPTH = 10                # JSON 嵌套最大深度

    def __init__(self, config: dict):
        try:
            _get_websocket()
        except ImportError:
            raise ImportError(
                "websocket-client 未安装，无法使用 WsClient。"
                "请在控制台输入 qqdeps install 自动安装，"
                "或手动执行: pip install websocket-client"
            )
        self.address = config.get("ws_address", "ws://127.0.0.1:8080")
        self.token = config.get("ws_token", "")
        self.ws = None  # type: "websocket.WebSocketApp"
        self.available = False
        self._on_message_callback: Optional[Callable[[dict], None]] = None
        self._reconnect = True
        self._thread: Optional[threading.Thread] = None
        self._initial_delay = 1
        self._max_delay = 60
        self._current_delay = self._initial_delay
        self._lock = threading.Lock()

        # TLS / 超时配置
        self._tls_verify_mode: str = config.get(
            "网络传输.TLS验证模式", "enabled"
        )
        self._connect_timeout: int = config.get(
            "网络传输.连接超时秒", 10
        )
        self._read_timeout: int = config.get(
            "网络传输.读超时秒", 30
        )
        self._ssl_context: Optional[ssl.SSLContext] = None
        if self.address.startswith("wss://"):
            self._ssl_context = self._build_ssl_context()

        # 断路器状态
        self._circuit_state = CircuitState.CLOSED
        self._circuit_failures = 0
        self._circuit_opened_at: float = 0.0

        logging.getLogger("websocket").setLevel(logging.WARNING)

    # ── TLS ──

    def _build_ssl_context(self) -> ssl.SSLContext:
        """根据配置构建 SSL 上下文。

        TLS验证模式:
          - "enabled": 完全证书验证（生产推荐）
          - "skip": 跳过证书验证（仅调试/内网）
        """
        if self._tls_verify_mode == "skip":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            logging.getLogger(__name__).warning(
                "⚠️ TLS 证书验证已跳过 (TLS验证模式=skip)。"
                "这仅在调试或可信内网中安全。%s",
                hint["WS_CONNECT_FAILED"],
            )
            return ctx
        return ssl.create_default_context()

    @staticmethod
    def _mask_token(token: str) -> str:
        """遮蔽 Token，日志中只显示前后各 4 字符。"""
        if not token:
            return "(无)"
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}***{token[-4:]}"

    def set_message_callback(self, callback: Callable[[dict], None]):
        """设置收到群消息时的回调函数。"""
        self._on_message_callback = callback

    def connect(self):
        """启动连接线程，自动重连。"""
        self._reconnect = True
        self._current_delay = self._initial_delay
        self._circuit_state = CircuitState.CLOSED
        self._circuit_failures = 0
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

    def is_circuit_open(self) -> bool:
        """查询断路器是否处于熔断状态。"""
        return self._circuit_state == CircuitState.OPEN

    # ── 断路器逻辑 ──

    def _on_connect_success(self):
        """连接成功：重置断路器。"""
        self._circuit_failures = 0
        if self._circuit_state != CircuitState.CLOSED:
            logging.getLogger(__name__).info("断路器恢复 → CLOSED")
        self._circuit_state = CircuitState.CLOSED

    def _on_connect_failure(self):
        """连接失败：累加失败计数，达到阈值触发熔断。"""
        logger = logging.getLogger(__name__)
        self._circuit_failures += 1
        if self._circuit_state == CircuitState.HALF_OPEN:
            # 探测阶段失败立即回 OPEN
            logger.warning("断路器探测失败，重新熔断 (尝试 %d/%d)",
                           self._circuit_failures, self.CIRCUIT_PROBE_COUNT)
            if self._circuit_failures >= self.CIRCUIT_PROBE_COUNT:
                self._circuit_state = CircuitState.OPEN
                self._circuit_opened_at = time.time()
        elif self._circuit_failures >= self.CIRCUIT_FAILURE_THRESHOLD:
            self._circuit_state = CircuitState.OPEN
            self._circuit_opened_at = time.time()
            logger.warning(
                "⚡ WebSocket 断路器已熔断 (连续 %d 次失败)。"
                "将在 %d 秒后尝试探测恢复。消息收发将暂停。",
                self._circuit_failures, self.CIRCUIT_RECOVERY_TIMEOUT,
            )

    def _maybe_probe_recovery(self):
        """熔断超时后进入 HALF_OPEN 探测状态。"""
        if self._circuit_state != CircuitState.OPEN:
            return
        elapsed = time.time() - self._circuit_opened_at
        if elapsed >= self.CIRCUIT_RECOVERY_TIMEOUT:
            logging.getLogger(__name__).info(
                "断路器探测中 (HALF_OPEN) — 尝试恢复连接..."
            )
            self._circuit_state = CircuitState.HALF_OPEN
            self._circuit_failures = 0

    # ── 连接管理 ──

    @staticmethod
    def _jitter(delay: float) -> float:
        """给延迟加 ±25% 随机抖动，防止重连风暴。"""
        jitter_range = delay * 0.25
        return delay + random.uniform(-jitter_range, jitter_range)

    def _run_forever(self):
        """后台线程：管理 WebSocket 连接与重连，含断路器。"""
        logger = logging.getLogger(__name__)
        while True:
            with self._lock:
                if not self._reconnect:
                    break

            # 断路器：OPEN 时等待恢复窗口
            if self._circuit_state == CircuitState.OPEN:
                self._maybe_probe_recovery()
                if self._circuit_state == CircuitState.OPEN:
                    time.sleep(5)  # 熔断期间慢速轮询
                    continue

            try:
                # OneBot 协议: 优先通过 Authorization 请求头传递 token，
                # 避免 URL 参数被代理/负载均衡器/应用日志记录。
                # 保留 URL 参数作为 fallback（部分旧版 OneBot 实现不支持 header 认证）。
                addr = self.address
                ws_mod = _get_websocket()
                ws_kwargs = {
                    "on_open": self._on_open,
                    "on_message": self._on_message,
                    "on_error": self._on_error,
                    "on_close": self._on_close,
                }
                if self.token:
                    ws_kwargs["header"] = {
                        "Authorization": f"Bearer {self.token}"
                    }
                    # Fallback: URL 参数认证
                    sep = "&" if "?" in addr else "?"
                    addr = f"{addr}{sep}access_token={self.token}"
                    logger.info(
                        "正在连接 %s (Token=%s, TLS=%s)...",
                        self.address,
                        self._mask_token(self.token),
                        self._tls_verify_mode,
                    )
                if self._ssl_context is not None:
                    ws_kwargs["sslopt"] = {"context": self._ssl_context}
                self.ws = ws_mod.WebSocketApp(addr, **ws_kwargs)
                self.ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10,
                    ping_payload="keepalive",
                )
            except Exception as e:
                logger.error(
                    "WebSocket 连接异常: %s → %s。%s",
                    type(e).__name__, e, hint["WS_CONNECT_FAILED"],
                )
            self.available = False
            self._on_connect_failure()

            with self._lock:
                if not self._reconnect:
                    break
                delay = self._current_delay
                self._current_delay = min(
                    self._current_delay * 2, self._max_delay
                )
            jittered = self._jitter(delay)
            if delay == self._initial_delay:
                logger.warning(
                    "WebSocket 首次连接失败，将自动重试。%s",
                    hint["WS_CONNECT_FAILED"],
                )
            logger.info(
                "将在 %.1f 秒后重连 (base=%ds)...", jittered, delay
            )
            time.sleep(jittered)

    def _on_open(self, ws):
        """连接建立回调。"""
        self.available = True
        with self._lock:
            self._current_delay = self._initial_delay
        self._on_connect_success()
        logging.getLogger(__name__).info(
            "已连接到 OneBot 服务器 (%s, Token=%s)",
            self.address, self._mask_token(self.token),
        )

    def _on_message(self, ws, message: str):
        """消息接收回调。"""
        # ── 大小限制：超过 1MB 丢弃 ──
        if len(message.encode("utf-8")) > self.MAX_MESSAGE_BYTES:
            logging.getLogger(__name__).warning(
                "收到超大 WS 消息 (%d 字节)，已丢弃。%s",
                len(message.encode("utf-8")), hint["WS_MESSAGE_INVALID"],
            )
            return

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logging.getLogger(__name__).warning(
                "收到畸形 JSON 消息 (%d 字节)，已丢弃。%s",
                len(message), hint["WS_MESSAGE_INVALID"],
            )
            return
        except Exception:
            return

        # ── 深度检查：JSON 嵌套不超过 10 层 ──
        if _json_depth(data) > self.MAX_JSON_DEPTH:
            logging.getLogger(__name__).warning(
                "WS 消息 JSON 嵌套过深 (max=%d)，已丢弃。%s",
                self.MAX_JSON_DEPTH, hint["WS_MESSAGE_INVALID"],
            )
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
                    e, hint["EVENT_HANDLER_FAILED"],
                )

    @staticmethod
    def _on_error(ws, error):
        """错误回调。只记录类型和简短描述，不泄露完整 traceback。"""
        err_type = type(error).__name__
        err_msg = str(error)[:200] if error else "(无详细信息)"
        logging.getLogger(__name__).error(
            "WebSocket 传输错误 (%s): %s。%s",
            err_type, err_msg, hint["WS_CONNECT_FAILED"],
        )

    def _on_close(self, ws, code, msg):
        """连接关闭回调。"""
        self.available = False
        self.ws = None
        logging.getLogger(__name__).info(
            "WebSocket 连接关闭 (code=%s, reason=%s)。%s",
            code or "?", (msg or "无")[:100],
            hint["WS_DISCONNECTED"],
        )

    def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群消息。TOCTOU 已防御: ws 引用捕获 + try/except。"""
        if self._circuit_state == CircuitState.OPEN:
            logging.getLogger(__name__).warning(
                "断路器已熔断，消息发送被跳过 (group_id=%s)", group_id
            )
            return False
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
                group_id, e, hint["WS_SEND_FAILED"],
            )
            return False

    def send_private_msg(self, user_id: int, message: str) -> bool:
        """发送私聊消息。TOCTOU 已防御: ws 引用捕获 + try/except。"""
        if self._circuit_state == CircuitState.OPEN:
            logging.getLogger(__name__).warning(
                "断路器已熔断，消息发送被跳过 (user_id=%s)", user_id
            )
            return False
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
                user_id, e, hint["WS_SEND_FAILED"],
            )
            return False

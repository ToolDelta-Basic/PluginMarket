from __future__ import annotations

import json
import logging
import uuid as _uuid

logger = logging.getLogger(__name__)

# 预定义错误码
ERR_METHOD_NOT_FOUND = -1
ERR_TIMEOUT         = -2
ERR_PARSE           = -3
ERR_INTERNAL        = -4
ERR_DISCONNECTED    = -5

# 全局方法注册表: REGISTRY[method] = async_callable
REGISTRY: dict[str, object] = {}


class IPCError(RuntimeError):
    """IPC 协议层异常."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"[IPC {code}] {message}")
        self.code = code
        self.raw_message = message


# ---------------------------------------------------------------------------
# 编解码
# ---------------------------------------------------------------------------

class Encoder(json.JSONEncoder):
    """定制 JSON 编码器，确保 float 精度."""

    pass


def _decode_line(line: str) -> dict:
    """解析一行 JSON，返回 dict。失败时抛出 IPCError."""
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise IPCError(ERR_PARSE, f"Invalid JSON line: {exc}") from exc


def _encode_message(msg: dict) -> bytes:
    """将 dict 编码为一行 JSON + 换行."""
    return (json.dumps(msg, cls=Encoder, ensure_ascii=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# 构造工厂
# ---------------------------------------------------------------------------

def make_request(method: str, params: dict | None = None) -> dict:
    """创建请求消息."""
    return {
        "id": _uuid.uuid4().hex,
        "method": method,
        "params": params or {},
        "ts": __import__("time").time(),
    }


def make_response(request_id: str, result: object) -> dict:
    """创建成功响应."""
    return {"id": request_id, "result": result}


def make_error(request_id: str, code: int, message: str) -> dict:
    """创建错误响应."""
    return {"id": request_id, "error": {"code": code, "message": message}}


def make_event(event: str, data: dict | None = None) -> dict:
    """创建推送事件."""
    return {"event": event, "data": data or {}}


def is_request(msg: dict) -> bool:
    """是否为请求消息."""
    return "id" in msg and "method" in msg


def is_response(msg: dict) -> bool:
    """是否为成功响应."""
    return "id" in msg and "result" in msg and "method" not in msg


def is_error(msg: dict) -> bool:
    """是否为错误响应."""
    return "id" in msg and "error" in msg


def is_event(msg: dict) -> bool:
    """是否为推送事件."""
    return "event" in msg and "id" not in msg


# ---------------------------------------------------------------------------
# 版本协商
# ---------------------------------------------------------------------------

IPC_VERSION = 2

DEFAULT_CAPABILITIES = [
    "group_message", "send_group_msg", "send_private_msg",
    "game_command", "player_list", "freeze_module", "thaw_module",
    "telemetry_snapshot",
]

HELLO_MSG = {
    "type": "HELLO",
    "version": IPC_VERSION,
    "capabilities": DEFAULT_CAPABILITIES,
}

HELLO_ACK_MSG = {
    "type": "HELLO_ACK",
    "version": IPC_VERSION,
    "capabilities": DEFAULT_CAPABILITIES,
}


def is_hello(msg: dict) -> bool:
    """是否为 HELLO 握手消息."""
    return msg.get("type") == "HELLO" and "version" in msg


def is_hello_ack(msg: dict) -> bool:
    """是否为 HELLO_ACK 握手回复."""
    return msg.get("type") == "HELLO_ACK" and "version" in msg


def make_hello(version: int = IPC_VERSION, capabilities: list | None = None) -> dict:
    """创建 HELLO 握手消息."""
    return {
        "type": "HELLO",
        "version": version,
        "capabilities": capabilities or DEFAULT_CAPABILITIES,
    }


def make_hello_ack(version: int = IPC_VERSION, capabilities: list | None = None) -> dict:
    """创建 HELLO_ACK 握手回复."""
    return {
        "type": "HELLO_ACK",
        "version": version,
        "capabilities": capabilities or DEFAULT_CAPABILITIES,
    }


def negotiate_capabilities(client_caps: list, server_caps: list) -> list:
    """协商共同支持的能力集.

    Args:
        client_caps: 客户端声明的能力列表.
        server_caps: 服务端声明的能力列表.
    Returns:
        双方共同支持的能力列表（交集）。
    """
    return list(set(client_caps) & set(server_caps))

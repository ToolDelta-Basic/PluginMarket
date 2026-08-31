from .protocol import IPCError, REGISTRY
from .client import IPCClient
from .server import IPCServer
from .pool import WorkerPool
from .game_proxy import GameProxy, PermissionGateway, RPC_METHODS
from .shell import Shell
from .integration import IPCAdapterProxy

# ── IPC Bridge (事件序列化 + LaneRouter 桥接) ──
from .bridge import EventSerializer, IPCBridgeProtocol

__all__ = [
    "IPCClient",
    "IPCServer",
    "WorkerPool",
    "IPCError",
    "REGISTRY",
    "RPC_METHODS",
    "GameProxy",
    "PermissionGateway",
    "Shell",
    "IPCAdapterProxy",
    # Bridge
    "EventSerializer",
    "IPCBridgeProtocol",
]

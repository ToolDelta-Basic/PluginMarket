"""QQLinker IPC 安全层 — 进程隔离 + 权限网关。

架构：
    宿主进程 (ToolDelta)
    ├─ Shell → IPCServer → PermissionGateway → game_ctrl

    框架进程 (QQLinker)
    ├─ IPCClient → GameProxy / IPCAdapterProxy
"""

from .protocol import IPCError, REGISTRY
from .client import IPCClient
from .server import IPCServer
from .pool import WorkerPool
from .game_proxy import GameProxy, PermissionGateway, RPC_METHODS
from .shell import Shell
from .integration import IPCAdapterProxy

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
]

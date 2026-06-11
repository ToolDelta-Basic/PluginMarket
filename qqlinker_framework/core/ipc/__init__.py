"""core.ipc — 进程间通信模块.

导出:
    IPCClient  — Unix socket 客户端
    IPCServer  — Unix socket 服务端
    WorkerPool — 子进程管理池
    IPCError   — IPC 协议异常
"""

from .protocol import IPCError, REGISTRY
from .client import IPCClient
from .server import IPCServer
from .pool import WorkerPool

__all__ = ["IPCClient", "IPCServer", "WorkerPool", "IPCError", "REGISTRY"]

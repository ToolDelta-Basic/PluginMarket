"""Worker 主进程 — 注册全部服务方法并启动 IPC 服务.

注册方法:
    ai.chat, dedup.check, dedup.add, audit.record, stats.report, ping

启动方式:
    python -m core.ipc.worker <socket_path>
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from qqlinker_framework.core.ipc.server import IPCServer
from qqlinker_framework.core.ipc.protocol import ERR_INTERNAL, IPCError

logger = logging.getLogger("worker")

# ---------------------------------------------------------------------------
# 桩处理器
# ---------------------------------------------------------------------------

async def _handle_ai_chat(params: dict) -> dict:
    logger.info("ai.chat called: %s", params)
    return {
        "reply": f"echo: {params.get('message', '')}",
        "model": "stub",
        "tokens": len(params.get("message", "")),
    }


async def _handle_dedup_check(params: dict) -> dict:
    logger.info("dedup.check called: %s", params)
    # 桩：总是返回不重复
    return {"duplicate": False, "similarity": 0.0}


async def _handle_dedup_add(params: dict) -> dict:
    logger.info("dedup.add called: %s", params)
    return {"ok": True}


async def _handle_audit_record(params: dict) -> dict:
    logger.info("audit.record called: action=%s user=%s", params.get("action"), params.get("user"))
    return {"recorded": True, "id": f"audit-{int(time.time() * 1000)}"}


async def _handle_stats_report(params: dict) -> dict:
    logger.info("stats.report called: %s", params)
    return {
        "uptime": time.time(),  # stub
        "requests": 0,
        "errors": 0,
    }


async def _handle_ping(params: dict) -> dict:
    return {"pong": True, "ts": time.time()}


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

REGISTRY = {
    "ai.chat": _handle_ai_chat,
    "dedup.check": _handle_dedup_check,
    "dedup.add": _handle_dedup_add,
    "audit.record": _handle_audit_record,
    "stats.report": _handle_stats_report,
    "ping": _handle_ping,
}


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    """Worker 主入口."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <socket_path>", file=sys.stderr)
        sys.exit(1)
    socket_path = sys.argv[1]

    async def run() -> None:
        server = IPCServer(socket_path)
        for method, handler in REGISTRY.items():
            server.register(method, handler)
        async with server:
            # 保持运行直到被信号终止
            while True:
                await asyncio.sleep(3600)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Worker shutting down")


if __name__ == "__main__":
    main()

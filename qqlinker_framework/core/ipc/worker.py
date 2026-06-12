"""Worker 主进程 — 注册全部服务方法并启动 IPC 服务.

注册方法:
    registry.set_enabled, registry.is_enabled, registry.get_all, registry.auto_register
    registry.stats, registry.get_entry, registry.remove_entry
    module.reload, module.unload
    ai.chat, dedup.check, dedup.add, audit.record, stats.report, ping

启动方式:
    python -m core.ipc.worker <socket_path> [--data-path <path>]
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import Optional

from .server import IPCServer
from .protocol import ERR_INTERNAL, IPCError
from ..drivers.registry import ModuleRegistry
from qqlinker_framework.管理 import file_watcher_main

logger = logging.getLogger("worker")

# ── 全局注册表实例（worker 进程内单例）──
_registry: Optional[ModuleRegistry] = None


def _get_registry() -> ModuleRegistry:
    if _registry is None:
        raise IPCError(ERR_INTERNAL, "注册表未初始化（缺少 --data-path 参数）")
    return _registry


# ═══════════════════════════════════════════════════════════════
# 注册表服务方法
# ═══════════════════════════════════════════════════════════════

async def _registry_set_enabled(params: dict) -> dict:
    """设置模块启用状态。params: {module_name, enabled}"""
    reg = _get_registry()
    name = params.get("module_name", "")
    enabled = params.get("enabled", False)
    if not name:
        raise IPCError(ERR_INTERNAL, "缺少 module_name")
    ok = reg.set_enabled(name, enabled)
    return {"ok": ok, "module_name": name, "enabled": enabled}


async def _registry_is_enabled(params: dict) -> dict:
    """查询模块是否启用。params: {module_name}"""
    reg = _get_registry()
    name = params.get("module_name", "")
    if not name:
        raise IPCError(ERR_INTERNAL, "缺少 module_name")
    return {"module_name": name, "enabled": reg.is_enabled(name)}


async def _registry_get_all(params: dict) -> dict:
    """获取所有已启用模块列表。"""
    reg = _get_registry()
    entries = reg.get_all_entries()
    return {"modules": entries}


async def _registry_auto_register(params: dict) -> dict:
    """自动注册新模块。params: {module_names: [str]}"""
    reg = _get_registry()
    names = params.get("module_names", [])
    if not isinstance(names, list):
        raise IPCError(ERR_INTERNAL, "module_names 必须是 list")
    new_modules = reg.auto_register(names)
    return {"new_modules": list(new_modules)}


async def _registry_stats(params: dict) -> dict:
    """获取注册表统计。"""
    reg = _get_registry()
    return reg.stats()


async def _registry_get_entry(params: dict) -> dict:
    """获取单个模块的注册表条目。"""
    reg = _get_registry()
    name = params.get("module_name", "")
    if not name:
        raise IPCError(ERR_INTERNAL, "缺少 module_name")
    entry = reg.get_entry(name)
    if entry is None:
        return {"module_name": name, "found": False}
    return {"module_name": name, "found": True, "entry": entry}


async def _registry_remove_entry(params: dict) -> dict:
    """从注册表删除模块条目。"""
    reg = _get_registry()
    name = params.get("module_name", "")
    if not name:
        raise IPCError(ERR_INTERNAL, "缺少 module_name")
    ok = reg.remove_entry(name)
    return {"ok": ok, "module_name": name}


# ═══════════════════════════════════════════════════════════════
# 模块管理服务方法
# ═══════════════════════════════════════════════════════════════

async def _module_reload(params: dict) -> dict:
    """重载模块（由主进程实际执行，这里只返回请求确认）。"""
    name = params.get("module_name", "")
    if not name:
        raise IPCError(ERR_INTERNAL, "缺少 module_name")
    return {"ok": True, "module_name": name, "action": "reload"}


async def _module_unload(params: dict) -> dict:
    """卸载模块（由主进程实际执行，这里只返回请求确认）。"""
    name = params.get("module_name", "")
    if not name:
        raise IPCError(ERR_INTERNAL, "缺少 module_name")
    return {"ok": True, "module_name": name, "action": "unload"}


# ═══════════════════════════════════════════════════════════════
# 原有桩处理器
# ═══════════════════════════════════════════════════════════════

async def _handle_ai_chat(params: dict) -> dict:
    logger.info("ai.chat called: %s", params)
    return {
        "reply": f"echo: {params.get('message', '')}",
        "model": "stub",
        "tokens": len(params.get("message", "")),
    }


async def _handle_dedup_check(params: dict) -> dict:
    logger.info("dedup.check called: %s", params)
    return {"duplicate": False, "similarity": 0.0}


async def _handle_dedup_add(params: dict) -> dict:
    logger.info("dedup.add called: %s", params)
    return {"ok": True}


async def _handle_audit_record(params: dict) -> dict:
    logger.info(
        "audit.record called: action=%s user=%s",
        params.get("action"), params.get("user"),
    )
    return {"recorded": True, "id": f"audit-{int(time.time() * 1000)}"}


async def _handle_stats_report(params: dict) -> dict:
    logger.info("stats.report called: %s", params)
    return {
        "uptime": time.time(),
        "requests": 0,
        "errors": 0,
    }


async def _handle_ping(params: dict) -> dict:
    return {"pong": True, "ts": time.time()}


# ═══════════════════════════════════════════════════════════════
# 注册表
# ═══════════════════════════════════════════════════════════════

REGISTRY = {
    # 注册表服务
    "registry.set_enabled": _registry_set_enabled,
    "registry.is_enabled": _registry_is_enabled,
    "registry.get_all": _registry_get_all,
    "registry.auto_register": _registry_auto_register,
    "registry.stats": _registry_stats,
    "registry.get_entry": _registry_get_entry,
    "registry.remove_entry": _registry_remove_entry,
    # 模块管理
    "module.reload": _module_reload,
    "module.unload": _module_unload,
    # 原有桩
    "ai.chat": _handle_ai_chat,
    "dedup.check": _handle_dedup_check,
    "dedup.add": _handle_dedup_add,
    "audit.record": _handle_audit_record,
    "stats.report": _handle_stats_report,
    "ping": _handle_ping,
}


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    """Worker 主入口。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    import argparse
    parser = argparse.ArgumentParser(description="QQLinker IPC Worker")
    parser.add_argument("socket_path", help="Unix socket 路径")
    parser.add_argument("--data-path", default=None, help="数据目录路径")
    parser.add_argument("--no-file-watcher", action="store_true",
                        help="禁用文件监控 Worker")
    args = parser.parse_args()

    socket_path = args.socket_path
    data_path = args.data_path

    # 初始化注册表（如果有 data_path）
    global _registry
    if data_path:
        _registry = ModuleRegistry(data_path)
        logger.info("注册表已初始化: %s", _registry.stats())

    async def run() -> None:
        server = IPCServer(socket_path)
        for method, handler in REGISTRY.items():
            server.register(method, handler)

        # 启动文件监控 worker（如果提供了 data_path 且未禁用）
        file_watcher_task = None
        if data_path and not args.no_file_watcher:
            file_watcher_task = asyncio.create_task(
                file_watcher_main(data_path, socket_path)
            )

        async with server:
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
            finally:
                if file_watcher_task:
                    file_watcher_task.cancel()
                    try:
                        await file_watcher_task
                    except asyncio.CancelledError:
                        pass

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Worker shutting down")


if __name__ == "__main__":
    main()

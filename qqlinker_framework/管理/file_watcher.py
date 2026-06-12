"""文件监控 Worker — 通过 IPC 通知主进程模块目录变化

═══════════════════════════════════════════════════════════════════════════
 设计
═══════════════════════════════════════════════════════════════════════════
 · 作为 WorkerPool 的一个子进程运行
 · 通过 Unix socket IPC 与主进程通信
 · 调用 IPC 方法: registry.auto_register, registry.set_enabled 等
 · 检测变化后通过 IPC notify 推送事件到主进程

 职责边界（子进程侧）:
   - 扫描模块源件目录，检测新增/删除/修改
   - 新模块自动注册到注册表（调用 registry.auto_register）
   - 推送 MODULE_FILE_ADDED / MODULE_FILE_REMOVED / MODULE_FILE_CHANGED
   - 不直接操作框架内部状态，全部通过 IPC

 安全:
   - 仅监控 .py 文件
   - 通过 IPC 单向上报，不接触框架内核
═══════════════════════════════════════════════════════════════════════════
"""
import asyncio
import logging
import os
import time
from typing import Dict

from qqlinker_framework.core.ipc.client import IPCClient

_log = logging.getLogger("module_file_watcher")

# 监控的模块源件子目录
WATCH_SUBDIR = "插件数据文件/模块源件"

# 默认扫描间隔
DEFAULT_SCAN_INTERVAL = 3.0


class ModuleFileWatcher:
    """文件监控 Worker：持续扫描模块目录，通过 IPC 上报变化。

    作为 WorkerPool 子进程运行，与主进程完全隔离。
    """

    def __init__(
        self,
        data_path: str,
        ipc_socket_path: str,
        scan_interval: float = DEFAULT_SCAN_INTERVAL,
    ):
        self._data_path = data_path
        self._watch_dir = os.path.join(data_path, WATCH_SUBDIR)
        self._ipc_socket_path = ipc_socket_path
        self._scan_interval = scan_interval
        self._snapshot: Dict[str, float] = {}
        self._client: IPCClient = IPCClient(ipc_socket_path)
        self._stopped = False
        self._scan_count = 0
        self._changes_detected = 0

    # ═══════════════════════════════════════════════════════════
    # 快照
    # ═══════════════════════════════════════════════════════════

    def _take_snapshot(self) -> Dict[str, float]:
        """扫描模块目录，返回 {文件名: mtime} 快照。"""
        snapshot: Dict[str, float] = {}
        if not os.path.isdir(self._watch_dir):
            return snapshot
        try:
            for entry in os.listdir(self._watch_dir):
                if not entry.endswith(".py"):
                    continue
                if entry.startswith("__"):
                    continue
                full_path = os.path.join(self._watch_dir, entry)
                if os.path.isfile(full_path):
                    try:
                        snapshot[entry] = os.path.getmtime(full_path)
                    except OSError:
                        snapshot[entry] = 0.0
        except OSError as e:
            _log.error("文件监控: 扫描目录失败: %s", e)
        return snapshot

    async def _compare_and_notify(self, old: Dict[str, float], new: Dict[str, float]):
        """对比快照，通过 IPC 推送事件。"""
        old_names = set(old.keys())
        new_names = set(new.keys())

        # 新增文件
        added = new_names - old_names
        for name in added:
            mod_name = name[:-3]
            _log.info("文件监控: 检测到新增模块 '%s'", mod_name)
            try:
                # 自动注册到注册表
                await self._client.call(
                    "registry.auto_register",
                    {"module_names": [mod_name]},
                    timeout=5.0,
                )
                await self._client.notify(
                    "module_file_added",
                    {"module_name": mod_name, "filename": name},
                )
                self._changes_detected += 1
            except Exception as e:
                _log.error("IPC 通知失败 (新增 %s): %s", mod_name, e)

        # 删除文件
        removed = old_names - new_names
        for name in removed:
            mod_name = name[:-3]
            _log.info("文件监控: 检测到删除模块 '%s'", mod_name)
            try:
                await self._client.notify(
                    "module_file_removed",
                    {"module_name": mod_name, "filename": name},
                )
                self._changes_detected += 1
            except Exception as e:
                _log.error("IPC 通知失败 (删除 %s): %s", mod_name, e)

        # 修改文件（mtime 变化）
        common = old_names & new_names
        for name in common:
            old_mtime = old.get(name, 0)
            new_mtime = new.get(name, 0)
            if abs(new_mtime - old_mtime) > 0.01:
                mod_name = name[:-3]
                _log.info(
                    "文件监控: 检测到修改模块 '%s' (mtime: %.2f → %.2f)",
                    mod_name, old_mtime, new_mtime,
                )
                try:
                    await self._client.notify(
                        "module_file_changed",
                        {
                            "module_name": mod_name,
                            "filename": name,
                            "old_mtime": old_mtime,
                            "new_mtime": new_mtime,
                        },
                    )
                    self._changes_detected += 1
                except Exception as e:
                    _log.error("IPC 通知失败 (修改 %s): %s", mod_name, e)

    # ═══════════════════════════════════════════════════════════
    # 主循环
    # ═══════════════════════════════════════════════════════════

    async def run(self) -> None:
        """启动文件监控主循环（通过 IPC 连接主进程）。"""
        _log.info(
            "文件监控 Worker 启动 (目录=%s, 间隔=%.1fs, IPC=%s)",
            self._watch_dir, self._scan_interval, self._ipc_socket_path,
        )

        # 连接 IPC
        try:
            await self._client.connect()
        except Exception as e:
            _log.error("文件监控: IPC 连接失败: %s", e)
            return

        # 首次扫描：建立基线快照（不上报，但自动注册已有模块）
        self._snapshot = self._take_snapshot()
        existing_modules = [name[:-3] for name in self._snapshot.keys()]
        if existing_modules:
            try:
                await self._client.call(
                    "registry.auto_register",
                    {"module_names": existing_modules},
                    timeout=5.0,
                )
            except Exception as e:
                _log.warning("初始注册已有模块失败: %s", e)
        _log.info(
            "文件监控: 基线快照已建立 (%d 个 .py 文件)",
            len(self._snapshot),
        )

        # 扫描循环
        while not self._stopped:
            try:
                await asyncio.sleep(self._scan_interval)
                if self._stopped:
                    break

                self._scan_count += 1
                new_snapshot = self._take_snapshot()
                await self._compare_and_notify(self._snapshot, new_snapshot)
                self._snapshot = new_snapshot

            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.error("文件监控: 扫描异常: %s", e)
                await asyncio.sleep(1.0)

        # 清理
        try:
            await self._client.close()
        except Exception:
            pass
        _log.info(
            "文件监控 Worker 已停止 (扫描=%d, 变化=%d)",
            self._scan_count, self._changes_detected,
        )

    def stop(self) -> None:
        """停止监控。"""
        self._stopped = True

    # ═══════════════════════════════════════════════════════════
    # 手动触发（同步，worker 启动时使用）
    # ═══════════════════════════════════════════════════════════

    def get_current_files(self) -> list:
        """返回模块目录中所有 .py 文件名（不含扩展名，同步）。"""
        snapshot = self._take_snapshot()
        return sorted([name[:-3] for name in snapshot.keys()])


# ═══════════════════════════════════════════════════════════════
# Worker 入口（供 WorkerPool 启动）
# ═══════════════════════════════════════════════════════════════

async def file_watcher_main(data_path: str, ipc_socket_path: str) -> None:
    """文件监控 Worker 主入口（由 WorkerPool 调用）。"""
    watcher = ModuleFileWatcher(
        data_path=data_path,
        ipc_socket_path=ipc_socket_path,
    )
    await watcher.run()

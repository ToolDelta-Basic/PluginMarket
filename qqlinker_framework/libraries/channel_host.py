"""信道主机 — 纯信道框架启动器。

不依赖 core/host.py。用新信道库启动框架。
"""
import asyncio
import logging
import os

_log = logging.getLogger(__name__)

# ── 内置库清单（按依赖顺序）──
BUILTIN_LIBRARIES = [
    "qqlinker_framework.libraries.service_bus.CoreLibrary",
    "qqlinker_framework.libraries.config_source.ConfigSourceLibrary",
    "qqlinker_framework.libraries.message_bus.MessageBusLibrary",
    "qqlinker_framework.libraries.module_loader.ModuleLoaderLibrary",
    "qqlinker_framework.libraries.command_router.CommandRouterLibrary",
    "qqlinker_framework.libraries.adapter_bridge.AdapterBridgeLibrary",
]


class ChannelHost:
    """纯信道框架启动器。"""

    def __init__(self, data_path: str):
        self._data_path = data_path
        self._libraries = []
        self._logger = logging.getLogger(__name__)

    async def start(self) -> None:
        # 创建目录
        for d in ["模块", "工具", "工具/工具数据", "第三方库", "注册表", "日志"]:
            os.makedirs(os.path.join(self._data_path, d), exist_ok=True)

        # 动态导入并实例化每个库
        import importlib
        for class_path in BUILTIN_LIBRARIES:
            module_path, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            lib_cls = getattr(module, class_name)
            instance = lib_cls()
            instance._data_path = self._data_path
            self._libraries.append(instance)

        # 拓扑排序
        sorted_libs = self._topo_sort()

        # 顺序挂载
        for lib in sorted_libs:
            self._logger.info("挂载: %s v%s", lib.name, lib.version)
            await lib.mount()

        self._logger.info("框架启动完成 (%d 个库)", len(sorted_libs))

    async def stop(self) -> None:
        for lib in reversed(self._libraries):
            self._logger.info("卸载: %s", lib.name)
            await lib.unmount()

    def _topo_sort(self) -> list:
        name_to_lib = {l.name: l for l in self._libraries}
        in_degree = {l.name: 0 for l in self._libraries}
        graph = {l.name: [] for l in self._libraries}

        for lib in self._libraries:
            for dep in lib.dependencies:
                if dep in name_to_lib:
                    graph[dep].append(lib.name)
                    in_degree[lib.name] += 1

        queue = [n for n, d in in_degree.items() if d == 0]
        result = []
        while queue:
            name = queue.pop(0)
            result.append(name_to_lib[name])
            for neighbor in graph[name]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self._libraries):
            remaining = [l.name for l in self._libraries if l not in result]
            _log.error("循环依赖: %s", remaining)
            result.extend(l for l in self._libraries if l not in result)

        return result

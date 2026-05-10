# __init__.py
"""云链群服互通框架 - ToolDelta 插件入口"""
import asyncio
import json
import os
import threading
from tooldelta import Plugin, plugin_entry, ToolDelta
from .core.host import FrameworkHost
from .adapters.tooldelta_adapter import ToolDeltaAdapter


class QQLinkerFrameworkPlugin(Plugin):
    """ToolDelta 插件主类，负责启动框架主机及依赖检查。"""

    name = "群服互通框架"
    version = (1, 0, 0)
    author = "小石潭记qwq"
    description = "模块化群服互通框架"

    def __init__(self, frame: ToolDelta):
        """初始化插件，注册预加载事件。

        Args:
            frame: ToolDelta 框架实例。
        """
        super().__init__(frame)
        self.ListenPreload(self.on_preload)
        self._framework_thread = None
        self._host = None
        self._loop = None

    def on_preload(self):
        """预加载事件处理：创建配置、适配器、启动后台异步线程。"""
        data_dir = str(self.data_path)
        config_path = os.path.join(data_dir, "config.json")
        if not os.path.exists(config_path):
            minimal_cfg = {
                "网络连接": {
                    "地址": "ws://127.0.0.1:8080",
                    "令牌": "",
                }
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(minimal_cfg, f, ensure_ascii=False, indent=2)

        adapter = ToolDeltaAdapter(self)
        self._host = FrameworkHost(adapter, data_path=data_dir)

        pkg_mgr = self._host.package_mgr
        pkg_mgr.register_requirements({
            "websocket-client": "websocket",
            "aiohttp": "aiohttp",
            "cachetools": "cachetools",
            "redis": "redis",
        })

        self._host.register_modules_from_package("qqlinker_framework.modules")

        self._framework_thread = threading.Thread(
            target=self._run_framework, daemon=True
        )
        self._framework_thread.start()

    def _run_framework(self):
        """在独立线程中创建事件循环并运行框架主机。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._host.start())
            self._loop.run_forever()
        except Exception as e:
            print(f"[Framework] 运行异常: {e}")
        finally:
            self._loop.close()


entry = plugin_entry(QQLinkerFrameworkPlugin)

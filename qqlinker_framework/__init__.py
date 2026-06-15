# __init__.py

__version__ = "1.5.1"

"""云链群服互通框架 - ToolDelta 插件入口 (v1.5.1)

启动方式:
  1. ToolDelta 环境 → 自动作为插件加载
  2. 无 ToolDelta → python -m qqlinker_framework             进入 mock CLI
  3. 无 ToolDelta → python -m qqlinker_framework --test      运行测试
  4. 无 ToolDelta → python -m qqlinker_framework --mock      仅启动 mock 框架
"""
import asyncio
import json
import logging
import os
import sys
import threading
import traceback

# ═══════════════════════════════════════════════════════════════
# 第一道防线：文件完整性检查
# ═══════════════════════════════════════════════════════════════

_skip_integrity = os.environ.get("QQLINKER_SKIP_INTEGRITY", "0") == "1"

def _bootstrap_integrity_check():
    if _skip_integrity:
        return
    _framework_base = os.path.dirname(os.path.abspath(__file__))
    _fatal_files = {
        "core/host.py":            "框架核心调度器",
        "core/module.py":          "模块基类",
        "core/kernel/bus.py":          "事件总线",
        "core/kernel/services.py":     "服务容器",
        "管理/config_mgr.py":  "配置管理器",
        "管理/source_mgr.py":  "加载源管理器",
        "adapters/base.py":        "适配器基类",
    }
    missing = []
    for rel, desc in _fatal_files.items():
        # v6: 同时检查 管理/ 和 managers/ 路径
        check_paths = [rel, rel.replace("管理/", "managers/", 1)] if "管理/" in rel else [rel]
        found = any(os.path.isfile(os.path.join(_framework_base, p)) for p in check_paths)
        if not found:
            missing.append((rel, desc))
    if not missing:
        return
    print(f"\n❌ 关键文件缺失: {missing[0][0]}", file=sys.stderr)
    sys.exit(1)

_bootstrap_integrity_check()

# ═══════════════════════════════════════════════════════════════
# 检测 ToolDelta 环境
# ═══════════════════════════════════════════════════════════════

try:
    from tooldelta import Plugin, plugin_entry, ToolDelta
    HAS_TOOLDELTA = True
except ImportError:
    HAS_TOOLDELTA = False
    class Plugin:
        """ToolDelta Plugin 基类 mock。"""
        name: str = ""
        version: tuple = (0, 0, 0)
        author: str = ""
        description: str = ""
        def __init__(self, frame=None):
            self.frame = frame
            self.game_ctrl = None
            self.data_path = "."
        def ListenPreload(self, func, priority=0):  # noqa: PYL-R0201
            """预加载监听。"""
            pass
        def ListenActive(self, func, priority=0):  # noqa: PYL-R0201
            """激活监听。"""
            pass
        def ListenPlayerJoin(self, func, priority=0):  # noqa: PYL-R0201
            """玩家加入监听。"""
            pass
        def ListenPlayerPreJoin(self, func, priority=0):  # noqa: PYL-R0201
            """玩家预加入监听。"""
            pass
        def ListenPlayerLeave(self, func, priority=0):  # noqa: PYL-R0201
            """玩家离开监听。"""
            pass
        def ListenChat(self, func, priority=0):  # noqa: PYL-R0201
            """聊天监听。"""
            pass
        def ListenFrameExit(self, func, priority=0):  # noqa: PYL-R0201
            """框架退出监听。"""
            pass
        def ListenPacket(self, pk_id, func, priority=0):  # noqa: PYL-R0201
            """数据包监听。"""
            pass
        def ListenBytesPacket(self, pk_id, func, priority=0):  # noqa: PYL-R0201
            """字节数据包监听。"""
            pass
        def ListenInternalBroadcast(self, name, func, priority=0):  # noqa: PYL-R0201
            """内部广播监听。"""
            pass
        @staticmethod
        def GetPluginAPI(api_name, min_version=(0, 0, 0), force=True):
            """获取插件 API。"""
            return None
        @staticmethod
        def BroadcastEvent(evt):
            """广播事件。"""
            return []
        def get_typecheck_plugin_api(self, api_cls):  # noqa: PYL-R0201
            """类型检查插件 API。"""
            raise NotImplementedError
    def plugin_entry(cls, *args, **kwargs): return cls
    ToolDelta = None

from .core.host import FrameworkHost
from .core.kernel.containment import (
    plugin_wrapper,
    register_shutdown_callback, trigger_safe_shutdown,
    reset_failure_count,
)
from .adapters.tooldelta_adapter import ToolDeltaAdapter


# ═══════════════════════════════════════════════════════════════
# 插件主类
# ═══════════════════════════════════════════════════════════════

class QQLinkerFrameworkPlugin(Plugin):
    """群服互通框架插件入口，负责生命周期管理。"""

    name = "群服互通框架"
    version = (1, 5, 0)
    author = "小石潭记qwq"
    description = "模块化群服互通框架 · 约定优于配置"

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_def)
        self._framework_thread = None
        self._host = None
        self._loop = None
        self._adapter = None

    @plugin_wrapper
    def on_preload(self):
        """预加载: 初始化适配器、注册前置插件、发现模块。"""
        data_dir = str(self.data_path)
        self._adapter = ToolDeltaAdapter(self)

        # 前置插件依赖
        pre_deps = self._load_pre_plugin_deps(data_dir)
        if pre_deps:
            for api_name, min_ver in pre_deps.items():
                registered = self._adapter.register_pre_plugin_api(api_name, min_ver)
                if not registered:
                    logging.getLogger(__name__).warning(
                        "⚠ 前置插件 '%s' (>= v%s) 不可用", api_name,
                        ".".join(str(x) for x in min_ver))

        self._host = FrameworkHost(self._adapter, data_path=data_dir)

        # 注册框架软重启服务（memory_guard 等模块通过 services.get("framework_restart") 调用）
        self._host.services.register("framework_restart", self.soft_restart, uid=100,
                                      _caller="qqlinker_framework.__init__")

        pre_apis = self._adapter.get_pre_plugin_apis()
        if pre_apis:
            for api_name, api_inst in pre_apis.items():
                svc_name = f"pre_api.{api_name}"
                self._host.services.register(svc_name, api_inst, uid=400,
                                              _caller="qqlinker_framework.__init__")

        self._host.package_mgr.register_requirements({"websocket-client": "websocket"})
        self._host.register_modules_from_package("qqlinker_framework.modules")
        self._host.register_external_modules()

        logging.getLogger(__name__).info("插件预加载完成，等待游戏连接...")

    @plugin_wrapper
    def on_active(self):
        """游戏连接就绪后启动框架线程。"""
        logging.getLogger(__name__).info("游戏连接已就绪，启动框架...")
        if not self._host:
            return

        pkg_mgr = self._host.package_mgr
        missing = pkg_mgr.check_missing()
        if missing:
            logging.getLogger(__name__).warning(
                "⚠ 缺失依赖: %s。请在控制台执行 qqdeps install 自动安装",
                ", ".join(missing.keys()))

        if self._adapter:
            self._adapter.handle_active()
        self._framework_thread = threading.Thread(
            target=self._run_framework, daemon=True)
        self._framework_thread.start()

    @plugin_wrapper
    def _run_framework(self):
        """在独立线程中创建事件循环并运行框架。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        reset_failure_count()
        try:
            self._loop.run_until_complete(self._host.start())
            register_shutdown_callback(self._safe_shutdown)
            self._loop.run_forever()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.getLogger(__name__).critical(
                "⚠ 框架运行异常: %s\n%s", e, traceback.format_exc())
            trigger_safe_shutdown()
        finally:
            self._safe_shutdown()

    def _safe_shutdown(self):
        """安全关闭框架。"""
        try:
            if self._loop and self._host and not self._loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(self._host.stop(), self._loop)
                try:
                    future.result(timeout=30)
                except Exception:
                    pass
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass

    async def soft_restart(self, reason: str = "") -> bool:
        """框架级软重启 — 停止旧线程 + 事件循环，重新创建并启动。

        不会杀死进程，不会中断 Minecraft/OneBot 连接。
        重启期间框架不可用约 5-15 秒。

        Returns:
            True 如果重启成功。
        """
        logger = logging.getLogger(__name__)
        logger.warning("🔄 框架软重启触发 (原因: %s)", reason or "手动")
        result = False
        try:
            # 1. 停止旧框架
            old_loop = self._loop
            old_host = self._host
            if old_loop and old_host and not old_loop.is_closed():
                logger.info("停止旧框架...")
                try:
                    future = asyncio.run_coroutine_threadsafe(old_host.stop(), old_loop)
                    future.result(timeout=30)
                except Exception:
                    pass
                try:
                    old_loop.call_soon_threadsafe(old_loop.stop)
                except Exception:
                    pass

            # 2. 等待旧线程结束
            if self._framework_thread and self._framework_thread.is_alive():
                self._framework_thread.join(timeout=10)
                if self._framework_thread.is_alive():
                    logger.warning("旧框架线程未在 10 秒内停止，继续重启")

            # 3. 关闭旧事件循环
            if old_loop and not old_loop.is_closed():
                try:
                    old_loop.close()
                except Exception:
                    pass

            # 4. 重置状态
            self._loop = None
            self._host = None
            self._framework_thread = None

            # 5. 回收内存
            import gc
            gc.collect()

            # 6. 重新创建 host（保留 adapter + data_path）
            from .core.host import FrameworkHost
            data_dir = str(self.data_path)

            # 保留旧 adapter 引用
            old_adapter = self._adapter
            self._adapter = ToolDeltaAdapter(self)
            # 复制状态
            if old_adapter and hasattr(old_adapter, '_pre_apis'):
                self._adapter._pre_apis = getattr(old_adapter, '_pre_apis', {})

            self._host = FrameworkHost(self._adapter, data_path=data_dir)

            pre_apis = self._adapter.get_pre_plugin_apis()
            if pre_apis:
                for api_name, api_inst in pre_apis.items():
                    svc_name = f"pre_api.{api_name}"
                    self._host.services.register(svc_name, api_inst, uid=400,
                                                  _caller="qqlinker_framework.__init__.soft_restart")

            self._host.package_mgr.register_requirements({"websocket-client": "websocket"})
            self._host.register_modules_from_package("qqlinker_framework.modules")
            self._host.register_external_modules()

            # 7. 重新启动框架线程
            logger.info("启动新框架线程...")
            self._framework_thread = threading.Thread(
                target=self._run_framework, daemon=True)
            self._framework_thread.start()

            # 8. 等待新框架就绪
            await asyncio.sleep(5)
            logger.info("✅ 框架软重启完成")
            result = True

        except Exception as e:
            logger.critical("框架软重启失败: %s\n%s", e, traceback.format_exc())
            # 如果出错了仍尝试通过 containment 机制触发安全关闭
            trigger_safe_shutdown()

        return result

    @plugin_wrapper
    def on_def(self, _frame_exit=None):
        """插件卸载时停止框架。"""
        if self._loop and self._host:
            future = asyncio.run_coroutine_threadsafe(self._host.stop(), self._loop)
            try:
                future.result(timeout=30)
            except Exception:
                pass
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
        if self._framework_thread and self._framework_thread.is_alive():
            self._framework_thread.join(timeout=5)

    @staticmethod
    def _load_pre_plugin_deps(data_dir: str) -> dict:
        """从 datas.json 加载前置插件依赖。"""
        datas_path = os.path.join(os.path.dirname(__file__), "datas.json")
        if not os.path.exists(datas_path):
            return {}
        try:
            with open(datas_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}
        pre_plugins = data.get("pre-plugins", {})
        result = {}
        for api_name, ver_str in (pre_plugins if isinstance(pre_plugins, dict) else {}).items():
            if ver_str in ("any", "*", ""):
                result[api_name] = (0, 0, 0)
            else:
                try:
                    parts = tuple(int(x) for x in str(ver_str).split("."))
                    result[api_name] = parts if len(parts) == 3 else (0, 0, 0)
                except ValueError:
                    result[api_name] = (0, 0, 0)
        return result


entry = plugin_entry(QQLinkerFrameworkPlugin)


# ═══════════════════════════════════════════════════════════════
# 无 ToolDelta 时的测试模式入口
# ═══════════════════════════════════════════════════════════════

def _main():
    args = sys.argv[1:]
    if "--test" in args or "-t" in args:
        from .testing.runner import run_all_tests
        success = run_all_tests()
        sys.exit(0 if success else 1)
    elif "--mock" in args or "-m" in args:
        from .testing.cli import start_mock_cli
        start_mock_cli(start_framework=True)
    elif "--backup" in args:
        from .testing.cli import backup_data
        idx = args.index("--backup")
        output = args[idx + 1] if idx + 1 < len(args) and not args[idx + 1].startswith("--") else None
        backup_data(data_dir=".", output=output)
    elif "--restore" in args:
        from .testing.cli import restore_data
        idx = args.index("--restore")
        if idx + 1 >= len(args) or args[idx + 1].startswith("--"):
            print("用法: python -m qqlinker_framework --restore <备份文件> [数据目录]")
            sys.exit(1)
        backup_file = args[idx + 1]
        data_dir = args[idx + 2] if idx + 2 < len(args) and not args[idx + 2].startswith("--") else "."
        restore_data(backup_file=backup_file, data_dir=data_dir)
    elif "--help" in args or "-h" in args:
        print(__doc__)
    else:
        from .testing.cli import start_mock_cli
        start_mock_cli(start_framework=True)


if __name__ == "__main__":
    if not HAS_TOOLDELTA:
        _main()

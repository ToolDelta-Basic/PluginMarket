# __init__.py
"""云链群服互通框架 - ToolDelta 插件入口 (v1.3.0)

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
# 在任何 import 框架模块之前执行，防止因文件缺失导致宿主崩溃
# ═══════════════════════════════════════════════════════════════

_skip_integrity = os.environ.get("QQLINKER_SKIP_INTEGRITY", "0") == "1"

# 内联完整性检查（避免循环导入）
def _bootstrap_integrity_check():
    """启动前检查关键文件是否存在。"""
    if _skip_integrity:
        return

    _framework_base = os.path.dirname(os.path.abspath(__file__))

    # 关键文件清单 (相对路径 → 描述)
    _fatal_files = {
        "core/host.py":            "框架核心调度器",
        "core/module.py":          "模块基类",
        "core/bus.py":             "事件总线",
        "core/services.py":        "服务容器",
        "core/events.py":          "事件定义",
        "core/routing.py":         "命令路由",
        "core/defguard.py":        "防御层",
        "core/error_hints.py":     "错误提示库",
        "managers/config_mgr.py":  "配置管理器",
        "managers/module_mgr.py":  "模块管理器",
        "managers/command_mgr.py": "命令管理器",
        "managers/message_mgr.py": "消息管理器",
        "adapters/base.py":        "适配器基类",
    }

    missing = []
    for rel, desc in _fatal_files.items():
        if not os.path.isfile(os.path.join(_framework_base, rel)):
            missing.append((rel, desc))

    if not missing:
        return

    msg_lines = [
        "",
        "╔══════════════════════════════════════════════════════════╗",
        "║  ❌ 群服互通框架 启动失败                                ║",
        "╠══════════════════════════════════════════════════════════╣",
        "║  关键文件缺失，框架无法继续运行。                       ║",
        "╠══════════════════════════════════════════════════════════╣",
    ]
    for i, (rel, desc) in enumerate(missing[:10], 1):
        msg_lines.append(f"║  {i}. {rel}")
        msg_lines.append(f"║     ── {desc}")
    if len(missing) > 10:
        msg_lines.append(f"║  ... 及其他 {len(missing) - 10} 个文件")
    msg_lines.extend([
        "╠══════════════════════════════════════════════════════════╣",
        "║  可能的原因：                                          ║",
        "║  ① 安装包不完整或被损坏                                ║",
        "║  ② 文件被手动删除或移动                                ║",
        "║  ③ 解压/部署时出错                                     ║",
        "╠══════════════════════════════════════════════════════════╣",
        "║  建议重新下载并安装完整的框架包。                      ║",
        f"║  框架位置: {_framework_base[:48]}",
        "╚══════════════════════════════════════════════════════════╝",
        "",
        "💡 如需跳过此检查（不推荐），设置环境变量:",
        "   export QQLINKER_SKIP_INTEGRITY=1",
        "",
    ])
    print("\n".join(msg_lines), file=sys.stderr)
    sys.exit(1)

# 立即执行检查
_bootstrap_integrity_check()

# ═══════════════════════════════════════════════════════════════
# 现在安全加载框架
# ═══════════════════════════════════════════════════════════════

try:
    from tooldelta import Plugin, plugin_entry, ToolDelta
    HAS_TOOLDELTA = True
except ImportError:
    HAS_TOOLDELTA = False

    class Plugin:
        """ToolDelta 插件基类桩，用于非 ToolDelta 环境。

        完整实现了 ToolDelta Plugin 的生命周期监听接口桩。
        """

        name: str = ""
        version: tuple = (0, 0, 0)
        author: str = ""
        description: str = ""

        def __init__(self, frame=None):
            self.frame = frame
            self.game_ctrl = None
            self.data_path = "."

        # ── 生命周期监听 ──

        def ListenPreload(self, func, priority=0):
            """注册预加载回调（桩）。"""

        def ListenActive(self, func, priority=0):
            """注册激活回调。"""

        def ListenPlayerJoin(self, func, priority=0):
            """注册玩家加入回调。"""

        def ListenPlayerPreJoin(self, func, priority=0):
            """注册玩家预加入回调。"""

        def ListenPlayerLeave(self, func, priority=0):
            """注册玩家离开回调。"""

        def ListenChat(self, func, priority=0):
            """注册聊天回调。"""

        def ListenFrameExit(self, func, priority=0):
            """注册框架退出回调。"""

        def ListenDeath(self, func, priority=0):
            """注册玩家死亡回调（桩）。"""

        def ListenAttack(self, func, priority=0):
            """注册玩家击杀回调（桩）。"""

        def ListenSleep(self, func, priority=0):
            """注册玩家睡觉回调（桩）。"""

        def ListenWeather(self, func, priority=0):
            """注册天气变化回调（桩）。"""

        def ListenPacket(self, pk_id, func, priority=0):
            """注册字典数据包监听。"""

        def ListenBytesPacket(self, pk_id, func, priority=0):
            """注册二进制数据包监听。"""

        def ListenInternalBroadcast(self, name, func, priority=0):
            """注册内部广播监听。"""

        # ── 跨插件 API ──

        @staticmethod
        def GetPluginAPI(api_name, min_version=(0, 0, 0), force=True):
            """获取前置插件 API 实例。"""
            return None

        @staticmethod
        def BroadcastEvent(evt):
            """广播内部事件。"""
            return []

        def get_typecheck_plugin_api(self, api_cls):
            """TYPE_CHECKING 辅助（桩）。"""
            raise NotImplementedError

    def plugin_entry(cls, *args, **kwargs):
        """ToolDelta 插件入口标记。

        支持三种形式:
          plugin_entry(PluginClass)
          plugin_entry(PluginClass, "api-name", (0, 0, 1))
          plugin_entry(PluginClass, ["api-a", "api-b"], (0, 0, 1))
        """
        return cls

    ToolDelta = None

from .core.host import FrameworkHost
from .core.containment import (
    plugin_wrapper, safe_handler, safe_call,
    register_shutdown_callback, trigger_safe_shutdown,
    reset_failure_count, is_shutting_down,
)
from .adapters.tooldelta_adapter import ToolDeltaAdapter


# ── 依赖解析 ────────────────────────────────────────────────

def _load_pre_plugin_deps(data_dir: str) -> dict:
    """从 datas.json 加载前置插件依赖声明。"""
    datas_path = os.path.join(data_dir, "..", "datas.json")
    if not os.path.exists(datas_path):
        alt = os.path.join(os.path.dirname(__file__), "datas.json")
        if os.path.exists(alt):
            datas_path = alt
        else:
            return {}
    try:
        with open(datas_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    pre_plugins = data.get("pre-plugins", {})
    if not isinstance(pre_plugins, dict):
        return {}
    result = {}
    for api_name, ver_str in pre_plugins.items():
        if ver_str in ("any", "*", ""):
            result[api_name] = (0, 0, 0)
        else:
            try:
                parts = tuple(int(x) for x in str(ver_str).split("."))
                result[api_name] = parts if len(parts) == 3 else (0, 0, 0)
            except ValueError:
                result[api_name] = (0, 0, 0)
    return result


# ── 插件主类 ────────────────────────────────────────────────

class QQLinkerFrameworkPlugin(Plugin):
    """群服互通框架插件入口，负责生命周期管理。"""

    name = "群服互通框架"
    version = (1, 3, 0)
    author = "小石潭记qwq"
    description = "模块化群服互通框架 · 约定优于配置"

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_frame_exit)
        self._framework_thread = None
        self._host = None
        self._loop = None
        self._adapter = None

    @plugin_wrapper
    def on_preload(self):
        """预加载: 初始化适配器、注册前置插件、发现模块。"""
        data_dir = str(self.data_path)
        self._adapter = ToolDeltaAdapter(self)

        pre_deps = _load_pre_plugin_deps(data_dir)
        if pre_deps:
            logging.getLogger(__name__).info(
                "检测到 %d 个前置插件依赖，正在注册...", len(pre_deps)
            )
            for api_name, min_ver in pre_deps.items():
                registered = self._adapter.register_pre_plugin_api(
                    api_name, min_ver
                )
                if not registered:
                    logging.getLogger(__name__).warning(
                        "⚠ 前置插件 '%s' (>= v%s) 不可用", api_name,
                        ".".join(str(x) for x in min_ver)
                    )

        self._host = FrameworkHost(self._adapter, data_path=data_dir)

        # 通过公共方法访问前置插件 API，避免直接访问受保护成员
        pre_apis = self._adapter.get_pre_plugin_apis()
        if pre_apis:
            for api_name, api_inst in pre_apis.items():
                svc_name = f"pre_api.{api_name}"
                self._host.services.register(svc_name, api_inst, uid=3000,
                                              _caller="qqlinker_framework.__init__")
                logging.getLogger(__name__).info(
                    "前置插件 API '%s' 已暴露为服务 '%s'", api_name, svc_name
                )

        pkg_mgr = self._host.package_mgr
        pkg_mgr.register_requirements({
            "websocket-client": "websocket",
        })

        self._host.register_modules_from_package("qqlinker_framework.modules")
        # 同时扫描 插件数据文件/模块源件/ 中的外部模块
        self._host.register_external_modules()
        logging.getLogger(__name__).info("插件预加载完成，等待游戏连接...")

    @plugin_wrapper
    def on_active(self):
        """游戏连接就绪后启动框架线程。"""
        logging.getLogger(__name__).info("游戏连接已就绪，启动框架...")
        if not self._host:
            logging.getLogger(__name__).error("框架主机未初始化")
            return
        # 通知适配器游戏已激活
        if self._adapter:
            self._adapter.handle_active()
        self._framework_thread = threading.Thread(
            target=self._run_framework, daemon=True
        )
        self._framework_thread.start()

    @plugin_wrapper
    def _run_framework(self):
        """在独立线程中创建事件循环并运行框架。

        此方法是框架运行的最后防线——任何未捕获异常都不会传播到 ToolDelta。
        """
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        reset_failure_count()
        try:
            self._loop.run_until_complete(self._host.start())
            # 注册安全卸载回调
            register_shutdown_callback(lambda: self._safe_shutdown())
            self._loop.run_forever()
        except asyncio.CancelledError:
            logging.getLogger(__name__).info("框架事件循环收到取消信号")
        except Exception as e:
            logging.getLogger(__name__).critical(
                "⚠ 框架运行异常，正在安全退出。ToolDelta 不受影响。错误: %s\n%s",
                e, traceback.format_exc(),
            )
            trigger_safe_shutdown()
        finally:
            self._safe_shutdown()

    def _safe_shutdown(self):
        """安全关闭框架，确保资源释放。此方法本身也受保护。"""
        try:
            if self._loop and self._host and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._host.stop(), self._loop
                )
                self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception as e:
            logging.getLogger(__name__).error(
                "框架关闭异常（不影响 ToolDelta）: %s", e
            )
        finally:
            try:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass

    @plugin_wrapper
    def on_def(self):
        """插件卸载时停止框架和事件循环。"""
        if self._loop and self._host:
            asyncio.run_coroutine_threadsafe(self._host.stop(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._framework_thread and self._framework_thread.is_alive():
            self._framework_thread.join(timeout=5)


entry = plugin_entry(QQLinkerFrameworkPlugin)


# ═══════════════════════════════════════════════════════════════
# 无 ToolDelta 时的测试模式入口
# ═══════════════════════════════════════════════════════════════

def _main():
    """测试模式入口函数（供 __main__.py 和 __init__.py 共用）。"""
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
        # 支持 --backup [output_path]
        idx = args.index("--backup")
        output = args[idx + 1] if idx + 1 < len(args) and not args[idx + 1].startswith("--") else None
        backup_data(data_dir=".", output=output)
    elif "--restore" in args:
        from .testing.cli import restore_data
        # --restore <backup_file> [data_dir]
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

"""控制台命令管理器 — qqdeps 依赖管理、qqhealth 健康检查。

从 FrameworkHost 拆分出来，保持内核简洁。
"""
import json
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.host import FrameworkHost

_log = logging.getLogger(__name__)


class ConsoleCommands:
    """控制台命令注册与处理。"""

    def __init__(self, host: "FrameworkHost"):
        self.host = host

    def register_all(self):
        """注册所有控制台命令到 adapter。"""
        adapter = self.host.adapter
        adapter.register_console_command(
            ["qqdeps"],
            "[check|install|module] <list|add|remove> [url/名称]",
            "管理框架 Python 依赖与外部模块",
            self._qqdeps,
        )
        adapter.register_console_command(
            ["qqhealth"],
            "",
            "查看框架健康状态",
            self._qqhealth,
        )

    # ── qqdeps ──

    def _qqdeps(self, args: list):
        """控制台命令: qqdeps。"""
        if not args:
            print("用法: qqdeps check|install|module <list|add|remove|search> [参数]")
            return
        sub = args[0].lower()

        if sub == "module":
            self._qd_module(args)
        elif sub == "market":
            self._qd_market(args)
        elif sub == "check":
            self._qd_check()
        elif sub == "install":
            self._qd_install()
        else:
            print("未知子命令，可用: check / install / module / market")

    def _qd_module(self, args: list):
        if len(args) < 2:
            print("用法: qqdeps module <list|add|remove|search> [参数]")
            return
        action = args[1].lower()
        host = self.host

        if action == "list":
            from ..core.autodiscover import list_external_modules
            mods = list_external_modules(host.data_path)
            if not mods:
                print("暂无已安装的外部模块")
                print(f"放置路径: {host.data_path}/插件数据文件/模块源件/")
            else:
                print(f"已安装 {len(mods)} 个外部模块:")
                for m in mods:
                    print(f"  · {m['name']} ({m['type']}) v{m.get('version', '?')} — {m.get('description', '')}")

        elif action == "add":
            if len(args) < 3:
                print("用法: qqdeps module add <URL | 模块名>")
                return
            target = args[2]
            from ..core.autodiscover import download_module
            if target.startswith("http://") or target.startswith("https://"):
                print(f"正在从 {target} 下载模块...")
                name = download_module(target, host.data_path)
            else:
                if not host.market_aggregator:
                    print("❌ 市场聚合器未配置，请先启用模块市场")
                    return
                print(f"正在从市场源搜索 '{target}'...")
                name = host.market_aggregator.fetch_module(target, host.data_path)
            if name:
                print(f"✅ 模块 '{name}' 安装成功，请重载插件使其生效")
            else:
                print("❌ 安装失败，请检查名称或网络连接")

        elif action == "remove":
            if len(args) < 3:
                print("用法: qqdeps module remove <模块名>")
                return
            from ..core.autodiscover import remove_external_module
            if remove_external_module(args[2], host.data_path):
                print(f"✅ 模块 '{args[2]}' 已删除")
            else:
                print(f"❌ 未找到模块 '{args[2]}'")

        elif action == "search":
            if len(args) < 3:
                print("用法: qqdeps module search <关键词>")
                return
            if not host.market_aggregator:
                print("❌ 市场聚合器未配置")
                return
            result = host.market_aggregator.search(" ".join(args[2:]))
            mods = result.get("modules", [])
            if not mods:
                print("未找到匹配的结果")
            else:
                print(f"搜索 — {len(mods)} 个结果:")
                for m in mods:
                    src = m.get("_source", "?")
                    print(f"  · {m['name']} v{m.get('version', '?')} — {m.get('description', '')[:40]}")
                    print(f"    来源: {src}")
        else:
            print("未知操作，可用: list / add / remove / search")

    def _qd_market(self, args: list):
        if len(args) < 2:
            print("用法: qqdeps market <sources|refresh>")
            return
        action = args[1].lower()
        host = self.host
        if action == "sources":
            if not host.market_aggregator:
                print("市场聚合器未配置")
            else:
                print(f"已配置 {len(host.market_aggregator._sources)} 个市场源:")  # noqa: PYL-W0212 (same-package internal access — reading protected attribute from managing host)
                for i, s in enumerate(host.market_aggregator._sources, 1):  # noqa: PYL-W0212 (same-package internal access — reading protected attribute from managing host)
                    print(f"  {i}. {s}")
        elif action == "refresh":
            if not host.market_aggregator:
                print("❌ 市场聚合器未配置")
                return
            print("正在从市场源刷新...")
            result = host.market_aggregator.list_all()
            mods = result.get("modules", [])
            conflicts = result.get("conflicts", [])
            print(f"发现 {len(mods)} 个模块 (来自 {len(result.get('sources', []))} 个源)")
            if conflicts:
                print(f"⚠ {len(conflicts)} 个模块存在冲突（已按优先级保留）")
        else:
            print("未知操作，可用: sources / refresh")

    def _qd_check(self):
        missing = self.host.package_mgr.check_missing()
        if missing:
            print(f"缺失依赖: {', '.join(missing.keys())}")
        else:
            print("所有 Python 依赖已就绪")

    def _qd_install(self):
        host = self.host
        missing = host.package_mgr.check_missing()
        if not missing:
            print("所有 Python 依赖已就绪，无需安装")
            return
        print(f"正在后台安装缺失依赖: {', '.join(missing.keys())}...")
        threading.Thread(
            target=self._install_deps_thread,
            args=(list(missing.keys()),),
            daemon=True,
        ).start()

    def _install_deps_thread(self, packages: list):
        if self.host.package_mgr.install_packages(packages):
            print("[qqdeps] 依赖安装成功，请重载插件以使新模块生效")
        else:
            print("[qqdeps] 部分或全部依赖安装失败，请检查日志")

    # ── qqhealth ──

    def _qqhealth(self, args: list):
        host = self.host
        status = {
            "ws_connected": host.ws_client.available if host.ws_client else False,
            "loaded_modules": host.module_mgr.get_loaded_modules(),
            "counters": {},
            "redis_connected": False,
        }
        if host.dedup and host.dedup.redis and host.dedup.redis.client:
            try:
                host.dedup.redis.client.ping()
                status["redis_connected"] = True
            except Exception:
                pass
        debug = host.services.get("debug")
        if debug:
            status["counters"] = debug.get_counters()
        print(json.dumps(status, ensure_ascii=False, indent=2))

"""FrameworkHost - 框架核心调度器 (v11)

职责: 组装服务/管理器/模块、控制生命周期、提供模块热插拔 API。
非职责: 事件桥接 → core/event_bridge.py
        控制台命令 → managers/console.py

v11 — 集成模块注册表 + IPC 子进程 + 文件热监控
"""
import asyncio
import logging
import os
import time
from typing import Type, Optional, List, Dict

from .kernel.services import (
    ServiceContainer,
    TIER_KERNEL,
    TIER_DAEMON,
    TIER_SERVICE,
    TIER_APP,
    UID_NOBODY,
    MID_KERNEL,
    MID_SERVICE,
    InteractiveSessionTracker,
)
from .kernel.bus import EventBus
from .module import Module
from qqlinker_framework.managers import CommandRouter
from .drivers.event_bridge import EventBridge

from qqlinker_framework.managers import ConfigManager
from qqlinker_framework.managers import GroupConfigManager
from qqlinker_framework.managers import GroupModuleFilter
from qqlinker_framework.managers import RecoveryEngine
from qqlinker_framework.managers import PackageManager
from qqlinker_framework.managers import SourceManager
from qqlinker_framework.managers import CommandManager
from qqlinker_framework.managers import MessageManager
from qqlinker_framework.managers import ToolManager
from qqlinker_framework.managers import ConsoleCommands

from ..adapters.base import IFrameworkAdapter
from ..services.ws_client import WsClient, _get_websocket
from ..services.dedup import LayeredDedup, DedupConfig
from ..services.debug_engine import DebugEngine
from ..services.market_server import (
    ModuleMarketServer,
    MarketSourceAggregator,
)
from .kernel.error_hints import hint
from .drivers.gatekeeper import GatekeeperBridge, register_default_capabilities
from qqlinker_framework.managers import NetworkManager, NetworkConfig
from .kernel.events import ConfigReloadEvent
from .kernel.resource_guardian import ResourceGuardian, GuardianConfig
from .kernel.degradation import GracefulDegradation
from .kernel.health_score import ModuleHealthScorer
from .drivers.watchdog import EventLoopWatchdog
from qqlinker_framework.managers.telemetry_hub import TelemetryHub


class FrameworkHost:
    """框架核心调度器 — 组装 + 生命周期 + 热插拔 API。

    驱动加载策略：
      - 内核必须加载（services, bus, events 等基础模块）
      - 驱动可选加载（recovery, event_bridge, gatekeeper）
      - 驱动通过 getattr(self, 'xxx', NOOP) 方式调用
      - 未加载时使用 drivers.py 中定义的空实现
    """

    def __init__(self, adapter: IFrameworkAdapter, data_path: str = None):
        self.adapter = adapter
        self.data_path = data_path or "."

        # ── v5.2: 服务注册表（允则控制）──
        from .drivers.registry import ServiceRegistry, ConventionRegistry
        self._service_registry = ServiceRegistry(self.data_path)
        self._convention_registry = ConventionRegistry(self.data_path)

        self.services = ServiceContainer(mid=MID_KERNEL,
                                         service_registry=self._service_registry)
        self.event_bus = EventBus()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        config_file = f"{self.data_path}/config.json" if data_path else "config.json"
        self.config_mgr = ConfigManager(file_path=config_file, data_dir=self.data_path)
        self.group_config_mgr = GroupConfigManager(self.config_mgr, self.data_path)
        self.recovery = RecoveryEngine(self.data_path)

        # 多机器人守卫（连接数 >1 时自动初始化）
        self.robot_registry = None
        self.cross_validator = None
        self.send_guard = None
        self.load_balancer = None
        self.hash_router = None
        self._msg_mgrs: Dict[str, object] = {}  # 每机器人独立 message_mgr 映射

        # 驱动列表 — 不在内核依赖树中的模块
        self._drivers_enabled = {
            "recovery": True,
            "event_bridge": True,
            "gatekeeper": True,
            "ipc": True,       # v11: IPC Service + Worker Pool
            "registry": True,   # v11: 模块注册表（允则权威来源）
        }
        self.package_mgr = PackageManager()
        self.command_mgr = CommandManager()
        self.tool_mgr = ToolManager()

        # root 级 (uid=0): 终端持有者/内核开发者
        self.services.register("event_bus", self.event_bus, uid=TIER_KERNEL,
                               _caller="qqlinker_framework.core.host")
        # app 级 (uid=300): 所有模块可访问的管理器
        self.services.register("config", self.config_mgr, uid=TIER_APP,
                               _caller="qqlinker_framework.core.host")
        self.services.register("group_config", self.group_config_mgr, uid=TIER_APP,
                               _caller="qqlinker_framework.core.host")
        self.services.register("package", self.package_mgr, uid=TIER_APP,
                               _caller="qqlinker_framework.core.host")
        self.services.register("command", self.command_mgr, uid=TIER_APP,
                               _caller="qqlinker_framework.core.host")
        self.services.register("tool", self.tool_mgr, uid=TIER_APP,
                               _caller="qqlinker_framework.core.host")
        self.services.register("adapter", adapter, uid=TIER_SERVICE,
                               _caller="qqlinker_framework.core.host")

        # v8: SourceManager 注入子管理器引用，统一所有扫描/发现/加载入口
        self.module_mgr = SourceManager(
            self,
            tool_mgr=self.tool_mgr,
            package_mgr=self.package_mgr,
        )
        self.message_mgr = MessageManager(adapter)
        self.services.register("message", self.message_mgr, uid=TIER_APP,
                               _caller="qqlinker_framework.core.host")
        self.services.register("recovery", self.recovery, uid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")
        # UID 查询函数（所有模块可读，仅查询不修改）
        self.services.register("uid_lookup", self._lookup_uid, uid=TIER_APP,
                               is_factory=False,
                               _caller="qqlinker_framework.core.host")
        # v1.4.3: 交互式会话追踪器
        self._session_tracker = InteractiveSessionTracker()
        self.services.register("session_tracker", self._session_tracker, uid=TIER_APP,
                               is_factory=False,
                               _caller="qqlinker_framework.core.host")
        # FrameworkHost 自身注册为 _host 服务（供 kernel_auth .exec 等使用）
        self.services.register("_host", self, uid=TIER_KERNEL,
                               _caller="qqlinker_framework.core.host")

        # 事件桥接 + 控制台命令（在 start() 中构造，依赖 services 就绪）
        self.bridge = None
        self.console = ConsoleCommands(self)

        # 资源守护者（v5 第四层奶酪片 — 运行时资源监控）
        self.guardian = ResourceGuardian(
            config=GuardianConfig(),
            kill_callback=self._guardian_kill_module,
            host_ref=self,
        )

        # 能力安全桥梁（uid=0 特权，但不注册为服务）
        self.gatekeeper = GatekeeperBridge(self.services)

        # ── 优雅降级引擎（v5: 级联故障隔离 + 服务分级）──
        self.degradation = GracefulDegradation(
            event_bus=self.event_bus,
            on_panic=None,  # panic 回调由框架外部 watchdog 设置
        )
        self.services.register("degradation", self.degradation, uid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")

        # ── v5.2: 服务注册表注册为服务（管理面板/状态命令可查）──
        self.services.register("service_registry", self._service_registry,
                               mid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")
        # ── v5.3: 约定注册表 ──
        self.services.register("convention_registry", self._convention_registry,
                               mid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")

        # ── 模块健康评分系统（v5: 多维度评分）──
        self.health_scorer = ModuleHealthScorer(data_path=self.data_path)
        self._module_health_status: Dict[str, str] = {}  # "healthy"|"degraded"|"dead"

        # ── TelemetryHub — 统一可观测性中心（v6）──
        self.telemetry = TelemetryHub(
            event_bus=self.event_bus,
            health_scorer=self.health_scorer,
        )

        # ── 事件循环看门狗（v5: 假死检测 + 降级恢复）──
        self._watchdog: Optional[EventLoopWatchdog] = None

        # ── v11: 模块注册表 + IPC（延迟到 _post_start_init）──
        self._registry: Optional[object] = None
        self._ipc_server: Optional[object] = None
        self._ipc_pool: Optional[object] = None

        self._modules: List[Module] = []
        self._router = None
        self._game_events_bridged = False

    # ── 模块发现与注册 ──

    def register_module(self, module_cls: Type[Module]):
        """注册单个模块类。"""
        self.module_mgr.register(module_cls)

    def register_modules_from_package(
        self, package_name: str = "qqlinker_framework.modules"
    ):
        """从 Python 包自动发现并注册模块（委托给 SourceManager）。"""
        self.module_mgr.discover_from_package(package_name)

    def register_external_modules(self):
        """从外部目录扫描并注册模块（委托给 SourceManager）。"""
        self.module_mgr.discover_from_files(self.data_path)

    # ── 生命周期 ──

    async def start(self):
        """启动框架：通过库挂载链初始化所有组件。

        框架不直接初始化任何业务组件。
        每个组件通过独立的引导库 mount(host) 接入信道。
        """
        self._main_loop = asyncio.get_running_loop()
        logger = logging.getLogger(__name__)

        # 递归重启防护
        if not self.recovery.check_restart_guard():
            logger.critical(
                "递归重启防护已激活，框架拒绝启动。"
                "请检查配置后删除 %s",
                self.recovery.get_blocked_path(),
            )
            return

        # 目录结构
        data_dir = self.data_path
        for d in [os.path.join(data_dir, "模块"),
                  os.path.join(data_dir, "工具"),
                  os.path.join(data_dir, "工具", "工具数据"),
                  os.path.join(data_dir, "第三方库")]:
            os.makedirs(d, exist_ok=True)
        self._ensure_log_handlers()
        self.package_mgr.set_target_dir(os.path.join(self.data_path, "第三方库"))

        # 模块注册表
        from .drivers.registry import ModuleRegistry
        self._registry = ModuleRegistry(self.data_path)
        self.module_mgr.registry = self._registry
        logger.info("模块注册表已加载: %s", self._registry.stats())
        self.console.register_all()

        # ── 配置引导 ──
        from qqlinker_framework.managers.config_bootstrap import ConfigBootstrap
        await ConfigBootstrap().mount(self)

        # ── 模块市场引导 ──
        from qqlinker_framework.managers.market_bootstrap import MarketBootstrap
        await MarketBootstrap().mount(self)

        # ── 核心服务（消息管理器、工具、EventBridge）──
        self.tool_mgr.init_with_services(self.services)
        await self.message_mgr.start()

        # ── WebSocket 引导（去重/调试/WS/多机器人）──
        from qqlinker_framework.services.ws_bootstrap import WsBootstrap
        ws_bootstrap = WsBootstrap()
        await ws_bootstrap.mount(self)

        # ── 核心服务引导（事件桥接、路由、模块加载、恢复）──
        from qqlinker_framework.managers.core_services_bootstrap import CoreServicesBootstrap
        await CoreServicesBootstrap().mount(self)

        # ── 运行时守护 ──
        from qqlinker_framework.managers.runtime_bootstrap import RuntimeBootstrap
        await RuntimeBootstrap().mount(self)

        logger.info("框架启动完成")

    def _bridge_game_events(self):
        """绑定游戏侧回调到事件桥接（防重复）。"""
        if self._game_events_bridged:
            return
        self._game_events_bridged = True
        adapter = self.adapter
        if hasattr(adapter, 'listen_game_chat'):
            adapter.listen_game_chat(self.bridge.on_game_chat)
        elif hasattr(adapter, 'on_game_chat'):
            adapter.on_game_chat(self.bridge.on_game_chat)
        if hasattr(adapter, 'listen_player_join'):
            adapter.listen_player_join(self.bridge.on_player_join)
        elif hasattr(adapter, 'on_player_join'):
            adapter.on_player_join(self.bridge.on_player_join)
        if hasattr(adapter, 'listen_player_leave'):
            adapter.listen_player_leave(self.bridge.on_player_leave)
        elif hasattr(adapter, 'on_player_leave'):
            adapter.on_player_leave(self.bridge.on_player_leave)

    def _ensure_log_handlers(self):
        """确保 access 日志输出到文件。"""
        access_log = logging.getLogger("access")
        log_dir = os.path.join(self.data_path, "日志")
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, "聊天记录.log")
        abs_target = os.path.abspath(file_path)
        if not any(
            isinstance(h, logging.FileHandler)
            and hasattr(h, 'baseFilename')
            and os.path.exists(getattr(h, 'baseFilename', ''))
            and os.path.samefile(getattr(h, 'baseFilename', ''), abs_target)
            for h in access_log.handlers
        ):
            fh = logging.FileHandler(file_path, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"))
            access_log.addHandler(fh)
        access_log.setLevel(logging.INFO)
        access_log.propagate = False

    def send_message_round_robin(self, group_id: int, message: str) -> bool:
        """多机器人发送（通过 SendGuard + LoadBalancer 智能调度）。

        多机器人模式:
          - 通过 SendGuard.send_with_ack() 发送（含回显确认 + 故障转移）
          - LoadBalancer 选最空闲的机器人

        单机器人模式:
          - 降级为直接 send_group_msg
        """
        # 多机器人守卫模式
        if self.send_guard is not None:
            try:
                return self.send_guard.send_with_ack(group_id, message, priority=1)
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "SendGuard 发送失败 (fallback 到轮询): %s", e
                )

        # 单机器人或 fallback：轮询
        ws_clients = []
        for i in range(3):  # 最多3个
            svc_name = "ws_client" if i == 0 else f"ws_client_{i}"
            c = self.services.try_get(svc_name)
            if c and c.available:
                ws_clients.append(c)
        if not ws_clients:
            return False
        if not hasattr(self, '_rr_index'):
            self._rr_index = 0
        start = self._rr_index % len(ws_clients)
        for offset in range(len(ws_clients)):
            idx = (start + offset) % len(ws_clients)
            c = ws_clients[idx]
            try:
                c.send_group_msg(group_id, message)
                self._rr_index = (idx + 1) % len(ws_clients)
                return True
            except Exception:
                continue
        return False

    async def _guardian_kill_module(self, module_name: str) -> None:
        """资源守护者回调：杀死指定模块。"""
        logger = logging.getLogger(__name__)
        try:
            await self.unload_module(module_name)
            logger.warning("资源守护者已卸载模块: %s", module_name)
        except Exception as e:
            logger.error("资源守护者卸载模块 '%s' 失败: %s", module_name, e)

    # ═══════════════════════════════════════════════════════════
    # v11: IPC 服务 + Worker Pool（需 QQLINKER_ENABLE_IPC=1）
    # ═══════════════════════════════════════════════════════════

    async def _start_ipc(self) -> None:
        """启动 IPC 服务端和 Worker 子进程池。

        启动顺序:
          1. IPCServer — 监听 Unix socket
          2. WorkerPool — 启动 worker 子进程（含文件监控）

        Worker 子进程通过 Unix socket 与主进程通信，
        负责: 注册表操作、文件监控、AI 推理等非内核任务。
        """
        logger = logging.getLogger(__name__)

        try:
            from .ipc.server import IPCServer
            from .ipc.pool import WorkerPool
        except ImportError:
            logger.warning("IPC 模块不可用，跳过 IPC 服务启动")
            return

        # 确保 socket 目录存在
        os.makedirs(os.path.dirname(self._ipc_socket_path), exist_ok=True)

        # 1. 启动 IPC Server
        self._ipc_server = IPCServer(self._ipc_socket_path)  # noqa: F821 (imported in try block above)

        # 注册主进程侧处理器:
        # worker 通过 IPC 发来的重载/卸载请求在主事件循环中执行
        async def _handle_module_reload(params: dict):
            name = params.get("module_name", "")
            if name:
                ok = await self.reload_module(name)
                return {"ok": ok, "module_name": name}
            return {"ok": False, "error": "missing module_name"}

        async def _handle_module_unload(params: dict):
            name = params.get("module_name", "")
            if name:
                ok = await self.unload_module(name)
                return {"ok": ok, "module_name": name}
            return {"ok": False, "error": "missing module_name"}

        self._ipc_server.register("module.reload_exec", _handle_module_reload)
        self._ipc_server.register("module.unload_exec", _handle_module_unload)

        await self._ipc_server.start()
        logger.info("IPC 服务已启动: %s", self._ipc_socket_path)

        # 2. 启动 Worker Pool（含文件监控 worker）
        #    延迟启动，等待主进程事件循环稳定
        self._ipc_pool = WorkerPool(self._ipc_socket_path, count=1)  # noqa: F821 (imported in try block above)
        import sys
        _pkg_name = __package__ or "qqlinker_framework"
        self._ipc_pool._worker_cmd = [
            sys.executable, "-m", f"{_pkg_name}.core.ipc.worker",
            self._ipc_socket_path,
            "--data-path", self.data_path,
        ]
        # 延迟 2s 启动 Worker，确保主循环稳定
        asyncio.create_task(self._delayed_start_workers())

    async def _delayed_start_workers(self) -> None:
        """延迟启动 Worker 子进程，避免干扰主循环初始化。"""
        await asyncio.sleep(2)
        logger = logging.getLogger(__name__)
        try:
            await self._ipc_pool.start_all()
            logger.info("Worker Pool 已启动 (%d worker)", self._ipc_pool._count)
        except Exception as e:
            logger.error("Worker Pool 启动失败（不影响主框架）: %s", e)

    async def stop(self):
        """优雅停止框架。幂等——可被多次调用。"""
        logger = logging.getLogger(__name__)
        from .kernel.events import SystemStopEvent
        try:
            await self.event_bus.publish(SystemStopEvent(), caller_uid=0)
        except Exception as e:
            logger.debug("发布停止事件时异常: %s", e)
        for mod in self._modules:
            try:
                await asyncio.wait_for(mod.on_stop(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("模块 %s 停止超时 (5s)，强制跳过", mod.name)
            except Exception as e:
                logger.error("模块 %s 停止异常: %s。%s",
                             mod.name, e, hint["MODULE_STOP_FAILED"])
        self._modules.clear()
        try:
            await self.message_mgr.stop()
        except Exception as e:
            logger.debug("停止消息管理器时异常: %s", e)
        ws_client = self.services.try_get("ws_client")
        if ws_client:
            try:
                ws_client.disconnect()
            except Exception as e:
                logger.debug("断开 WS 时异常: %s", e)
        try:
            self.config_mgr.stop_watching()
        except Exception as e:
            logger.debug("停止配置监控时异常: %s", e)
        try:
            self.group_config_mgr.stop_watching()
        except Exception as e:
            logger.debug("停止群配置监控时异常: %s", e)
        try:
            await self.recovery.stop()
        except Exception as e:
            logger.debug("停止恢复引擎时异常: %s", e)
        try:
            await self.guardian.stop()
        except Exception as e:
            logger.debug("停止资源守护者时异常: %s", e)
        # ── v5: 停止看门狗 ──
        if self._watchdog:
            try:
                await self._watchdog.stop()
            except Exception as e:
                logger.debug("停止看门狗时异常: %s", e)
        # ── v11: 停止 IPC ──
        if self._ipc_pool:
            try:
                await self._ipc_pool.stop_all()
            except Exception as e:
                logger.debug("停止 WorkerPool 时异常: %s", e)
        if self._ipc_server:
            try:
                await self._ipc_server.stop()
            except Exception as e:
                logger.debug("停止 IPCServer 时异常: %s", e)
        self.recovery.mark_clean_exit()
        self.recovery.clean_shutdown()
        market_server = self.services.try_get("market_server")
        if market_server:
            try:
                market_server.stop()
            except Exception as e:
                logger.debug("停止市场服务时异常: %s", e)
        # 持久化健康评分
        try:
            self.health_scorer.save()
        except Exception as e:
            logger.debug("保存健康评分时异常: %s", e)
        logger.info("框架已停止")

    # ── 配置热重载回调（watcher 线程安全）──

    def _lookup_uid(self, user_id: int) -> int:
        """查询用户的 UID 等级（供 CommandRouter 使用）。

        逻辑（与 auth 模块一致）:
          1. 查 权限管理.UID授权 表
          2. 查 管理员.管理员QQ 列表 → uid=100
          3. 否则 nobody (400)
        """
        if user_id == 0:
            return TIER_KERNEL

        uid_map = self.config_mgr.get("权限管理.UID授权", {}, requester_uid=0)
        if isinstance(uid_map, dict):
            for uid_str, qq_list in uid_map.items():
                try:
                    uid_level = int(uid_str)
                except ValueError:
                    continue
                if isinstance(qq_list, list):
                    uid_int = int(user_id) if not isinstance(user_id, int) else user_id
                    qq_ints = [int(q) for q in qq_list if q]
                    if uid_int in qq_ints:
                        return uid_level
        # 管理员列表（兼容字符串和整数 user_id）
        admin_list = self.config_mgr.get("管理员.管理员QQ", [], requester_uid=0)
        if isinstance(admin_list, list):
            try:
                uid_int = int(user_id) if not isinstance(user_id, int) else user_id
                admin_ints = [int(q) for q in admin_list if q]
                if uid_int in admin_ints:
                    return 100
            except (TypeError, ValueError):
                pass
        return UID_NOBODY

    def _on_config_reloaded(self):
        """配置热重载后，安全广播 ConfigReloadEvent。

        也从 watcher 线程调用，通过 run_coroutine_threadsafe 投递到主循环。

        Fix 3: 0.5s 防抖窗口 — config_mgr 和 group_config_mgr 两个 watcher
        可能短时间内同时触发，去重后只广播一次 ConfigReloadEvent。
        """
        if not (self._main_loop and self._main_loop.is_running() and self.event_bus):
            return
        now = time.monotonic()
        if hasattr(self, '_last_config_reload_ts'):
            if now - self._last_config_reload_ts < 0.5:
                return  # 防抖：静默跳过
        self._last_config_reload_ts = now

        # v1.4.3: 同时重载模块注册表（注册表是独立文件，不在 ConfigManager 管理范围内）
        if hasattr(self, '_registry') and self._registry is not None:
            self._registry.reload()

        asyncio.run_coroutine_threadsafe(
            self.event_bus.publish(ConfigReloadEvent(), caller_uid=0),
            self._main_loop,
        )

    # ── 审计追溯命令 ──

    def _register_audit_command(self) -> None:
        """注册 .审计 内核命令 (daemon 级权限)。"""
        from .kernel.context import CommandContext

        async def _cmd_audit(ctx: CommandContext):
            """.审计 <用户|模块|热点|用户排行|统计> [参数]"""
            at = self.audit_trail
            if not at:
                await ctx.reply("⚠️ 审计追溯系统未初始化")
                return

            args = ctx.args
            if not args:
                # 默认显示统计 + 热点
                stats = at.get_stats()
                hotspots = at.get_hotspots(5)
                lines = [
                    "📊 **审计统计**",
                    f"  总命令数: {stats['total_commands']}",
                    f"  成功率: {stats['success_rate']*100:.1f}%",
                    f"  独立用户: {stats['unique_users']}",
                    f"  独立模块: {stats['unique_modules']}",
                    f"  平均耗时: {stats['avg_elapsed_ms']:.1f}ms",
                ]
                if hotspots:
                    lines.append("  \n🔥 **热点命令 Top 5**:")
                    for cmd, count in hotspots:
                        lines.append(f"    {cmd}: {count} 次")
                lines.append("\n💡 用法: .审计 <用户|模块|热点|用户排行|统计>")
                await ctx.reply("\n".join(lines))
                return

            sub = args[0].lower()

            if sub == "用户":
                uid = int(args[1]) if len(args) > 1 and args[1].isdigit() else ctx.user_id
                records = at.get_by_user(uid, limit=10)
                if not records:
                    await ctx.reply(f"📭 用户 {uid} 暂无命令记录")
                else:
                    lines = [f"📋 用户 {uid} 最近 {len(records)} 条命令:"]
                    for r in records:
                        status = "✅" if r.get("success") else "❌"
                        lines.append(
                            f"  {status} {r.get('command')} "
                            f"(模块:{r.get('module')}, 耗时:{r.get('elapsed_ms',0):.0f}ms)"
                        )
                    await ctx.reply("\n".join(lines))

            elif sub == "模块":
                mod_name = args[1] if len(args) > 1 else "core"
                records = at.get_by_module(mod_name, limit=10)
                if not records:
                    await ctx.reply(f"📭 模块 '{mod_name}' 暂无命令记录")
                else:
                    lines = [f"📦 模块 '{mod_name}' 最近 {len(records)} 条命令:"]
                    for r in records:
                        status = "✅" if r.get("success") else "❌"
                        lines.append(
                            f"  {status} {r.get('command')} "
                            f"(用户:{r.get('user_id')}, 耗时:{r.get('elapsed_ms',0):.0f}ms)"
                        )
                    await ctx.reply("\n".join(lines))

            elif sub == "热点":
                hotspots = at.get_hotspots(10)
                if not hotspots:
                    await ctx.reply("📭 暂无命令数据")
                else:
                    lines = [f"🔥 **最常用命令 Top {len(hotspots)}**:"]
                    for i, (cmd, count) in enumerate(hotspots, 1):
                        lines.append(f"  {i}. {cmd}: {count} 次")
                    await ctx.reply("\n".join(lines))

            elif sub == "用户排行":
                hot_users = at.get_hot_users(10)
                if not hot_users:
                    await ctx.reply("📭 暂无命令数据")
                else:
                    lines = [f"👤 **最活跃用户 Top {len(hot_users)}**:"]
                    for i, (uid, count) in enumerate(hot_users, 1):
                        lines.append(f"  {i}. QQ:{uid}: {count} 次")
                    await ctx.reply("\n".join(lines))

            elif sub == "统计":
                stats = at.get_stats()
                lines = [
                    "📊 **审计统计摘要**",
                    f"  总命令数: {stats['total_commands']}",
                    f"  成功率: {stats['success_rate']*100:.1f}%",
                    f"  独立用户: {stats['unique_users']}",
                    f"  独立模块: {stats['unique_modules']}",
                    f"  平均耗时: {stats['avg_elapsed_ms']:.1f}ms",
                ]
                await ctx.reply("\n".join(lines))

            else:
                await ctx.reply(
                    "📋 **.审计 用法:**\n"
                    "  .审计              → 统计摘要 + 热点\n"
                    "  .审计 用户 [QQ号]  → 查询用户命令记录\n"
                    "  .审计 模块 <模块名> → 查询模块命令记录\n"
                    "  .审计 热点         → 最常用命令排名\n"
                    "  .审计 用户排行     → 最活跃用户排名\n"
                    "  .审计 统计         → 统计摘要"
                )

        self.command_mgr.register(
            ".审计", _cmd_audit,
            description="命令审计追溯 (用户/模块/热点/统计)",
            plugin_name="kernel",
            min_uid=100,  # daemon 级权限
        )

    # ── 热插拔 API ──

    async def unload_module(self, module_name: str) -> bool:
        """卸载指定模块。"""
        result = await self.module_mgr.unload_module(module_name)
        if result:
            self.health_scorer.save()
            # v6: 同步 module_names
            self.group_filter.set_module_names(
                set(self.module_mgr._loaded_modules.keys())
            )
            self.telemetry.record("module.lifecycle", {
                "module": module_name, "action": "unload",
            })
        return result

    async def load_module(self, module_cls: Type[Module]) -> Optional[Module]:
        """热加载新模块类。"""
        mod = await self.module_mgr.load_module(module_cls)
        if mod:
            self.health_scorer.register_module(mod.name)
            self.health_scorer.on_module_init(mod.name, success=True)
            # v6: 同步 module_names
            self.group_filter.set_module_names(
                set(self.module_mgr._loaded_modules.keys())
            )
            self.telemetry.record("module.lifecycle", {
                "module": mod.name, "action": "load",
            })
        return mod

    async def reload_module(self, module_name: str) -> bool:
        """重载指定模块。"""
        result = await self.module_mgr.reload_module(module_name)
        if result:
            self.health_scorer.on_module_init(module_name, success=True)
            self.group_filter.set_module_names(
                set(self.module_mgr._loaded_modules.keys())
            )
            self.telemetry.record("module.lifecycle", {
                "module": module_name, "action": "reload",
            })
        return result

    # ── v6: FREEZE / THAW API ──

    async def freeze_module(self, name: str) -> bool:
        """冻结指定模块 — 委托给 SourceManager。"""
        result = await self.module_mgr.freeze_module(name)
        if result:
            self.telemetry.record("module.lifecycle", {
                "module": name, "action": "freeze",
            })
        return result

    async def thaw_module(self, name: str) -> bool:
        """解冻指定模块 — 委托给 SourceManager。"""
        result = await self.module_mgr.thaw_module(name)
        if result:
            self.telemetry.record("module.lifecycle", {
                "module": name, "action": "thaw",
            })
        return result

    def list_frozen(self) -> list:
        """返回已冻结模块列表 — 委托给 SourceManager。"""
        return self.module_mgr.list_frozen()

    @property
    def main_loop(self):
        """公开主事件循环引用（供 event_bridge 等内部组件使用）。"""
        return self._main_loop

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
        self.services = ServiceContainer(mid=MID_KERNEL)
        self.event_bus = EventBus()
        self.data_path = data_path or "."
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
        """启动框架：初始化目录、配置、服务、模块、事件桥接。"""
        self._main_loop = asyncio.get_running_loop()
        logger = logging.getLogger(__name__)

        # 递归重启防护检查（在目录创建前，避免写文件）
        if not self.recovery.check_restart_guard():
            logger.critical(
                "递归重启防护已激活，框架拒绝启动。"
                "请检查配置后删除 %s",
                self.recovery.get_blocked_path(),
            )
            return

        data_dir = self.data_path
        dirs = [
            os.path.join(data_dir, "模块"),
            os.path.join(data_dir, "工具"),
            os.path.join(data_dir, "工具", "工具数据"),
            os.path.join(data_dir, "第三方库"),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        self._ensure_log_handlers()
        self.package_mgr.set_target_dir(os.path.join(self.data_path, "第三方库"))

        # v1.4.3: 模块注册表（同步加载，纯文件IO，毫秒级）
        from .drivers.registry import ModuleRegistry
        self._registry = ModuleRegistry(self.data_path)
        self.module_mgr.registry = self._registry
        logger.info("模块注册表已加载: %s", self._registry.stats())

        # 控制台命令
        self.console.register_all()

        # 配置节
        self.config_mgr.register_section("网络连接", {
            "地址": "ws://127.0.0.1:8080", "令牌": "",
            "启用多机器人守卫": True,
            "错误显示模式": "友好",
        }, caller_uid=0)
        self.config_mgr.register_section("权限管理", {
            "角色": {},
        }, caller_uid=0)
        self.config_mgr.register_section("启动检查", {
            "跳过完整性校验": False,
        }, caller_uid=0)
        self.config_mgr.register_section("去重", {
            "本地ID有效期秒": 300, "本地内容有效期秒": 120,
            "本地最大条目数": 10000, "启用Redis": False,
            "Redis地址": "redis://localhost:6379/0",
        }, caller_uid=0)
        self.config_mgr.register_section("调试引擎", {
            "消息记录上限": 200, "API记录上限": 100,
            "启用WebSocket原始帧": False,
        }, caller_uid=0)
        self.config_mgr.register_section("模块管理", {
            "禁用模块": [],
            "启用模块": [],
            "禁用命令": [],
            "启用命令": [],
            "模式": "黑名单",
        }, caller_uid=0)
        self.group_config_mgr.register_module_schema(
            "模块管理",
            {"禁用模块": [], "启用模块": [],
             "禁用命令": [], "启用命令": [], "模式": "黑名单"},
            scope="group",
        )
        self.config_mgr.register_section("模块市场", {
            "启用": False, "地址": "127.0.0.1", "端口": 8380,
            "上传密钥": "", "签名密钥": "", "强制签名校验": False,
            "白名单模块": [], "每页数量": 20,
            "源列表": ["http://127.0.0.1:8380"],
        }, caller_uid=0)
        # 安全配置
        self.config_mgr.register_section("审计日志", {
            "审计日志最大行数": 100000,
            "审计日志清理间隔": 86400,
        }, caller_uid=0)
        self.config_mgr.register_section("网络传输", {
            "TLS验证模式": "enabled",
            "连接超时秒": 10,
            "读超时秒": 30,
        }, caller_uid=0)
        self.config_mgr.register_section("SSRF防护", {
            "黑名单域名": ["metadata.google.internal", "169.254.169.254"],
            "禁止内网IP": True,
        }, caller_uid=0)
        self.config_mgr.register_section("调试", {
            "生产模式禁用": True,
        }, caller_uid=0)
        self.config_mgr.load()

        # ── 初始化审计日志 ──
        from .kernel.audit import configure_audit
        audit_log_path = os.path.join(
            self.data_path, "日志", "审计日志.log"
        )
        audit_max_lines = self.config_mgr.get(
            "审计日志.审计日志最大行数", 100000
        , requester_uid=0)
        audit_cleanup = self.config_mgr.get(
            "审计日志.审计日志清理间隔", 86400
        , requester_uid=0)
        configure_audit(audit_log_path, audit_max_lines, audit_cleanup)
        logger.info("审计日志已配置: %s", audit_log_path)

        # 错误显示模式
        from .kernel.error_hints import ErrorMode
        ErrorMode.set_config_source(self.config_mgr)
        logger.info("错误显示模式: %s", "友好" if ErrorMode.is_friendly() else "调试")

        # 配置热重载（watcher 线程感知 → 通过 run_coroutine_threadsafe 安全投递）
        self.config_mgr.start_watching(
            interval=2.0,
            on_reload=self._on_config_reloaded,
        )
        self.group_config_mgr.set_reload_callback(self._on_config_reloaded)
        self.group_config_mgr.start_watching(interval=3.0)

        ws_address = self.config_mgr.get("网络连接.地址", "ws://127.0.0.1:8080", requester_uid=0)
        # 安全: WebSocket 令牌优先从环境变量读取，避免明文存在配置文件中
        ws_token = os.environ.get("QQLINKER_WS_TOKEN",
                                  self.config_mgr.get("网络连接.令牌", "", requester_uid=0))
        logger.info("WebSocket 地址: %s", ws_address)

        if hasattr(self.adapter, 'set_config_mgr'):
            self.adapter.set_config_mgr(self.config_mgr)

        # 去重引擎（仅通过 services 访问，不存 self.dedup）— 非关键服务，降级运行
        dedup_cfg = DedupConfig(
            local_id_ttl=self.config_mgr.get("去重.本地ID有效期秒", 300, requester_uid=0),
            local_content_ttl=self.config_mgr.get("去重.本地内容有效期秒", 120, requester_uid=0),
            local_max_size=self.config_mgr.get("去重.本地最大条目数", 10000, requester_uid=0),
            redis_enabled=self.config_mgr.get("去重.启用Redis", False, requester_uid=0),
            redis_url=self.config_mgr.get("去重.Redis地址", "redis://localhost:6379/0", requester_uid=0),
            redis_password=os.environ.get("QQLINKER_REDIS_PASSWORD") or self.config_mgr.get("去重.Redis密码", None, requester_uid=0),
        )
        try:
            dedup = LayeredDedup(dedup_cfg)
            self.services.register("dedup", dedup, uid=TIER_SERVICE,
                                   _caller="qqlinker_framework.core.host")
        except Exception as e:
            logger.warning("去重引擎初始化失败: %s", e)
            self.degradation.on_service_fail("dedup", str(e), e)
            dedup = None

        try:
            debug_engine = DebugEngine(self.services, self.config_mgr, self.event_bus)
            self.services.register("debug", debug_engine, uid=UID_NOBODY,
                                   _caller="qqlinker_framework.core.host")
        except Exception as e:
            logger.warning("调试引擎初始化失败: %s", e)
            self.degradation.on_service_fail("debug_engine", str(e), e)

        self.tool_mgr.init_with_services(self.services)
        await self.message_mgr.start()

        # 事件桥接：使用独立参数构造，不持有 FrameworkHost 引用
        self.bridge = EventBridge(
            event_bus=self.event_bus,
            config_mgr=self.config_mgr,
            dedup=dedup,
            main_loop_getter=lambda: self._main_loop,
            adapter=self.adapter,
            session_tracker=self._session_tracker,
        )

        # 模块市场（可选，仅通过 services 访问，不存 self 引用）
        market_cfg = self.config_mgr.get("模块市场", {}, requester_uid=0)
        if market_cfg.get("启用", False):
            # 安全: 敏感密钥优先从环境变量读取，避免明文存在配置文件中
            upload_token = os.environ.get(
                "QQLINKER_UPLOAD_TOKEN", market_cfg.get("上传密钥", ""))
            sign_secret = os.environ.get(
                "QQLINKER_SIGN_SECRET", market_cfg.get("签名密钥", ""))
            market_server = ModuleMarketServer(
                data_path=self.data_path,
                host=market_cfg.get("地址", "127.0.0.1"),
                port=market_cfg.get("端口", 8380),
                upload_token=upload_token,
                whitelist=market_cfg.get("白名单模块", []),
                sign_secret=sign_secret,
                strict_sign=market_cfg.get("强制签名校验", False),
                per_page=market_cfg.get("每页数量", 20),
            )
            market_server.start()
            # 注册到 services，stop() 中通过 services 获取并停止
            self.services.register("market_server", market_server, uid=TIER_SERVICE,
                                   _caller="qqlinker_framework.core.host")
            logger.info("模块市场已启动: %s", market_server.url)

        source_urls = market_cfg.get("源列表", ["http://127.0.0.1:8380"])
        market_aggregator = MarketSourceAggregator(source_urls)
        self.services.register("market", market_aggregator, uid=TIER_SERVICE,
                               _caller="qqlinker_framework.core.host")

        # WebSocket 多连接（仅通过 services 访问，不存 self.ws_client）
        try:
            _get_websocket()
            ws_available = True
        except ImportError:
            ws_available = False

        if ws_available:
            # 读取多机器人配置
            robot_list = self.config_mgr.get("网络连接.机器人列表", None, requester_uid=0)
            if robot_list and isinstance(robot_list, list):
                ws_addresses = [r.get("地址", ws_address) for r in robot_list]
                ws_tokens = [r.get("令牌", ws_token) for r in robot_list]
            else:
                ws_addresses = [ws_address]
                ws_tokens = [ws_token]

            # WebSocket 连接循环
            for i, (addr, tok) in enumerate(zip(ws_addresses, ws_tokens)):
                svc_name = "ws_client" if i == 0 else f"ws_client_{i}"
                ws_client = WsClient({
                    "ws_address": addr,
                    "ws_token": tok,
                    "网络传输.TLS验证模式": self.config_mgr.get(
                        "网络传输.TLS验证模式", "enabled"
                    , requester_uid=0),
                    "网络传输.连接超时秒": self.config_mgr.get(
                        "网络传输.连接超时秒", 10
                    , requester_uid=0),
                    "网络传输.读超时秒": self.config_mgr.get(
                        "网络传输.读超时秒", 30
                    , requester_uid=0),
                })
                self.services.register(svc_name, ws_client, uid=TIER_SERVICE,
                                       _caller="qqlinker_framework.core.host")
                if i == 0:
                    if hasattr(self.adapter, 'set_ws_client'):
                        self.adapter.set_ws_client(ws_client)
                    if hasattr(self.adapter, 'event_bus'):
                        self.adapter.event_bus = self.event_bus
                # v6: 包装 WS 回调，嵌入 TelemetryHub 记录点
                _orig_ws_cb = self.bridge.on_ws_group_message

                def _ws_cb_with_telemetry(data):
                    t0 = time.monotonic()
                    _orig_ws_cb(data)
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    self.telemetry.record("ws.message.in", {
                        "elapsed_ms": round(elapsed_ms, 2),
                        "has_message": bool(data.get("message") if isinstance(data, dict) else False),
                    })
                ws_client.set_message_callback(_ws_cb_with_telemetry)
                ws_client.connect()
                logger.info("WebSocket 连接已发起: %s", svc_name)

            # 多机器人守卫（机器人数 > 1 且配置开关开启时初始化）
            guard_enabled = self.config_mgr.get("网络连接.启用多机器人守卫", True, requester_uid=0)
            if guard_enabled and len(ws_addresses) > 1:
                from .drivers.robot_guard import RobotRegistry, CrossValidation, SendGuard
                from .drivers.load_balancer import LoadBalancer, HashRouter
                self.robot_registry = RobotRegistry()
                # 根据机器人数自动计算 quorum：>50% 共识
                n = len(ws_addresses)
                if n > 2:
                    quorum = max(2, n // 2 + 1)
                else:
                    quorum = min(2, n)
                self.cross_validator = CrossValidation(self.robot_registry, quorum=quorum)

                # ── 初始化负载均衡器 + 哈希路由器 ──
                self.load_balancer = LoadBalancer()
                self.hash_router = HashRouter()

                # ── 初始化 SendGuard（注入负载均衡器和路由器）──
                self.send_guard = SendGuard(
                    self.robot_registry,
                    load_balancer=self.load_balancer,
                    hash_router=self.hash_router,
                    max_retries=2,
                )

                # ── 为每个机器人创建独立的 MessageManager ──
                linked_groups = self.config_mgr.get("消息转发.链接的群聊", [], requester_uid=0)
                bot_names = []
                for i, (addr, _) in enumerate(zip(ws_addresses, ws_tokens)):
                    name = f"bot_{i}"
                    bot_names.append(name)
                    svc_name = "ws_client" if i == 0 else f"ws_client_{i}"
                    ws_client = self.services.get(svc_name)
                    self.robot_registry.register(name, ws_client, linked_groups)
                    # 为每个机器人创建独立 MessageManager（用于队列深度查询）
                    if name not in self._msg_mgrs:
                        from qqlinker_framework.managers import MessageManager
                        mgr = MessageManager(self.adapter)
                        mgr._queue = __import__('asyncio').PriorityQueue()
                        self._msg_mgrs[name] = mgr
                        svc_name_mgr = "message_mgr" if i == 0 else f"message_mgr_{i}"
                        self.services.register(svc_name_mgr, mgr, uid=TIER_DAEMON,
                                               _caller="qqlinker_framework.core.host")
                # 注入 message_mgrs 到 SendGuard
                self.send_guard.set_message_managers(self._msg_mgrs)

                # ── 注入 send_guard 到 adapter ──
                if hasattr(self.adapter, '_send_guard'):
                    self.adapter._send_guard = self.send_guard
                else:
                    setattr(self.adapter, '_send_guard', self.send_guard)

                logger.info(
                    "[多机器人守卫] 已启用 (quorum=%d, %d 个机器人: %s)",
                    quorum, len(ws_addresses), ", ".join(bot_names),
                )
                logger.info("[负载均衡] LoadBalancer (最少队列优先) + HashRouter 已初始化")
                logger.info("[发送确认] SendGuard (send_with_ack + 故障转移, max_retries=%d) 已初始化", 2)
        else:
            logger.warning("websocket-client 未安装，跳过 WS 连接")

        # 事件桥接：游戏侧 ↔ QQ 侧
        self._bridge_game_events()

        # 群级模块过滤器
        self.group_filter = GroupModuleFilter(self.group_config_mgr)
        # ── 网络连接管理器 ─────────────────────────────────
        self._network_mgr = NetworkManager(
            NetworkConfig(
                connect_timeout=self.config_mgr.get("网络传输.连接超时秒", 10, requester_uid=0),
                total_timeout=self.config_mgr.get("网络传输.读超时秒", 30, requester_uid=0),
                tls_verify=self.config_mgr.get("网络传输.TLS验证模式", "enabled", requester_uid=0),
                pool_size=self.config_mgr.get("网络传输.连接池大小", 5, requester_uid=0),
                pool_per_host=self.config_mgr.get("网络传输.每主机最大连接", 10, requester_uid=0),
            )
        )
        self.services.register("network", self._network_mgr, uid=TIER_SERVICE,
                               description="统一网络连接管理器（HTTP/WS/重试/熔断）")

        self.services.register("group_filter", self.group_filter, uid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")

        # 审计追溯系统
        from .kernel.audit_trail import AuditTrail
        self.audit_trail = AuditTrail(
            data_dir=self.data_path,
            retention_days=30,
        )
        logger.info("审计追溯系统已初始化: %s", self.audit_trail._data_dir)

        # 命令路由
        self._router = CommandRouter(
            self.command_mgr, self.adapter,
            self.config_mgr, self.message_mgr,
            group_filter=self.group_filter,
            loaded_modules=self.module_mgr._loaded_modules,
            uid_lookup=self._lookup_uid,
            audit_trail=self.audit_trail,
            source_mgr=self.module_mgr,
        )
        # v6: 包装命令路由，嵌入 TelemetryHub 记录点
        _orig_handle = self._router.handle_message

        async def _handle_with_telemetry(event):
            t0 = time.monotonic()
            result = await _orig_handle(event)
            elapsed_ms = (time.monotonic() - t0) * 1000
            self.telemetry.record("module.command.done", {
                "module": getattr(event, 'module_name', 'core'),
                "elapsed_ms": round(elapsed_ms, 2),
                "success": result is not False,
            })
            return result
        self.event_bus.subscribe("GroupMessageEvent", _handle_with_telemetry)

        # 注册内核 .审计 命令
        self._register_audit_command()

        # ── 管理工具编排器 ──（在模块加载前注册，模块可引用）
        from qqlinker_framework.managers import AdminToolManager
        self._admin_tool_mgr = AdminToolManager(self.services)
        self._admin_tool_mgr.init_with_services()
        self.services.register("admin_tool", self._admin_tool_mgr, uid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")
        # v8: 将 admin_tool_mgr 注入 SourceManager，统一管理
        self.module_mgr._admin_tool_mgr = self._admin_tool_mgr

        # ── v8: 工作流扫描（工具扫描由 AICore.on_init 中的 register_all 完成）──
        self.module_mgr.init_workflow_scanner(self.data_path)

        # 加载所有模块
        self._modules = await self.module_mgr.initialize_all()
        # 模块初始化后通知健康评分系统
        for mod in self._modules:
            self.health_scorer.register_module(mod.name)
            self.health_scorer.on_module_init(mod.name, success=True)
        if not any(m.name == "help" for m in self._modules):
            logger.warning("help 模块未加载，用户将无法查看命令帮助")

        # ── v6: 同步模块名列表到 GroupModuleFilter ──
        self.group_filter.set_module_names(
            {m.name for m in self._modules}
        )

        # ── 能力安全桥梁 ──（在所有服务和模块就绪后注册白名单方法）
        register_default_capabilities(self.gatekeeper)
        # 注册新的多层配置桥接
        from qqlinker_framework.managers import register_config_bridge
        register_config_bridge(self.gatekeeper, self.config_mgr)

        # 模块加载完毕后，传播新增字段到所有群子配置
        affected = self.group_config_mgr.propagate_new_fields()
        if affected:
            logger.info(
                "新字段已传播到 %d 个群子配置: %s",
                len(affected), ", ".join(affected),
            )

        # ── 崩溃恢复 ──
        was_crashed = self.recovery.was_crashed()
        if was_crashed:
            logger.warning("‼️ 检测到上次非正常退出，进入恢复模式")
            restored = await self.recovery.restore_all_checkpoints()
            if restored:
                logger.info(
                    "已加载 %d 个模块检查点: %s",
                    len(restored), ", ".join(restored.keys()),
                )
                for mod in self._modules:
                    if mod.name in restored:
                        try:
                            await mod.restore_checkpoint(restored[mod.name])
                            logger.info("模块 '%s' 状态已恢复", mod.name)
                        except Exception as e:
                            logger.error(
                                "模块 '%s' 恢复失败: %s", mod.name, e
                            )
        
        # 注册 checkpoint 模块（recovery.register_module 自动过滤未覆写的）
        for mod in self._modules:
            self.recovery.register_module(mod)
        
        self.recovery.start_heartbeat(interval=5.0)
        self.recovery.start_checkpoint_loop(interval=30.0)

        if not self.services.has("ws_client"):
            logger.info("未启用 WebSocket")
        # ── 启动资源守护者 ──
        await self.guardian.start()
        self.services.register(
            "guardian", self.guardian,
            uid=TIER_DAEMON,
            _caller="qqlinker_framework.core.host",
        )

        # ── 注册健康评分器到 services ──
        self.services.register(
            "health_scorer", self.health_scorer,
            uid=TIER_DAEMON,
            _caller="qqlinker_framework.core.host",
        )

        # ── v6: 注册 TelemetryHub 到 services ──
        self.services.register(
            "telemetry", self.telemetry,
            uid=MID_SERVICE,
            _caller="qqlinker_framework.core.host",
        )
        logger.info("TelemetryHub 已注册")

        logger.info("模块健康评分器已注册")

        # ── v5: 启动事件循环看门狗（假死检测 + 降级恢复）──
        try:
            self._watchdog = EventLoopWatchdog(
                event_loop=self._main_loop,
                degradation=self.degradation,
            )
            await self._watchdog.start()
            self.services.register(
                "watchdog", self._watchdog,
                uid=TIER_DAEMON,
                _caller="qqlinker_framework.core.host",
            )
        except Exception as e:
            logger.warning("看门狗启动失败（非关键）: %s", e)
            self.degradation.on_service_fail("watchdog", str(e), e)

        # ── 启动后自动压力测试（后台线程，不阻塞）──
        try:
            from .kernel.stress_tester import StressTester
            self._stress_tester = StressTester(self, data_path=self.data_path)
            self._stress_tester.start()
        except Exception as e:
            logger.warning("StressTester 启动失败（非关键）: %s", e)

        logger.info("框架启动完成")

        # v1.4.3: 注册表已在 start() 中同步加载，此处无延迟初始化
        # IPC Server/WorkerPool 暂不启动（ToolDelta 环境下不稳定）
        # 如需启用: 设置环境变量 QQLINKER_ENABLE_IPC=1

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
                await mod.on_stop()
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
                if isinstance(qq_list, list) and user_id in qq_list:
                    return uid_level
        # 管理员列表
        admin_list = self.config_mgr.get("管理员.管理员QQ", [], requester_uid=0)
        if isinstance(admin_list, list):
            try:
                if user_id in [int(q) for q in admin_list if q]:
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

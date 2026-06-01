"""FrameworkHost - 框架核心调度器 (v10)

职责: 组装服务/管理器/模块、控制生命周期、提供模块热插拔 API。
非职责: 事件桥接 → core/event_bridge.py
        控制台命令 → managers/console.py
"""
import asyncio
import logging
import os
from typing import Type, Optional, List

from .services import ServiceContainer
from .bus import EventBus
from .module import Module
from .routing import CommandRouter
from .event_bridge import EventBridge
from .autodiscover import (
    discover_modules as discover_from_package,
    discover_from_files,
    sort_by_dependencies,
)

from ..managers.config_mgr import ConfigManager
from ..managers.package_mgr import PackageManager
from ..managers.module_mgr import ModuleManager
from ..managers.command_mgr import CommandManager
from ..managers.message_mgr import MessageManager
from ..managers.tool_mgr import ToolManager
from ..managers.console import ConsoleCommands

from ..adapters.base import IFrameworkAdapter
from ..services.ws_client import WsClient, _get_websocket
from ..services.dedup import LayeredDedup, DedupConfig
from ..services.debug_engine import DebugEngine
from ..services.market_server import (
    ModuleMarketServer,
    MarketSourceAggregator,
)
from .error_hints import hint
from .events import ConfigReloadEvent


class FrameworkHost:
    """框架核心调度器 — 组装 + 生命周期 + 热插拔 API。"""

    def __init__(self, adapter: IFrameworkAdapter, data_path: str = None):
        self.adapter = adapter
        self.services = ServiceContainer(uid=0)
        self.event_bus = EventBus()
        self.data_path = data_path or "."
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        config_file = f"{self.data_path}/config.json" if data_path else "config.json"
        self.config_mgr = ConfigManager(file_path=config_file, data_dir=self.data_path)
        self.package_mgr = PackageManager()
        self.command_mgr = CommandManager()
        self.tool_mgr = ToolManager()

        # root 级 (uid=0): 终端持有者/内核开发者
        self.services.register("event_bus", self.event_bus, uid=0,
                               _caller="qqlinker_framework.core.host")
        # daemon 级 (uid=1): 框架内部守护 — 管理器
        self.services.register("config", self.config_mgr, uid=1,
                               _caller="qqlinker_framework.core.host")
        self.services.register("package", self.package_mgr, uid=1,
                               _caller="qqlinker_framework.core.host")
        self.services.register("command", self.command_mgr, uid=1,
                               _caller="qqlinker_framework.core.host")
        self.services.register("tool", self.tool_mgr, uid=1,
                               _caller="qqlinker_framework.core.host")
        self.services.register("adapter", adapter, uid=1,
                               _caller="qqlinker_framework.core.host")

        self.module_mgr = ModuleManager(self)
        self.message_mgr = MessageManager(adapter)
        self.services.register("message", self.message_mgr, uid=1,
                               _caller="qqlinker_framework.core.host")

        # 事件桥接 + 控制台命令
        self.bridge = EventBridge(self)
        self.console = ConsoleCommands(self)

        self.dedup = None
        self.ws_client = None
        self.market_server = None
        self.market_aggregator = None
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
        """从 Python 包自动发现并注册模块。"""
        classes = discover_from_package(package_name)
        if not classes:
            logging.getLogger(__name__).warning("未发现任何模块")
            return
        for cls in sort_by_dependencies(classes):
            self.module_mgr.register(cls)
        logging.getLogger(__name__).info(
            "从 '%s' 自动发现并注册了 %d 个模块", package_name, len(classes))

    def register_external_modules(self):
        """从外部目录扫描并注册模块。"""
        classes = discover_from_files(self.data_path)
        if not classes:
            logging.getLogger(__name__).debug("未发现外部模块")
            return
        for cls in sort_by_dependencies(classes):
            self.module_mgr.register(cls)
        logging.getLogger(__name__).info(
            "从外部目录发现并注册了 %d 个模块", len(classes))

    # ── 生命周期 ──

    async def start(self):
        """启动框架：初始化目录、配置、服务、模块、事件桥接。"""
        self._main_loop = asyncio.get_running_loop()
        logger = logging.getLogger(__name__)

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

        # 控制台命令
        self.console.register_all()

        # 配置节
        self.config_mgr.register_section("网络连接", {
            "地址": "ws://127.0.0.1:8080", "令牌": "",
            "错误显示模式": "友好",
        })
        self.config_mgr.register_section("权限管理", {
            "角色": {},
        })
        self.config_mgr.register_section("启动检查", {
            "跳过完整性校验": False,
        })
        self.config_mgr.register_section("去重", {
            "本地ID有效期秒": 300, "本地内容有效期秒": 120,
            "本地最大条目数": 10000, "启用Redis": False,
            "Redis地址": "redis://localhost:6379/0",
        })
        self.config_mgr.register_section("调试引擎", {
            "消息记录上限": 200, "API记录上限": 100,
            "启用WebSocket原始帧": False,
        })
        self.config_mgr.register_section("模块市场", {
            "启用": False, "地址": "127.0.0.1", "端口": 8380,
            "上传密钥": "", "签名密钥": "", "强制签名校验": False,
            "白名单模块": [], "每页数量": 20,
            "源列表": ["http://127.0.0.1:8380"],
        })
        self.config_mgr.load()

        # 错误显示模式
        from .error_hints import ErrorMode
        ErrorMode.set_config_source(self.config_mgr)
        logger.info("错误显示模式: %s", "友好" if ErrorMode.is_friendly() else "调试")

        # 配置热重载（watcher 线程感知 → 通过 run_coroutine_threadsafe 安全投递）
        self.config_mgr.start_watching(
            interval=2.0,
            on_reload=self._on_config_reloaded,
        )

        ws_address = self.config_mgr.get("网络连接.地址", "ws://127.0.0.1:8080")
        ws_token = self.config_mgr.get("网络连接.令牌", "")
        logger.info("WebSocket 地址: %s", ws_address)

        if hasattr(self.adapter, 'set_config_mgr'):
            self.adapter.set_config_mgr(self.config_mgr)

        # 去重引擎
        dedup_cfg = DedupConfig(
            local_id_ttl=self.config_mgr.get("去重.本地ID有效期秒", 300),
            local_content_ttl=self.config_mgr.get("去重.本地内容有效期秒", 120),
            local_max_size=self.config_mgr.get("去重.本地最大条目数", 10000),
            redis_enabled=self.config_mgr.get("去重.启用Redis", False),
            redis_url=self.config_mgr.get("去重.Redis地址", "redis://localhost:6379/0"),
        )
        self.dedup = LayeredDedup(dedup_cfg)
        self.services.register("dedup", self.dedup, uid=1000,
                               _caller="qqlinker_framework.core.host")

        debug_engine = DebugEngine(self.services, self.config_mgr, self.event_bus)
        self.services.register("debug", debug_engine, uid=1000,
                               _caller="qqlinker_framework.core.host")

        self.tool_mgr.init_with_services(self.services)
        await self.message_mgr.start()

        # 模块市场（可选）
        self.market_server = None
        market_cfg = self.config_mgr.get("模块市场", {})
        if market_cfg.get("启用", False):
            self.market_server = ModuleMarketServer(
                data_path=self.data_path,
                host=market_cfg.get("地址", "127.0.0.1"),
                port=market_cfg.get("端口", 8380),
                upload_token=market_cfg.get("上传密钥", ""),
                whitelist=market_cfg.get("白名单模块", []),
                sign_secret=market_cfg.get("签名密钥", ""),
                strict_sign=market_cfg.get("强制签名校验", False),
                per_page=market_cfg.get("每页数量", 20),
            )
            self.market_server.start()
            logger.info("模块市场已启动: %s", self.market_server.url)

        source_urls = market_cfg.get("源列表", ["http://127.0.0.1:8380"])
        self.market_aggregator = MarketSourceAggregator(source_urls)
        self.services.register("market", self.market_aggregator, uid=1000,
                               _caller="qqlinker_framework.core.host")

        # WebSocket
        try:
            _get_websocket()
            ws_available = True
        except ImportError:
            ws_available = False

        if ws_available:
            self.ws_client = WsClient({"ws_address": ws_address, "ws_token": ws_token})
            if hasattr(self.adapter, 'set_ws_client'):
                self.adapter.set_ws_client(self.ws_client)
            if hasattr(self.adapter, 'event_bus'):
                self.adapter.event_bus = self.event_bus
            self.ws_client.set_message_callback(self.bridge.on_ws_group_message)
            self.ws_client.connect()
            logger.info("WebSocket 连接已发起")
        else:
            logger.warning("websocket-client 未安装，跳过 WS 连接")

        # 事件桥接：游戏侧 ↔ QQ 侧
        self._bridge_game_events()

        # 命令路由
        self._router = CommandRouter(
            self.command_mgr, self.adapter,
            self.config_mgr, self.message_mgr,
        )
        self.event_bus.subscribe("GroupMessageEvent", self._router.handle_message)

        # 加载所有模块
        self._modules = await self.module_mgr.initialize_all()
        if not any(m.name == "help" for m in self._modules):
            logger.warning("help 模块未加载，用户将无法查看命令帮助")

        if not self.ws_client:
            logger.info("未启用 WebSocket")
        logger.info("框架启动完成")

    def _bridge_game_events(self):
        """绑定游戏侧回调到事件桥接（防重复）。"""
        if self._game_events_bridged:
            return
        self._game_events_bridged = True
        adapter = self.adapter
        if hasattr(adapter, 'on_game_chat'):
            adapter.on_game_chat(self.bridge.on_game_chat)
        if hasattr(adapter, 'on_player_join'):
            adapter.on_player_join(self.bridge.on_player_join)
        if hasattr(adapter, 'on_player_leave'):
            adapter.on_player_leave(self.bridge.on_player_leave)

    def _ensure_log_handlers(self):
        """确保 access 日志输出到文件。"""
        access_log = logging.getLogger("access")
        log_dir = os.path.join(self.data_path, "日志")
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, "聊天记录.log")
        if not any(isinstance(h, logging.FileHandler)
                   and getattr(h, 'baseFilename', '') == os.path.abspath(file_path)
                   for h in access_log.handlers):
            fh = logging.FileHandler(file_path, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"))
            access_log.addHandler(fh)
        access_log.setLevel(logging.INFO)
        access_log.propagate = False

    async def stop(self):
        """优雅停止框架。幂等——可被多次调用。"""
        logger = logging.getLogger(__name__)
        from .events import SystemStopEvent
        try:
            await self.event_bus.publish(SystemStopEvent())
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
        if self.ws_client:
            try:
                self.ws_client.disconnect()
            except Exception as e:
                logger.debug("断开 WS 时异常: %s", e)
        try:
            self.config_mgr.stop_watching()
        except Exception as e:
            logger.debug("停止配置监控时异常: %s", e)
        if self.market_server:
            try:
                self.market_server.stop()
            except Exception as e:
                logger.debug("停止市场服务时异常: %s", e)
        logger.info("框架已停止")

    # ── 配置热重载回调（watcher 线程安全）──

    def _on_config_reloaded(self):
        """配置热重载后，安全广播 ConfigReloadEvent。

        从 watcher 线程调用，通过 run_coroutine_threadsafe 投递到主循环。
        """
        if self._main_loop and self._main_loop.is_running() and self.event_bus:
            asyncio.run_coroutine_threadsafe(
                self.event_bus.publish(ConfigReloadEvent()),
                self._main_loop,
            )

    # ── 热插拔 API ──

    async def unload_module(self, module_name: str) -> bool:
        """卸载指定模块。"""
        return await self.module_mgr.unload_module(module_name)

    async def load_module(self, module_cls: Type[Module]) -> Optional[Module]:
        """热加载新模块类。"""
        return await self.module_mgr.load_module(module_cls)

    async def reload_module(self, module_name: str) -> bool:
        """重载指定模块。"""
        return await self.module_mgr.reload_module(module_name)

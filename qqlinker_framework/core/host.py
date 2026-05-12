"""FrameworkHost - 框架核心调度器"""
import asyncio
import json
import logging
import os
import sys
import threading
from typing import Type, Optional, List

from .services import ServiceContainer
from .bus import EventBus
from .module import Module
from .routing import CommandRouter
from .autodiscover import discover_modules, sort_by_dependencies

from ..managers.config_mgr import ConfigManager
from ..managers.package_mgr import PackageManager
from ..managers.module_mgr import ModuleManager
from ..managers.command_mgr import CommandManager
from ..managers.message_mgr import MessageManager
from ..managers.tool_mgr import ToolManager

from ..adapters.base import IFrameworkAdapter
from ..services.ws_client import WsClient, HAS_WEBSOCKET
from ..services.dedup import LayeredDedup, DedupConfig
from ..services.debug_engine import DebugEngine
from .events import (
    GroupMessageEvent,
    GameChatEvent,
    PlayerJoinEvent,
    PlayerLeaveEvent,
)

access_log = logging.getLogger("access")


class FrameworkHost:
    """框架核心调度器，负责初始化所有服务、管理器、模块并控制生命周期。"""

    def __init__(self, adapter: IFrameworkAdapter, data_path: str = None):
        """初始化框架主机，创建各管理器和服务。"""
        self.adapter = adapter
        self.services = ServiceContainer()
        self.event_bus = EventBus()
        self.data_path = data_path or "."
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        config_file = (
            f"{self.data_path}/config.json" if data_path else "config.json"
        )
        self.config_mgr = ConfigManager(
            file_path=config_file, data_dir=self.data_path
        )
        self.package_mgr = PackageManager()
        self.command_mgr = CommandManager()
        self.tool_mgr = ToolManager()

        self.services.register("config", self.config_mgr)
        self.services.register("package", self.package_mgr)
        self.services.register("command", self.command_mgr)
        self.services.register("tool", self.tool_mgr)
        self.services.register("event_bus", self.event_bus)
        self.services.register("adapter", adapter)

        self.module_mgr = ModuleManager(self)
        self.message_mgr = MessageManager(adapter)
        self.services.register("message", self.message_mgr)

        self.dedup = None
        self.ws_client = None
        self._modules: List[Module] = []
        self._game_events_bridged = False

    def register_module(self, module_cls: Type[Module]):
        """向模块管理器注册一个模块类。"""
        self.module_mgr.register(module_cls)

    def register_modules_from_package(
        self, package_name: str = "qqlinker_framework.modules"
    ):
        """从指定 Python 包自动发现并注册所有模块。"""
        classes = discover_modules(package_name)
        if not classes:
            logging.getLogger(__name__).warning("未发现任何模块")
            return
        sorted_classes = sort_by_dependencies(classes)
        for cls in sorted_classes:
            self.module_mgr.register(cls)
        logging.getLogger(__name__).info(
            "从 '%s' 自动发现并注册了 %d 个模块",
            package_name,
            len(sorted_classes),
        )

    async def start(self):
        """启动框架：初始化配置、WS连接、模块、事件桥接等。"""
        self._main_loop = asyncio.get_running_loop()
        self._ensure_log_handlers()

        data_dir = self.data_path
        dirs = [
            os.path.join(data_dir, "模块"),
            os.path.join(data_dir, "工具"),
            os.path.join(data_dir, "工具", "工具数据"),
            os.path.join(data_dir, "第三方库"),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        site_pkgs = os.path.join(self.data_path, "第三方库")
        self.package_mgr.set_target_dir(site_pkgs)

        self.adapter.register_console_command(
            ["qqdeps"],
            "[check|install]",
            "管理框架 Python 依赖",
            self._console_cmd_qqdeps,
        )
        self.adapter.register_console_command(
            ["qqhealth"],
            "",
            "查看框架健康状态",
            self._console_cmd_health,
        )

        self.config_mgr.register_section("网络连接", {
            "地址": "ws://127.0.0.1:8080",
            "令牌": "",
        })
        self.config_mgr.register_section("去重", {
            "本地ID有效期秒": 300,
            "本地内容有效期秒": 120,
            "本地最大条目数": 10000,
            "启用Redis": False,
            "Redis地址": "redis://localhost:6379/0",
            "启用布隆过滤器": False,
            "布隆错误率": 0.001,
            "布隆容量": 1000000,
            "启用分布式锁": False,
            "锁超时秒": 10,
            "Redis失败降级到本地": True,
        })
        self.config_mgr.register_section("调试引擎", {
            "启用": True,
            "消息记录上限": 200,
            "API记录上限": 100,
            "启用WebSocket原始帧": False,
        })

        self.config_mgr.load()

        ws_address = self.config_mgr.get(
            "网络连接.地址", "ws://127.0.0.1:8080"
        )
        ws_token = self.config_mgr.get("网络连接.令牌", "")
        logging.getLogger(__name__).info("WebSocket 地址: %s", ws_address)

        if hasattr(self.adapter, 'set_config_mgr'):
            self.adapter.set_config_mgr(self.config_mgr)

        dedup_cfg = DedupConfig(
            local_id_ttl=self.config_mgr.get("去重.本地ID有效期秒", 300),
            local_content_ttl=self.config_mgr.get("去重.本地内容有效期秒", 120),
            local_max_size=self.config_mgr.get("去重.本地最大条目数", 10000),
            redis_enabled=self.config_mgr.get("去重.启用Redis", False),
            redis_url=self.config_mgr.get("去重.Redis地址", "redis://localhost:6379/0"),
        )
        self.dedup = LayeredDedup(dedup_cfg)
        self.services.register("dedup", self.dedup)

        debug_engine = DebugEngine(self.services, self.config_mgr, self.event_bus)
        self.services.register("debug", debug_engine)

        self.tool_mgr.init_with_services(self.services)
        await self.message_mgr.start()

        if HAS_WEBSOCKET:
            self.ws_client = WsClient(
                {"ws_address": ws_address, "ws_token": ws_token}
            )
            if hasattr(self.adapter, 'set_ws_client'):
                self.adapter.set_ws_client(self.ws_client)
            if hasattr(self.adapter, 'event_bus'):
                self.adapter.event_bus = self.event_bus
            self.ws_client.set_message_callback(self._on_ws_group_message)
            self.ws_client.connect()
            logging.getLogger(__name__).info("WebSocket 连接已发起")
        else:
            logging.getLogger(__name__).warning(
                "websocket-client 未安装，跳过 WS 连接"
            )

        if not self._game_events_bridged:
            if hasattr(self.adapter, 'main_loop'):
                self.adapter.main_loop = self._main_loop
            self.adapter.listen_game_chat(self._on_game_chat_bridge)
            self.adapter.listen_player_join(self._on_player_join_bridge)
            self.adapter.listen_player_leave(self._on_player_leave_bridge)
            self._game_events_bridged = True

        self._modules = await self.module_mgr.initialize_all()

        debug_engine.install_hooks()

        if HAS_WEBSOCKET:
            router = CommandRouter(
                self.command_mgr,
                self.adapter,
                self.config_mgr,
                self.message_mgr,
            )
            self.event_bus.subscribe(
                "GroupMessageEvent", router.handle_message
            )

        from .events import SystemStartEvent
        await self.event_bus.publish(SystemStartEvent())

        if self.ws_client and self.ws_client.available:
            logging.getLogger(__name__).info("WebSocket 已就绪")
        elif self.ws_client:
            logging.getLogger(__name__).warning(
                "WebSocket 连接未建立，请检查地址或网络"
            )
        else:
            logging.getLogger(__name__).info("未启用 WebSocket")

        logging.getLogger(__name__).info("框架启动完成")

    def _ensure_log_handlers(self):
        """确保控制台和文件日志处理器已挂载。"""
        root = logging.getLogger()
        if not any(
            isinstance(h, logging.StreamHandler) for h in root.handlers
        ):
            console = logging.StreamHandler(sys.stderr)
            console.setLevel(logging.INFO)
            console.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            root.addHandler(console)

        file_path = f"{self.data_path}/framework.log"
        if not any(
            isinstance(h, logging.FileHandler)
            and h.baseFilename == os.path.abspath(file_path)
            for h in root.handlers
        ):
            file_handler = logging.FileHandler(file_path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            root.addHandler(file_handler)
        root.setLevel(logging.DEBUG)

        logging.getLogger("websocket").setLevel(logging.WARNING)

        if not any(
            isinstance(h, logging.FileHandler)
            and h.baseFilename == os.path.abspath(file_path)
            for h in access_log.handlers
        ):
            file_handler = logging.FileHandler(file_path, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            access_log.addHandler(file_handler)
        access_log.setLevel(logging.INFO)
        access_log.propagate = False

    async def stop(self):
        """优雅停止框架。"""
        logger = logging.getLogger(__name__)
        from .events import SystemStopEvent
        await self.event_bus.publish(SystemStopEvent())
        for mod in self._modules:
            await mod.on_stop()
        await self.message_mgr.stop()
        if self.ws_client:
            self.ws_client.disconnect()
        logger.info("框架已停止")

    def _console_cmd_qqdeps(self, args: list):
        """控制台命令 qqdeps。"""
        if not args:
            print("用法: qqdeps check | install")
            return
        sub = args[0].lower()
        if sub == "check":
            missing = self.package_mgr.check_missing()
            if missing:
                print(f"缺失依赖: {', '.join(missing.keys())}")
            else:
                print("所有 Python 依赖已就绪")
        elif sub == "install":
            missing = self.package_mgr.check_missing()
            if not missing:
                print("所有 Python 依赖已就绪，无需安装")
                return
            print(f"正在后台安装缺失依赖: {', '.join(missing.keys())}...")
            threading.Thread(
                target=self._install_deps_thread,
                args=(list(missing.keys()),),
                daemon=True,
            ).start()
        else:
            print("未知子命令，请使用 check 或 install")

    def _install_deps_thread(self, packages: list):
        """后台线程执行 pip 安装。"""
        success = self.package_mgr.install_packages(packages)
        if success:
            print("[qqdeps] 依赖安装成功，请重载插件以使新模块生效")
        else:
            print("[qqdeps] 部分或全部依赖安装失败，请检查日志")

    def _console_cmd_health(self, args: list):
        """控制台命令：输出框架健康状态。"""
        status = {
            "ws_connected": (
                self.ws_client.available if self.ws_client else False
            ),
            "loaded_modules": self.module_mgr.get_loaded_modules(),
            "counters": {},
            "redis_connected": False,
        }
        if self.dedup and self.dedup.redis and self.dedup.redis.client:
            try:
                self.dedup.redis.client.ping()
                status["redis_connected"] = True
            except Exception:
                pass
        debug = self.services.get("debug")
        if debug:
            status["counters"] = debug.get_counters()
        print(json.dumps(status, ensure_ascii=False, indent=2))

    def _on_game_chat_bridge(self, player_name: str, message: str):
        """将游戏聊天事件桥接到事件总线。"""
        if self._main_loop and self._main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.event_bus.publish(
                    GameChatEvent(player_name=player_name, message=message)
                ),
                self._main_loop,
            )

    def _on_player_join_bridge(self, player_name: str):
        """玩家加入事件桥接。"""
        if self._main_loop and self._main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.event_bus.publish(PlayerJoinEvent(player_name=player_name)),
                self._main_loop,
            )

    def _on_player_leave_bridge(self, player_name: str):
        """玩家离开事件桥接。"""
        if self._main_loop and self._main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.event_bus.publish(PlayerLeaveEvent(player_name=player_name)),
                self._main_loop,
            )

    def _on_ws_group_message(self, raw: dict):
        """处理 WebSocket 群消息。"""
        linked_groups = self.config_mgr.get("消息转发.链接的群聊", [])
        group_id = raw.get("group_id")
        if group_id not in linked_groups:
            return

        msg_id = raw.get("message_id")
        if msg_id and not self.dedup.check_and_add_id(f"raw_{msg_id}"):
            return

        raw_msg = raw.get("message")
        if isinstance(raw_msg, list):
            text_parts = []
            for seg in raw_msg:
                if seg.get("type") == "text":
                    text_parts.append(seg["data"].get("text", ""))
                elif seg.get("type") == "at":
                    qq = seg["data"].get("qq")
                    text_parts.append(
                        f"[@{qq}]" if qq != "all" else "[@全体成员]"
                    )
                else:
                    text_parts.append(f"[{seg.get('type')}]")
            text = "".join(text_parts)
        else:
            text = str(raw_msg) if raw_msg else ""

        nickname = (
            raw.get("sender", {}).get("card")
            or raw.get("sender", {}).get("nickname", "未知")
        )
        access_log.info("[QQ] %s: %s", nickname, text.strip())

        try:
            if hasattr(self.adapter, 'trigger_raw_group_handlers'):
                self.adapter.trigger_raw_group_handlers(raw)
        except Exception as e:
            logging.getLogger(__name__).error("原始消息处理器异常: %s", e)

        event = GroupMessageEvent(
            user_id=raw.get("user_id"),
            group_id=group_id,
            nickname=nickname,
            message=text.strip(),
            raw_data=raw,
        )

        if self._main_loop and self._main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.event_bus.publish(event), self._main_loop
            )

    async def unload_module(self, module_name: str) -> bool:
        """卸载指定名称的模块。"""
        return await self.module_mgr.unload_module(module_name)

    async def load_module(
        self, module_cls: Type[Module]
    ) -> Optional[Module]:
        """加载一个新的模块类实例。"""
        return await self.module_mgr.load_module(module_cls)

    async def reload_module(self, module_name: str) -> bool:
        """重载指定模块（先卸载再加载）。"""
        return await self.module_mgr.reload_module(module_name)

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
from .autodiscover import (
    discover_modules as discover_from_package,
    discover_from_files,
    download_module,
    list_external_modules,
    remove_external_module,
    sort_by_dependencies,
)

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
from ..services.market_server import (
    ModuleMarketServer,
    MarketSourceAggregator,
)
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
        self.market_server = None
        self.market_aggregator = None
        self._modules: List[Module] = []
        self._game_events_bridged = False

    def register_module(self, module_cls: Type[Module]):
        """向模块管理器注册一个模块类。"""
        self.module_mgr.register(module_cls)

    def register_modules_from_package(
        self, package_name: str = "qqlinker_framework.modules"
    ):
        """从指定 Python 包自动发现并注册所有模块。"""
        classes = discover_from_package(package_name)
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

    def register_external_modules(self):
        """从 插件数据文件/模块源件/ 扫描并注册外部模块。"""
        classes = discover_from_files(self.data_path)
        if not classes:
            logging.getLogger(__name__).debug("未发现外部模块")
            # 这是正常情况，不报 warning
            return
        sorted_classes = sort_by_dependencies(classes)
        for cls in sorted_classes:
            self.module_mgr.register(cls)
        logging.getLogger(__name__).info(
            "从 插件数据文件/模块源件/ 发现并注册了 %d 个模块",
            len(sorted_classes),
        )

    async def start(self):
        """启动框架：初始化配置、WS连接、模块、事件桥接等。"""
        self._main_loop = asyncio.get_running_loop()

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

        site_pkgs = os.path.join(self.data_path, "第三方库")
        self.package_mgr.set_target_dir(site_pkgs)

        self.adapter.register_console_command(
            ["qqdeps"],
            "[check|install|module] <list|add|remove> [url/名称]",
            "管理框架 Python 依赖与外部模块",
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
        self.config_mgr.register_section("模块市场", {
            "启用": False,
            "地址": "127.0.0.1",
            "端口": 8380,
            "上传密钥": "",
            "签名密钥": "",
            "白名单模块": [],
            "源列表": ["http://127.0.0.1:8380"],
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

        # ── 模块市场 HTTP 服务（可选）──
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
            )
            self.market_server.start()
            logging.getLogger(__name__).info(
                "模块市场已启动: %s", self.market_server.url
            )

        # ── 市场多源聚合器 ──
        source_urls = market_cfg.get("源列表", ["http://127.0.0.1:8380"])
        self.market_aggregator = MarketSourceAggregator(source_urls)
        self.services.register("market", self.market_aggregator)

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
            try:
                await mod.on_stop()
            except Exception as e:
                logger.error("模块 %s 停止异常: %s", mod.name, e)
        await self.message_mgr.stop()
        if self.ws_client:
            self.ws_client.disconnect()
        if self.market_server:
            self.market_server.stop()
        self.event_bus.shutdown()
        logger.info("框架已停止")

    def _console_cmd_qqdeps(self, args: list):
        """控制台命令 qqdeps — 管理 Python 依赖 + 外部模块 + 市场。

        用法:
          qqdeps check                  检查 Python 依赖
          qqdeps install                安装缺失的 Python 依赖
          qqdeps module list            列出已安装的外部模块
          qqdeps module add <url|名称>  从 URL 或市场下载模块
          qqdeps module remove <名>     删除外部模块
          qqdeps module search <关键词> 在市场源中搜索模块
          qqdeps market sources         查看已配置的市场源
          qqdeps market refresh         从市场源刷新模块列表
        """
        if not args:
            print("用法: qqdeps check|install|module <list|add|remove|search> [参数]")
            return
        sub = args[0].lower()

        # ── 外部模块管理 ──
        if sub == "module":
            if len(args) < 2:
                print("用法: qqdeps module <list|add|remove|search> [参数]")
                return
            action = args[1].lower()

            if action == "list":
                mods = list_external_modules(self.data_path)
                if not mods:
                    print("暂无已安装的外部模块")
                    print(f"放置路径: {self.data_path}/插件数据文件/模块源件/")
                else:
                    print(f"已安装 {len(mods)} 个外部模块:")
                    for m in mods:
                        print(f"  · {m['name']} ({m['type']}) v{m.get('version','?')} — {m.get('description','')}")

            elif action == "add":
                if len(args) < 3:
                    print("用法: qqdeps module add <URL | 模块名>")
                    print("  URL:  http://example.com/modules/download/my_mod")
                    print("  名称: 从已配置的市场源中搜索下载")
                    return
                target = args[2]
                # 判断是 URL 还是模块名
                if target.startswith("http://") or target.startswith("https://"):
                    print(f"正在从 {target} 下载模块...")
                    name = download_module(target, self.data_path)
                else:
                    # 从聚合市场下载
                    if not self.market_aggregator:
                        print("❌ 市场聚合器未配置，请先启用模块市场")
                        return
                    print(f"正在从市场源搜索 '{target}'...")
                    name = self.market_aggregator.fetch_module(
                        target, self.data_path
                    )
                if name:
                    print(f"✅ 模块 '{name}' 安装成功，请重载插件使其生效")
                else:
                    print("❌ 安装失败，请检查名称或网络连接")

            elif action == "remove":
                if len(args) < 3:
                    print("用法: qqdeps module remove <模块名>")
                    return
                name = args[2]
                if remove_external_module(name, self.data_path):
                    print(f"✅ 模块 '{name}' 已删除")
                else:
                    print(f"❌ 未找到模块 '{name}'")

            elif action == "search":
                if len(args) < 3:
                    print("用法: qqdeps module search <关键词>")
                    return
                if not self.market_aggregator:
                    print("❌ 市场聚合器未配置")
                    return
                keyword = " ".join(args[2:])
                result = self.market_aggregator.search(keyword)
                mods = result.get("modules", [])
                if not mods:
                    print(f"未找到匹配 '{keyword}' 的模块")
                    print(f"已查询 {len(result.get('sources',[]))} 个源")
                else:
                    print(f"搜索 '{keyword}' — {len(mods)} 个结果 (来自 {len(result.get('sources',[]))} 个源):")
                    for m in mods:
                        src = m.get("_source", "?")
                        print(f"  · {m['name']} v{m.get('version','?')} — {m.get('description','')[:40]}")
                        print(f"    来源: {src}")
            else:
                print("未知操作，可用: list / add / remove / search")
            return

        # ── 市场源管理 ──
        if sub == "market":
            if len(args) < 2:
                print("用法: qqdeps market <sources|refresh>")
                return
            action = args[1].lower()
            if action == "sources":
                if not self.market_aggregator:
                    print("市场聚合器未配置")
                else:
                    print(f"已配置 {len(self.market_aggregator._sources)} 个市场源:")
                    for i, s in enumerate(self.market_aggregator._sources, 1):
                        print(f"  {i}. {s}")
            elif action == "refresh":
                if not self.market_aggregator:
                    print("❌ 市场聚合器未配置")
                    return
                print("正在从市场源刷新...")
                result = self.market_aggregator.list_all()
                mods = result.get("modules", [])
                conflicts = result.get("conflicts", [])
                print(
                    f"发现 {len(mods)} 个模块"
                    f" (来自 {len(result.get('sources',[]))} 个源)"
                )
                if conflicts:
                    print(f"⚠ {len(conflicts)} 个模块存在冲突（已按优先级保留）:")
                    for c in conflicts:
                        print(
                            f"  · {c['name']} 保留来自 {c['kept_source']}"
                            f"，跳过 {c['skipped_source']}"
                        )
            else:
                print("未知操作，可用: sources / refresh")
            return

        # ── Python 依赖管理 ──
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
            print("未知子命令，可用: check / install / module")

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
            try:
                asyncio.run_coroutine_threadsafe(
                    self.event_bus.publish(
                        GameChatEvent(player_name=player_name, message=message)
                    ),
                    self._main_loop,
                )
            except Exception as e:
                logging.getLogger(__name__).error(
                    "游戏聊天事件桥接失败: %s", e
                )

    def _on_player_join_bridge(self, player_name: str):
        """玩家加入事件桥接。"""
        if self._main_loop and self._main_loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self.event_bus.publish(PlayerJoinEvent(player_name=player_name)),
                    self._main_loop,
                )
            except Exception as e:
                logging.getLogger(__name__).error(
                    "玩家加入事件桥接失败: %s", e
                )

    def _on_player_leave_bridge(self, player_name: str):
        """玩家离开事件桥接。"""
        if self._main_loop and self._main_loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self.event_bus.publish(PlayerLeaveEvent(player_name=player_name)),
                    self._main_loop,
                )
            except Exception as e:
                logging.getLogger(__name__).error(
                    "玩家离开事件桥接失败: %s", e
                )

    @staticmethod
    def _parse_onebot_message(raw_msg) -> str:
        """解析 OneBot 消息段为纯文本。"""
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
            return "".join(text_parts)
        return str(raw_msg) if raw_msg else ""

    def _on_ws_group_message(self, raw: dict):
        """处理 WebSocket 群消息。"""
        linked_groups = self.config_mgr.get("消息转发.链接的群聊", [])
        group_id = raw.get("group_id")
        if group_id not in linked_groups:
            return

        msg_id = raw.get("message_id")
        if msg_id and not self.dedup.check_and_add_id(f"raw_{msg_id}"):
            return

        text = self._parse_onebot_message(raw.get("message"))
        nickname = (
            raw.get("sender", {}).get("card")
            or raw.get("sender", {}).get("nickname", "未知")
        )
        access_log.info("[QQ] %s: %s", nickname, text.strip())

        try:
            trigger = getattr(self.adapter, "trigger_raw_group_handlers", None)
            if trigger:
                trigger(raw)
        except Exception as e:
            logging.getLogger(__name__).error("原始消息处理器异常: %s", e)

        event = GroupMessageEvent(
            user_id=raw.get("user_id") or 0,
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

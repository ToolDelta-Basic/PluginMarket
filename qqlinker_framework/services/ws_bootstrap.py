"""WebSocket 连接引导库 — 从 host.py.start() 提取。

职责：读取 WS 配置、创建 WsClient、去重引擎、调试引擎、多机器人守卫。
框架只负责 mount() / unmount()。
"""
import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.host import FrameworkHost

from ..core.library import Library
from ..core.kernel.services import TIER_SERVICE, TIER_DAEMON, UID_NOBODY
from ..services.ws_client import WsClient, _get_websocket
from ..services.dedup import LayeredDedup, DedupConfig
from ..services.debug_engine import DebugEngine

_log = logging.getLogger(__name__)


class WsBootstrap:
    """WebSocket 连接引导库。"""

    __slots__ = ("_ws_clients", "_dedup", "_debug", "_msg_mgrs")

    async def mount(self, host: "FrameworkHost") -> None:
        self._ws_clients = []
        self._msg_mgrs = {}

        # 去重引擎
        dedup_cfg = DedupConfig(
            local_id_ttl=host.config_mgr.get("去重.本地ID有效期秒", 300, requester_uid=0),
            local_content_ttl=host.config_mgr.get("去重.本地内容有效期秒", 120, requester_uid=0),
            local_max_size=host.config_mgr.get("去重.本地最大条目数", 10000, requester_uid=0),
            redis_enabled=host.config_mgr.get("去重.启用Redis", False, requester_uid=0),
            redis_url=host.config_mgr.get("去重.Redis地址", "redis://localhost:6379/0", requester_uid=0),
            redis_password=os.environ.get("QQLINKER_REDIS_PASSWORD") or host.config_mgr.get("去重.Redis密码", None, requester_uid=0),
        )
        try:
            self._dedup = LayeredDedup(dedup_cfg)
            host.services.register("dedup", self._dedup, uid=TIER_SERVICE,
                                   _caller="qqlinker_framework.core.host")
        except Exception as e:
            _log.warning("去重引擎初始化失败: %s", e)
            host.degradation.on_service_fail("dedup", str(e), e)
            self._dedup = None

        # 调试引擎
        try:
            self._debug = DebugEngine(host.services, host.config_mgr, host.event_bus)
            host.services.register("debug", self._debug, uid=UID_NOBODY,
                                   _caller="qqlinker_framework.core.host")
        except Exception as e:
            _log.warning("调试引擎初始化失败: %s", e)
            host.degradation.on_service_fail("debug_engine", str(e), e)

        # WebSocket
        ws_address = host.config_mgr.get("网络连接.地址", "ws://127.0.0.1:8080", requester_uid=0)
        ws_token = os.environ.get("QQLINKER_WS_TOKEN",
                                  host.config_mgr.get("网络连接.令牌", "", requester_uid=0))
        _log.info("WebSocket 地址: %s", ws_address)

        if hasattr(host.adapter, 'set_config_mgr'):
            host.adapter.set_config_mgr(host.config_mgr)

        try:
            _get_websocket()
            ws_available = True
        except ImportError:
            ws_available = False

        if not ws_available:
            _log.warning("websocket-client 未安装，跳过 WS 连接")
            return

        robot_list = host.config_mgr.get("网络连接.机器人列表", None, requester_uid=0)
        if robot_list and isinstance(robot_list, list):
            ws_addresses = [r.get("地址", ws_address) for r in robot_list]
            ws_tokens = [r.get("令牌", ws_token) for r in robot_list]
        else:
            ws_addresses = [ws_address]
            ws_tokens = [ws_token]

        for i, (addr, tok) in enumerate(zip(ws_addresses, ws_tokens)):
            svc_name = "ws_client" if i == 0 else f"ws_client_{i}"
            ws_client = WsClient({
                "ws_address": addr,
                "ws_token": tok,
                "网络传输.TLS验证模式": host.config_mgr.get("网络传输.TLS验证模式", "enabled", requester_uid=0),
                "网络传输.连接超时秒": host.config_mgr.get("网络传输.连接超时秒", 10, requester_uid=0),
                "网络传输.读超时秒": host.config_mgr.get("网络传输.读超时秒", 30, requester_uid=0),
            })
            host.services.register(svc_name, ws_client, uid=TIER_SERVICE,
                                   _caller="qqlinker_framework.core.host")
            self._ws_clients.append(ws_client)
            if i == 0:
                if hasattr(host.adapter, 'set_ws_client'):
                    host.adapter.set_ws_client(ws_client)
                if hasattr(host.adapter, 'event_bus'):
                    host.adapter.event_bus = host.event_bus

            # WS 消息回调 → bridge.on_ws_group_message
            if host.bridge:
                _orig_ws_cb = host.bridge.on_ws_group_message
                def _ws_cb_with_telemetry(data, _cb=_orig_ws_cb, _telemetry=host.telemetry):
                    t0 = time.monotonic()
                    _cb(data)
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    _telemetry.record("ws.message.in", {
                        "elapsed_ms": round(elapsed_ms, 2),
                        "has_message": bool(data.get("message") if isinstance(data, dict) else False),
                    })
                ws_client.set_message_callback(_ws_cb_with_telemetry)

            ws_client.connect()
            _log.info("WebSocket 连接已发起: %s", svc_name)

        # 多机器人守卫
        guard_enabled = host.config_mgr.get("网络连接.启用多机器人守卫", True, requester_uid=0)
        if guard_enabled and len(ws_addresses) > 1:
            self._setup_multi_robot(host, ws_addresses, ws_tokens)

    def _setup_multi_robot(self, host, ws_addresses, ws_tokens):
        from ..core.drivers.robot_guard import RobotRegistry, CrossValidation, SendGuard
        from ..core.drivers.load_balancer import LoadBalancer, HashRouter
        host.robot_registry = RobotRegistry()
        n = len(ws_addresses)
        quorum = max(2, n // 2 + 1) if n > 2 else min(2, n)
        host.cross_validator = CrossValidation(host.robot_registry, quorum=quorum)
        host.load_balancer = LoadBalancer()
        host.hash_router = HashRouter()
        host.send_guard = SendGuard(
            host.robot_registry,
            load_balancer=host.load_balancer,
            hash_router=host.hash_router,
            max_retries=2,
        )
        linked_groups = host.config_mgr.get("消息转发.链接的群聊", [], requester_uid=0)
        bot_names = []
        for i, (addr, _) in enumerate(zip(ws_addresses, ws_tokens)):
            name = f"bot_{i}"
            bot_names.append(name)
            svc_name = "ws_client" if i == 0 else f"ws_client_{i}"
            ws_client = host.services.get(svc_name)
            host.robot_registry.register(name, ws_client, linked_groups)
            if name not in self._msg_mgrs:
                from qqlinker_framework.managers import MessageManager
                mgr = MessageManager(host.adapter)
                mgr._queue = asyncio.PriorityQueue()
                self._msg_mgrs[name] = mgr
                svc_name_mgr = "message_mgr" if i == 0 else f"message_mgr_{i}"
                host.services.register(svc_name_mgr, mgr, uid=TIER_DAEMON,
                                       _caller="qqlinker_framework.core.host")
        host.send_guard.set_message_managers(self._msg_mgrs)
        if hasattr(host.adapter, '_send_guard'):
            host.adapter._send_guard = host.send_guard
        else:
            setattr(host.adapter, '_send_guard', host.send_guard)
        _log.info("[多机器人守卫] 已启用 (quorum=%d, %d 个机器人: %s)",
                  quorum, len(ws_addresses), ", ".join(bot_names))

    async def unmount(self, host: "FrameworkHost") -> None:
        for ws_client in self._ws_clients:
            try:
                ws_client.disconnect()
            except Exception:
                pass
        self._ws_clients.clear()
        self._msg_mgrs.clear()
        self._dedup = None
        self._debug = None

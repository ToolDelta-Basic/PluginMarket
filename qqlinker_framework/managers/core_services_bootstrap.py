"""核心服务引导库 — 从 host.py.start() 提取。

职责：EventBridge、CommandRouter、模块加载、Gatekeeper、崩溃恢复。
"""
import logging
import time

from ..core.library import Library
from ..core.kernel.services import TIER_DAEMON

_log = logging.getLogger(__name__)


class CoreServicesBootstrap:
    """核心服务引导库 — 事件桥接、路由、模块。"""

    async def mount(self, host) -> None:
        logger = logging.getLogger(__name__)

        # EventBridge（依赖 dedup 和主循环）
        dedup = host.services.try_get("dedup")
        from ..core.drivers.event_bridge import EventBridge
        host.bridge = EventBridge(
            event_bus=host.event_bus,
            config_mgr=host.config_mgr,
            dedup=dedup,
            main_loop_getter=lambda: host._main_loop,
            adapter=host.adapter,
            session_tracker=host._session_tracker,
        )

        # 桥接游戏事件
        host._bridge_game_events()

        # 补设 WS 消息回调（WsBootstrap 先于 EventBridge 创建，回调未设置）
        for i in range(10):
            svc_name = "ws_client" if i == 0 else f"ws_client_{i}"
            ws_client = host.services.try_get(svc_name)
            if ws_client is None:
                break
            if hasattr(ws_client, 'set_message_callback'):
                _orig_cb = host.bridge.on_ws_group_message
                def _ws_cb(data, _cb=_orig_cb, _t=host.telemetry):
                    import time as _time
                    t0 = _time.monotonic()
                    _cb(data)
                    elapsed = (_time.monotonic() - t0) * 1000
                    _t.record("ws.message.in", {
                        "elapsed_ms": round(elapsed, 2),
                        "has_message": bool(data.get("message") if isinstance(data, dict) else False),
                    })
                ws_client.set_message_callback(_ws_cb)
                logger.info("WS 消息回调已补设: %s", svc_name)

        # 群级模块过滤器
        from qqlinker_framework.managers import GroupModuleFilter
        host.group_filter = GroupModuleFilter(host.group_config_mgr)
        host.services.register("group_filter", host.group_filter, uid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")

        # 审计追溯
        from ..core.kernel.audit_trail import AuditTrail
        host.audit_trail = AuditTrail(data_dir=host.data_path, retention_days=30)
        logger.info("审计追溯系统已初始化: %s", host.audit_trail._data_dir)

        # 命令路由
        from qqlinker_framework.managers import CommandRouter
        host._router = CommandRouter(
            host.command_mgr, host.adapter,
            host.config_mgr, host.message_mgr,
            group_filter=host.group_filter,
            loaded_modules=host.module_mgr._loaded_modules,
            uid_lookup=host._lookup_uid,
            audit_trail=host.audit_trail,
            source_mgr=host.module_mgr,
        )
        _orig_handle = host._router.handle_message

        async def _handle_with_telemetry(event):
            t0 = time.monotonic()
            result = await _orig_handle(event)
            elapsed_ms = (time.monotonic() - t0) * 1000
            host.telemetry.record("module.command.done", {
                "module": getattr(event, 'module_name', 'core'),
                "elapsed_ms": round(elapsed_ms, 2),
                "success": result is not False,
            })
            return result
        host.event_bus.subscribe("GroupMessageEvent", _handle_with_telemetry)

        host._register_audit_command()

        # AdminToolManager
        from qqlinker_framework.managers import AdminToolManager
        host._admin_tool_mgr = AdminToolManager(host.services)
        host._admin_tool_mgr.init_with_services()
        host.services.register("admin_tool", host._admin_tool_mgr, uid=TIER_DAEMON,
                               _caller="qqlinker_framework.core.host")
        host.module_mgr._admin_tool_mgr = host._admin_tool_mgr

        # 工作流扫描
        host.module_mgr.init_workflow_scanner(host.data_path)

        # 加载所有模块
        host._modules = await host.module_mgr.initialize_all()
        for mod in host._modules:
            host.health_scorer.register_module(mod.name)
            host.health_scorer.on_module_init(mod.name, success=True)
        if not any(m.name == "help" for m in host._modules):
            logger.warning("help 模块未加载，用户将无法查看命令帮助")

        host.group_filter.set_module_names({m.name for m in host._modules})

        # Gatekeeper 能力注册
        from ..core.drivers.gatekeeper import register_default_capabilities
        register_default_capabilities(host.gatekeeper)
        from qqlinker_framework.managers import register_config_bridge
        register_config_bridge(host.gatekeeper, host.config_mgr)

        # 群配置传播
        affected = host.group_config_mgr.propagate_new_fields()
        if affected:
            logger.info("新字段已传播到 %d 个群子配置: %s",
                        len(affected), ", ".join(affected))

        # 崩溃恢复
        was_crashed = host.recovery.was_crashed()
        if was_crashed:
            logger.warning("‼️ 检测到上次非正常退出，进入恢复模式")
            restored = await host.recovery.restore_all_checkpoints()
            if restored:
                logger.info("已加载 %d 个模块检查点: %s",
                            len(restored), ", ".join(restored.keys()))
                for mod in host._modules:
                    if mod.name in restored:
                        try:
                            await mod.restore_checkpoint(restored[mod.name])
                            logger.info("模块 '%s' 状态已恢复", mod.name)
                        except Exception as e:
                            logger.error("模块 '%s' 恢复失败: %s", mod.name, e)

        for mod in host._modules:
            host.recovery.register_module(mod)
        host.recovery.start_heartbeat(interval=5.0)
        host.recovery.start_checkpoint_loop(interval=30.0)

    async def unmount(self, host) -> None:
        pass

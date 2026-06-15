"""配置引导库 — 从 host.py.start() 提取。

职责：注册所有配置节、加载配置、初始化审计日志、网络管理器。
"""
import logging
import os

from ..core.library import Library
from ..core.kernel.services import TIER_SERVICE, TIER_DAEMON, MID_SERVICE

_log = logging.getLogger(__name__)


class ConfigBootstrap:
    """配置节注册引导库。"""

    async def mount(self, host) -> None:
        logger = logging.getLogger(__name__)

        # 所有配置节注册
        host.config_mgr.register_section("网络连接", {
            "地址": "ws://127.0.0.1:8080", "令牌": "",
            "启用多机器人守卫": True,
            "错误显示模式": "友好",
        }, caller_uid=0)
        host.config_mgr.register_section("权限管理", {"角色": {}}, caller_uid=0)
        host.config_mgr.register_section("启动检查", {"跳过完整性校验": False}, caller_uid=0)
        host.config_mgr.register_section("去重", {
            "本地ID有效期秒": 300, "本地内容有效期秒": 120,
            "本地最大条目数": 10000, "启用Redis": False,
            "Redis地址": "redis://localhost:6379/0",
        }, caller_uid=0)
        host.config_mgr.register_section("调试引擎", {
            "消息记录上限": 200, "API记录上限": 100,
            "启用WebSocket原始帧": False,
        }, caller_uid=0)
        host.config_mgr.register_section("模块管理", {
            "禁用模块": [], "启用模块": [],
            "禁用命令": [], "启用命令": [], "模式": "黑名单",
        }, caller_uid=0)
        host.group_config_mgr.register_module_schema(
            "模块管理",
            {"禁用模块": [], "启用模块": [],
             "禁用命令": [], "启用命令": [], "模式": "黑名单"},
            scope="group",
        )
        host.config_mgr.register_section("模块市场", {
            "启用": False, "地址": "127.0.0.1", "端口": 8380,
            "上传密钥": "", "签名密钥": "", "强制签名校验": False,
            "白名单模块": [], "每页数量": 20,
            "源列表": ["http://127.0.0.1:8380"],
        }, caller_uid=0)
        host.config_mgr.register_section("审计日志", {
            "审计日志最大行数": 100000,
            "审计日志清理间隔": 86400,
        }, caller_uid=0)
        host.config_mgr.register_section("网络传输", {
            "TLS验证模式": "enabled", "连接超时秒": 10, "读超时秒": 30,
        }, caller_uid=0)
        host.config_mgr.register_section("SSRF防护", {
            "黑名单域名": ["metadata.google.internal", "169.254.169.254"],
            "禁止内网IP": True,
        }, caller_uid=0)
        host.config_mgr.register_section("调试", {"生产模式禁用": True}, caller_uid=0)
        host.config_mgr.load()

        # 审计日志
        from ..core.kernel.audit import configure_audit
        audit_log_path = os.path.join(host.data_path, "日志", "审计日志.log")
        audit_max_lines = host.config_mgr.get("审计日志.审计日志最大行数", 100000, requester_uid=0)
        audit_cleanup = host.config_mgr.get("审计日志.审计日志清理间隔", 86400, requester_uid=0)
        configure_audit(audit_log_path, audit_max_lines, audit_cleanup)
        logger.info("审计日志已配置: %s", audit_log_path)

        # 错误显示模式
        from ..core.kernel.error_hints import ErrorMode
        ErrorMode.set_config_source(host.config_mgr)
        logger.info("错误显示模式: %s", "友好" if ErrorMode.is_friendly() else "调试")

        # 配置热重载
        host.config_mgr.start_watching(interval=2.0, on_reload=host._on_config_reloaded)
        host.group_config_mgr.set_reload_callback(host._on_config_reloaded)
        host.group_config_mgr.start_watching(interval=3.0)

        # 网络管理器
        from qqlinker_framework.managers import NetworkManager, NetworkConfig
        host._network_mgr = NetworkManager(
            NetworkConfig(
                connect_timeout=host.config_mgr.get("网络传输.连接超时秒", 10, requester_uid=0),
                total_timeout=host.config_mgr.get("网络传输.读超时秒", 30, requester_uid=0),
                tls_verify=host.config_mgr.get("网络传输.TLS验证模式", "enabled", requester_uid=0),
                pool_size=host.config_mgr.get("网络传输.连接池大小", 5, requester_uid=0),
                pool_per_host=host.config_mgr.get("网络传输.每主机最大连接", 10, requester_uid=0),
            )
        )
        host.services.register("network", host._network_mgr, uid=TIER_SERVICE)

    async def unmount(self, host) -> None:
        pass

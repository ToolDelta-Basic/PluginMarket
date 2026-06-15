"""模块市场引导库 — 从 host.py.start() 提取。"""
import logging
import os

from ..core.kernel.services import TIER_SERVICE

_log = logging.getLogger(__name__)


class MarketBootstrap:
    """模块市场引导库。"""

    async def mount(self, host) -> None:
        logger = logging.getLogger(__name__)
        market_cfg = host.config_mgr.get("模块市场", {}, requester_uid=0)
        if market_cfg.get("启用", False):
            from ..services.market_server import ModuleMarketServer
            upload_token = os.environ.get("QQLINKER_UPLOAD_TOKEN", market_cfg.get("上传密钥", ""))
            sign_secret = os.environ.get("QQLINKER_SIGN_SECRET", market_cfg.get("签名密钥", ""))
            market_server = ModuleMarketServer(
                data_path=host.data_path,
                host=market_cfg.get("地址", "127.0.0.1"),
                port=market_cfg.get("端口", 8380),
                upload_token=upload_token,
                whitelist=market_cfg.get("白名单模块", []),
                sign_secret=sign_secret,
                strict_sign=market_cfg.get("强制签名校验", False),
                per_page=market_cfg.get("每页数量", 20),
            )
            market_server.start()
            host.services.register("market_server", market_server, uid=TIER_SERVICE,
                                   _caller="qqlinker_framework.core.host")
            logger.info("模块市场已启动: %s", market_server.url)

        from ..services.market_server import MarketSourceAggregator
        source_urls = market_cfg.get("源列表", ["http://127.0.0.1:8380"])
        market_aggregator = MarketSourceAggregator(source_urls)
        host.services.register("market", market_aggregator, uid=TIER_SERVICE,
                               _caller="qqlinker_framework.core.host")

    async def unmount(self, host) -> None:
        pass

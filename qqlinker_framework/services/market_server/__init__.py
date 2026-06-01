"""模块市场 — 内建 HTTP 服务 + 多源聚合

子包结构:
  signer.py    — HMAC-SHA256 签名/验证
  handler.py   — REST API 处理器（列表/搜索/下载/上传）
  server.py    — ModuleMarketServer + MarketSourceAggregator
"""
from .signer import sign_module, verify_signature
from .handler import MarketHandler
from .server import ModuleMarketServer, MarketSourceAggregator

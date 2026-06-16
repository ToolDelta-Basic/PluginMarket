"""信道协议 v1.6.0 — 框架唯一的通信契约。

Library 基类和协议定义已移至 libraries/channel_host.py。
此文件保留为兼容导入入口。
"""
from qqlinker_framework.libraries.channel_host import (
    Library,
    ServiceRegistry,
    ScopedView,
    EventBus,
    BootstrapError,
    ChannelHost,
)

__all__ = [
    "Library",
    "ServiceRegistry",
    "ScopedView",
    "EventBus",
    "BootstrapError",
    "ChannelHost",
]

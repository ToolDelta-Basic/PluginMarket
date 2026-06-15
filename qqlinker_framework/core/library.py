"""框架库接口 — 所有可挂载库的契约。

每个库只需实现 mount(host) / unmount(host)，框架负责在启动时调用。
库之间通过 host 提供的信道通信：services(服务), event_bus(事件), config(配置)。

═══ 理念 ═══
  框架 = 通信信道
  库   = 独立功能包
  框架不实现业务逻辑，只连接库与库。
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class Library(Protocol):
    """可挂载到框架的独立库。

    库通过 mount(host) 挂载到框架信道：
      - host.services.register(...) — 提供服务
      - host.event_bus.subscribe(...) — 订阅事件
      - host.config.register_section(...) — 注册配置节
      - host.services.get(...) — 依赖其他服务

    库通过 unmount(host) 卸载：
      - 取消事件订阅
      - 停止后台任务
      - 释放资源
    """

    async def mount(self, host: "FrameworkHost") -> None:  # noqa: F821
        """将库挂载到框架信道。"""

    async def unmount(self, host: "FrameworkHost") -> None:  # noqa: F821
        """从框架信道卸载库。"""

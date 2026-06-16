"""QQLinker 框架入口 v1.6.0 — 纯信道启动。"""
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def main():
    from qqlinker_framework.libraries.channel_host import ChannelHost, BootstrapError

    data_path = os.environ.get("QQLINKER_DATA", ".")
    host = ChannelHost(data_path=data_path)

    try:
        await host.start()
    except BootstrapError as e:
        logging.getLogger(__name__).critical("启动失败: %s", e)
        sys.exit(1)

    # 运行循环
    try:
        logging.getLogger(__name__).info("框架运行中... (Ctrl+C 停止)")
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await host.stop()
        logging.getLogger(__name__).info("框架已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

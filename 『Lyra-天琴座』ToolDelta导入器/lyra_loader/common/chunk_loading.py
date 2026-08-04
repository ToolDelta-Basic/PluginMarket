"""等待目标区块可由命令访问"""

import time
from collections.abc import Callable

from tooldelta.internal.types import Packet_CommandOutput

OUT_OF_WORLD_MESSAGE = "commands.testforblock.outOfWorld"
RETRY_INTERVAL = 0.1


def wait_for_chunk_loaded(
    sendaicmd_with_resp: Callable[[str], Packet_CommandOutput],
    x: int,
    y: int,
    z: int,
) -> None:
    """阻塞到 testforblock 的返回不再表示区块尚未加载"""
    command = f"/testforblock {x} {y} {z} air"
    while True:
        response = sendaicmd_with_resp(command)
        messages = response.as_dict.get("OutputMessages", [])
        if not isinstance(messages, list | tuple):
            return
        if not any(
            (message.get("Message") or message.get("MessageId")) == OUT_OF_WORLD_MESSAGE
            for message in messages
        ):
            return
        time.sleep(RETRY_INTERVAL)


def chunk_preload(
    sendaicmd: Callable[[str], object],
    sendaicmd_with_resp: Callable[[str], Packet_CommandOutput],
    bot_name: str,
    dimension_id: str,
    x: int,
    y: int,
    z: int,
) -> None:
    """传送机器人并等待目标区块可由命令访问"""
    sendaicmd(f'/execute in {dimension_id} run tp @a[name="{bot_name}"] {x} {y} {z}')
    wait_for_chunk_loaded(sendaicmd_with_resp, x, y, z)

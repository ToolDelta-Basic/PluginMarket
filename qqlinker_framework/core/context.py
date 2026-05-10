"""命令上下文"""
from typing import List


class CommandContext:
    """封装一次命令请求的相关信息与方法。

    Attributes:
        user_id: 发送者 QQ 号。
        group_id: 群号。
        nickname: 发送者昵称。
        message: 原始消息文本。
        args: 以空格分割的参数列表。
        adapter: 平台适配器实例。
        _message_mgr: 消息管理器（可选），用于限流发送。
    """

    def __init__(
        self,
        user_id: int,
        group_id: int,
        nickname: str,
        message: str,
        args: List[str],
        adapter,
        message_mgr=None,
    ):
        """初始化命令上下文。

        Args:
            user_id: QQ 号。
            group_id: 群号。
            nickname: 昵称。
            message: 完整消息。
            args: 参数列表。
            adapter: 适配器。
            message_mgr: 消息管理器实例。
        """
        self.user_id = user_id
        self.group_id = group_id
        self.nickname = nickname
        self.message = message
        self.args = args
        self.adapter = adapter
        self._message_mgr = message_mgr

    async def reply(self, text: str):
        """回复消息（优先走消息管理器以应用限流）。

        Args:
            text: 回复文本。
        """
        if self._message_mgr:
            await self._message_mgr.send_group(self.group_id, text)
        else:
            self.adapter.send_group_msg(self.group_id, text)

from typing import List

class CommandContext:
    def __init__(self, user_id: int, group_id: int, nickname: str,
                 message: str, args: List[str], adapter, message_mgr=None):
        self.user_id = user_id
        self.group_id = group_id
        self.nickname = nickname
        self.message = message
        self.args = args
        self.adapter = adapter
        self._message_mgr = message_mgr

    async def reply(self, text: str):
        if self._message_mgr:
            await self._message_mgr.send_group(self.group_id, text)
        else:
            self.adapter.send_group_msg(self.group_id, text)
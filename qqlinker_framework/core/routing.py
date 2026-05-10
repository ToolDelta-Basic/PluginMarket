"""命令路由中间件（带权限检查）"""
import logging
from ..managers.command_mgr import CommandManager
from .context import CommandContext

class CommandRouter:
    """将 GroupMessageEvent 分发给匹配的命令，并进行权限校验。"""

    def __init__(self, command_mgr: CommandManager, adapter, config_mgr, message_mgr):
        """初始化路由器。

        Args:
            command_mgr: 命令管理器。
            adapter: 平台适配器。
            config_mgr: 配置管理器。
            message_mgr: 消息管理器。
        """
        self.command_mgr = command_mgr
        self.adapter = adapter
        self.config_mgr = config_mgr
        self.message_mgr = message_mgr

    async def handle_message(self, event):
        """处理群消息事件，查找匹配命令并执行。

        Args:
            event: GroupMessageEvent 实例。

        Returns:
            是否匹配并尝试执行了命令。
        """
        msg = event.message.strip()
        for cmd_info in self.command_mgr.get_group_commands():
            trigger = cmd_info["trigger"]
            if msg.startswith(trigger):
                if cmd_info.get("op_only", False):
                    if not self.adapter.is_user_admin(event.user_id, self.config_mgr):
                        logging.getLogger(__name__).warning("用户 %d 尝试越权执行命令 %s", event.user_id, trigger)
                        return True
                args_str = msg[len(trigger):].strip()
                args = args_str.split() if args_str else []
                ctx = CommandContext(
                    user_id=event.user_id,
                    group_id=event.group_id,
                    nickname=event.nickname,
                    message=event.message,
                    args=args,
                    adapter=self.adapter,
                    message_mgr=self.message_mgr
                )
                try:
                    await cmd_info["callback"](ctx)
                    event.handled = True
                except Exception as e:
                    logging.getLogger(__name__).error("命令 %s 执行异常: %s", trigger, e)
                return True
        return False
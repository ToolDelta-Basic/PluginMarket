"""ToolDelta 拼手气红包插件。"""
from __future__ import annotations

import threading
from typing import Any

from tooldelta import Chat, FrameExit, Player, Plugin, plugin_entry, utils

from .runtime_reload import reload_plugin_modules

reload_plugin_modules(__name__)

from .broadcasting import RedPacketBroadcastMixin  # noqa: E402
from .configuration import load_configuration  # noqa: E402
from .interaction import CommandCollector  # noqa: E402
from .messages import is_red_packet_command  # noqa: E402
from .models import RedPacketState, player_identity  # noqa: E402
from .service import RedPacketService  # noqa: E402
from .storage import RedPacketStore  # noqa: E402
from .text_validation import (  # noqa: E402
    INVALID_CHARACTER_MESSAGE,
    has_invalid_characters,
)


class LuckyRedPacket(RedPacketBroadcastMixin, Plugin):
    """让玩家发送并领取拼手气口令红包。"""

    name = "红包"
    author = "Q3CC"
    version = (0, 2, 3)
    description = "支持全服口令领取的拼手气红包"

    def __init__(self, frame: Any) -> None:
        """初始化配置、持久化状态和事件监听器。"""
        super().__init__(frame)
        (
            self.config,
            self.scoreboard_name,
            self.currency_name,
            self.expiry_seconds,
        ) = load_configuration(
            self.name,
            self.version,
        )
        self._prompting_players: set[str] = set()
        self._prompting_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._storage_ready = True
        store = RedPacketStore(self.data_path / "红包状态.json")
        try:
            state = store.load()
        except ValueError as err:
            self._storage_ready = False
            state = RedPacketState()
            self.print_err(f"{err}；为防止资产异常，红包功能已停用")
        self.service = RedPacketService(self, store, state)
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenChat(self.on_chat)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenFrameExit(self.on_frame_exit)

    def on_preload(self) -> None:
        """注册聊天栏红包命令。"""
        chatbar = self.GetPluginAPI("聊天栏菜单", (0, 4, 1))
        chatbar.add_new_trigger(
            ["fhb", "发红包"],
            [
                ("总金额", str, ""),
                ("份数", str, ""),
                ("口令", str, ""),
            ],
            "发送拼手气红包",
            self.on_red_packet_command,
        )

    def on_active(self) -> None:
        """恢复到期任务并启动退款检查线程。"""
        if not self._storage_ready:
            return
        self.service.process_expired()
        utils.createThread(self._expiry_loop, usage="红包到期退款")
        self.print_suc(
            f"红包插件已启用，货币为 {self.currency_name}，"
            f"有效期 {self.expiry_seconds} 秒"
        )

    def on_frame_exit(self, _: FrameExit) -> None:
        """通知后台退款线程停止。"""
        self._stop_event.set()

    def on_red_packet_command(
        self,
        player: Player,
        args: tuple[Any, ...],
    ) -> bool:
        """接收红包命令并立即释放聊天栏菜单回调。"""
        if not self._storage_ready:
            player.show("§c红包数据异常，功能暂时不可用，请联系管理员§r")
            return True
        identity = player_identity(player)
        with self._prompting_lock:
            if identity in self._prompting_players:
                player.show("§e你正在创建红包，请先完成当前输入或发送 q 取消§r")
                return True
            self._prompting_players.add(identity)
        utils.createThread(
            lambda: self._run_red_packet_command(player, args, identity),
            usage=f"玩家 {player.name} 创建红包",
        )
        return True

    def _run_red_packet_command(
        self,
        player: Player,
        args: tuple[Any, ...],
        identity: str,
    ) -> None:
        """在独立线程中完成缺参询问和红包创建。"""
        collector = CommandCollector(
            player,
            args,
            lambda _: None,
        )
        try:
            request = collector.collect()
            if request is not None:
                if not request.has_valid_phrase():
                    player.show(f"§c{INVALID_CHARACTER_MESSAGE}§r")
                    return
                self.service.create(player, request)
        except Exception as err:
            self.print_err(f"玩家 {player.name} 创建红包失败: {err}")
            player.show("§c创建红包时发生错误，请稍后重试§r")
        finally:
            self._set_prompting(identity, False)

    def on_chat(self, chat: Chat) -> None:
        """把命中的普通聊天口令交给领取流程。"""
        if not self._storage_ready:
            return
        raw_message = str(chat.msg)
        phrase = raw_message.strip()
        if is_red_packet_command(phrase):
            return
        if has_invalid_characters(raw_message):
            chat.player.show(f"§c{INVALID_CHARACTER_MESSAGE}§r")
            return
        if not phrase:
            return
        identity = player_identity(chat.player)
        with self._prompting_lock:
            if identity in self._prompting_players:
                return
        if not self.service.has_active_phrase(phrase):
            return
        utils.createThread(
            lambda: self.service.claim(chat.player, phrase),
            usage=f"玩家 {chat.player.name} 领取红包",
        )

    def on_player_join(self, player: Player) -> None:
        """向上线玩家发送待投递的退款通知。"""
        if self._storage_ready:
            self.service.deliver_refund_notices(player)

    def _expiry_loop(self) -> None:
        """周期检查红包到期状态。"""
        while not self._stop_event.wait(1):
            self.service.process_expired()

    def _set_prompting(self, identity: str, prompting: bool) -> None:
        """更新玩家是否正在回答创建问题。"""
        with self._prompting_lock:
            if prompting:
                self._prompting_players.add(identity)
            else:
                self._prompting_players.discard(identity)

entry = plugin_entry(LuckyRedPacket)

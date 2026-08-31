# adapters/tooldelta_adapter.py
import logging
_log = logging.getLogger(__name__)
from typing import Callable, Dict, Any, List, Optional

try:
    from tooldelta import Plugin, Player, Chat
    from tooldelta.constants import PacketIDS
    HAS_TOOLDELTA = True
except ImportError:
    HAS_TOOLDELTA = False
    Plugin = object
    Player = object
    Chat = object
    PacketIDS = object

from .base import IFrameworkAdapter
from ..services.ws_client import WsClient


class ToolDeltaAdapter(IFrameworkAdapter):
    """基于 ToolDelta 的平台适配器，封装游戏控制、事件监听和 WebSocket 通信。"""

    def __init__(self, plugin_instance: Plugin):
        self.plugin = plugin_instance
        self.game_ctrl = getattr(plugin_instance, 'game_ctrl', None)
        self._config_mgr = None
        self._active = False
        self._pre_plugin_apis: Dict[str, Any] = {}

        # ── 核心事件（通过 Plugin 基类的实例方法注册）──
        self.plugin.ListenChat(self._on_game_chat)
        self.plugin.ListenPlayerJoin(self._on_player_join)
        self.plugin.ListenPlayerLeave(self._on_player_leave)
        try:
            self.plugin.ListenAttack(self._on_attack)
        except AttributeError:
            # 部分 ToolDelta 版本未暴露 ListenAttack
            logging.getLogger(__name__).debug(
                "ToolDelta 版本不支持 ListenAttack，跳过"
            )
        self.plugin.ListenFrameExit(self._on_frame_exit)
        # ListenPlayerPreJoin 在某些 ToolDelta 版本中不存在
        if hasattr(self.plugin, "ListenPlayerPreJoin"):
            self.plugin.ListenPlayerPreJoin(self._on_player_pre_join)

        self._chat_handlers: list[Callable] = []
        self._player_join_handlers: list[Callable] = []
        self._player_leave_handlers: list[Callable] = []
        self._player_pre_join_handlers: list[Callable] = []
        self._active_handlers: list[Callable] = []
        self._frame_exit_handlers: list[Callable] = []
        self._group_message_handlers: list[Callable] = []
        self._packet_handlers: Dict[int, list[Callable]] = {}
        self._attack_handlers: list[Callable] = []
        self._bytes_packet_handlers: Dict[int, list[Callable]] = {}

        self._ws_client: Optional[WsClient] = None
        self.event_bus = None
        self.main_loop = None

        # v1.4.3: IPC 客户端（薄壳模式下使用）
        self._ipc_client = None

    # ── 依赖注入 ────────────────────────────────────────────

    def set_ws_client(self, ws_client: WsClient):
        """设置 WebSocket 客户端实例。"""
        self._ws_client = ws_client

    def set_config_mgr(self, config_mgr):
        """设置配置管理器。"""
        self._config_mgr = config_mgr

    def set_ipc_client(self, ipc_client):
        """v1.4.3: 注入 IPC 客户端（薄壳模式下使用）。"""
        self._ipc_client = ipc_client

    @property
    def is_active(self) -> bool:
        """是否已与游戏服务器建立连接。"""
        return self._active

    # ── 游戏指令 ────────────────────────────────────────────

    def send_game_command(self, cmd: str):
        """发送游戏指令。"""
        try:
            self.game_ctrl.sendcmd(cmd)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "游戏命令发送失败: %s, 错误: %s", cmd, e
            )

    def send_game_message(self, target: str, text: str):
        """向游戏内目标发送消息。"""
        try:
            self.game_ctrl.say_to(target, text)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "游戏消息发送失败, 目标: %s, 错误: %s", target, e
            )

    def send_game_title(self, target: str, text: str):
        """向玩家显示标题栏消息。"""
        try:
            self.game_ctrl.player_title(target, text)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "标题栏消息发送失败: %s", e
            )

    def send_game_subtitle(self, target: str, text: str):
        """向玩家显示小标题栏消息。"""
        try:
            self.game_ctrl.player_subtitle(target, text)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "副标题消息发送失败: %s", e
            )

    def send_game_actionbar(self, target: str, text: str):
        """向玩家显示行动栏消息。"""
        try:
            self.game_ctrl.player_actionbar(target, text)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "行动栏消息发送失败: %s", e
            )

    def get_online_players(self) -> List[str]:
        """获取在线玩家列表，自动兼容 ToolDelta 返回的 list 或 dict。"""
        try:
            raw = self.game_ctrl.allplayers
            if isinstance(raw, dict):
                return list(raw.keys())
            if isinstance(raw, (list, tuple)):
                # 若列表元素为 Player 对象，提取 .name
                result = []
                for item in raw:
                    if hasattr(item, "name"):
                        result.append(item.name)
                    elif isinstance(item, str):
                        result.append(item)
                return result if result else list(raw)
            logging.getLogger(__name__).warning(
                "allplayers 返回了未知类型: %s", type(raw).__name__
            )
            return []
        except Exception as e:
            logging.getLogger(__name__).error(
                "获取在线玩家列表异常: %s", e
            )
            return []

    # ── 群聊消息 ────────────────────────────────────────────

    def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群消息。"""
        if not self._ws_client:
            logging.getLogger(__name__).warning("WebSocket 客户端不可用")
            return False
        if not self._ws_client.available:
            logging.getLogger(__name__).warning("WebSocket 未连接")
            return False
        return self._ws_client.send_group_msg(group_id, message)

    def send_message_round_robin(self, group_id: int, message: str) -> bool:
        """轮询式群消息发送。

        多机器人模式:
          - 如果 send_guard 可用 → 通过 SendGuard.send_with_ack() 发送
          - SendGuard 自动选择机器人 → 发送 → 回显确认 → 故障转移

        ToolDelta 单机器人模式下降级为 plugin.send_group_msg。
        """
        send_guard = getattr(self, '_send_guard', None)
        if send_guard is not None:
            try:
                return send_guard.send_with_ack(group_id, message, priority=1)
            except Exception as e:
                _log.debug("tooldelta_adapter.send_message_round_robin: %s", e)
        if hasattr(self.plugin, 'send_group_msg'):
            return self.plugin.send_group_msg(group_id, message)
        # 向后兼容 fallback
        return self.send_group_msg(group_id, message)

    def send_private_msg(self, user_id: int, message: str) -> bool:
        """发送私聊消息。"""
        if not self._ws_client:
            logging.getLogger(__name__).warning("WebSocket 客户端不可用")
            return False
        if not self._ws_client.available:
            logging.getLogger(__name__).warning("WebSocket 未连接")
            return False
        return self._ws_client.send_private_msg(user_id, message)

    # ── 生命周期事件 ────────────────────────────────────────

    def handle_active(self):
        """由插件入口 on_active 调用，通知适配器已激活并触发所有处理器。"""
        self._active = True
        logging.getLogger(__name__).info("ToolDelta 已与游戏建立连接")
        for h in self._active_handlers:
            try:
                h()
            except Exception as e:
                logging.getLogger(__name__).error("on_active 处理器异常: %s", e)

    def _on_frame_exit(self, evt):
        """框架退出或重载时触发。"""
        logging.getLogger(__name__).info(
            "ToolDelta 框架退出 状态码=%s 原因=%s",
            getattr(evt, "signal", "?"),
            getattr(evt, "reason", "?"),
        )
        for h in self._frame_exit_handlers:
            try:
                h(evt)
            except Exception as e:
                logging.getLogger(__name__).error("on_frame_exit 处理器异常: %s", e)

    # ── 游戏事件分发 ────────────────────────────────────────

    def _on_game_chat(self, chat: Chat):
        """分发游戏聊天事件给所有处理器。"""
        for h in self._chat_handlers:
            try:
                h(chat.player.name, chat.msg)
            except Exception as e:
                logging.getLogger(__name__).error("游戏聊天处理器异常: %s", e)

    def _on_player_join(self, player: Player):
        """分发玩家加入事件。"""
        for h in self._player_join_handlers:
            try:
                h(player.name)
            except Exception as e:
                logging.getLogger(__name__).error("玩家加入处理器异常: %s", e)

    def _on_player_leave(self, player: Player):
        """分发玩家离开事件。"""
        for h in self._player_leave_handlers:
            try:
                h(player.name)
            except Exception as e:
                logging.getLogger(__name__).error("玩家离开处理器异常: %s", e)

    def _on_attack(self, attack):
        """分发攻击事件（ToolDelta 内置事件，无需数据包监听）。"""
        for h in self._attack_handlers:
            try:
                h(attack.origin_player.name, attack.target_player.name,
                  attack.weapon_name)
            except Exception as e:
                logging.getLogger(__name__).error("攻击事件处理器异常: %s", e)

    def listen_attack(self, handler: Callable[[str, str, str], None]):
        """注册攻击事件处理器。（origin_player_name, target_player_name, weapon_name）"""
        self._attack_handlers.append(handler)

    def _on_player_pre_join(self, player: Player):
        """分发玩家预加入事件。"""
        for h in self._player_pre_join_handlers:
            try:
                h(player.name)
            except Exception as e:
                logging.getLogger(__name__).error("预加入处理器异常: %s", e)

    # ── 公共监听注册 ────────────────────────────────────────

    def listen_game_chat(self, handler: Callable[[str, str], None]):
        """注册游戏聊天处理器。"""
        self._chat_handlers.append(handler)

    def listen_player_join(self, handler: Callable[[str], None]):
        """注册玩家加入处理器。"""
        self._player_join_handlers.append(handler)

    def listen_player_leave(self, handler: Callable[[str], None]):
        """注册玩家离开处理器。"""
        self._player_leave_handlers.append(handler)

    def listen_player_pre_join(self, handler: Callable[[str], None]):
        """注册玩家预加入处理器。"""
        self._player_pre_join_handlers.append(handler)

    def listen_active(self, handler: Callable[[], None]):
        """注册框架就绪处理器。"""
        self._active_handlers.append(handler)

    def listen_frame_exit(self, handler: Callable[[Any], None]):
        """注册框架退出处理器。"""
        self._frame_exit_handlers.append(handler)

    def listen_dict_packet(self, packet_id: int, handler: Callable[[dict], bool]):
        """注册字典数据包监听（可返回 True 拦截）。

        ToolDelta 的类式插件在 on_active 之后才调用 hook_packet_handler，
        之后 neOmega 订阅的包列表就被冻结了。为此，我们把数据包注册推迟
        到 handle_active() 时统一执行（见 handle_active）。
        """
        self._packet_handlers.setdefault(packet_id, []).append(handler)

    def listen_bytes_packet(self, packet_id: int, handler: Callable[[bytes], bool]):
        """注册二进制数据包监听（可返回 True 拦截）。"""
        self._bytes_packet_handlers.setdefault(packet_id, []).append(handler)

    def listen_group_message(
        self, handler: Callable[[Dict[str, Any]], None]
    ):
        """注册原始群消息处理器。"""
        self._group_message_handlers.append(handler)

    def trigger_raw_group_handlers(self, data: dict):
        """触发所有原始群消息处理器。"""
        for handler in self._group_message_handlers:
            try:
                handler(data)
            except Exception as e:
                logging.getLogger(__name__).error("原始消息处理器异常: %s", e)

    # ── 控制台 ──────────────────────────────────────────────

    def register_console_command(
        self,
        triggers: List[str],
        hint: str,
        usage: str,
        func: Callable,
    ):
        """注册控制台命令。"""
        self.plugin.frame.add_console_cmd_trigger(triggers, hint, usage, func)

    # ── 跨插件 API ──────────────────────────────────────────

    def get_plugin_api(self, name: str) -> Optional[Any]:
        """获取其他插件的 API 实例。"""
        return self.plugin.GetPluginAPI(name)

    def register_pre_plugin_api(
        self, api_name: str, min_version: tuple = (0, 0, 0)
    ):
        """注册 datas.json 声明的依赖插件 API 到服务容器。

        在 on_preload 阶段调用，自动调用 GetPluginAPI 并注册到适配器内部存储。
        模块可通过 self.adapter._pre_plugin_apis['XUID获取'] 访问。
        """
        try:
            api_inst = self.plugin.GetPluginAPI(api_name, min_version=min_version)
            if api_inst is not None:
                self._pre_plugin_apis[api_name] = api_inst
                logging.getLogger(__name__).info(
                    "已注册前置插件 API: %s v%s",
                    api_name,
                    ".".join(str(x) for x in min_version),
                )
                return True
            logging.getLogger(__name__).warning(
                "前置插件 API '%s' 不可用（可能未加载或版本不符）", api_name
            )
            return False
        except Exception as e:
            logging.getLogger(__name__).warning(
                "注册前置插件 API '%s' 失败: %s", api_name, e
            )
            return False

    def get_pre_plugin_api(self, api_name: str) -> Optional[Any]:
        """获取已注册的前置插件 API 实例。"""
        return self._pre_plugin_apis.get(api_name)

    def get_pre_plugin_apis(self) -> Dict[str, Any]:
        """返回所有已注册的前置插件 API 字典。"""
        return dict(self._pre_plugin_apis)

    # ── 管理员检查 ──────────────────────────────────────────

    def is_user_admin(self, user_id: int, config_mgr=None) -> bool:
        """检查用户是否为管理员。"""
        cfg = config_mgr or self._config_mgr
        if cfg is None:
            return False
        admin_list = cfg.get("管理员.管理员QQ", [])
        try:
            uid_int = int(user_id) if not isinstance(user_id, int) else user_id
            return uid_int in [int(q) for q in admin_list]
        except (TypeError, ValueError):
            return False

    # ── 指令执行 ────────────────────────────────────────────

    def send_game_command_with_resp(
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[str]:
        """发送游戏指令并返回响应文本。"""
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(cmd, timeout)
            if resp and resp.OutputMessages:
                lines = []
                for msg in resp.OutputMessages:
                    if hasattr(msg, "Message"):
                        lines.append(msg.Message)
                    else:
                        lines.append(str(msg))
                return "\n".join(lines)
            return ""
        except Exception as e:
            logging.getLogger(__name__).error("同步指令执行失败: %s", e)
            return None

    def send_game_command_full(
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """发送游戏指令并返回完整响应（包括 Parameters）。"""
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(cmd, timeout)
            if resp is None:
                return None
            output = []
            for msg in resp.OutputMessages:
                output.append({
                    "message": getattr(msg, "Message", ""),
                    "parameters": getattr(msg, "Parameters", []),
                })
            return {
                "success_count": resp.SuccessCount,
                "output": output,
            }
        except Exception as e:
            logging.getLogger(__name__).error("完整指令执行失败: %s", e)
            return None

    # ── UUID 解析 ───────────────────────────────────────────

    def resolve_player_names(self, entries: list) -> dict:
        """通过 ToolDelta 的 players_uuid 映射 UUID 到玩家名。

        优先使用 players_uuid 字典，若为空则尝试遍历 allplayers 列表
        中的 Player 对象提取 UUID。

        Args:
            entries: 包含 uniqueId 键的条目列表。

        Returns:
            {uniqueId: player_name} 映射字典。
        """
        uuid_to_player: Dict[str, str] = {}

        # 方式 1: players_uuid 字典（最快）
        players_uuid = getattr(self.game_ctrl, "players_uuid", {})
        if players_uuid:
            uuid_to_player = {
                uid: name for name, uid in players_uuid.items()
            }

        # 方式 2: 从 allplayers 的 Player 对象中提取
        if not uuid_to_player:
            raw = self.game_ctrl.allplayers
            if isinstance(raw, dict):
                uuid_to_player = {
                    uid: name for name, uid in raw.items()
                    if isinstance(uid, str) and len(uid) > 20
                }
            elif isinstance(raw, (list, tuple)):
                for player in raw:
                    if hasattr(player, "name") and hasattr(player, "uuid"):
                        uuid_to_player[player.uuid] = player.name

        return uuid_to_player

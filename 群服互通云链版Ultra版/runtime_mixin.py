"""Runtime websocket and message forwarding logic for Ultra."""

import importlib
import json
import time
from copy import deepcopy
from typing import Any

from tooldelta import Chat, InternalBroadcast, Player, utils

from .message_utils import (
    EASTER_EGG_QQIDS,
    remove_color,
    remove_cq_code,
    replace_cq,
)
from .qqbot_client import convert_cq_at_to_official

try:
    from tooldelta.utils.mc_translator import translate
except ImportError:
    translate = None


# 运行时层只管消息流转：执行指令、WebSocket、广播、群服互通分发。
class QQLinkerRuntimeMixin:
    """负责云链运行时、消息分发与 WebSocket 生命周期。"""

    CLOUD_FAILURE_LIMIT = 5
    CLOUD_FAILURE_WINDOW_SECONDS = 60 * 60
    _ws_session_id = 0

    def load_websocket_dependency(self):
        """通过 pip 模块支持安装并加载 websocket-client。"""
        pip_support = self.GetPluginAPI("pip", (0, 0, 1))
        pip_support.require({"websocket-client": "websocket"})
        websocket_module = importlib.import_module("websocket")
        self._websocket_module = websocket_module
        return websocket_module

    def cloud_channel_enabled(self) -> bool:
        """返回云链通道配置开关。"""
        settings = getattr(self, "cfg", {}).get("云链设置", {})
        return isinstance(settings, dict) and bool(
            settings.get("是否启用该通道", False))

    def cloud_channel_available(self) -> bool:
        """返回云链通道当前是否可以发送消息。"""
        return (
            self.cloud_channel_enabled()
            and self.ws is not None
            and bool(self.available)
        )

    def any_message_channel_available(self) -> bool:
        """返回云链或官机中是否至少有一个通道可发送。"""
        qqbot_settings = getattr(self, "cfg", {}).get("官机设置", {})
        qqbot_available = (
            isinstance(qqbot_settings, dict)
            and bool(qqbot_settings.get("是否启用该通道", False))
            and getattr(self, "_qqbot_client", None) is not None
        )
        return self.cloud_channel_available() or qqbot_available

    def _start_ws_session(self):
        """注册一个新的 WebSocket 会话编号，并清空上次重连状态。"""
        self._ws_session_id += 1
        self.reloaded = False
        self._ws_reconnect_delay = None
        return self._ws_session_id

    def _is_current_ws_session(self, ws_obj, session_id: int):
        """判断回调是否来自当前仍然有效的 WebSocket 会话。"""
        return session_id == self._ws_session_id and ws_obj is self.ws

    def _print_cloud_status(
        self,
        title: str,
        page_label: str,
        lines: list[str],
        level: str = "info",
    ):
        """按统一的控制台卡片样式输出云链连接状态。"""
        self.print_console_card(title, page_label, lines, level=level)

    def _prune_ws_failure_timestamps(
        self,
        now: float | None = None,
    ) -> list[float]:
        """只保留滚动一小时窗口内的云链连接失败记录。"""
        now = time.time() if now is None else float(now)
        cutoff = now - self.CLOUD_FAILURE_WINDOW_SECONDS
        failures = [
            float(timestamp)
            for timestamp in getattr(self, "_ws_failure_timestamps", [])
            if float(timestamp) > cutoff
        ]
        failures.sort()
        self._ws_failure_timestamps = failures
        return failures

    def _cloud_retry_wait_seconds(self, now: float | None = None) -> float:
        """返回触发每小时五次限制后还需要等待的秒数。"""
        now = time.time() if now is None else float(now)
        failures = self._prune_ws_failure_timestamps(now)
        if len(failures) < self.CLOUD_FAILURE_LIMIT:
            return 0.0
        return max(
            0.0,
            failures[0] + self.CLOUD_FAILURE_WINDOW_SECONDS - now,
        )

    def _record_ws_connection_failure(
        self,
        session_id: int,
        now: float | None = None,
    ) -> tuple[bool, int, float]:
        """为一次连接会话最多记录一次失败，并返回当前限流状态。"""
        now = time.time() if now is None else float(now)
        failures = self._prune_ws_failure_timestamps(now)
        if getattr(self, "_ws_last_failure_session_id", None) == session_id:
            return False, len(failures), self._cloud_retry_wait_seconds(now)
        self._ws_last_failure_session_id = session_id
        failures.append(now)
        self._ws_failure_timestamps = failures
        return True, len(failures), self._cloud_retry_wait_seconds(now)

    def _reset_ws_failure_limit(self) -> None:
        """云链成功连接后重置失败次数和限流提示状态。"""
        self._ws_failure_timestamps = []
        self._ws_last_failure_session_id = None
        self._ws_rate_limit_notice_until = 0.0

    @staticmethod
    def _ceil_retry_delay(seconds: float) -> int:
        """把重试等待时间向上取整到整秒。"""
        delay = max(1, int(seconds))
        if delay < seconds:
            delay += 1
        return delay

    def execute_cmd_and_get_zhcn_cb(self, cmd: str):
        """执行 MC 指令，并把原始返回整理成适合群聊展示的文本。"""
        try:
            result = self.game_ctrl.sendwscmd_with_resp(cmd, 10)
            if len(result.OutputMessages) == 0:
                return ["😅 指令执行失败", "😄 指令执行成功"][bool(result.SuccessCount)]
            if result.OutputMessages[0].Message in (
                "commands.generic.syntax",
                "commands.generic.unknown",
            ):
                return f'😅 未知的 MC 指令, 可能是指令格式有误: "{cmd}"'
            if translate is not None:
                output_text = "\n".join(
                    translate(
                        i.Message,
                        i.Parameters) for i in result.OutputMessages)
            else:
                output_text = "\n".join(
                    i.Message for i in result.OutputMessages)
            if result.SuccessCount:
                return "😄 指令执行成功，执行结果：\n" + output_text
            return "😭 指令执行失败，原因：\n" + output_text
        except IndexError as exec_err:
            import traceback

            traceback.print_exc()
            return f"执行出现问题: {exec_err}"
        except TimeoutError:
            return "😭 超时：指令获取结果返回超时"

    def iter_game_to_group_targets(self):
        """遍历当前启用了“游戏到群”转发的群。"""
        for group_id in self.group_order:
            group_cfg = self.group_cfgs[group_id]
            if group_cfg["游戏到群"]["是否启用"]:
                yield group_id, group_cfg

    @staticmethod
    def should_forward_game_message(msg: str, group_cfg: dict[str, Any]):
        """根据群配置判断一条游戏消息是否要转发，以及转发时应裁掉哪些前缀。"""
        trans_chars = group_cfg["游戏到群"]["仅转发以下符号开头的消息(列表为空则全部转发)"]
        block_prefixs = group_cfg["游戏到群"]["屏蔽以下字符串开头的消息"]
        if trans_chars:
            for prefix in trans_chars:
                if msg.startswith(prefix):
                    return True, msg[len(prefix):]
            return False, msg
        if block_prefixs:
            for prefix in block_prefixs:
                if msg.startswith(prefix):
                    return False, msg
        return True, msg

    def _cloud_connection_requested(self) -> bool:
        """返回当前是否仍需要保持云链连接。"""
        return bool(self._manual_launch or self.cloud_channel_enabled())

    def _activate_ws_runner(self) -> bool:
        """独占云链连接线程，并拒绝重复启动请求。"""
        with self._ws_runner_lock:
            if self._ws_runner_active:
                self._print_cloud_status(
                    "群服互通 云链连接",
                    "运行中",
                    ["云链连接线程已在运行", "本次重复连接请求已忽略"],
                    level="warn",
                )
                return False
            self._ws_runner_active = True
        return True

    def _deactivate_ws_runner(self) -> None:
        """释放云链连接线程的独占运行标记。"""
        with self._ws_runner_lock:
            self._ws_runner_active = False

    def _prepare_ws_retry_stop(self):
        """清空上次停止信号并返回可中断等待的事件。"""
        retry_stop = getattr(self, "_ws_retry_stop", None)
        if retry_stop is not None:
            retry_stop.clear()
        return retry_stop

    def _wait_for_cloud_delay(self, retry_stop, delay: float) -> bool:
        """等待云链重试间隔，并返回是否收到停止信号。"""
        if retry_stop is not None:
            return bool(retry_stop.wait(delay))
        time.sleep(delay)
        return False

    def _print_cloud_rate_limit_notice(self, now: float, delay: int) -> None:
        """在每个限流周期内只输出一次云链暂停重连提示。"""
        if getattr(self, "_ws_rate_limit_notice_until", 0.0) > now:
            return
        minutes = max(1, (delay + 59) // 60)
        self._ws_rate_limit_notice_until = now + delay
        self._print_cloud_status(
            "群服互通 云链连接",
            "限流",
            [
                "本小时云链连接失败已达到 5 次",
                "每小时最多尝试 5 次，已暂停自动重连",
                f"约 {minutes} 分钟后自动恢复连接尝试",
            ],
            level="warn",
        )

    def _wait_for_cloud_rate_limit(self, retry_stop) -> bool | None:
        """处理每小时连接次数限制；未限流时返回 None。"""
        now = time.time()
        retry_wait = self._cloud_retry_wait_seconds(now)
        if retry_wait <= 0:
            return None
        delay = self._ceil_retry_delay(retry_wait)
        self._ws_reconnect_delay = delay
        self._print_cloud_rate_limit_notice(now, delay)
        return self._wait_for_cloud_delay(retry_stop, delay)

    def _cloud_websocket_header(self) -> dict[str, str] | None:
        """根据云链校验码构造 WebSocket 鉴权请求头。"""
        validate_code = self.cfg["云链设置"]["校验码"].strip()
        if not validate_code:
            return None
        return {"Authorization": f"Bearer {validate_code}"}

    def _create_cloud_websocket(
        self,
        target: str,
        header: dict[str, str] | None,
        session_id: int,
    ):
        """创建绑定当前会话编号的云链 WebSocket 客户端。"""
        websocket_module = getattr(self, "_websocket_module", None)
        if websocket_module is None:
            raise RuntimeError("websocket-client 依赖尚未加载")

        def _on_message(ws_obj, message, sid=session_id):
            """Forward websocket messages to the active session handler."""
            return self.on_ws_message(ws_obj, message, sid) and None

        def _on_error(ws_obj, error, sid=session_id):
            """Forward websocket errors to the active session handler."""
            return self.on_ws_error(ws_obj, error, sid)

        def _on_close(ws_obj, code, reason, sid=session_id):
            """Forward websocket close events to the active session handler."""
            return self.on_ws_close(ws_obj, code, reason, sid)

        ws_app = websocket_module.WebSocketApp(
            target,
            header,
            on_message=_on_message,
            on_error=_on_error,
            on_close=_on_close,
        )
        ws_app.on_open = lambda ws_obj, sid=session_id: self.on_ws_open(
            ws_obj, sid)
        return ws_app

    def _run_cloud_connection_attempt(self) -> None:
        """创建一个云链会话并运行到本次连接结束。"""
        target = self._get_websocket_target()
        self._print_cloud_status(
            "群服互通 云链连接",
            "连接中",
            ["正在尝试连接云链", f"目标地址: {target}"],
            level="info",
        )
        session_id = self._start_ws_session()
        ws_app = self._create_cloud_websocket(
            target,
            self._cloud_websocket_header(),
            session_id,
        )
        self.ws = ws_app
        self.available = False
        ws_app.run_forever()

    def _next_cloud_reconnect_delay(self):
        """返回下一次云链重连延迟；无需重连时返回 None。"""
        delay = self._ws_reconnect_delay
        if delay is None or not self._cloud_connection_requested():
            return None
        return delay

    def _run_cloud_connection_loop(self, retry_stop) -> None:
        """循环执行云链限流等待、连接和断线重试。"""
        while self._cloud_connection_requested():
            rate_limit_stopped = self._wait_for_cloud_rate_limit(retry_stop)
            if rate_limit_stopped is not None:
                if rate_limit_stopped:
                    return
                continue
            self._run_cloud_connection_attempt()
            delay = self._next_cloud_reconnect_delay()
            if delay is None:
                return
            if self._wait_for_cloud_delay(retry_stop, delay):
                return

    @utils.thread_func("云链群服连接进程")
    def connect_to_websocket(self):
        """按当前配置或本地桥接参数建立到云链的连接。"""
        if not self._cloud_connection_requested():
            return
        if not self._activate_ws_runner():
            return
        retry_stop = self._prepare_ws_retry_stop()
        self.reloaded = False
        try:
            self._run_cloud_connection_loop(retry_stop)
        finally:
            self._deactivate_ws_runner()

    def _get_websocket_target(self):
        """返回当前应连接的 WebSocket 地址。"""
        if self._manual_launch:
            return f"ws://127.0.0.1:{self._manual_launch_port}"
        return self.cfg["云链设置"]["地址"]

    def api_get_status(self) -> dict[str, Any]:
        """Return a compact runtime status snapshot for external plugins."""
        try:
            websocket_target = self._get_websocket_target()
        except Exception:
            websocket_target = ""
        return {
            "available": bool(self.available),
            "ws_initialized": self.ws is not None,
            "websocket_target": websocket_target,
            "manual_launch": bool(self._manual_launch),
            "manual_launch_port": int(self._manual_launch_port),
            "reloaded": bool(self.reloaded),
            "reconnect_delay": self._ws_reconnect_delay,
            "session_id": int(self._ws_session_id),
            "linked_groups": list(self.group_order),
            "default_group": self.linked_group,
        }

    def api_get_online_players(self) -> list[str]:
        """Return a copy of current online player names."""
        game_ctrl = getattr(self, "game_ctrl", None)
        if game_ctrl is None:
            return []
        raw_players = getattr(game_ctrl, "allplayers", [])
        try:
            players = list(raw_players)
        except TypeError:
            return []
        result: list[str] = []
        for player in players:
            name = getattr(player, "name", player)
            name = str(name).strip()
            if name:
                result.append(name)
        return result

    def api_is_player_online(
        self,
        player_name: str,
        ignore_case: bool = False,
    ) -> bool:
        """Return whether a player name is currently online."""
        name = str(player_name).strip()
        if not name:
            return False
        players = self.api_get_online_players()
        if ignore_case:
            name = name.lower()
            return any(player.lower() == name for player in players)
        return name in players

    def api_execute_game_cmd(self, command: str) -> tuple[bool, str]:
        """Execute an MC command and return a stable result tuple."""
        cmd = str(command).strip()
        if not cmd:
            return False, "MC指令不能为空"
        if getattr(self, "game_ctrl", None) is None:
            return False, "游戏控制器不可用"
        try:
            result = self.execute_cmd_and_get_zhcn_cb(cmd)
        except Exception as err:
            return False, f"MC指令执行失败: {err}"
        message = "\n".join(result) if isinstance(
            result, list) else str(result)
        fail_markers = (
            "指令执行失败",
            "未知的 MC 指令",
            "执行出现问题",
            "超时",
        )
        return not any(marker in message for marker in fail_markers), message

    def api_get_game_to_group_targets(
        self,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Return game-to-group forwarding rules for configured groups."""
        targets: list[dict[str, Any]] = []
        for group_id in self.group_order:
            group_cfg = self.group_cfgs.get(group_id)
            if group_cfg is None:
                continue
            game_to_group = group_cfg["游戏到群"]
            enabled = bool(game_to_group["是否启用"])
            if enabled_only and not enabled:
                continue
            targets.append(
                {
                    "group_id": group_id,
                    "enabled": enabled,
                    "format": str(game_to_group["转发格式"]),
                    "required_prefixes": list(
                        game_to_group["仅转发以下符号开头的消息(列表为空则全部转发)"]
                    ),
                    "blocked_prefixes": list(game_to_group["屏蔽以下字符串开头的消息"]),
                    "forward_player_events": bool(game_to_group["转发玩家进退提示"]),
                    "config": deepcopy(group_cfg),
                }
            )
        return targets

    def api_should_forward_game_message(
        self,
        group_id: int | str,
        message: str,
    ) -> tuple[bool, str] | None:
        """Preview whether a game chat message would be forwarded to a group."""
        try:
            gid = int(str(group_id).strip())
        except (TypeError, ValueError):
            return None
        group_cfg = self.group_cfgs.get(gid)
        if group_cfg is None:
            return None
        msg = str(message)
        if not group_cfg["游戏到群"]["是否启用"]:
            return False, msg
        return self.should_forward_game_message(msg, group_cfg)

    def reload_websocket_connection(self):
        """让云链连接按当前配置重新建立。"""
        self.stop_websocket_connection()
        if self.cloud_channel_enabled() and not self._manual_launch:
            self.connect_to_websocket()

    def stop_websocket_connection(self):
        """停止当前云链连接，并阻止旧会话继续重连。"""
        self.reloaded = True
        self._ws_reconnect_delay = None
        self.available = False
        self._ws_session_id += 1
        retry_stop = getattr(self, "_ws_retry_stop", None)
        if retry_stop is not None:
            retry_stop.set()
        ws_obj = self.ws
        if ws_obj is not None:
            try:
                ws_obj.close()
            except Exception as err:
                self._print_cloud_status(
                    "群服互通 云链连接",
                    "重载",
                    [f"关闭旧连接失败: {err}", "将继续尝试使用新配置连接"],
                    level="warn",
                )
        self.ws = None

    def api_reload_websocket(self) -> tuple[bool, str]:
        """Request the cloud WebSocket connection to reload."""
        try:
            self.reload_websocket_connection()
        except Exception as err:
            return False, f"云链重载失败: {err}"
        return True, "已请求云链重载"

    def _get_message_listener_store(self):
        """Return the raw group message listener registry."""
        if not hasattr(self, "_message_listeners") or not isinstance(
            self._message_listeners, dict
        ):
            self._message_listeners = {}
        return self._message_listeners

    def api_register_message_listener(
            self, name: str, listener) -> tuple[bool, str]:
        """Register a raw group message listener callback."""
        listener_name = str(name).strip()
        if not listener_name:
            return False, "监听器名称不能为空"
        if not callable(listener):
            return False, "监听器必须是可调用对象"
        listeners = self._get_message_listener_store()
        if listener_name in listeners:
            return False, "监听器已存在"
        listeners[listener_name] = listener
        return True, "已注册原始群消息监听器"

    def api_unregister_message_listener(self, name: str) -> tuple[bool, str]:
        """Unregister a raw group message listener callback."""
        listener_name = str(name).strip()
        if not listener_name:
            return False, "监听器名称不能为空"
        listeners = self._get_message_listener_store()
        if listener_name not in listeners:
            return False, "监听器不存在"
        del listeners[listener_name]
        return True, "已注销原始群消息监听器"

    def api_get_message_listeners(self) -> list[dict[str, Any]]:
        """Return metadata for registered raw group message listeners."""
        return [
            {"name": name, "callable": callable(listener)}
            for name, listener in self._get_message_listener_store().items()
        ]

    def _stop_when_message_listener_handled(
            self, data: dict[str, Any]) -> bool:
        """Run registered raw message listeners; truthy return stops processing."""
        for name, listener in list(self._get_message_listener_store().items()):
            try:
                if listener(deepcopy(data)):
                    return True
            except Exception as err:
                if hasattr(self, "_print_cloud_status"):
                    self._print_cloud_status(
                        "群服互通 原始消息监听",
                        "监听器异常",
                        [f"{name}: {err}"],
                        level="warn",
                    )
        return False

    @utils.thread_func("云链群服消息广播进程")
    def broadcast(self, data):
        """把原始群消息广播给主动注册的其他插件。"""
        for plugin_name in self.plugin:
            self.GetPluginAPI(plugin_name).QQLinker_message(data)

    def on_ws_open(self, _ws, session_id: int):
        """在 WebSocket 建立后标记连接可用。"""
        if not self._is_current_ws_session(_ws, session_id):
            return
        self._reset_ws_failure_limit()
        self.available = True
        self._print_cloud_status(
            "群服互通 云链连接",
            "已连接",
            ["已成功连接到群服互通云链版Ultra版", f"当前地址: {self._get_websocket_target()}"],
            level="success",
        )

    @utils.thread_func("群服互通消息接收线程")
    def on_ws_message(self, _ws, message, session_id: int):
        """处理来自云链的群消息，并按配置分发到不同入口。"""
        if not self._is_current_ws_session(_ws, session_id):
            return
        data = json.loads(message)
        self.process_group_message_data(data)

    def process_group_message_data(self, data: dict[str, Any]):
        """让任意 QQ 通道复用 Ultra 的群消息处理流水线。"""
        if self._stop_when_data_broadcast_handled(data):
            return

        payload = self._build_group_message_payload(data)
        if payload is None:
            return

        group_id, group_cfg, msg, user_id, nickname = payload
        if self._consume_waiting_reply(group_id, user_id, msg):
            return
        if self._stop_when_group_broadcast_handled(
                group_id, user_id, nickname, msg):
            return
        if self.execute_triggers(group_id, user_id, msg):
            return
        self._forward_group_message_to_game(group_cfg, user_id, nickname, msg)

    def _stop_when_data_broadcast_handled(self, data: dict[str, Any]) -> bool:
        """把原始数据广播给框架，其它插件声明已处理时立即停止后续流程。"""
        bc_recv = self.BroadcastEvent(InternalBroadcast("群服互通/数据json", data))
        if any(bc_recv):
            return True
        if data.get("post_type") != "message" or data.get(
                "message_type") != "group":
            return True
        if self._stop_when_message_listener_handled(data):
            return True
        self.broadcast(data)
        return False

    def _build_group_message_payload(self, data: dict[str, Any]):
        """把云链原始消息整理成后续逻辑统一使用的结构。"""
        group_id = data.get("group_id")
        if group_id not in self.group_cfgs:
            return None
        group_cfg = self.group_cfgs[group_id]
        msg = self._extract_text_message(data["message"])
        user_id = int(data["sender"]["user_id"])
        nickname = data["sender"]["card"] or data["sender"]["nickname"]
        return group_id, group_cfg, msg, user_id, nickname

    @staticmethod
    def _extract_text_message(msg: Any) -> str:
        """从云链消息结构里提取可处理的纯文本。"""
        if isinstance(msg, list):
            msg_rawdict = msg[0]
            msg_type = msg_rawdict["type"]
            msg_data = msg_rawdict["data"]
            if msg_type != "text":
                return ""
            return msg_data["text"]
        if not isinstance(msg, str):
            raise ValueError(f"键 'message' 值不是字符串类型, 而是 {msg}")
        return msg

    def _consume_waiting_reply(
            self,
            group_id: int,
            user_id: int,
            msg: str) -> bool:
        """把当前消息投递给等待输入的菜单回调。"""
        reopen_menu = self._is_help_menu_reopen_message(group_id, msg)
        wait_key = (group_id, user_id)
        cb = self.waitmsg_cbs.pop(wait_key, None)
        if cb is not None:
            if reopen_menu:
                cb(self._menu_exit_input_for_group(group_id))
                return False
            cb(msg)
            return True
        cb = self.waitmsg_cbs.pop(user_id, None)
        if cb is not None:
            if reopen_menu:
                cb(self._menu_exit_input_for_group(group_id))
                return False
            cb(msg)
            return True
        return False

    def _is_help_menu_reopen_message(self, group_id: int, msg: str) -> bool:
        """判断等待菜单期间的消息是否要求重新打开帮助菜单。"""
        return str(msg).strip() in self.get_group_help_triggers(group_id)

    def _menu_exit_input_for_group(self, group_id: int) -> str:
        """返回用于释放旧菜单等待的首个退出触发词。"""
        triggers = self.get_group_menu_exit_triggers(group_id)
        if triggers:
            return str(triggers[0])
        return "q"

    def _stop_when_group_broadcast_handled(
        self,
        group_id: int,
        user_id: int,
        nickname: str,
        msg: str,
    ) -> bool:
        """把群消息广播给框架层，其它插件声明已处理时立即停止。"""
        bc_recv = self.BroadcastEvent(
            InternalBroadcast(
                "群服互通/链接群消息",
                {"群号": group_id, "QQ号": user_id, "昵称": nickname, "消息": msg},
            ),
        )
        return any(bc_recv)

    def _forward_group_message_to_game(
        self,
        group_cfg: dict[str, Any],
        user_id: int,
        nickname: str,
        msg: str,
    ):
        """把普通群消息按当前群配置转发到游戏内。"""
        if not group_cfg["群到游戏"]["是否启用"]:
            return
        if user_id in group_cfg["群到游戏"]["屏蔽的QQ号"]:
            return
        trans_chars = group_cfg["群到游戏"]["仅转发以下符号开头的消息(列表为空则全部转发)"]
        if trans_chars:
            matched_prefix = None
            for prefix in trans_chars:
                if msg.startswith(prefix):
                    matched_prefix = prefix
                    break
            if matched_prefix is None:
                return
            msg = msg[len(matched_prefix):]

        if group_cfg["群到游戏"]["替换花里胡哨的昵称"]:
            nickname = remove_color(nickname)
        if group_cfg["群到游戏"]["替换花里胡哨的消息"]:
            msg = remove_color(msg)
        self.game_ctrl.say_to(
            "@a",
            utils.simple_fmt(
                {"[昵称]": nickname, "[消息]": replace_cq(msg)},
                group_cfg["群到游戏"]["转发格式"],
            ),
        )

    def on_ws_error(self, _ws, error, session_id: int):
        """处理 WebSocket 错误并按配置尝试重连。"""
        if not self._is_current_ws_session(_ws, session_id):
            return
        if not isinstance(error, Exception):
            # 某些 WebSocket 实现会在连接仍然可用时回调空字符串/None。
            # 这类“空错误”没有实际诊断价值，也不代表连接真的断开。
            if error is None or (isinstance(error, str)
                                 and error.strip() == ""):
                return
            self._print_cloud_status(
                "群服互通 云链连接",
                "停止",
                [f"连接线程已结束: {error}", "收到非异常错误对象，已停止重连"],
                level="info",
            )
            self.reloaded = True
            self._ws_reconnect_delay = None
            return
        self.available = False
        recorded, failure_count, retry_wait = (
            self._record_ws_connection_failure(session_id)
        )
        if not recorded:
            return
        if retry_wait > 0:
            delay = self._ceil_retry_delay(retry_wait)
            self._ws_reconnect_delay = delay
            self._ws_rate_limit_notice_until = time.time() + delay
            minutes = max(1, (delay + 59) // 60)
            retry_lines = [
                f"本小时云链连接失败已达到 {failure_count} 次",
                "每小时最多尝试 5 次，已暂停自动重连",
                f"约 {minutes} 分钟后自动恢复连接尝试",
            ]
        else:
            self._ws_reconnect_delay = 15
            retry_lines = [
                f"本小时连接失败次数: {failure_count}/5",
                "15 秒后尝试重连",
            ]
        self._print_cloud_status(
            "群服互通 云链连接",
            "异常",
            [f"连接失败: {error}", *retry_lines],
            level="error",
        )

    def waitMsg(
            self,
            qqid: int,
            timeout=60,
            group_id: int | None = None) -> str | None:
        """等待某个 QQ 在指定群里的下一条回复。
        带 `group_id` 时只收同群回复，不带时保留对旧插件的兼容行为。
        """
        getter, setter = utils.create_result_cb(str)
        key: int | tuple[int, int] = qqid if group_id is None else (
            group_id, qqid)
        self.waitmsg_cbs[key] = setter
        try:
            return getter(timeout)
        finally:
            if self.waitmsg_cbs.get(key) is setter:
                del self.waitmsg_cbs[key]

    def api_wait_group_msg(
        self,
        qqid: int | str,
        timeout: int = 60,
        group_id: int | str | None = None,
    ) -> str | None:
        """Wait for one QQ member's next group message."""
        try:
            qid = int(str(qqid).strip())
        except (TypeError, ValueError):
            return None
        if qid <= 0:
            return None
        gid = None
        if group_id is not None:
            try:
                gid = int(str(group_id).strip())
            except (TypeError, ValueError):
                return None
        try:
            wait_seconds = max(0, int(timeout))
        except (TypeError, ValueError):
            wait_seconds = 60
        return self.waitMsg(qid, wait_seconds, gid)

    def on_ws_close(self, _ws, _, _2, session_id: int):
        """连接关闭时按当前状态决定是否自动重连。"""
        if not self._is_current_ws_session(_ws, session_id):
            return
        self.available = False
        if self.reloaded:
            return
        if self._ws_reconnect_delay is None:
            recorded, failure_count, retry_wait = (
                self._record_ws_connection_failure(session_id)
            )
            if not recorded:
                return
            if retry_wait > 0:
                delay = self._ceil_retry_delay(retry_wait)
                self._ws_reconnect_delay = delay
                self._ws_rate_limit_notice_until = time.time() + delay
                minutes = max(1, (delay + 59) // 60)
                retry_lines = [
                    f"本小时云链连接失败已达到 {failure_count} 次",
                    "每小时最多尝试 5 次，已暂停自动重连",
                    f"约 {minutes} 分钟后自动恢复连接尝试",
                ]
            else:
                self._ws_reconnect_delay = 10
                retry_lines = [
                    f"本小时连接失败次数: {failure_count}/5",
                    "10 秒后尝试重连",
                ]
            self._print_cloud_status(
                "群服互通 云链连接",
                "关闭",
                ["连接已关闭", *retry_lines],
                level="error",
            )

    def on_player_join(self, playerf: Player):
        """把玩家加入事件转发到所有启用了游戏到群的群。"""
        player = playerf.name
        if not self.any_message_channel_available():
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            if group_cfg["游戏到群"]["转发玩家进退提示"]:
                self.sendmsg(group_id, f"{player} 加入了游戏")

    def on_player_leave(self, playerf: Player):
        """把玩家离开事件转发到所有启用了游戏到群的群。"""
        player = playerf.name
        if not self.any_message_channel_available():
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            if group_cfg["游戏到群"]["转发玩家进退提示"]:
                self.sendmsg(group_id, f"{player} 退出了游戏")

    def on_player_message(self, chat: Chat):
        """按各群配置把游戏聊天消息转发到对应群聊。"""
        if self.consume_game_binding_code(chat):
            return True

        player = chat.player.name
        msg = chat.msg
        if not self.any_message_channel_available():
            return False
        for group_id, group_cfg in self.iter_game_to_group_targets():
            can_send, filtered_msg = self.should_forward_game_message(
                msg, group_cfg)
            if not can_send:
                continue
            self.sendmsg(
                group_id,
                utils.simple_fmt(
                    {"[玩家名]": player, "[消息]": remove_cq_code(filtered_msg)},
                    group_cfg["游戏到群"]["转发格式"],
                ),
            )
        return False

    def execute_triggers(self, group_id: int, qqid: int, msg: str):
        """对一条群消息做内置命令和外挂命令的统一分发。"""
        clean_msg = msg.strip()
        if self._handle_exact_trigger(group_id, qqid, clean_msg):
            return True
        if self._handle_prefixed_command(group_id, qqid, clean_msg):
            return True
        if self._handle_group_orion_triggers(group_id, qqid, clean_msg):
            return True
        return self._handle_external_trigger(group_id, qqid, msg)

    def _reply_to_qq(self, group_id: int, qqid: int, text: str):
        """向指定 QQ 回复一条消息。"""
        self.sendmsg(
            group_id,
            f"[CQ:at,qq={qqid}] {text}",
            do_remove_cq_code=False,
        )

    def _handle_admin_menu_trigger(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
    ) -> bool:
        """处理完全匹配的管理员菜单触发词。"""
        if clean_msg not in self.get_group_admin_menu_triggers(group_id):
            return False
        if self._reject_qqbot_real_qq_feature(
            group_id,
            qqid,
            "admin_menu",
        ):
            return True
        if not self._has_any_group_permission(
            group_id,
            qqid,
            ("QQ普通管理员菜单权限", "QQ超级管理员菜单权限"),
        ):
            self._reply_permission_denied(group_id, qqid)
            return True
        self.qq_admin_menu(group_id, qqid)
        return True

    def _handle_identity_exact_trigger(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
    ) -> bool:
        """处理绑定、帮助及管理员菜单这类身份相关触发词。"""
        if (
            clean_msg in self.get_group_binding_triggers(group_id)
            and self._reject_qqbot_real_qq_feature(
                group_id,
                qqid,
                "binding",
            )
        ):
            return True
        if self._handle_binding_trigger(group_id, qqid, clean_msg):
            return True
        if clean_msg in self.get_group_help_triggers(group_id):
            self.on_qq_help(group_id, qqid, [])
            return True
        return self._handle_admin_menu_trigger(group_id, qqid, clean_msg)

    def _handle_permission_exact_trigger(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
    ) -> bool:
        """以统一表驱动方式处理带权限的完全匹配菜单。"""
        actions = (
            (
                self.get_group_config_menu_triggers(group_id),
                "配置配置文件权限",
                lambda: self.qq_config_center_menu(group_id, qqid),
            ),
            (
                self.get_group_player_list_triggers(group_id),
                "查看玩家人数权限",
                lambda: self.on_qq_player_list(group_id, qqid, []),
            ),
            (
                self.get_group_inventory_menu_triggers(group_id),
                "查询背包权限",
                lambda: self.qq_inventory_menu(group_id, qqid),
            ),
            (
                self.get_group_checker_menu_triggers(group_id),
                "白名单&管理员检测权限",
                lambda: self.qq_checker_menu(group_id, qqid),
            ),
            (
                self.get_group_task_menu_triggers(group_id),
                "任务系统权限",
                lambda: self.qq_task_system_menu(group_id, qqid),
            ),
            (
                self.get_group_land_menu_triggers(group_id),
                "领地系统权限",
                lambda: self.qq_land_system_menu(group_id, qqid),
            ),
        )
        for triggers, permission_name, action in actions:
            if clean_msg in triggers:
                return self._run_permission_action(
                    group_id,
                    qqid,
                    permission_name,
                    action,
                )
        return False

    def _handle_feature_exact_trigger(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
    ) -> bool:
        """处理权限菜单和公会菜单等功能型完全匹配触发词。"""
        if self._handle_permission_exact_trigger(group_id, qqid, clean_msg):
            return True
        if clean_msg in self.get_group_guild_menu_triggers(group_id):
            self.qq_guild_entry_menu(group_id, qqid)
            return True
        return False

    def _handle_exact_trigger(
            self,
            group_id: int,
            qqid: int,
            clean_msg: str) -> bool:
        """处理帮助、管理员菜单、背包查询等完全匹配型触发词。"""
        if self._handle_identity_exact_trigger(group_id, qqid, clean_msg):
            return True
        return self._handle_feature_exact_trigger(group_id, qqid, clean_msg)

    def _handle_prefixed_command(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
    ) -> bool:
        """处理带统一前缀的群内执行指令入口。"""
        cmd_prefix = self.get_group_cmd_prefix(group_id)
        if not clean_msg.startswith(cmd_prefix):
            return False

        args = clean_msg.removeprefix(cmd_prefix).strip().split()
        if not self._has_group_permission(group_id, qqid, "发送指令权限"):
            self._reply_permission_denied(group_id, qqid)
            return True
        if len(args) == 0:
            self._reply_to_qq(group_id, qqid, f"参数错误，格式：{cmd_prefix}[指令]")
            return True

        self.on_qq_execute_cmd(group_id, qqid, args)
        return True

    def _handle_group_orion_triggers(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
    ) -> bool:
        """处理 Orion 封禁/解封相关的前缀命令。"""
        if self._handle_orion_trigger(
            group_id,
            qqid,
            clean_msg,
            self.get_group_orion_ban_triggers(group_id),
            self.on_qq_orion_ban,
            "[玩家名/xuid] [封禁时间] [原因可选]",
            lambda args: len(args) == 0 or len(args) >= 2,
        ):
            return True
        return self._handle_orion_trigger(
            group_id,
            qqid,
            clean_msg,
            self.get_group_orion_unban_triggers(group_id),
            self.on_qq_orion_unban,
            "[玩家名/xuid]",
            lambda args: len(args) in (0, 1),
        )

    def _handle_orion_trigger(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
        triggers: list[str],
        handler,
        args_hint: str,
        args_validator,
    ) -> bool:
        """处理一组 Orion 触发词。"""
        for trigger in triggers:
            if not clean_msg.startswith(trigger):
                continue
            args = clean_msg.removeprefix(trigger).strip().split()
            if not self._has_group_permission(group_id, qqid, "封禁/解封玩家权限"):
                self._reply_permission_denied(group_id, qqid)
                return True
            if not args_validator(args):
                self._reply_to_qq(
                    group_id, qqid, f"参数错误，格式：{trigger} {args_hint}")
                return True
            handler(group_id, qqid, args)
            return True
        return False

    def _handle_external_trigger(
            self,
            group_id: int,
            qqid: int,
            msg: str) -> bool:
        """处理外部插件注册进来的自定义触发词。"""
        for trigger in self.triggers:
            matched = trigger.match(msg)
            if not matched:
                continue

            if trigger.op_only and not self.is_group_admin(group_id, qqid):
                self._reply_permission_denied(group_id, qqid)
                return True

            args = msg.removeprefix(matched).strip().split()
            if not trigger.args_pd(len(args)):
                self._reply_trigger_arg_error(
                    group_id,
                    qqid,
                    matched,
                    trigger.argument_hint,
                )
                return True

            if trigger.accept_group:
                trigger.func(group_id, qqid, args)
            else:
                trigger.func(qqid, args)
            return True
        return False

    def _reply_permission_denied(self, group_id: int, qqid: int):
        """统一处理没有管理权限时的回复。"""
        if easter_egg := EASTER_EGG_QQIDS.get(qqid):
            _name, nickname = easter_egg
            self._reply_to_qq(group_id, qqid, f"你没有权限执行此指令，即使你是 {nickname}..")
            return
        self._reply_to_qq(group_id, qqid, "你没有权限执行此指令")

    def _reply_trigger_arg_error(
        self,
        group_id: int,
        qqid: int,
        trigger: str,
        argument_hint: str | None,
    ):
        """统一处理外部触发器参数不足时的回复。"""
        suffix = f" {argument_hint}" if argument_hint else ""
        self._reply_to_qq(group_id, qqid, f"参数错误，格式：{trigger}{suffix}")

    def _has_group_permission(
            self,
            group_id: int,
            qqid: int,
            permission_name: str) -> bool:
        """Implement the has group permission operation."""
        if hasattr(self, "has_group_permission"):
            return self.has_group_permission(group_id, qqid, permission_name)
        return self.is_group_admin(group_id, qqid)

    def _has_any_group_permission(
        self,
        group_id: int,
        qqid: int,
        permission_names: tuple[str, ...],
    ) -> bool:
        """Implement the has any group permission operation."""
        return any(
            self._has_group_permission(group_id, qqid, permission_name)
            for permission_name in permission_names
        )

    def _run_permission_action(
        self,
        group_id: int,
        qqid: int,
        permission_name: str,
        action,
    ) -> bool:
        """执行按配置权限控制的动作。"""
        if not self._has_group_permission(group_id, qqid, permission_name):
            self._reply_permission_denied(group_id, qqid)
            return True
        action()
        return True

    def _run_admin_only_action(self, group_id: int, qqid: int, action) -> bool:
        """执行仅群管理员可用的动作。"""
        if not self.is_group_admin(group_id, qqid):
            self._reply_to_qq(group_id, qqid, "你没有权限执行此指令")
            return True
        action()
        return True

    def on_sendmsg_test(self, args: list[str]):
        """供控制台快速验证群消息发送链路是否正常。"""
        if not self.any_message_channel_available():
            self.print_console_error("云链和官机通道当前均不可用")
            return
        if not args:
            self.print_console_error("请输入要发送的消息")
            return
        target_group = None
        if len(args) >= 2:
            maybe_gid = utils.try_int(args[0])
            if maybe_gid in self.group_cfgs:
                target_group = maybe_gid
                args = args[1:]
        if target_group is not None:
            self.sendmsg(target_group, " ".join(args))
            return
        for group_id in self.group_order:
            self.sendmsg(group_id, " ".join(args))

    def sendmsg(self, group: int, msg: str, do_remove_cq_code=True):
        """向所有已启用且可用的 QQ 通道发送群消息。"""
        if msg.startswith("[CQ:at,qq="):
            cq_end = msg.find("]")
            if cq_end != -1:
                head = msg[: cq_end + 1]
                tail = msg[cq_end + 1:].lstrip()
                msg = head if tail == "" else head + "\n" + tail
        cloud_message = remove_cq_code(msg) if do_remove_cq_code else msg
        sent = False
        if self.cloud_channel_available():
            payload = {
                "action": "send_group_msg",
                "params": {"group_id": group, "message": cloud_message},
            }
            try:
                self.ws.send(json.dumps(payload))
                sent = True
            except Exception as error:
                self.print_console_error(f"云链群消息发送失败: {error}")

        qqbot_client = getattr(self, "_qqbot_client", None)
        qqbot_settings = getattr(self, "cfg", {}).get("官机设置", {})
        qqbot_enabled = isinstance(qqbot_settings, dict) and bool(
            qqbot_settings.get("是否启用该通道", False))
        if qqbot_enabled and qqbot_client is not None:
            official_message = convert_cq_at_to_official(
                msg,
                getattr(self, "_qqbot_user_names", {}),
            )
            try:
                qqbot_client.send_group_msg(group, official_message)
                sent = True
            except Exception as error:
                self.print_console_error(f"官机群消息发送失败: {error}")

        if not sent:
            self._print_cloud_status(
                "群服互通 消息通道",
                "忽略发送",
                ["当前没有可用消息通道", f"已忽略发送到群 {group} 的消息"],
                level="warn",
            )
        return sent

    def api_send_group_msg(
        self,
        group_id: int | str,
        message: str,
        strip_cq_code: bool = True,
    ) -> tuple[bool, str]:
        """Send a QQ group message and return a stable result tuple."""
        try:
            gid = int(str(group_id).strip())
        except (TypeError, ValueError):
            return False, "群号无效"
        if gid <= 0:
            return False, "群号无效"
        if not self.any_message_channel_available():
            return False, "云链和官机通道当前均不可用"
        try:
            sent = self.sendmsg(
                gid,
                str(message),
                do_remove_cq_code=bool(strip_cq_code))
        except Exception as err:
            return False, f"发送群消息失败: {err}"
        if not sent:
            return False, "所有可用通道均发送失败"
        return True, "已发送群消息"

    def api_reply_group_member(
        self,
        group_id: int | str,
        qqid: int | str,
        message: str,
    ) -> tuple[bool, str]:
        """Reply to a QQ group member with an at-mention."""
        try:
            qid = int(str(qqid).strip())
        except (TypeError, ValueError):
            return False, "QQ号无效"
        if qid <= 0:
            return False, "QQ号无效"
        return self.api_send_group_msg(
            group_id,
            f"[CQ:at,qq={qid}] {message}",
            strip_cq_code=False,
        )

    def api_send_private_msg(
        self,
        qqid: int | str,
        message: str,
    ) -> tuple[bool, str]:
        """Send a private QQ message and return a stable result tuple."""
        try:
            qid = int(str(qqid).strip())
        except (TypeError, ValueError):
            return False, "QQ号无效"
        if qid <= 0:
            return False, "QQ号无效"
        if not self.any_message_channel_available():
            return False, "云链和官机通道当前均不可用"
        try:
            sent = self.send_private_msg(qid, str(message))
        except Exception as err:
            return False, f"发送私信失败: {err}"
        if not sent:
            return False, "没有可用私信通道或缺少用户 OpenID"
        return True, "已发送私信"

import json
import threading
import time
from typing import Any

from websocket import WebSocketConnectionClosedException, create_connection

from tooldelta import Chat, Config, Player, Plugin, cfg, plugin_entry, utils
from tooldelta.internal.launch_cli import FrameFateArk, FrameNeOmgAccessPoint
from tooldelta.utils import mc_translator


class NEMCMessageSync(Plugin):
    """连接 AstrBot NEMC Sync，实现 MC 与 QQ 群纯文本消息互通。"""

    name = "NEMC消息互通"
    author = "Mono"
    description = "连接 AstrBot NEMC Sync，实现 MC 与 QQ 群纯文本消息互通"
    version = (0, 1, 1)

    DEFAULT_CONFIG = {
        "服务端地址": "ws://127.0.0.1:24011",
        "Token": "",
        "服务器ID": "default",
        "重连间隔秒": 5,
        "命令超时秒": 10,
        "转发MC聊天到QQ": True,
        "转发玩家加入到QQ": True,
        "转发玩家预加入到QQ": False,
        "转发玩家退出到QQ": True,
        "接收QQ群消息到MC": True,
        "执行QQ群命令": True,
        "QQ群消息显示格式": "§7[Group] §f<{sender}> {msg}",
        "忽略这些前缀开头的MC消息": ["/"],
    }

    CONFIG_SCHEMA = {
        "服务端地址": str,
        "Token": str,
        "服务器ID": str,
        "重连间隔秒": Config.PNumber,
        "命令超时秒": Config.PNumber,
        "转发MC聊天到QQ": bool,
        "转发玩家加入到QQ": bool,
        "转发玩家预加入到QQ": bool,
        "转发玩家退出到QQ": bool,
        "接收QQ群消息到MC": bool,
        "执行QQ群命令": bool,
        "QQ群消息显示格式": str,
        "忽略这些前缀开头的MC消息": Config.JsonList(str),
    }

    def __init__(self, frame):
        super().__init__(frame)
        self.config, _ = self.get_config_and_version(
            self.CONFIG_SCHEMA, self.DEFAULT_CONFIG
        )
        self._ensure_config_defaults()
        self.set_server_id()
        self._ws = None
        self._ws_lock = threading.Lock()
        self._stop_event = threading.Event()

        self.ListenActive(self.on_active)
        self.ListenChat(self.on_chat)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerPreJoin(self.on_player_pre_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenFrameExit(self.on_frame_exit)

    def on_active(self):
        """插件激活时启动 WebSocket 连接线程。"""
        if not self.config["Token"]:
            self.print_war("Token 为空，请先在插件配置文件中填写 AstrBot 端 token")
        utils.createThread(self._connect_loop, usage="NEMC消息互通 WebSocket 客户端")

    def on_frame_exit(self, _):
        """框架退出时关闭 WebSocket 连接。"""
        self._stop_event.set()
        with self._ws_lock:
            if self._ws is not None:
                try:
                    self._ws.close()
                except Exception:
                    pass
                self._ws = None

    def on_chat(self, chat: Chat):
        """处理 MC 聊天消息并转发到 QQ 群。"""
        if not self.config["转发MC聊天到QQ"]:
            return

        msg = chat.msg.strip()
        if not msg:
            return

        for prefix in self.config["忽略这些前缀开头的MC消息"]:
            if prefix and msg.startswith(prefix):
                return

        payload = {
            "s": "ok",
            "type": "message",
            "sender": chat.player.name,
            "msg": msg,
            "serverId": self.config["服务器ID"],
        }

        self._send_json(payload)

    def on_player_join(self, player: Player):
        """处理玩家加入事件。"""
        self._send_player_event("join", player, "转发玩家加入到QQ")

    def on_player_pre_join(self, player: Player):
        """处理玩家预加入事件。"""
        self._send_player_event("prejoin", player, "转发玩家预加入到QQ")

    def on_player_leave(self, player: Player):
        """处理玩家退出事件。"""
        self._send_player_event("leave", player, "转发玩家退出到QQ")

    def _send_player_event(self, event_type: str, player: Player, enabled_key: str):
        """发送玩家事件到 NEMC Sync 服务端。"""
        if not self.config.get(enabled_key, False):
            return

        playername = str(getattr(player, "name", "")).strip()
        if not playername:
            return

        payload = {
            "s": "ok",
            "type": event_type,
            "sender": playername,
            "playername": playername,
            "uuid": str(getattr(player, "uuid", "")),
            "xuid": str(getattr(player, "xuid", "")),
            "serverId": self.config["服务器ID"],
        }
        self._send_json(payload)

    def _connect_loop(self):
        """WebSocket 连接循环，处理重连逻辑。"""
        url = self.config["服务端地址"]
        reconnect_interval = float(self.config["重连间隔秒"])

        while not self._stop_event.is_set():
            try:
                ws = create_connection(url, timeout=10, enable_multithread=True)
                with self._ws_lock:
                    self._ws = ws

                self._send_json(
                    {"token": self.config["Token"], "serverId": self.config["服务器ID"]}
                )
                auth_payload = self._recv_json(ws)
                if not isinstance(auth_payload, dict) or auth_payload.get("s") != "ok":
                    reason = (
                        auth_payload.get("reason")
                        if isinstance(auth_payload, dict)
                        else "unknown"
                    )
                    raise RuntimeError(f"认证失败: {reason}")

                ws.settimeout(None)
                self.print_suc(f"已连接 AstrBot NEMC Sync: {url}")
                while not self._stop_event.is_set():
                    payload = self._recv_json(ws)
                    if isinstance(payload, dict):
                        self._handle_server_payload(payload)

            except WebSocketConnectionClosedException:
                self.print_war("WebSocket 连接已断开")
            except Exception as exc:
                self.print_war(f"WebSocket 连接异常: {exc}")
            finally:
                with self._ws_lock:
                    if self._ws is not None:
                        try:
                            self._ws.close()
                        except Exception:
                            pass
                    self._ws = None

            if not self._stop_event.is_set():
                time.sleep(reconnect_interval)

    def _handle_server_payload(self, payload: dict[str, Any]):
        """处理服务端发来的消息载荷。"""
        if payload.get("s") != "ok":
            return

        payload_type = payload.get("type")
        if payload_type == "message":
            if not self._is_for_this_server(payload):
                return
            if not self.config["接收QQ群消息到MC"]:
                return
            self._broadcast_group_message(payload)
        elif payload_type == "cmd":
            if not self._is_for_this_server(payload):
                return
            if not self.config["执行QQ群命令"]:
                self._send_command_result("")
                return
            cmd = str(payload.get("cmd", "")).strip()
            output = self._execute_command(cmd) if cmd else ""
            self._send_command_result(output)

    def _is_for_this_server(self, payload: dict[str, Any]) -> bool:
        """检查消息是否属于当前服务器。"""
        server_id = str(payload.get("serverId", "")).strip()
        return not server_id or server_id == str(self.config["服务器ID"])

    def _broadcast_group_message(self, payload: dict[str, Any]):
        """将 QQ 群消息广播到 MC 服务器。"""
        values = {
            "serverId": str(payload.get("serverId", "")),
            "groupId": str(payload.get("groupId", "")),
            "sender": str(payload.get("sender", "")),
            "msg": str(payload.get("msg", "")),
        }
        try:
            text = self.config["QQ群消息显示格式"].format(**values)
        except (KeyError, ValueError):
            text = f"[QQ:{values['groupId']}] <{values['sender']}> {values['msg']}"
        self.game_ctrl.say_to("@a", text)

    def _execute_command(self, cmd: str) -> str:
        """执行 MC 命令并返回结果。"""
        timeout = float(self.config["命令超时秒"])
        try:
            result = self.game_ctrl.sendwscmd_with_resp(cmd, timeout)
        except TimeoutError:
            return f"命令执行超时: {cmd}"
        except Exception as exc:
            return f"命令执行失败: {exc}"

        lines: list[str] = []
        for msg in result.OutputMessages:
            try:
                line = mc_translator.translate(msg.Message, msg.Parameters)
            except Exception:
                params = " ".join(str(i) for i in msg.Parameters)
                line = f"{msg.Message} {params}".strip()
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _send_command_result(self, output: str):
        """发送命令执行结果到服务端。"""
        self._send_json({"s": "ok", "type": "cmd-result", "output": output})

    def _send_json(self, payload: dict[str, Any]):
        """发送 JSON 数据到 WebSocket 服务端。"""
        data = json.dumps(payload, ensure_ascii=False)
        with self._ws_lock:
            if self._ws is None:
                return
            self._ws.send(data)

    @staticmethod
    def _recv_json(ws: Any) -> Any:
        """从 WebSocket 接收并解析 JSON 数据。"""
        raw = ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_server_id(self):
        """根据启动器类型自动设置服务器 ID。"""
        if isinstance(self.frame.launcher, FrameFateArk):
            self.config["服务器ID"] = self.frame.launcher.serverNumber
        elif isinstance(self.frame.launcher, FrameNeOmgAccessPoint):
            if self.frame.launcher.serverNumber is not None:
                self.config["服务器ID"] = self.frame.launcher.serverNumber
        cfg.upgrade_plugin_config(self.name, self.config, self.version)

    def _ensure_config_defaults(self):
        """确保配置中包含所有默认项，处理配置升级。"""
        changed = False
        for key, value in self.DEFAULT_CONFIG.items():
            if key not in self.config:
                self.config[key] = value
                changed = True
        if changed:
            cfg.upgrade_plugin_config(self.name, self.config, self.version)


entry = plugin_entry(NEMCMessageSync)

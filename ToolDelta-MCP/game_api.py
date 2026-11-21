"""Game-side operations for the ToolDelta MCP bridge."""

import json
import math
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from tooldelta.constants import PacketIDS, SysStatus, TextType
from tooldelta.internal.launch_cli import (
    FrameEulogistLauncher,
    FrameFateArk,
    FrameNeOmgAccessPoint,
    FrameTanGameAccessPoint,
)
from tooldelta.utils import ToolDeltaThread, get_playername_and_msg_from_text_packet, mc_translator
from tooldelta.version import get_tool_delta_version

from .records import COLOR, TEXT_LIMIT

if TYPE_CHECKING:
    from . import GameBridge

# These adapters implement server-bound dictionary Text packets.
CHAT_LAUNCHERS = (
    FrameFateArk,
    FrameNeOmgAccessPoint,
    FrameEulogistLauncher,
    FrameTanGameAccessPoint,
)


def _identifier(value):
    if isinstance(value, bytes):
        return str(UUID(bytes=value)) if len(value) == 16 else value.hex()
    return str(value) if value is not None else None


def _translation(message, parameters):
    try:
        return mc_translator.translate(message, parameters)
    except (ValueError, IndexError, KeyError, TypeError, AssertionError):
        # The translation table may not match the connected server's protocol.
        return message


def _tellraw_text(message):
    try:
        raw = json.loads(message)
        parts = raw.get("rawtext") if isinstance(raw, dict) else None
        if isinstance(parts, list):
            return "".join(str(p.get("text", p.get("translate", "")))
                           for p in parts if isinstance(p, dict))
    except (ValueError, RecursionError):
        pass
    return message


class GameAPI:
    def __init__(self, plugin: "GameBridge"):
        self.plugin = plugin
        self.frame = plugin.frame
        self.game = plugin.game_ctrl
        # All bridge generations for this frame share the in-flight reload guard.
        self.reload_lock = vars(self.frame).setdefault("_mcp_reload_lock", threading.Lock())

    def _connected(self):
        return (
            self.plugin.game_ready and self.frame.launcher.status == SysStatus.RUNNING
        )

    def _chat_identity(self):
        launcher = self.frame.launcher
        can_send = callable(getattr(self.game, "sendPacket", None))
        if not (self._connected() and can_send and isinstance(launcher, CHAT_LAUNCHERS)):
            return None
        name = getattr(launcher, "bot_name", "")
        bot = self.frame.get_players().getPlayerByName(name)
        return bot if bot and bot.online and bot.xuid else None

    def status(self):
        launcher = self.frame.launcher
        connected = self._connected()
        server_number = getattr(launcher, "serverNumber", None) if connected else None
        bot_name = getattr(launcher, "bot_name", "") if connected else ""
        player_count = (
            len(self.frame.get_players().getAllPlayers()) if connected else None
        )
        return {
            "connected": connected,
            "rental_server_id": str(server_number) if server_number else None,
            "launcher": launcher.launch_type,
            "launcher_status": launcher.status.name,
            "tooldelta_version": ".".join(map(str, get_tool_delta_version())),
            "bot_name": bot_name or None,
            "player_count": player_count,
            "bot_chat": {
                "available": self._chat_identity() is not None,
                "can_wait": False,
            },
            "command_channels": {
                "ws": {"identity": "WebSocket", "can_wait": True},
                "player": {"identity": "机器人玩家", "can_wait": True},
                "wo": {"identity": "游戏控制台", "can_wait": False},
                "ai": {
                    "identity": "魔法命令，具有最高的操作台权限",
                    "can_wait": callable(getattr(launcher, "sendaicmd", None)),
                },
                "console": {"identity": "ToolDelta 控制台菜单", "can_wait": False},
            },
        }

    def players_list(self):
        connected = self._connected()
        players = []
        if connected:
            roster = self.frame.get_players()
            bot_name = getattr(self.frame.launcher, "bot_name", "")
            for player in roster.getAllPlayers():
                # Player.abilities may wait 20 s for an update. Only read the cache.
                abilities = roster.player_abilities.get(player.unique_id)
                players.append({
                    "name": player.name,
                    "uuid": str(player.uuid),
                    "unique_id": _identifier(player.unique_id),
                    "runtime_id": _identifier(player.runtime_id),
                    "is_bot": player.name == bot_name if bot_name else None,
                    "is_op": abilities.command_permissions >= 3 if abilities else None,
                })
        return {"connected": connected, "count": len(players), "players": players}

    def console_list(self):
        commands = []
        allowed = self.plugin.console_allow
        # Group the actual registration keys, including aliases renamed after conflicts.
        aliases = {}
        for name, item in self.frame.cmd_manager.commands.copy().items():
            aliases.setdefault(item, []).append(name)
        for item, names in aliases.items():
            commands.append({
                "triggers": names,
                "argument_hint": item.argument_hint,
                "usage": item.usage,
                "allowed_triggers": [name for name in names if name in allowed],
            })
        return {"count": len(commands), "commands": commands}

    def _console_menu(self, command):
        registered = self.frame.cmd_manager.commands.copy()
        # Choose the same longest prefix as the console, before applying permissions.
        # Falling back to a shorter allowed prefix could invoke a different menu.
        trigger = max(
            (key for key in registered if key and command.startswith(key)),
            key=len,
            default=None,
        )
        if trigger is None or trigger not in self.plugin.console_allow:
            return None
        menu = registered[trigger]
        tail = command[len(trigger) :]
        # The framework also accepts joined arguments for prefixes such as "wo/" or "!".
        attached = trigger.endswith("/") or trigger.endswith("!")
        if tail and not (tail[0].isspace() or trigger[-1].isspace() or attached):
            return None
        return trigger, menu.cb, tail.split()

    def bot_chat(self, message: str):
        """Send one chat line from this connected bot's own identity."""
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")
        if any(char in message for char in ("\x00", "\r", "\n")):
            raise ValueError("only one line of chat is allowed")
        if not self._connected():
            return {"status": "disconnected", "error": "游戏尚未就绪"}
        bot = self._chat_identity()
        if bot is None:
            return {"status": "unsupported", "error": "当前接入点缺少机器人聊天身份"}
        packet = {
            "TextType": int(TextType.TextTypeChat),
            "NeedsTranslation": False,
            "SourceName": "",
            "Message": message,
            "Parameters": [],
            "XUID": bot.xuid,
            "PlatformChatID": bot.platform_chat_id or "",
        }
        try:
            self.game.sendPacket(PacketIDS.Text, packet)
        except Exception as exc:
            return {"status": "unknown", "error": f"{type(exc).__name__}: {exc}"}
        return {"status": "sent", "sender": bot.name}

    def game_command(self, command, channel="ws", wait=True, timeout=5, include_raw=False):
        """Execute one command once. A missing receipt leaves its outcome unknown."""
        if not isinstance(command, str) or not command.strip().strip("/").strip():
            raise ValueError("command must contain a command")
        if any(char in command for char in ("\x00", "\r", "\n")):
            raise ValueError("only one line of command input is allowed")
        if channel not in ("ws", "player", "wo", "ai", "console"):
            raise ValueError("channel must be ws, player, wo, ai or console")
        if not isinstance(wait, bool):
            raise ValueError("wait must be a boolean")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (float, int))
            or not 0 < timeout < math.inf
        ):
            raise ValueError("timeout must be a positive finite number of seconds")
        command = command.strip()
        started = time.monotonic()
        request_id = str(uuid4())

        def result(status, **fields):
            return {
                "status": status,
                "success": None,
                "request_id": request_id,
                "channel": channel,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                **fields,
            }

        if not self._connected():
            return result("disconnected", error="游戏尚未就绪")
        try:
            if channel == "console":
                match = self._console_menu(command)
                if match is None:
                    return result("unsupported", error="此控制台触发词未登记或未获准使用")
                trigger, callback, args = match
                if trigger in ("reload", "deepreload"):
                    if args:
                        raise ValueError("重载命令不接受参数")
                    if not self.reload_lock.acquire(blocking=False):
                        return result("busy", error="插件正在重载")

                    def run_reload():
                        try:
                            callback([])
                        finally:
                            self.reload_lock.release()

                    try:
                        ToolDeltaThread(run_reload, thread_level=ToolDeltaThread.SYSTEM,
                                        usage="MCP 控制台重载插件")
                    except BaseException:
                        self.reload_lock.release()
                        raise
                    return result("dispatched", trigger=trigger)
                callback(args)
                return result("dispatched", trigger=trigger)

            if not command.startswith("/"):
                command = "/" + command
            if channel == "wo":
                self.game.sendwocmd(command)
                return result("sent")
            if channel == "ai" and wait and not callable(
                getattr(self.frame.launcher, "sendaicmd", None)
            ):
                return result("unsupported", error="当前接入点不支持魔法命令回执")
            sender = {
                "player": self.game.sendcmd,
                "ws": self.game.sendwscmd,
                "ai": self.game.sendaicmd,
            }[channel]
            receipt = sender(command, wait, timeout)
            if not wait:
                return result("sent")
            if receipt is None:
                return result("unknown", error="接入点未提供回执，执行结果未知")
            origin = receipt.CommandOrigin
            reply = result(
                "success" if receipt.SuccessCount else "failed",
                success=bool(receipt.SuccessCount),
                success_count=receipt.SuccessCount,
                output_type=receipt.OutputType,
                messages=[
                    {
                        "success": msg.Success,
                        "message": msg.Message,
                        "parameters": msg.Parameters,
                        "translated": _translation(msg.Message, msg.Parameters),
                    }
                    for msg in receipt.OutputMessages
                ],
                data_set=receipt.DataSet,
                origin={
                    "type": origin.Origin,
                    "uuid": _identifier(origin.UUID),
                    "request_id": _identifier(origin.RequestID),
                    "player_unique_id": _identifier(origin.PlayerUniqueID),
                },
            )
            if include_raw:
                reply["raw"] = receipt.as_dict
            return reply
        except TimeoutError:
            return result("timeout", error="等待回执超时，执行结果未知")
        except Exception as exc:
            return result("unknown", error=f"{type(exc).__name__}: {exc}")

    def register_events(self, emit: Callable[[str, dict], None]):
        plugin = self.plugin
        plugin.ListenPlayerPreJoin(
            lambda p: emit("player.pre_join", {"player": p.name})
        )
        plugin.ListenPlayerJoin(lambda p: emit("player.join", {"player": p.name}))
        plugin.ListenPlayerLeave(lambda p: emit("player.leave", {"player": p.name}))
        plugin.ListenSleep(lambda p: emit("player.sleep", {"player": p.name}))
        plugin.ListenDeath(lambda event: emit("player.death", {
            "player": event.player.name, "death_type": event.death_type,
        }))
        plugin.ListenAttack(lambda event: emit("player.kill", {
            "player": event.origin_player.name,
            "target": event.target_player.name,
            "weapon": event.weapon_name,
        }))
        weather = {1: "rain_start", 2: "thunder_start", 3: "rain_end", 4: "thunder_end"}
        plugin.ListenWeather(lambda value: emit("world.weather", {
            "type": weather.get(value, "unknown"), "value": value,
        }))

        def on_text(packet: dict) -> bool:
            text_type = packet.get("TextType")
            message = str(packet.get("Message") or "")
            sender = None
            verified = False
            kind = "game.text"
            parameters = packet.get("Parameters")
            if not isinstance(parameters, list):
                parameters = []
            displayed = message
            if text_type == TextType.TextTypeTranslation:
                displayed = _translation(message, parameters)
            elif text_type == TextType.TextTypeObjectWhisper and isinstance(message, str):
                displayed = _tellraw_text(message)
            if text_type in (
                TextType.TextTypeChat,
                TextType.TextTypeWhisper,
                TextType.TextTypeAnnouncement,
            ):
                try:
                    sender, parsed, verified = get_playername_and_msg_from_text_packet(
                        self.frame, packet
                    )
                    displayed = parsed if parsed is not None else message
                except (IndexError, TypeError, ValueError, KeyError):
                    sender = packet.get("SourceName")
                if verified:
                    kind = "player.chat"
            emit(kind, {
                "text_type": text_type,
                "source_name": packet.get("SourceName"),
                "sender": sender,
                "verified_player": verified,
                "message": message[:TEXT_LIMIT],
                "text": COLOR.sub("", displayed[:TEXT_LIMIT]),
                "truncated": len(message) > TEXT_LIMIT or len(displayed) > TEXT_LIMIT,
                "parameters": [str(p)[:1024] for p in (parameters or [])[:32]],
            })
            return False

        plugin.ListenPacket(PacketIDS.Text, on_text)

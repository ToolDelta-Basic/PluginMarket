import json
import shutil
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

try:
    from websockets.exceptions import ConnectionClosed
    from websockets.sync.client import connect as ws_connect
except Exception:  # pragma: no cover
    ws_connect = None  # type: ignore[assignment]
    ConnectionClosed = Exception  # type: ignore[misc,assignment]

from tooldelta import Chat, Player, Plugin, cfg as Config, plugin_entry, utils
from tooldelta.constants import TOOLDELTA_CLASSIC_PLUGIN_PATH, PacketIDS
from tooldelta.utils import mc_translator


MAX_FILE_SIZE = 4 * 1024 * 1024
VFS_ROOTS = ("config", "storage", "code")

DEFAULT_ITEM_ID_ALIASES: dict[str, str] = {
    "lit_pumpkin": "jack_o_lantern",
    "waterlily": "lily_pad",
    "reeds": "sugar_cane",
    "snow_layer": "snow",
    "stonecutter_block": "stonecutter",
    "zombie_pigman_spawn_egg": "zombified_piglin_spawn_egg",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_rel_path(path: Any) -> str | None:
    if not isinstance(path, str):
        return None
    s = path.replace("\\", "/").strip()
    s = s.lstrip("/")
    parts: list[str] = []
    for part in s.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts)


def _safe_json_load(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for it in value:
        if isinstance(it, str) and it.strip():
            out.append(it.strip())
    return out


def _normalize_bedrock_id_tail(name: Any) -> str:
    if not isinstance(name, str):
        return ""
    s = name.strip()
    if not s:
        return ""
    if ":" in s:
        s = s.split(":")[-1]
    s = s.strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"[^0-9a-z_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _resolve_item_id_alias(name: Any, aliases: dict[str, Any]) -> str:
    normalized = _normalize_bedrock_id_tail(name)
    if not normalized:
        return ""
    custom = aliases.get(normalized)
    if isinstance(custom, str) and custom.strip():
        mapped = _normalize_bedrock_id_tail(custom)
        return mapped or normalized
    default = DEFAULT_ITEM_ID_ALIASES.get(normalized)
    if isinstance(default, str) and default.strip():
        mapped = _normalize_bedrock_id_tail(default)
        return mapped or normalized
    return normalized


def _bedrock_name_to_material(name: Any, aliases: dict[str, Any]) -> str:
    resolved = _resolve_item_id_alias(name, aliases)
    return resolved.upper() if resolved else ""


@dataclass
class PlayerRecord:
    id: str
    firstPlay: int
    lastOnline: int
    playTime: int
    online: bool
    onlineSince: int
    quit: int
    death: int
    playerKill: int
    entityKill: int
    tnt: int
    whitelisted: bool
    ban: str | None

    def to_player_data(self) -> dict[str, Any]:
        return {
            "name": self.id,
            "ban": self.ban,
            "whitelisted": bool(self.whitelisted),
            "playTime": int(self.playTime),
            "lastOnline": int(self.lastOnline),
            "online": bool(self.online),
        }

    def to_player_info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ban": self.ban,
            "whitelisted": bool(self.whitelisted),
            "playTime": int(self.playTime),
            "lastOnline": int(self.lastOnline),
            "hasPlayedBefore": True,
            "firstPlay": int(self.firstPlay),
            "isOP": False,
            "death": int(self.death),
            "quit": int(self.quit),
            "playerKill": int(self.playerKill),
            "entityKill": int(self.entityKill),
            "tnt": int(self.tnt),
        }


class NekoMaidRelayAgent(Plugin):
    name = "NekoMaid中转站Agent"
    author = "Codex"
    version = (0, 1, 0)
    description = "ToolDelta -> neko-relay Agent（用于共用 NekoMaid 前端）"

    def __init__(self, frame):
        super().__init__(frame)

        cfg_default = {
            "中转服务地址": "ws://user.flyshop.chat/ws/agent",
            "对外访问地址": "https://user.flyshop.chat",
            "面板前端地址": "https://user.flyshop.chat",
            "节点ID": "",
            "节点密钥": "",
            "网页Token": "",
            "默认身份": "ws",
            "状态刷新间隔秒": 2,
            "命令超时秒": 3,
            "启用玩家上下线事件": True,
            "启用聊天事件": True,
            "排除机器人": True,
            "物品ID别名": {},
        }
        cfg_std = {
            "中转服务地址": str,
            "对外访问地址": str,
            "节点ID": str,
            "节点密钥": str,
            "网页Token": str,
            "默认身份": str,
            "状态刷新间隔秒": int,
            "命令超时秒": int,
            "启用玩家上下线事件": bool,
            "启用聊天事件": bool,
            "排除机器人": bool,
            Config.KeyGroup("面板前端地址"): str,
            Config.KeyGroup("物品ID别名"): dict,
        }

        self.cfg, _ = Config.get_plugin_config_and_version(
            self.name, cfg_std, cfg_default, self.version
        )

        self.relay_ws_url = self.cfg["中转服务地址"].strip()
        self.public_base_url = self.cfg["对外访问地址"].strip().rstrip("/")
        self.frontend_base_url = str(
            self.cfg.get("面板前端地址", self.public_base_url)
        ).strip().rstrip("/")
        self.node_id = self.cfg["节点ID"].strip()
        self.node_secret = self.cfg["节点密钥"].strip()
        self.web_token = self.cfg["网页Token"].strip()
        self.default_mode: Literal["ws", "bot", "wo"] = (
            self.cfg.get("默认身份", "ws").strip().lower() or "ws"
        )  # type: ignore[assignment]
        self.status_interval = max(1, int(self.cfg.get("状态刷新间隔秒", 2)))
        self.cmd_timeout = max(1, int(self.cfg.get("命令超时秒", 3)))
        self.enable_player_events = bool(self.cfg.get("启用玩家上下线事件", True))
        self.enable_chat_events = bool(self.cfg.get("启用聊天事件", True))
        self.exclude_bot = bool(self.cfg.get("排除机器人", True))
        self.item_id_aliases = (
            self.cfg.get("物品ID别名") if isinstance(self.cfg.get("物品ID别名"), dict) else {}
        )

        self.boot_ms = _now_ms()

        self._conn: Any | None = None
        self._connected = False
        self._stop = False
        self._send_queue: queue.Queue[str] = queue.Queue(maxsize=1000)

        self._tps_calc: Any | None = None
        self._tps_value = -1.0
        self._tps_last_real = time.time()
        self._tps_last_server = 0.0
        self._tps_warned = False
        self._entities_cache_ms = 0
        self._entities_cache_count = 0
        self._entities_cache_sample: list[dict[str, Any]] = []
        self._weather_cache_ms = 0
        self._weather_cache_code = 0
        self._daytime_cache_ms = 0
        self._daytime_cache_value = 0
        self._game_rules: dict[str, Any] = {}

        self._data_lock = threading.RLock()
        self._records: dict[str, PlayerRecord] = {}
        self._load_records()
        self._records_dirty = False
        self._last_records_flush_ms = _now_ms()

        self._vfs_roots = {
            "config": Path.cwd(),
            "storage": Path.cwd() / "插件数据文件",
            "code": Path.cwd() / "插件文件",
        }
        for p in self._vfs_roots.values():
            _ensure_dir(p)

        self._ensure_node_identity()

        self.ListenPreload(self._on_preload)
        self.ListenActive(self._on_active)
        self.ListenFrameExit(self._on_frame_exit)
        self.ListenPacket(PacketIDS.GameRulesChanged, self._on_game_rules_changed)
        self.ListenPacket(PacketIDS.IDSetTime, self._on_set_time)

        if self.enable_player_events:
            self.ListenPlayerJoin(self._on_player_join)
            self.ListenPlayerLeave(self._on_player_leave)
        if self.enable_chat_events:
            self.ListenChat(self._on_chat)

    # ------------------------ 生命周期 ------------------------

    def _on_preload(self):
        try:
            self._tps_calc = self.GetPluginAPI("tps计算器", (0, 0, 1), False)
        except Exception:
            self._tps_calc = None

    def _on_active(self):
        try:
            self.frame.add_console_cmd_trigger(  # type: ignore[attr-defined]
                ["maid", "neko", "relay"],
                None,
                "显示 NekoMaid 中转站链接",
                self._cmd_show_links,
            )
        except Exception:
            pass

        self._start_threads()

    def _on_frame_exit(self, _evt):
        self._stop = True
        self._close_ws()
        self._save_records()

    def _on_game_rules_changed(self, pk: dict[str, Any]) -> bool:
        rules = pk.get("GameRules")
        if not isinstance(rules, list):
            return False
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            name = str(rule.get("Name") or "").strip()
            if not name:
                continue
            self._game_rules[name.lower()] = rule.get("Value")
        return False

    def _on_set_time(self, pkt: dict[str, Any]) -> bool:
        server_time = pkt.get("Time")
        if not isinstance(server_time, int | float):
            return False
        now_real = time.time()
        server_time = float(server_time)
        server_delta = server_time - self._tps_last_server
        real_delta = now_real - self._tps_last_real

        self._tps_last_real = now_real
        self._tps_last_server = server_time
        self._daytime_cache_value = int(server_time) % 24000
        self._daytime_cache_ms = _now_ms()

        if server_delta <= 0 or real_delta <= 0:
            return False
        self._tps_value = min(20.0, server_delta / real_delta)
        self._tps_warned = False
        return False

    # ------------------------ 控制台命令 ------------------------

    def _cmd_show_links(self, _args: list[str]):
        self._print_endpoints(force=True)

    def _print_endpoints(self, force: bool = False):
        if not self.public_base_url:
            if force:
                self.print_war("未配置 对外访问地址，无法生成面板链接")
            return
        if not self.node_id:
            return
        token = self.web_token or "<等待中转站下发>"
        server_url = f"{self.public_base_url}/s/{self.node_id}?token={token}"
        frontend = self.frontend_base_url or self.public_base_url
        panel_url = f"{frontend}/?{quote(server_url, safe='')}#/NekoMaid/dashboard"
        if force:
            self.print_inf(f"对外服务器地址: {server_url}")
            self.print_inf(f"面板打开链接: {panel_url}")
        else:
            self.print_suc(f"已连接中转站，面板链接: {panel_url}")

    # ------------------------ Agent 连接与协议 ------------------------

    def _start_threads(self):
        utils.createThread(
            self._run_ws_loop,
            usage="NekoMaid中转站Agent: ws_loop",
            thread_level=utils.ToolDeltaThread.PLUGIN,
        )
        utils.createThread(
            self._status_loop,
            usage="NekoMaid中转站Agent: status",
            thread_level=utils.ToolDeltaThread.PLUGIN,
        )

    def _run_ws_loop(self):
        if ws_connect is None:
            self.print_err("缺少 websockets 依赖，无法连接中转站（请安装/启用 ToolDelta 运行依赖）")
            return
        if not self.relay_ws_url:
            self.print_err("中转服务地址 为空，无法启动")
            return
        while not self._stop:
            try:
                self.print_inf(f"正在连接中转站: {self.relay_ws_url}")
                with ws_connect(
                    self.relay_ws_url,
                    open_timeout=10,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                    max_size=2 * 1024 * 1024,
                ) as conn:
                    self._conn = conn
                    self._connected = True
                    self._clear_send_queue()
                    self._send_hello_now()
                    while not self._stop:
                        self._drain_send_queue()
                        try:
                            raw = conn.recv(timeout=1)
                        except TimeoutError:
                            continue
                        except ConnectionClosed:
                            break
                        except Exception:
                            break
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="ignore")
                        if isinstance(raw, str):
                            self._handle_relay_msg(raw)
            except Exception as exc:
                self.print_war(f"中转站连接异常: {exc}")
            finally:
                self._connected = False
                self._conn = None
            if not self._stop:
                time.sleep(5)

    def _handle_relay_msg(self, raw: str):
        try:
            msg = json.loads(raw) if isinstance(raw, str) else None
        except Exception:
            return
        if not isinstance(msg, dict):
            return
        msg_type = str(msg.get("type") or "")

        if msg_type == "ping":
            self._send_json({"type": "pong", "ts": int(time.time())})
            return

        if msg_type == "hello_ack":
            if msg.get("ok") is True:
                web_token = str(msg.get("web_token") or "").strip()
                if web_token and web_token != self.web_token:
                    self.web_token = web_token
                    self.cfg["网页Token"] = web_token
                    Config.upgrade_plugin_config(self.name, self.cfg, self.version)
                self._print_endpoints(force=False)
            else:
                self.print_err(f"中转站鉴权失败: {msg.get('error')}")
            return

        if msg_type == "cmd":
            utils.createThread(
                self._handle_cmd,
                args=(msg,),
                usage="NekoMaid中转站Agent: cmd",
                thread_level=utils.ToolDeltaThread.PLUGIN,
            )
            return

        if msg_type == "rpc":
            utils.createThread(
                self._handle_rpc,
                args=(msg,),
                usage="NekoMaid中转站Agent: rpc",
                thread_level=utils.ToolDeltaThread.PLUGIN,
            )
            return

    def _close_ws(self):
        conn = self._conn
        if conn is None:
            return
        try:
            conn.close()
        except Exception:
            pass

    def _send_json(self, obj: dict[str, Any]) -> None:
        if not self._connected:
            return
        data = json.dumps(obj, ensure_ascii=False)
        try:
            self._send_queue.put_nowait(data)
        except queue.Full:
            try:
                _ = self._send_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._send_queue.put_nowait(data)
            except queue.Full:
                return
        except Exception:
            self._connected = False

    def _send_hello_now(self) -> None:
        conn = self._conn
        if conn is None:
            return
        hello = {
            "type": "agent_hello",
            "node_id": self.node_id,
            "agent_secret": self.node_secret,
            "web_token": self.web_token,
            "boot_ms": self.boot_ms,
            "bot": getattr(self.game_ctrl, "bot_name", ""),
        }
        try:
            conn.send(json.dumps(hello, ensure_ascii=False))
        except Exception:
            self._connected = False

    def _clear_send_queue(self) -> None:
        while True:
            try:
                _ = self._send_queue.get_nowait()
            except queue.Empty:
                return

    def _drain_send_queue(self) -> None:
        conn = self._conn
        if conn is None:
            return
        while True:
            try:
                data = self._send_queue.get_nowait()
            except queue.Empty:
                return
            try:
                conn.send(data)
            except Exception:
                self._connected = False
                return

    # ------------------------ cmd / rpc ------------------------

    def _handle_cmd(self, msg: dict[str, Any]) -> None:
        req_id = str(msg.get("req_id") or "").strip()
        cmd = str(msg.get("cmd") or "").strip()
        mode = str(msg.get("mode") or self.default_mode).strip().lower()
        timeout_sec = int(msg.get("timeout_sec") or self.cmd_timeout)
        if not req_id:
            return
        ok, lines = self._run_mc_cmd(cmd, mode, timeout_sec)
        self._send_json({"type": "cmd_result", "req_id": req_id, "ok": ok, "lines": lines})

    def _handle_rpc(self, msg: dict[str, Any]) -> None:
        req_id = str(msg.get("req_id") or "").strip()
        method = str(msg.get("method") or "").strip()
        args = msg.get("args")
        if not isinstance(args, list):
            args = []
        if not req_id:
            return
        try:
            data = self._dispatch_rpc(method, args)
            self._send_json({"type": "rpc_result", "req_id": req_id, "ok": True, "data": data})
        except Exception as exc:
            self._send_json(
                {
                    "type": "rpc_result",
                    "req_id": req_id,
                    "ok": False,
                    "data": None,
                    "error": str(exc),
                }
            )

    def _run_mc_cmd(self, cmd: str, mode: str, timeout_sec: int) -> tuple[bool, list[str]]:
        cmd = cmd.strip()
        if not cmd:
            return False, []
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        timeout = max(1, float(timeout_sec))
        try:
            if mode == "bot":
                out = self.game_ctrl.sendcmd_with_resp(cmd, timeout)
            elif mode == "wo":
                self.game_ctrl.sendwocmd(cmd)
                return True, []
            else:
                out = self.game_ctrl.sendwscmd_with_resp(cmd, timeout)
            lines: list[str] = []
            for m in out.OutputMessages:
                lines.append(mc_translator.translate(m.Message, m.Parameters))
            if not lines:
                lines = [f"(无输出) {cmd}"]
            return bool(out.SuccessCount), lines
        except TimeoutError:
            return False, [f"指令超时: {cmd}"]
        except Exception as exc:
            return False, [f"指令失败: {cmd} ({exc})"]

    # ------------------------ 状态上报与玩家记录 ------------------------

    def _status_loop(self):
        while not self._stop:
            try:
                self._sync_online_players()
                status = self._build_status()
                self._send_json({"type": "status", "data": status})
            except Exception:
                pass
            try:
                self._flush_records_if_needed()
            except Exception:
                pass
            time.sleep(self.status_interval)

    def _run_ws_cmd_raw(self, cmd: str, timeout_sec: float | None = None) -> Any | None:
        cmd = cmd.strip()
        if not cmd:
            return None
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        timeout = float(timeout_sec) if timeout_sec is not None else float(self.cmd_timeout)
        try:
            return self.game_ctrl.sendwscmd_with_resp(cmd, timeout)
        except TimeoutError:
            return None
        except Exception:
            return None

    def _get_tps_mspt(self) -> tuple[float, float]:
        tps = float(self._tps_value) if self._tps_value > 0 else -1.0
        if tps <= 0 and self._tps_calc is not None:
            try:
                tps = float(self._tps_calc.get_tps())
            except Exception:
                tps = -1.0
        mspt = 1000.0 / tps if tps > 0 else -1.0
        return tps, mspt

    def _get_entities_count_cached(self, now_ms: int) -> tuple[int, list[dict[str, Any]]]:
        if self._entities_cache_ms > 0 and now_ms - self._entities_cache_ms < 5000:
            return int(self._entities_cache_count), list(self._entities_cache_sample)
        out = self._run_ws_cmd_raw("testfor @e", timeout_sec=self.cmd_timeout)
        count = 0
        try:
            count = int(getattr(out, "SuccessCount", 0) or 0)
        except Exception:
            count = 0
        self._entities_cache_ms = now_ms
        self._entities_cache_count = max(0, count)
        self._entities_cache_sample = []
        return int(self._entities_cache_count), list(self._entities_cache_sample)

    def _detect_weather_code(self, out: Any | None) -> int:
        if out is None:
            return 0
        try:
            msgs = list(getattr(out, "OutputMessages", []) or [])
        except Exception:
            msgs = []
        for m in msgs:
            key = str(getattr(m, "Message", "") or "")
            if key == "commands.weather.query.clear":
                return 0
            if key == "commands.weather.query.rain":
                return 1
            if key == "commands.weather.query.thunder":
                return 2
            text = ""
            try:
                text = mc_translator.translate(key, getattr(m, "Parameters", []) or [])
            except Exception:
                text = ""
            if "雷阵雨" in text or "雷" in text:
                return 2
            if "不下雨" in text:
                return 0
            if "下雨" in text:
                return 1
        return 0

    def _get_weather_code_cached(self, now_ms: int) -> int:
        if self._weather_cache_ms > 0 and now_ms - self._weather_cache_ms < 5000:
            return int(self._weather_cache_code)
        out = self._run_ws_cmd_raw("weather query", timeout_sec=self.cmd_timeout)
        code = self._detect_weather_code(out)
        self._weather_cache_ms = now_ms
        self._weather_cache_code = int(code)
        return int(code)

    def _get_daytime_cached(self, now_ms: int) -> int:
        if self._daytime_cache_ms > 0 and now_ms - self._daytime_cache_ms < 5000:
            return int(self._daytime_cache_value)
        out = self._run_ws_cmd_raw("time query daytime", timeout_sec=self.cmd_timeout)
        value = 0
        if out is not None:
            try:
                msgs = list(getattr(out, "OutputMessages", []) or [])
            except Exception:
                msgs = []
            for m in msgs:
                key = str(getattr(m, "Message", "") or "")
                params = getattr(m, "Parameters", []) or []
                if key == "commands.time.query.daytime" and params:
                    try:
                        value = int(str(params[0]))
                        break
                    except Exception:
                        pass
                try:
                    text = mc_translator.translate(key, params)
                except Exception:
                    text = ""
                m2 = re.search(r"(\\d+)", text)
                if m2:
                    try:
                        value = int(m2.group(1))
                        break
                    except Exception:
                        pass
        self._daytime_cache_ms = now_ms
        self._daytime_cache_value = int(value)
        return int(value)

    def _build_status(self) -> dict[str, Any]:
        players = [p.name for p in self.frame.players_maintainer.getAllPlayers()]
        if self.exclude_bot:
            bot = getattr(self.game_ctrl, "bot_name", "")
            players = [p for p in players if p and p != bot]
        now_ms = _now_ms()
        tps, mspt = self._get_tps_mspt()
        entities, sample = self._get_entities_count_cached(now_ms)
        return {
            "server_version": "ToolDelta",
            "max_players": 0,
            "spawn_radius": 0,
            "players": players,
            "current_players": len(players),
            "tps": float(tps),
            "mspt": float(mspt),
            "entities": int(entities),
            "entities_sample": sample,
        }

    def _sync_online_players(self):
        now = _now_ms()
        online_names = [p.name for p in self.frame.players_maintainer.getAllPlayers()]
        if self.exclude_bot:
            bot = getattr(self.game_ctrl, "bot_name", "")
            online_names = [p for p in online_names if p and p != bot]
        online_set = set(online_names)

        with self._data_lock:
            for name in online_names:
                rec = self._records.get(name)
                if rec is None:
                    self._records[name] = PlayerRecord(
                        id=name,
                        firstPlay=now,
                        lastOnline=now,
                        playTime=0,
                        online=True,
                        onlineSince=now,
                        quit=0,
                        death=0,
                        playerKill=0,
                        entityKill=0,
                        tnt=0,
                        whitelisted=False,
                        ban=None,
                    )
                    self._records_dirty = True
                    continue
                if not rec.online:
                    rec.online = True
                    rec.onlineSince = now
                rec.lastOnline = now
                if rec.firstPlay <= 0:
                    rec.firstPlay = now

            for name, rec in list(self._records.items()):
                if rec.online and name not in online_set:
                    delta = max(0, now - rec.onlineSince)
                    rec.playTime += int(delta / 1000 * 20)
                    rec.online = False
                    rec.lastOnline = now
                    rec.quit += 1
                    self._records_dirty = True

            for name, rec in self._records.items():
                if rec.ban:
                    self._kick_if_online(name, rec.ban)

    def _kick_if_online(self, name: str, reason: str):
        player = self.frame.players_maintainer.getPlayerByName(name)
        if player is None:
            return
        suffix = f" {reason}" if reason else ""
        try:
            self.game_ctrl.sendwocmd(f"kick {player.safe_name}{suffix}")
        except Exception:
            pass

    def _on_player_join(self, player: Player):
        if self.exclude_bot and player.name == getattr(self.game_ctrl, "bot_name", ""):
            return
        now = _now_ms()
        with self._data_lock:
            rec = self._records.get(player.name)
            if rec is None:
                rec = PlayerRecord(
                    id=player.name,
                    firstPlay=now,
                    lastOnline=now,
                    playTime=0,
                    online=True,
                    onlineSince=now,
                    quit=0,
                    death=0,
                    playerKill=0,
                    entityKill=0,
                    tnt=0,
                    whitelisted=False,
                    ban=None,
                )
                self._records[player.name] = rec
                self._records_dirty = True
            rec.online = True
            rec.onlineSince = now
            rec.lastOnline = now
            if rec.firstPlay <= 0:
                rec.firstPlay = now
                self._records_dirty = True

            if rec.ban:
                self._kick_if_online(player.name, rec.ban)

        self._send_json({"type": "event", "text": f"玩家加入: {player.name}"})
        self._flush_records_if_needed(force=True)

    def _on_player_leave(self, player: Player):
        if self.exclude_bot and player.name == getattr(self.game_ctrl, "bot_name", ""):
            return
        now = _now_ms()
        with self._data_lock:
            rec = self._records.get(player.name)
            if rec is None:
                return
            if rec.online:
                delta = max(0, now - rec.onlineSince)
                rec.playTime += int(delta / 1000 * 20)
            rec.online = False
            rec.lastOnline = now
            rec.quit += 1
            self._records_dirty = True

        self._send_json({"type": "event", "text": f"玩家离开: {player.name}"})
        self._flush_records_if_needed(force=True)

    def _on_chat(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg
        if self.exclude_bot and player == getattr(self.game_ctrl, "bot_name", ""):
            return
        self._send_json({"type": "event", "text": f"[chat] {player}: {msg}"})

    # ------------------------ RPC 路由 ------------------------

    def _dispatch_rpc(self, method: str, args: list[Any]) -> Any:
        match method:
            case "omega:reload":
                return self._rpc_reload()
            case "worlds:fetch":
                return self._rpc_worlds_fetch()
            case "inventory:fetchInv":
                return self._rpc_inventory_fetch(36, args)
            case "inventory:fetchEnderChest":
                return self._rpc_inventory_fetch(27, args)
            case "playerList:fetchPage":
                return self._rpc_player_fetch_page(args)
            case "playerList:query":
                return self._rpc_player_query(args)
            case "playerList:ban":
                return self._rpc_player_ban(args)
            case "playerList:pardon":
                return self._rpc_player_pardon(args)
            case "playerList:addWhitelist":
                return self._rpc_player_whitelist(args, True)
            case "playerList:removeWhitelist":
                return self._rpc_player_whitelist(args, False)
            case "files:fetch":
                return self._rpc_files_fetch(args)
            case "files:content":
                return self._rpc_files_content(args)
            case "files:update":
                return self._rpc_files_update(args)
            case "files:createDirectory":
                return self._rpc_files_create_dir(args)
            case "files:rename":
                return self._rpc_files_rename(args)
            case "files:copy":
                return self._rpc_files_copy(args)
            case "plugins:fetch":
                return self._rpc_plugins_fetch()
            case "plugins:setEnabled":
                return self._rpc_plugins_set_enabled(args)
            case "plugins:setAllEnabled":
                return self._rpc_plugins_set_all_enabled(args)
            case "plugins:enable":
                return self._rpc_plugins_enable(args)
            case "plugins:disableForever":
                return self._rpc_plugins_disable_forever(args)
            case _:
                raise ValueError("unknown_method")

    # ------------------------ RPC: omega/worlds/inv ------------------------

    def _rpc_reload(self) -> bool:
        try:
            utils.createThread(
                self.frame.reload,
                usage="NekoMaid中转站Agent: frame.reload",
                thread_level=utils.ToolDeltaThread.SYSTEM,
            )
            return True
        except Exception:
            return False

    def _rpc_worlds_fetch(self) -> list[dict[str, Any]]:
        status = self._build_status()
        now_ms = _now_ms()
        with self._data_lock:
            rule_map = dict(self._game_rules)

        def to_rule_string(v: Any) -> str:
            if isinstance(v, bool):
                return "true" if v else "false"
            return str(v)

        rules: list[list[str]] = [[k, to_rule_string(v)] for k, v in rule_map.items()]
        rules.sort(key=lambda it: it[0])

        def to_bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            return s in ("1", "true", "yes", "on")

        pvp = to_bool(rule_map.get("pvp"))
        allow_monsters = to_bool(
            rule_map.get("domobspawning")
            if "domobspawning" in rule_map
            else rule_map.get("doMobSpawning".lower())
        )
        weather = self._get_weather_code_cached(now_ms)
        day_time = self._get_daytime_cached(now_ms)
        return [
            {
                "rules": rules,
                "name": "world",
                "id": "world",
                "difficulty": "NORMAL",
                "alias": "",
                "entities": int(status.get("entities") or 0),
                "chunks": 0,
                "tiles": 0,
                "players": int(status.get("current_players") or 0),
                "weather": int(weather),
                "viewDistance": 0,
                "time": int(day_time),
                "seed": 0,
                "allowMonsters": bool(allow_monsters),
                "allowAnimals": bool(allow_monsters),
                "pvp": bool(pvp),
                "allowFlight": False,
                "autoHeal": False,
                "hunger": False,
            }
        ]

    def _rpc_inventory_fetch(self, size: int, args: list[Any]) -> list[Any]:
        target = str(args[0]).strip() if args else ""
        if not target:
            return [None] * size
        bot = getattr(self.game_ctrl, "bot_name", "")
        if self.exclude_bot and bot and target == bot:
            return [None] * size
        if size != 36:
            return [None] * size
        player = self.frame.players_maintainer.getPlayerByName(target)
        if player is None:
            return [None] * size
        try:
            inv_payload = player.queryInventory()
        except Exception:
            return [None] * size

        out: list[Any] = [None] * size
        slots = getattr(inv_payload, "slots", None)
        first = int(getattr(inv_payload, "first", 0) or 0)

        def build(slot_item: Any) -> dict[str, Any] | None:
            if slot_item is None:
                return None
            item_id = getattr(slot_item, "id", None) or getattr(slot_item, "ID", None)
            if not item_id:
                return None
            namespace = getattr(slot_item, "namespace", "") or ""
            raw_name = str(item_id)
            if ":" not in raw_name and namespace:
                raw_name = f"{namespace}:{raw_name}"
            material = _bedrock_name_to_material(raw_name, self.item_id_aliases)
            if not material or material == "AIR":
                return None
            amount = int(getattr(slot_item, "stackSize", 0) or 0)
            if amount <= 0:
                return None
            ench = getattr(slot_item, "enchantments", None)
            has_enchants = bool(ench) and len(ench) > 0  # type: ignore[arg-type]
            return {"type": material, "amount": amount, "hasEnchants": has_enchants}

        if isinstance(slots, list):
            if len(slots) >= size:
                for i in range(size):
                    it = build(slots[i])
                    if it is not None:
                        out[i] = it
            elif slots:
                for i, slot_value in enumerate(slots):
                    slot_index = first + i
                    if 0 <= slot_index < size:
                        it = build(slot_value)
                        if it is not None:
                            out[slot_index] = it
        return out

    # ------------------------ RPC: playerList ------------------------

    def _rpc_player_fetch_page(self, args: list[Any]) -> dict[str, Any]:
        page = int(args[0]) if len(args) >= 1 and str(args[0]).isdigit() else 0
        state = int(args[1]) if len(args) >= 2 and str(args[1]).isdigit() else 0
        filter_kw = str(args[2]).strip().lower() if len(args) >= 3 and args[2] is not None else ""
        per_page = 10
        now = _now_ms()

        with self._data_lock:
            self._sync_online_players()
            records = list(self._records.values())

            if state == 1:
                names = [r.id for r in records if r.whitelisted]
            elif state == 2:
                names = [r.id for r in records if r.ban]
            else:
                names = [r.id for r in records if r.online]

            if filter_kw:
                names = [n for n in names if filter_kw in n.lower()]

            names = sorted(set(names))

            start = max(0, page) * per_page
            slice_names = names[start : start + per_page]
            players = []
            for name in slice_names:
                rec = self._records.get(name)
                if rec is None:
                    continue
                if rec.online:
                    delta = max(0, now - rec.onlineSince)
                    play_time = rec.playTime + int(delta / 1000 * 20)
                else:
                    play_time = rec.playTime
                players.append(
                    {
                        "name": rec.id,
                        "ban": rec.ban,
                        "whitelisted": bool(rec.whitelisted),
                        "playTime": int(play_time),
                        "lastOnline": int(rec.lastOnline),
                        "online": bool(rec.online),
                    }
                )

            return {"count": len(names), "players": players}

    def _rpc_player_query(self, args: list[Any]) -> dict[str, Any]:
        name = str(args[0]).strip() if args else ""
        if not name:
            return PlayerRecord(
                id="",
                firstPlay=0,
                lastOnline=0,
                playTime=0,
                online=False,
                onlineSince=0,
                quit=0,
                death=0,
                playerKill=0,
                entityKill=0,
                tnt=0,
                whitelisted=False,
                ban=None,
            ).to_player_info()

        now = _now_ms()
        with self._data_lock:
            self._sync_online_players()
            rec = self._records.get(name)
            if rec is None:
                return {
                    "id": name,
                    "ban": None,
                    "whitelisted": False,
                    "playTime": 0,
                    "lastOnline": 0,
                    "hasPlayedBefore": False,
                    "firstPlay": 0,
                    "isOP": False,
                    "death": 0,
                    "quit": 0,
                    "playerKill": 0,
                    "entityKill": 0,
                    "tnt": 0,
                }

            is_op = False
            if rec.online:
                p = self.frame.players_maintainer.getPlayerByName(name)
                if p is not None:
                    try:
                        is_op = bool(p.is_op())
                    except Exception:
                        is_op = False

            if rec.online:
                delta = max(0, now - rec.onlineSince)
                play_time = rec.playTime + int(delta / 1000 * 20)
                last_online = now
            else:
                play_time = rec.playTime
                last_online = rec.lastOnline

            has_played_before = bool(rec.firstPlay or rec.lastOnline or rec.playTime)
            return {
                "id": rec.id or name,
                "ban": rec.ban,
                "whitelisted": bool(rec.whitelisted),
                "playTime": int(play_time),
                "lastOnline": int(last_online),
                "hasPlayedBefore": has_played_before,
                "firstPlay": int(rec.firstPlay or 0),
                "isOP": is_op,
                "death": int(rec.death),
                "quit": int(rec.quit),
                "playerKill": int(rec.playerKill),
                "entityKill": int(rec.entityKill),
                "tnt": int(rec.tnt),
            }

    def _rpc_player_ban(self, args: list[Any]) -> bool:
        name = str(args[0]).strip() if args else ""
        reason = str(args[1]).strip() if len(args) >= 2 else ""
        if not name:
            return False
        with self._data_lock:
            rec = self._records.get(name)
            if rec is None:
                rec = PlayerRecord(
                    id=name,
                    firstPlay=0,
                    lastOnline=_now_ms(),
                    playTime=0,
                    online=False,
                    onlineSince=0,
                    quit=0,
                    death=0,
                    playerKill=0,
                    entityKill=0,
                    tnt=0,
                    whitelisted=False,
                    ban=reason or "banned",
                )
                self._records[name] = rec
            rec.ban = reason or "banned"
        self._kick_if_online(name, reason)
        self._save_records()
        return True

    def _rpc_player_pardon(self, args: list[Any]) -> bool:
        name = str(args[0]).strip() if args else ""
        if not name:
            return False
        with self._data_lock:
            rec = self._records.get(name)
            if rec is None:
                return True
            rec.ban = None
        self._save_records()
        return True

    def _rpc_player_whitelist(self, args: list[Any], enabled: bool) -> bool:
        name = str(args[0]).strip() if args else ""
        if not name:
            return False
        with self._data_lock:
            rec = self._records.get(name)
            if rec is None:
                now = _now_ms()
                rec = PlayerRecord(
                    id=name,
                    firstPlay=now,
                    lastOnline=now,
                    playTime=0,
                    online=False,
                    onlineSince=0,
                    quit=0,
                    death=0,
                    playerKill=0,
                    entityKill=0,
                    tnt=0,
                    whitelisted=enabled,
                    ban=None,
                )
                self._records[name] = rec
            rec.whitelisted = enabled
        self._save_records()
        return True

    # ------------------------ RPC: files (VFS) ------------------------

    def _vfs_abs(self, rel_path: str) -> tuple[Path | None, str | None]:
        cleaned = _normalize_rel_path(rel_path)
        if cleaned is None:
            return None, None
        if cleaned == "":
            return None, None
        root = cleaned.split("/", 1)[0]
        if root not in VFS_ROOTS:
            return None, None
        sub = cleaned[len(root) + 1 :] if cleaned != root else ""
        base = self._vfs_roots[root]
        return (base / sub) if sub else base, root

    def _allow_file(self, root: str, rel_path: str) -> bool:
        rel_lower = rel_path.lower()
        if root == "config":
            return rel_lower.endswith(".json")
        if root == "code":
            return rel_lower.endswith((".py", ".md", ".txt", ".json"))
        if root == "storage":
            return rel_lower.endswith((".json", ".txt", ".log"))
        return False

    def _rpc_files_fetch(self, args: list[Any]) -> list[list[str]]:
        path = str(args[0]) if args else ""
        cleaned = _normalize_rel_path(path) or ""
        if cleaned == "":
            return [list(VFS_ROOTS), []]
        abs_path, root = self._vfs_abs(cleaned)
        if abs_path is None or root is None:
            return [[], []]
        if not abs_path.exists() or not abs_path.is_dir():
            return [[], []]
        dirs: list[str] = []
        files: list[str] = []
        for entry in abs_path.iterdir():
            if entry.is_dir():
                dirs.append(entry.name)
            elif self._allow_file(root, entry.name):
                files.append(entry.name)
        return [dirs, files]

    def _rpc_files_content(self, args: list[Any]) -> int | str | None:
        path = str(args[0]) if args else ""
        cleaned = _normalize_rel_path(path)
        if cleaned is None or cleaned == "":
            return 0
        abs_path, root = self._vfs_abs(cleaned)
        if abs_path is None or root is None:
            return 0
        if not self._allow_file(root, cleaned):
            return None
        if not abs_path.exists():
            return 1
        if abs_path.is_dir():
            return 2
        try:
            if abs_path.stat().st_size > MAX_FILE_SIZE:
                return 3
            return abs_path.read_text(encoding="utf-8")
        except Exception:
            return 0

    def _rpc_files_update(self, args: list[Any]) -> bool:
        if len(args) < 2:
            return False
        path = str(args[0])
        content = args[1]
        cleaned = _normalize_rel_path(path)
        if cleaned is None or cleaned == "":
            return False
        abs_path, root = self._vfs_abs(cleaned)
        if abs_path is None or root is None:
            return False
        if not self._allow_file(root, cleaned):
            return False
        if not isinstance(content, str):
            content = str(content)
        try:
            _ensure_dir(abs_path.parent)
            abs_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def _rpc_files_create_dir(self, args: list[Any]) -> bool:
        path = str(args[0]) if args else ""
        cleaned = _normalize_rel_path(path)
        if cleaned is None or cleaned == "":
            return False
        abs_path, root = self._vfs_abs(cleaned)
        if abs_path is None or root is None:
            return False
        if root == "config":
            return False
        try:
            _ensure_dir(abs_path)
            return True
        except Exception:
            return False

    def _rpc_files_rename(self, args: list[Any]) -> bool:
        if len(args) < 2:
            return False
        src = _normalize_rel_path(str(args[0]))
        dst = _normalize_rel_path(str(args[1]))
        if src is None or dst is None or src == "" or dst == "":
            return False
        src_abs, src_root = self._vfs_abs(src)
        dst_abs, dst_root = self._vfs_abs(dst)
        if src_abs is None or dst_abs is None or src_root is None or dst_root is None:
            return False
        if src_root != dst_root or src_root != "storage":
            return False
        try:
            if not src_abs.exists():
                return False
            if dst_abs.exists():
                return False
            _ensure_dir(dst_abs.parent)
            src_abs.rename(dst_abs)
            return True
        except Exception:
            return False

    def _rpc_files_copy(self, args: list[Any]) -> bool:
        if len(args) < 2:
            return False
        src = _normalize_rel_path(str(args[0]))
        dst = _normalize_rel_path(str(args[1]))
        if src is None or dst is None or src == "" or dst == "":
            return False
        src_abs, src_root = self._vfs_abs(src)
        dst_abs, dst_root = self._vfs_abs(dst)
        if src_abs is None or dst_abs is None or src_root is None or dst_root is None:
            return False
        if src_root != dst_root or src_root != "storage":
            return False
        try:
            if not src_abs.exists() or src_abs.is_dir():
                return False
            if dst_abs.exists():
                return False
            _ensure_dir(dst_abs.parent)
            shutil.copyfile(src_abs, dst_abs)
            return True
        except Exception:
            return False

    # ------------------------ RPC: plugins ------------------------

    def _rpc_plugins_fetch(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for plugin_dir in TOOLDELTA_CLASSIC_PLUGIN_PATH.iterdir():
            if not plugin_dir.is_dir():
                continue
            enabled = not plugin_dir.name.endswith("+disabled")
            base_name = plugin_dir.name.replace("+disabled", "")

            datas = _safe_json_load(plugin_dir / "datas.json") or {}
            version = str(datas.get("version") or "0.0.0")
            author = str(datas.get("author") or "unknown")
            description = str(datas.get("description") or "")
            pre_plugins = datas.get("pre-plugins") or {}
            depends = list(pre_plugins.keys()) if isinstance(pre_plugins, dict) else []

            if base_name == self.name:
                file = f"插件配置文件/{self.name}.json"
            else:
                file = f"{plugin_dir.as_posix()}/datas.json"

            items.append(
                {
                    "name": base_name,
                    "file": file,
                    "entry": str(plugin_dir.as_posix()),
                    "author": author,
                    "description": description,
                    "version": version,
                    "enabled": enabled,
                    "loaded": enabled,
                    "depends": _str_list(depends),
                    "softDepends": [],
                }
            )
        return items

    def _is_agent_plugin(self, plugin_base_name: str) -> bool:
        return plugin_base_name == self.name

    def _rpc_plugins_set_enabled(self, args: list[Any]) -> bool:
        if len(args) < 2:
            return False
        file = str(args[0] or "").strip().lstrip("/")
        enabled = bool(args[1])

        if file.endswith(f"插件配置文件/{self.name}.json") and enabled is False:
            return False

        if "插件文件/ToolDelta类式插件/" not in file:
            return False
        if not file.endswith("/datas.json") and not file.endswith("\\datas.json"):
            return False

        plugin_dir = Path(file).parent
        if plugin_dir.name.replace("+disabled", "") == self.name and enabled is False:
            return False

        try:
            if enabled:
                if plugin_dir.name.endswith("+disabled"):
                    plugin_dir.rename(Path(str(plugin_dir).removesuffix("+disabled")))
                return True
            if not plugin_dir.name.endswith("+disabled"):
                plugin_dir.rename(Path(str(plugin_dir) + "+disabled"))
            return True
        except Exception:
            return False

    def _rpc_plugins_set_all_enabled(self, args: list[Any]) -> bool:
        if not args:
            return False
        enabled = bool(args[0])
        try:
            for plugin_dir in TOOLDELTA_CLASSIC_PLUGIN_PATH.iterdir():
                if not plugin_dir.is_dir():
                    continue
                base = plugin_dir.name.replace("+disabled", "")
                if not enabled and self._is_agent_plugin(base):
                    continue
                if enabled:
                    if plugin_dir.name.endswith("+disabled"):
                        plugin_dir.rename(Path(str(plugin_dir).removesuffix("+disabled")))
                else:
                    if not plugin_dir.name.endswith("+disabled"):
                        plugin_dir.rename(Path(str(plugin_dir) + "+disabled"))
            return True
        except Exception:
            return False

    def _rpc_plugins_enable(self, args: list[Any]) -> bool:
        if not args:
            return False
        return self._rpc_plugins_set_enabled([args[0], True])

    def _rpc_plugins_disable_forever(self, args: list[Any]) -> bool:
        if not args:
            return False
        return self._rpc_plugins_set_enabled([args[0], False])

    # ------------------------ 持久化 ------------------------

    def _ensure_node_identity(self):
        changed = False
        if not self.node_id:
            self.node_id = str(uuid.uuid4())
            self.cfg["节点ID"] = self.node_id
            changed = True
        if not self.node_secret:
            self.node_secret = str(uuid.uuid4())
            self.cfg["节点密钥"] = self.node_secret
            changed = True
        if changed:
            Config.upgrade_plugin_config(self.name, self.cfg, self.version)

    def _load_records(self):
        try:
            data = utils.read_from_plugin(self.name, "players", default={})
        except Exception:
            data = {}
        if not isinstance(data, dict):
            return
        for name, raw in data.items():
            if not isinstance(name, str) or not isinstance(raw, dict):
                continue
            self._records[name] = PlayerRecord(
                id=str(raw.get("id") or name),
                firstPlay=int(raw.get("firstPlay") or 0),
                lastOnline=int(raw.get("lastOnline") or 0),
                playTime=int(raw.get("playTime") or 0),
                online=bool(raw.get("online") or False),
                onlineSince=int(raw.get("onlineSince") or 0),
                quit=int(raw.get("quit") or 0),
                death=int(raw.get("death") or 0),
                playerKill=int(raw.get("playerKill") or 0),
                entityKill=int(raw.get("entityKill") or 0),
                tnt=int(raw.get("tnt") or 0),
                whitelisted=bool(raw.get("whitelisted") or False),
                ban=(str(raw.get("ban")) if raw.get("ban") is not None else None),
            )

    def _flush_records_if_needed(self, force: bool = False) -> None:
        now = _now_ms()
        with self._data_lock:
            if not force:
                if not self._records_dirty:
                    return
                if now - self._last_records_flush_ms < 30_000:
                    return
        self._save_records()

    def _save_records(self):
        with self._data_lock:
            data = {
                name: {
                    "id": rec.id,
                    "firstPlay": rec.firstPlay,
                    "lastOnline": rec.lastOnline,
                    "playTime": rec.playTime,
                    "online": rec.online,
                    "onlineSince": rec.onlineSince,
                    "quit": rec.quit,
                    "death": rec.death,
                    "playerKill": rec.playerKill,
                    "entityKill": rec.entityKill,
                    "tnt": rec.tnt,
                    "whitelisted": rec.whitelisted,
                    "ban": rec.ban,
                }
                for name, rec in self._records.items()
            }
        try:
            utils.write_to_plugin(self.name, "players", data, indent=2)
        except Exception:
            pass
        else:
            with self._data_lock:
                self._records_dirty = False
                self._last_records_flush_ms = _now_ms()


entry = plugin_entry(NekoMaidRelayAgent)

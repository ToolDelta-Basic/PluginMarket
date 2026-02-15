from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, List, Optional, Set, Tuple

from tooldelta import Plugin, Print, ToolDelta, cfg, plugin_entry


@dataclass
class _ReportCase:
    reporter: str
    target: str
    created_ts: float


class KillAuraReport(Plugin):
    name = "杀戮光环举报"
    author = "丸山彩"
    version = (0, 0, 1)

    _PKT_LEVEL_SOUND_EVENT = 123

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)

        default_cfg = {
            "提示词": "r",
            "检测半径米": 3.0,
            "受击阈值每秒": 4,
            "持续秒": 3.0,
            "传送刷新间隔秒": 0.2,
            "是否封禁": True,
            "封禁理由": "作弊",
            "封禁时长秒": 3600,
            "每页显示人数": 15,
            "每次最长检测秒": 30.0,
        }
        std_cfg = {
            "提示词": str,
            "检测半径米": float,
            "受击阈值每秒": int,
            "持续秒": float,
            "传送刷新间隔秒": float,
            "是否封禁": bool,
            "封禁理由": str,
            "封禁时长秒": int,
            "每页显示人数": int,
            "每次最长检测秒": float,
        }
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, std_cfg, default_cfg, self.version
        )

        self.funclib = None
        self.ban_api = None

        self._q: Deque[_ReportCase] = deque()
        self._q_event = threading.Event()
        self._q_lock = threading.Lock()
        self._queued_targets: Set[str] = set()

        self._case_lock = threading.Lock()
        self._current: Optional[_ReportCase] = None
        self._bot_pos: Optional[Tuple[float, float, float]] = None
        self._hit_times: Deque[float] = deque()
        self._over_since: Optional[float] = None

        self._worker_started = False

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenChat(self.on_chat)
        self.ListenPacket(self._PKT_LEVEL_SOUND_EVENT, self.on_pkt_sound)

    def on_preload(self):
        self.funclib = self.GetPluginAPI("基本插件功能库")
        try:
            self.ban_api = self.GetPluginAPI("封禁系统", force=False)
        except Exception:
            self.ban_api = None

    def on_active(self):
        if not self._worker_started:
            self._worker_started = True
            t = threading.Thread(target=self._worker_loop, name="KillAuraReportWorker")
            t.daemon = True
            t.start()

    def on_chat(self, chat):
        msg = getattr(chat, "msg", "")
        player = getattr(chat, "player", None)
        if player is None:
            return False

        pname = getattr(player, "name", "")
        if not isinstance(msg, str) or not isinstance(pname, str) or not pname:
            return False

        trig = str(self.config.get("提示词", "r")).strip() or "r"
        msg_strip = msg.strip()

        if msg_strip == trig:
            self._start_pick_flow(pname)
            return False

        prefix = trig + " "
        if msg_strip.startswith(prefix):
            target = msg_strip[len(prefix) :].strip()
            if target:
                self._enqueue_report(pname, target)
            return False

        return False

    def _start_pick_flow(self, reporter: str):
        th = threading.Thread(
            target=self._pick_flow_thread,
            args=(reporter,),
            name=f"KillAuraPick:{reporter}",
            daemon=True,
        )
        th.start()

    def _pick_flow_thread(self, reporter: str):
        try:
            from tooldelta import game_utils
        except Exception:
            self._tell(reporter, "§c缺少 game_utils，无法进行交互输入。")
            return

        maxn = int(self.config.get("每页显示人数", 15))
        maxn = max(1, min(maxn, 50))

        page = 0

        while True:
            players = self._get_online_player_names()
            players = [p for p in players if p != reporter]

            if not players:
                self._tell(reporter, "§e当前没有可举报的在线玩家。")
                return

            total_pages = (len(players) + maxn - 1) // maxn
            if total_pages <= 0:
                total_pages = 1

            if page < 0:
                page = 0
            if page > (total_pages - 1):
                page = total_pages - 1

            start = page * maxn
            end = min(start + maxn, len(players))
            shown = players[start:end]

            lines = [
                f"§e请输入序号举报玩家（第 §b{page + 1}§e/§b{total_pages}§e 页）",
                "§7输入 §f+§7 下一页，§f-§7 上一页，§f.§7 退出选择",
            ]
            for i, n in enumerate(shown, start=1):
                lines.append(f"§f{i}. §b{n}")

            if len(players) > end:
                lines.append(f"§7（后面还有 {len(players) - end} 人）")
            if start > 0:
                lines.append(f"§7（前面还有 {start} 人）")

            self._tell(reporter, "\n".join(lines))

            resp = game_utils.waitMsg(reporter)
            if not isinstance(resp, str):
                return
            resp = resp.strip()

            if resp in (".", "q", "Q"):
                self._tell(reporter, "§7已退出选择。")
                return

            if resp == "+":
                if page < total_pages - 1:
                    page += 1
                else:
                    self._tell(reporter, "§7已经是最后一页。")
                continue

            if resp == "-":
                if page > 0:
                    page -= 1
                else:
                    self._tell(reporter, "§7已经是第一页。")
                continue

            if not resp.isdigit():
                self._tell(reporter, "§c输入无效：请发送序号 / + / - / .")
                continue

            idx = int(resp)
            if idx < 1 or idx > len(shown):
                self._tell(reporter, "§c序号超出范围，请重新输入。")
                continue

            target = shown[idx - 1]
            self._enqueue_report(reporter, target)
            return

    def _enqueue_report(self, reporter: str, target: str):
        if target not in self._get_online_player_names():
            self._tell(reporter, f"§c玩家 §f{target}§c 不在线或名字不匹配。")
            return

        with self._q_lock:
            if target in self._queued_targets:
                self._tell(reporter, f"§e已在检测队列中：§f{target}")
                return

            case = _ReportCase(reporter=reporter, target=target, created_ts=time.time())
            self._q.append(case)
            self._queued_targets.add(target)
            qpos = len(self._q)

        if qpos == 1:
            self._tell(reporter, f"§a已举报：§f{target}§a")
        else:
            self._tell(reporter, f"§a已举报：§f{target}§a，当前排队第 §e{qpos}§a 位")

        self._q_event.set()

    def _worker_loop(self):
        while True:
            self._q_event.wait()
            while True:
                with self._q_lock:
                    if not self._q:
                        self._q_event.clear()
                        break
                    case = self._q.popleft()

                try:
                    self._run_case(case)
                finally:
                    with self._q_lock:
                        self._queued_targets.discard(case.target)

    def _run_case(self, case: _ReportCase):
        target = case.target

        if target not in self._get_online_player_names():
            self._tell(case.reporter, f"§7玩家 §f{target}§7 已离线，取消检测。")
            return

        with self._case_lock:
            self._current = case
            self._bot_pos = None
            self._hit_times.clear()
            self._over_since = None

        try:
            try:
                self.funclib.sendaicmd("/gamerule sendcommandfeedback false")
            except Exception:
                pass

            radius = float(self.config.get("检测半径米", 3.0))
            radius = max(0.5, min(radius, 16.0))

            per_sec = int(self.config.get("受击阈值每秒", 4))
            per_sec = max(1, min(per_sec, 30))

            sustain = float(self.config.get("持续秒", 3.0))
            sustain = max(0.5, min(sustain, 30.0))

            interval = float(self.config.get("传送刷新间隔秒", 0.2))
            interval = max(0.05, min(interval, 2.0))

            max_round = float(self.config.get("每次最长检测秒", 30.0))
            max_round = max(1.0, min(max_round, 300.0))

            self._tell(case.reporter, f"§e开始检测：§f{target}")

            start_ts = time.time()
            while True:
                if target not in self._get_online_player_names():
                    self._tell(case.reporter, f"§7玩家 §f{target}§7 已离线，结束检测。")
                    break

                tp_cmd = (
                    f'/execute at @a[name="{target}"] rotated as @a[name="{target}"] '
                    f"positioned ^ ^ ^-0.5 run tp ~ ~ ~"
                )

                tp_ok = False
                try:
                    tp_resp = self.game_ctrl.sendwscmd_with_resp(tp_cmd, 2)
                    tp_ok = self._ws_has_receipt(tp_resp, allow_empty=True)
                except Exception:
                    tp_ok = False

                if tp_ok:
                    self._refresh_bot_pos()

                if self._should_punish(per_sec=per_sec, sustain=sustain):
                    self._punish(target, reporter=case.reporter)
                    break

                if time.time() - start_ts > max_round:
                    self._tell(
                        case.reporter,
                        f"§7{int(max_round)} 秒内未检测到异常：§f{target}",
                    )
                    break

                time.sleep(interval)

        finally:
            with self._case_lock:
                self._current = None
                self._bot_pos = None
                self._hit_times.clear()
                self._over_since = None

            try:
                self.game_ctrl.sendwscmd_with_resp(
                    "/gamerule sendcommandfeedback true", 2
                )
            except Exception:
                pass

    def _refresh_bot_pos(self):
        pos = self._querytarget_self_pos()
        if pos is None:
            return
        with self._case_lock:
            self._bot_pos = pos

    def _should_punish(self, *, per_sec: int, sustain: float) -> bool:
        with self._case_lock:
            if self._current is None:
                return False

            now = time.time()
            while self._hit_times and self._hit_times[0] < (now - 1.0):
                self._hit_times.popleft()

            hits = len(self._hit_times)
            if hits > per_sec:
                if self._over_since is None:
                    self._over_since = now
                if (now - self._over_since) >= sustain:
                    return True
            else:
                self._over_since = None

        return False

    def _punish(self, target: str, reporter: str):
        self._tell(reporter, f"§c判定异常：§f{target}§c")

        try:
            self.game_ctrl.sendwscmd_with_resp(f'/kick @a[name="{target}"]', 2)
        except Exception:
            pass

        if bool(self.config.get("是否封禁", True)) and self.ban_api is not None:
            reason = str(self.config.get("封禁理由", "作弊"))
            seconds = int(self.config.get("封禁时长秒", 3600))
            seconds = max(1, min(seconds, 7 * 24 * 3600))
            try:
                self.ban_api.ban(target, seconds, reason)
            except Exception as e:
                Print.print_war(f"[{self.name}] 调用封禁系统失败：{e}")

    def on_pkt_sound(self, pkt: dict):
        try:
            sound_type = int(pkt.get("SoundType", -1))
        except Exception:
            return False

        if sound_type != 43:
            return False

        pos = pkt.get("Position")
        if (
            not isinstance(pos, list)
            or len(pos) < 3
            or not isinstance(pos[0], (int, float))
        ):
            return False

        sx = float(pos[0])
        sy = float(pos[1]) + 0.72
        sz = float(pos[2])

        radius = float(self.config.get("检测半径米", 3.0))
        radius = max(0.5, min(radius, 16.0))
        radius2 = radius * radius

        with self._case_lock:
            if self._current is None or self._bot_pos is None:
                return False
            bx, by, bz = self._bot_pos

        dx = bx - sx
        dy = by - sy
        dz = bz - sz
        if (dx * dx + dy * dy + dz * dz) <= radius2:
            with self._case_lock:
                if self._current is not None:
                    self._hit_times.append(time.time())

        return False

    def _get_online_player_names(self) -> List[str]:
        names: List[str] = []
        try:
            for p in list(self.game_ctrl.players):
                n = getattr(p, "name", None)
                if isinstance(n, str) and n:
                    names.append(n)
        except Exception:
            return []
        return names

    def _tell(self, player_name: str, text: str):
        try:
            raw = {"rawtext": [{"text": text}]}
            raw_s = json.dumps(raw, ensure_ascii=False)
            cmd = f'/tellraw @a[name="{player_name}"] {raw_s}'
            self.funclib.sendaicmd(cmd)
        except Exception:
            pass

    @staticmethod
    def _ws_has_receipt(resp: Any, *, allow_empty: bool = False) -> bool:
        """回执处理"""
        if isinstance(resp, list):
            if not resp:
                return bool(allow_empty)
            first = resp[0]
            if isinstance(first, dict):
                return bool(first.get("Success", False))
            return bool(allow_empty)

        try:
            out = getattr(resp, "OutputMessages", None)
            if out:
                return bool(out[0].Success)
        except Exception:
            return bool(allow_empty)

        return bool(allow_empty)

    @staticmethod
    def _ws_is_success(resp: Any) -> bool:
        return KillAuraReport._ws_has_receipt(resp, allow_empty=False)

    def _ws_get_first_parameter(self, resp: Any) -> Optional[Any]:
        try:
            out = getattr(resp, "OutputMessages", None)
            if out and out[0].Success:
                params = out[0].Parameters
                if isinstance(params, list) and params:
                    return params[0]
        except Exception:
            pass

        if not isinstance(resp, list) or not resp:
            return None
        first = resp[0]
        if not isinstance(first, dict):
            return None
        params = first.get("Parameters")
        if isinstance(params, list) and params:
            return params[0]
        return None

    def _parse_querytarget_parameter(self, parameter: Any) -> Optional[List[dict]]:
        try:
            if isinstance(parameter, str):
                obj = json.loads(parameter)
            else:
                obj = parameter
            return obj if isinstance(obj, list) else None
        except Exception:
            return None

    def _querytarget_self_pos(self) -> Optional[Tuple[float, float, float]]:
        try:
            resp = self.game_ctrl.sendwscmd_with_resp("/querytarget @s", 2)
            parameter = self._ws_get_first_parameter(resp)
            result_list = self._parse_querytarget_parameter(parameter)
            if not result_list:
                return None

            one = result_list[0]
            if not isinstance(one, dict):
                return None

            pos = one.get("position")
            if not isinstance(pos, dict):
                return None

            x = pos.get("x")
            y = pos.get("y")
            z = pos.get("z")
            if not all(isinstance(v, (int, float)) for v in (x, y, z)):
                return None

            return (float(x), float(y), float(z))
        except Exception:
            return None


entry = plugin_entry(KillAuraReport)

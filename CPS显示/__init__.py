from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Optional, List, Tuple

from tooldelta import Plugin, plugin_entry, ToolDelta, Print, cfg, game_utils, utils

try:
    from tooldelta.constants import PacketIDS
except ImportError:
    from tooldelta.constants import PacketIDs as PacketIDS


@dataclass
class _Subscription:
    """CPS 阈值订阅项"""

    sub_id: int
    threshold: float
    cooldown: float
    handler: Callable[[str, float], None]
    last_fire_by_player: Dict[str, float]


class SwingCPSAPI(Plugin):
    """CPS 显示插件，对外提供接口"""

    name = "CPS显示"
    author = "丸山彩"
    version = (0, 0, 2)

    _MODE1_DEDUP_EPS = 0.051

    _MODE1_IGNORE_MIN = 0.0
    _MODE1_IGNORE_MAX = 0.051

    _MODE2_FIRST_DIST_IF_MOB = 1.0
    _MODE2_FIRST_SECOND_PLAYER_DIST_MAX = 10.0

    def __init__(self, frame: ToolDelta):
        """初始化插件状态与监听"""
        super().__init__(frame)

        default_cfg = {
            "模式": 1,
            "检测周期秒": 1.0,
            "是否显示": True,
            "显示间隔秒": 1.0,
            "前置空格": "               ",
            "颜色前缀": "§e",
        }
        std_cfg = {
            "模式": int,
            "检测周期秒": float,
            "是否显示": bool,
            "显示间隔秒": float,
            "前置空格": str,
            "颜色前缀": str,
        }
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, std_cfg, default_cfg, self.version
        )

        self.funclib = None

        self.rt_to_name: Dict[int, str] = {}

        self._swing_times: Dict[str, Deque[float]] = {}
        self._last_cps: Dict[str, float] = {}
        self._last_title_ts: Dict[str, float] = {}

        self._last_players_scan_ts: float = 0.0

        self._next_sub_id = 1
        self._subs: Dict[int, _Subscription] = {}

        self._pending_actions: Dict[str, Deque[float]] = {}
        self._last_sound42_ts: Dict[str, float] = {}

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerLeave(self.on_player_leave)

    def on_preload(self):
        """获取前置库 API，并注册包监听"""
        self.funclib = self.GetPluginAPI("基本插件功能库")

        for attr in ("AddPlayer", "PlayerList"):
            pid = getattr(PacketIDS, attr, None)
            if pid is not None:
                self.ListenPacket(int(pid), self._make_mapping_cb(attr))

        self.ListenPacket(int(PacketIDS.LevelSoundEvent), self.on_pkt_sound)

        animate_pid = getattr(PacketIDS, "Animate", 44)
        self.ListenPacket(int(animate_pid), self.on_pkt_animate_action)

        self._clamp_config()

    def on_active(self):
        """检查前置插件与重载后在线玩家映射补齐"""
        if self.funclib is None:
            self.funclib = self.GetPluginAPI("基本插件功能库")

        if self.funclib is None:
            raise RuntimeError("缺少前置插件《基本插件功能库》")

        self._refresh_mapping_from_online_players(force=True)

    def on_player_leave(self, player):
        """玩家离线时清理统计缓存"""
        try:
            name = player.name
        except Exception:
            return

        self._swing_times.pop(name, None)
        self._last_cps.pop(name, None)
        self._last_title_ts.pop(name, None)

        self._pending_actions.pop(name, None)
        self._last_sound42_ts.pop(name, None)

        for sub in self._subs.values():
            sub.last_fire_by_player.pop(name, None)

    def get_cps(self, player_name: str) -> float:
        """获取指定玩家最近一次计算到的"""
        return float(self._last_cps.get(player_name, 0.0))

    def get_all_cps(self) -> Dict[str, float]:
        """获取所有玩家 CPS 快照"""
        return dict(self._last_cps)

    def subscribe(
        self,
        threshold: float,
        handler: Callable[[str, float], None],
        cooldown: float = 1.0,
    ) -> int:
        """订阅：当CPS达到阈值触发 handler(player_name, cps)"""
        if threshold <= 0:
            threshold = 0.1

        cooldown = max(cooldown, 0.0)

        sub_id = self._next_sub_id
        self._next_sub_id += 1

        self._subs[sub_id] = _Subscription(
            sub_id=sub_id,
            threshold=float(threshold),
            cooldown=float(cooldown),
            handler=handler,
            last_fire_by_player={},
        )
        return sub_id

    def unsubscribe(self, sub_id: int) -> bool:
        """取消订阅"""
        return self._subs.pop(int(sub_id), None) is not None

    def _make_mapping_cb(self, pkt_name: str):
        """生成用于更新映射的包回调函数"""

        def _cb(pkt):
            """监听包时更新映射"""
            try:
                self._update_mapping(pkt_name, pkt)
            except Exception:
                pass
            return False

        return _cb

    @staticmethod
    def _get_int(d, keys):
        """从 dict 中按 keys 顺序取第一个 int 值"""
        if not isinstance(d, dict):
            return None
        for k in keys:
            v = d.get(k)
            if isinstance(v, int):
                return v
        return None

    @staticmethod
    def _get_str(d, keys):
        """从 dict 中按 keys 顺序取第一个非空 str 值"""
        if not isinstance(d, dict):
            return None
        for k in keys:
            v = d.get(k)
            if isinstance(v, str) and v:
                return v
        return None

    def _update_mapping(self, pkt_name: str, pkt):
        """根据 AddPlayer/PlayerList 包更新 runtimeId->name 映射。"""
        if not isinstance(pkt, dict):
            return
        pn = pkt_name.lower()

        if pn == "addplayer":
            rt = self._get_int(
                pkt,
                ["EntityRuntimeID", "entityRuntimeId", "RuntimeID", "runtimeId"],
            )
            name = self._get_str(
                pkt,
                ["Username", "username", "PlayerName", "playername", "Name", "name"],
            )
            if rt is not None and name:
                self.rt_to_name[rt] = name
            return

        if pn == "playerlist":
            for key in (
                "Records",
                "records",
                "Entries",
                "entries",
                "players",
                "Players",
            ):
                arr = pkt.get(key)
                if isinstance(arr, list):
                    for it in arr:
                        if not isinstance(it, dict):
                            continue
                        rt = self._get_int(
                            it,
                            [
                                "EntityRuntimeID",
                                "entityRuntimeId",
                                "RuntimeID",
                                "runtimeId",
                            ],
                        )
                        name = self._get_str(
                            it,
                            [
                                "Username",
                                "username",
                                "PlayerName",
                                "playername",
                                "Name",
                                "name",
                            ],
                        )
                        if rt is not None and name:
                            self.rt_to_name[rt] = name
                    return

    def on_pkt_animate_action(self, pkt: dict):
        """模式1：挥手动作"""
        try:
            if int(self.config.get("模式", 1)) != 1:
                return False

            if not isinstance(pkt, dict):
                return False

            if pkt.get("ActionType", None) != 1:
                return False

            rt = self._get_int(
                pkt,
                ["EntityRuntimeID", "entityRuntimeId", "RuntimeID", "runtimeId"],
            )
            if rt is None:
                return False

            name = self.rt_to_name.get(rt)
            if not name:
                name = self._resolve_name_from_online_players(int(rt))
            if not name:
                return False

            now_real = time.time()

            self._flush_pending_actions(name, now_real)

            dq = self._pending_actions.get(name)
            if dq is None:
                dq = deque()
                self._pending_actions[name] = dq
            dq.append(now_real)

        except Exception as e:
            Print.print_err(f"[{self.name}] 处理 Animate 动作包出错：{e}")

        return False

    def on_pkt_sound(self, pkt: dict):
        """两种模式：LevelSoundEvent"""
        try:
            parsed = self._parse_level_sound_event(pkt)
            if not parsed:
                return False

            st, tx, ty, tz, now_real = parsed
            mode = int(self.config.get("模式", 1))

            if mode == 1:
                self._handle_sound_mode1(st, tx, ty, tz, now_real)
            else:
                self._handle_sound_mode2(st, tx, ty, tz, now_real)

        except Exception as e:
            Print.print_err(f"[{self.name}] 处理 LevelSoundEvent 包出错：{e}")

        return False

    @staticmethod
    def _parse_level_sound_event(
        pkt: dict,
    ) -> Optional[Tuple[int, float, float, float, float]]:
        """解析 LevelSoundEvent"""
        if not isinstance(pkt, dict):
            return None
        st = pkt.get("SoundType", None)
        if not isinstance(st, int):
            return None
        pos = pkt.get("Position", None)
        if not isinstance(pos, (list, tuple)) or len(pos) < 3:
            return None
        sx, sy, sz = pos[0], pos[1], pos[2]
        if not all(isinstance(t, (int, float)) for t in (sx, sy, sz)):
            return None
        tx = float(sx)
        ty = float(sy) - 0.9
        tz = float(sz) - 1.0
        now_real = time.time()
        return st, tx, ty, tz, now_real

    def _handle_sound_mode1(
        self, st: int, tx: float, ty: float, tz: float, now_real: float
    ) -> None:
        """模式1：空挥(42)，按规则忽略动作"""
        if st != 42:
            return
        name = self._bind_nearest_player_by_sound(tx, ty, tz)
        if not name:
            return
        self._last_sound42_ts[name] = now_real
        self._flush_pending_actions(name, now_real)
        dq = self._pending_actions.get(name)
        if dq:
            dt = now_real - dq[-1]
            if self._MODE1_IGNORE_MIN < dt <= self._MODE1_IGNORE_MAX:
                dq.pop()
        self._record_event(name, now_real)

    def _handle_sound_mode2(
        self, st: int, tx: float, ty: float, tz: float, now_real: float
    ) -> None:
        """模式2：空挥(42)+攻击(43)"""
        if st == 42:
            name = self._bind_nearest_player_by_sound(tx, ty, tz)
            if not name:
                return
            self._record_event(name, now_real)
            return
        if st == 43:
            attacker = self._bind_attacker_for_attack_sound(tx, ty, tz)
            if not attacker:
                return
            self._record_event(attacker, now_real)
            return

    def _flush_pending_actions(self, name: str, now_real: float):
        """把超过 EPS 的 pending 动作刷入统计"""
        dq = self._pending_actions.get(name)
        if not dq:
            return

        eps = self._MODE1_DEDUP_EPS

        while dq and (now_real - dq[0]) >= eps:
            ts = dq.popleft()
            self._record_event(name, ts)

    def _record_event(self, name: str, event_ts: float):
        """把一次挥手/攻击计入统计窗口并显示/触发订阅"""
        period = float(self.config["检测周期秒"])
        show_enabled = bool(self.config["是否显示"])
        title_interval = float(self.config["显示间隔秒"])
        now_real = time.time()

        dq = self._swing_times.get(name)
        if dq is None:
            dq = deque()
            self._swing_times[name] = dq

        dq.append(event_ts)

        cutoff = event_ts - period
        while dq and dq[0] < cutoff:
            dq.popleft()

        cps = len(dq) / period
        self._last_cps[name] = cps

        if self._subs:
            self._fire_subscriptions(name, cps, now_real)

        if show_enabled and self.funclib is not None:
            last_ts = self._last_title_ts.get(name, 0.0)
            if (now_real - last_ts) >= title_interval:
                self._last_title_ts[name] = now_real
                self._send_title(name, cps)

    @staticmethod
    def _get_single_pos(player: str):
        """获取单个玩家的坐标"""
        return player, game_utils.getPosXYZ(player)

    def _gather_positions(self):
        """获取坐标"""
        try:
            players = self.game_ctrl.allplayers
        except Exception:
            return []
        try:
            return utils.thread_gather([(self._get_single_pos, (p,)) for p in players])
        except Exception:
            return []

    def _bind_nearest_player_by_sound(
        self, x: float, y: float, z: float
    ) -> Optional[str]:
        """选处理后声音点最近的玩家"""
        ress = self._gather_positions()
        best_name = None
        best_d2 = None

        for pname, (px, py, pz) in ress:
            try:
                if not isinstance(pname, str) or not pname:
                    continue
                dx = float(px) - x
                dy = float(py) - y
                dz = float(pz) - z
                d2 = dx * dx + dy * dy + dz * dz
                if best_d2 is None or d2 < best_d2:
                    best_d2 = d2
                    best_name = pname
            except Exception:
                continue

        return best_name

    def _bind_attacker_for_attack_sound(
        self, x: float, y: float, z: float
    ) -> Optional[str]:
        """选择攻击者"""
        ress = self._gather_positions()
        candidates: List[Tuple[float, str, float, float, float]] = []

        for pname, (px, py, pz) in ress:
            try:
                if not isinstance(pname, str) or not pname:
                    continue
                fpx, fpy, fpz = float(px), float(py), float(pz)
                dx = fpx - x
                dy = fpy - y
                dz = fpz - z
                d2 = dx * dx + dy * dy + dz * dz
                candidates.append((d2, pname, fpx, fpy, fpz))
            except Exception:
                continue

        if not candidates:
            return None

        candidates.sort(key=lambda t: t[0])
        d2_1, name1, x1, y1, z1 = candidates[0]
        dist1 = d2_1 ** 0.5

        if dist1 > self._MODE2_FIRST_DIST_IF_MOB:
            return name1

        if len(candidates) < 2:
            return None

        _, name2, x2, y2, z2 = candidates[1]
        dxp = x1 - x2
        dyp = y1 - y2
        dzp = z1 - z2
        dist12 = (dxp * dxp + dyp * dyp + dzp * dzp) ** 0.5

        if dist12 > self._MODE2_FIRST_SECOND_PLAYER_DIST_MAX:
            return None

        return name2

    def _fire_subscriptions(self, player_name: str, cps: float, now: float):
        """触发所有阈值订阅回调"""
        for sub in list(self._subs.values()):
            if cps < sub.threshold:
                continue

            last = sub.last_fire_by_player.get(player_name, 0.0)
            if sub.cooldown > 0 and (now - last) < sub.cooldown:
                continue

            sub.last_fire_by_player[player_name] = now
            try:
                sub.handler(player_name, cps)
            except Exception as e:
                Print.print_war(f"[{self.name}] 订阅回调异常（sub_id={sub.sub_id}）：{e}")

    def _refresh_mapping_from_online_players(self, force: bool = False):
        """从在线玩家列表刷新映射"""
        now = time.time()
        if (not force) and (now - self._last_players_scan_ts) < 0.5:
            return
        self._last_players_scan_ts = now

        try:
            players_mgr = self.frame.get_players()
            players = players_mgr.getAllPlayers()
        except Exception:
            return

        for p in players:
            try:
                name = getattr(p, "name", None)
                if not isinstance(name, str) or not name:
                    continue

                rt = self._get_runtime_id_from_player_obj(p)
                if rt is None:
                    continue

                self.rt_to_name[int(rt)] = name
            except Exception:
                continue

    def _resolve_name_from_online_players(self, rt: int) -> Optional[str]:
        """从在线玩家列表补齐映射缺失"""
        self._refresh_mapping_from_online_players(force=False)
        name = self.rt_to_name.get(rt)
        if name:
            return name

        self._refresh_mapping_from_online_players(force=True)
        return self.rt_to_name.get(rt)

    @staticmethod
    def _get_runtime_id_from_player_obj(p) -> Optional[int]:
        """从 Player 对象读取 runtime_id"""
        try:
            v = getattr(p, "runtime_id", None)
            return v if isinstance(v, int) else None
        except Exception:
            return None

    def _send_title(self, player_name: str, cps: float):
        """向玩家发送 titleraw 显示 CPS"""
        self.funclib.sendaicmd("/gamerule sendcommandfeedback false")

        cps_s = f"{cps:.1f}"
        space = self.config["前置空格"]
        color = self.config["颜色前缀"]

        selector_name = player_name
        cmd = (
            f'/titleraw @a[name="{selector_name}"] title '
            f'{{"rawtext":[{{"text":"{space}{color}cps:{cps_s}"}}]}}'
        )
        self.funclib.sendaicmd(cmd)

    def _clamp_config(self):
        """修正配置"""
        mode = int(self.config.get("模式", 1))
        if mode not in (1, 2):
            mode = 1
        self.config["模式"] = mode

        period = float(self.config.get("检测周期秒", 1.0))
        if period <= 0:
            period = 1.0
        self.config["检测周期秒"] = period

        interval = float(self.config.get("显示间隔秒", period))
        if interval <= 0:
            interval = period
        self.config["显示间隔秒"] = interval


entry = plugin_entry(SwingCPSAPI, "CPS显示")

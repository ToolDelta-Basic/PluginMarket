from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Optional

from tooldelta import Plugin, plugin_entry, ToolDelta, Print, cfg

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
    version = (0, 0, 1)

    def __init__(self, frame: ToolDelta):
        """初始化插件状态与监听"""
        super().__init__(frame)

        default_cfg = {
            "检测周期秒": 1.0,
            "是否显示": True,
            "显示间隔秒": 1.0,
            "前置空格": "               ",
            "颜色前缀": "§e",
        }
        std_cfg = {
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

        self.ListenPacket(int(PacketIDS.Animate), self.on_pkt_animate)

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

    def on_pkt_animate(self, pkt: dict):
        """统计挥手次数并计算 CPS"""
        try:
            if not isinstance(pkt, dict):
                return False

            if pkt.get("ActionType", None) != 1:
                return False

            rt = pkt.get("EntityRuntimeID", None)
            if not isinstance(rt, int):
                return False

            name = self.rt_to_name.get(rt)
            if not name:
                name = self._resolve_name_from_online_players(rt)
                if not name:
                    return False

            now = time.time()
            period = float(self.config["检测周期秒"])
            show_enabled = bool(self.config["是否显示"])
            title_interval = float(self.config["显示间隔秒"])

            dq = self._swing_times.get(name)
            if dq is None:
                dq = deque()
                self._swing_times[name] = dq

            dq.append(now)

            cutoff = now - period
            while dq and dq[0] < cutoff:
                dq.popleft()

            cps = len(dq) / period
            self._last_cps[name] = cps

            if self._subs:
                self._fire_subscriptions(name, cps, now)

            if show_enabled and self.funclib is not None:
                last_ts = self._last_title_ts.get(name, 0.0)
                if (now - last_ts) >= title_interval:
                    self._last_title_ts[name] = now
                    self._send_title(name, cps)

        except Exception as e:
            Print.print_err(f"[{self.name}] 处理 Animate 包出错：{e}")

        return False

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
        period = float(self.config.get("检测周期秒", 1.0))
        if period <= 0:
            period = 1.0
        self.config["检测周期秒"] = period

        interval = float(self.config.get("显示间隔秒", period))
        if interval <= 0:
            interval = period
        self.config["显示间隔秒"] = interval


entry = plugin_entry(SwingCPSAPI, "CPS显示")

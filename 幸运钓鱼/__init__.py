"""
一次完整的数据包抓取对应四个包:
    AddActor         抛竿, 记下鱼钩是谁的、落在哪
    ActorEvent 12    鱼在靠近
    ActorEvent 13    咬住了
    RemoveActor      收竿, 距咬钩在窗口内算钓上

奖励由插件自己发, 战利品表写在配置文件里, 所以不用去包里解物品 ID。
配置在插件构造时读一次, 改完配置要重载框架才生效。
"""

import sys
import threading
import time

from tooldelta import Player, Plugin, ToolDelta, plugin_entry
from tooldelta.constants import PacketIDS
from tooldelta.utils import thread_func

# 热重载时把上一代子模块清出去, 否则改了子模块也还是跑旧代码
for _submodule in [n for n in sys.modules if n.startswith(f"{__name__}.")]:
    globals().pop(_submodule.rsplit(".", 1)[-1], None)
    del sys.modules[_submodule]

from .actionbar import ActionBar
from .bot import Bot
from .config import CFG_DEFAULT, CFG_STD, Settings
from .loot import LootDealer
from .packets import (
    HOOK_EVENTS,
    Hook,
    HookStore,
    get_any,
    is_hook,
    owner_of,
    parse_pos,
    runtime_id,
    unique_id,
)

API_NAME = "幸运钓鱼"
API_VERSION = (0, 1, 0)

# 鱼钩记录的最长保留时间(秒)
HOOK_TTL = 180.0

MAINTAIN = 1.0


LIVE_TOKEN_ATTR = "_fishing_pro_live_token"


class FishingSystem(Plugin):
    name = "幸运钓鱼"
    author = "jiru"
    version = (0, 1, 0)
    description = "幸运钓鱼: 上钩预警 + 收竿抽奖 + 稀有物品播报"

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self._stop = threading.Event()
        cfg, _ = self.get_config_and_version(CFG_STD, CFG_DEFAULT)
        self.settings = Settings(cfg)
        self.actionbar = ActionBar(self.send, self._stop, self.is_current)
        self.dealer = LootDealer(self, self.settings, self.actionbar, self._stop)
        self.bot = Bot(self, self.settings)
        self.hooks = HookStore()
        self._token = object()
        setattr(frame, LIVE_TOKEN_ATTR, self._token)

        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_frame_exit)
        self.ListenPacket(PacketIDS.AddActor, self.on_add_actor)
        self.ListenPacket(PacketIDS.RemoveActor, self.on_remove_actor)
        self.ListenPacket(PacketIDS.ActorEvent, self.on_actor_event)
        self.ListenPacket(PacketIDS.MoveActorAbsolute, self.on_move_actor)

    def is_current(self) -> bool:
        return getattr(self.frame, LIVE_TOKEN_ATTR, None) is self._token

    def send(self, cmd: str) -> None:
        self.game_ctrl.sendaicmd(cmd)

    def send_with_resp(self, cmd: str, timeout: float = 5):
        "发一条要回包的指令"
        return self.game_ctrl.sendaicmd_with_resp(cmd, timeout)

    def on_active(self) -> None:
        self._report()
        self._stop.clear()
        self._maintain_loop()

    def on_frame_exit(self, _evt) -> None:
        self._stop.set()

    def _report(self) -> None:
        lo, hi = self.settings.region()
        self.print_inf(
            f"钓鱼判定区: {lo[0]:.0f} {lo[1]:.0f} {lo[2]:.0f} ~ "
            f"{hi[0]:.0f} {hi[1]:.0f} {hi[2]:.0f}"
        )
        table = self.settings.loot_table()
        if not table:
            self.print_war("配置里一件战利品都没有, 钓上来不会有奖励")
        else:
            total = sum(float(e.get("权重", 0)) for e in table)
            rare = [e for e in table if e.get("稀有度") in ("史诗", "传说")]
            odds = sum(float(e.get("权重", 0)) for e in rare) / total * 100 if total else 0
            self.print_inf(f"战利品 {len(table)} 种, 稀有 {len(rare)} 种, 出货率 {odds:.1f}%")
        if self.settings["机器人停靠"]:
            d = self.settings.dock_point()
            auto = "自动" if not self.settings["机器人停靠坐标"] else "手动"
            self.print_inf(f"机器人停靠点 ({auto}): {d[0]:.0f} {d[1]:.0f} {d[2]:.0f}")

    @thread_func("钓鱼系统-维护")
    def _maintain_loop(self) -> None:
        last_dock = 0.0
        while not self._stop.is_set():
            if not self.is_current():
                return
            try:
                now = time.time()
                if now - last_dock >= float(self.settings["停靠检查间隔(秒)"]):
                    last_dock = now
                    self.bot.keep_docked()
                self._sweep(now)
            except Exception as err:  # skipcq: PYL-W0703
                self.print_err(f"维护循环出错: {err}")
            if self._stop.wait(MAINTAIN):
                return

    def _sweep(self, now: float) -> None:
        "咬钩之后等不到 RemoveActor 就判为跑了, 不然收竿包一丢玩家就停在上钩了上"
        window = float(self.settings["收竿窗口(秒)"])
        for hook in self.hooks.sweep(now, window, HOOK_TTL):
            self._settle_async(hook, window + 1)

    # ---------------- 数据包 ----------------

    def on_add_actor(self, packet: dict) -> bool:
        if not is_hook(packet):
            return False
        rid = runtime_id(packet)
        pos = parse_pos(get_any(packet, "Position", "position", "pos"))
        if rid is None or pos is None:
            return False
        uid = unique_id(packet)
        hook = Hook(
            runtime_id=rid,
            unique_id=uid,
            owner_id=owner_of(packet),
            pos=pos,
            cast_at=time.time(),
        )
        self.hooks.add(hook)
        return False

    def on_move_actor(self, packet: dict) -> bool:
        """更新落点。

        抛竿后鱼钩要飞一两秒才落水, AddActor 里的坐标还在玩家手上, 拿它判水域会全错。
        所有实体都会走这个回调, 所以第一步就是查表、不是鱼钩立刻返回。
        """
        rid = runtime_id(packet)
        if rid is None:
            return False
        hook = self.hooks.get(rid)
        if hook is None:
            return False
        pos = parse_pos(get_any(packet, "Position", "position", "pos"))
        if pos is not None:
            hook.pos = pos
        return False

    def on_actor_event(self, packet: dict) -> bool:
        self._track_event(packet)
        return False

    def _track_event(self, packet: dict) -> None:
        "鱼钩的靠近/咬钩事件"
        rid = runtime_id(packet)
        if rid is None:
            return
        hook = self.hooks.get(rid)
        if hook is None:
            return
        evt = get_any(packet, "EventType", "eventType", "event_id", "Event", "event")
        try:
            evt = int(evt)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if evt not in HOOK_EVENTS:
            return

        now = time.time()
        if evt == int(self.settings["即将上钩事件号"]):
            if not hook.warned:
                hook.warned = True
                self._notify(hook, self.settings["即将上钩提示"])
        elif evt == int(self.settings["咬钩事件号"]) and now - hook.last_alert >= 1.0:
            hook.last_alert = now
            hook.bit_at = now
            self._notify(hook, self.settings["上钩提示"])

    def on_remove_actor(self, packet: dict) -> bool:
        "鱼钩消失 = 收竿 (或自然销毁), 这就是钓没钓上的判定点"
        uid = unique_id(packet)
        if uid is None:
            return False
        hook = self.hooks.take(uid)
        if hook is None or not hook.bit_at:
            return False
        # 结算要发指令、还要把提示挂两秒, 在收包线程上做会堵住整条链路
        self._settle_async(hook, time.time() - hook.bit_at)
        return False

    # ---------------- 提示与结算 ----------------

    @thread_func("钓鱼系统-提示")
    def _notify(self, hook: Hook, text: str) -> None:
        if not self.is_current() or not text.strip():
            return
        try:
            if not self.settings.in_region(hook.pos):
                return
            player = self._owner(hook)
            if player is None:
                self.print_war(f"鱼钩 #{hook.runtime_id} 认不出主人, 提示无法发送")
                return
            self.actionbar.show(player, text, float(self.settings["提示持续(秒)"]))
        except Exception as err:  # skipcq: PYL-W0703
            self.print_err(f"发提示出错: {err}")

    def _owner(self, hook: Hook) -> Player | None:
        # 元数据这条路不发任何指令, 命令回显被关掉也照样准
        if hook.owner_id is not None:
            maintainer = self.game_ctrl.players
            player = maintainer.getPlayerByUniqueID(hook.owner_id)
            if player is None:
                player = maintainer.getPlayerByRuntimeID(hook.owner_id)
            if player is not None:
                return player
        return self.bot.nearest_player(hook.pos)

    @thread_func("钓鱼系统-结算")
    def _settle_async(self, hook: Hook, elapsed: float) -> None:
        # 奖励也要看区域, 不然在世界任何地方钓鱼都能拿战利品
        if not self.is_current() or not self.settings.in_region(hook.pos):
            return
        player = self._owner(hook)
        if player is None:
            return
        duration = float(self.settings["提示持续(秒)"])
        if elapsed > float(self.settings["收竿窗口(秒)"]):
            if tip := self.settings["跑掉提示"]:
                self.actionbar.show(player, tip, duration)
            return
        # 先清原版再发奖励: 那条鱼是收竿瞬间生成的, 晚了就飞到玩家身上了
        if self.settings["清除原版渔获"]:
            self.dealer.clear_vanilla(hook.pos)
        if prize := self.dealer.roll():
            self.dealer.grant(player, prize)

    # ---------------- 对外 API ----------------

    def is_alerting(self, player: Player) -> bool:
        "给别的也往动作栏写字的插件用, 别把只有一两秒的上钩提示冲掉"
        return self.actionbar.is_alerting(player)

    def fishing_region(self) -> tuple[tuple, tuple]:
        return self.settings.region()


entry = plugin_entry(FishingSystem, API_NAME, API_VERSION)

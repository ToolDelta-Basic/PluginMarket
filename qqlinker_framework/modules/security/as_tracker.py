"""攻速检测模块 — 基于 PlayerAuthInput 数据包实时检测连点器/宏鼠标

══════════════════════════════════════════════════════════════
检测原理
══════════════════════════════════════════════════════════════
通过 listen_packet(PacketIDS.PlayerAuthInput) 监听客户端→服务端的
PlayerBlockActions 字段，提取 ActionType=1（攻击动作），在滑动时间窗口
内统计攻击次数，超阈值则触发阶梯惩罚。

══════════════════════════════════════════════════════════════
命令
══════════════════════════════════════════════════════════════
QQ 群命令:
  .攻速管理              — 管理菜单
  .攻速踢出 <玩家名>     — 手动惩罚
  .攻速拉黑 <玩家名>     — 永久拉黑
  .攻速解封 <玩家名>     — 解封

游戏聊天命令:
  攻速 / aspeed          — 查看自身攻速
  攻速帮助                — 帮助手册
  攻速管理                — 管理菜单 (OP)
══════════════════════════════════════════════════════════════
"""
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ...core.module import Module
from ...core.decorators import command, listen

_log = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────

# PlayerAuthInput 数据包 ID (Bedrock Edition)
PACKET_ID_PLAYER_AUTH_INPUT = 144

# PlayerBlockActions 中的攻击动作类型
ATTACK_ACTION_TYPES = {1, }  # ActionType=1: 开始破坏方块/攻击

# ── 默认配置 ──────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "攻速检测": {
        "是否启用": True,
        "时间窗口秒": 1.0,
        "窗口最大攻击次数": 8,
        "首次惩罚扣血点数": 15,
        "历史违规阈值": 3,
        "白名单管理员": [],
        "违规警告文案": "§c[攻速检测] {player} 攻击速度异常，请勿使用连点器！",
        "踢出提示文案": "§c你因超速攻击被暂时踢出服务器，如再犯将被永久封禁！",
        "永久封禁文案": "§c你已被永久封禁！原因：多次超速攻击。",
    }
}


class AttackStore:
    """数据持久化 — JSON 文件存储。"""

    def __init__(self, data_dir: str):
        self._dir = data_dir
        os.makedirs(self._dir, exist_ok=True)

    def _player_file(self, player: str) -> str:
        safe = player.replace("/", "_").replace("\\", "_")
        return os.path.join(self._dir, f"{safe}.json")

    def load_player(self, player: str) -> dict:
        path = self._player_file(player)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"violations": 0, "total_attacks": 0, "last_punish": 0}

    def save_player(self, player: str, data: dict):
        with open(self._player_file(player), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_blacklist(self) -> Set[str]:
        path = os.path.join(self._dir, "_blacklist.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def save_blacklist(self, blacklist: Set[str]):
        with open(os.path.join(self._dir, "_blacklist.json"), "w") as f:
            json.dump(sorted(blacklist), f, ensure_ascii=False, indent=2)


class AttackDetector:
    """滑动窗口攻击速率检测。"""

    def __init__(self, window_seconds: float, max_attacks: int):
        self._window = window_seconds
        self._max = max_attacks
        self._history: Dict[str, List[float]] = {}

    def record_attack(self, player: str) -> bool:
        """记录一次攻击，返回 True 表示超速。"""
        now = time.time()
        attacks = self._history.setdefault(player, [])
        attacks.append(now)
        # 清理过期记录
        cutoff = now - self._window
        while attacks and attacks[0] < cutoff:
            attacks.pop(0)
        return len(attacks) > self._max

    def get_current_rate(self, player: str) -> float:
        """获取当前攻击速率（次/秒）。"""
        attacks = self._history.get(player, [])
        if not attacks:
            return 0.0
        now = time.time()
        cutoff = now - self._window
        attacks = [t for t in attacks if t >= cutoff]
        return len(attacks) / self._window if self._window > 0 else 0.0


class AttackSpeedTracker(Module):
    """攻速检测 — 基于 PlayerAuthInput 数据包。"""

    name = "as_tracker"
    uid = 1000  # service: 服务引擎
    version = (1, 0, 0)
    default_config = DEFAULT_CONFIG
    required_services = ["config", "adapter", "message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._active = False
        self._store: Optional[AttackStore] = None
        self._detector: Optional[AttackDetector] = None

    async def on_init(self) -> None:
        self._active = self.config.get("攻速检测.是否启用", True)
        if not self._active:
            _log.info("[攻速检测] 已禁用")
            return

        store_dir = os.path.join(self.data_dir, "player_data")
        self._store = AttackStore(store_dir)
        self._detector = AttackDetector(
            self.config.get("攻速检测.时间窗口秒", 1.0),
            self.config.get("攻速检测.窗口最大攻击次数", 8),
        )

        # 核心：监听 PlayerAuthInput 数据包
        self.listen_packet(PACKET_ID_PLAYER_AUTH_INPUT, self._on_auth_input)

        # 控制台命令
        adapter = self.services.get("adapter")
        adapter.register_console_command(
            ["攻速管理"], "",
            "打开攻速检测管理菜单",
            self._console_menu,
        )

        _log.info("[攻速检测] 模块初始化完成 (PlayerAuthInput)")

    # ═══════════════════════════════════════════════════════════
    # 核心：数据包监听
    # ═══════════════════════════════════════════════════════════

    def _on_auth_input(self, pkt: dict) -> bool:
        """处理 PlayerAuthInput 数据包 (Bedrock ID=144)。"""
        if not self._active:
            return False

        block_actions = pkt.get("PlayerBlockActions")
        if not block_actions:
            return False

        if isinstance(block_actions, dict):
            actions = [block_actions]
        elif isinstance(block_actions, list):
            actions = block_actions
        else:
            return False

        has_attack = any(
            a.get("ActionType") in ATTACK_ACTION_TYPES for a in actions
        )
        if not has_attack:
            return False

        player = pkt.get("PlayerName") or pkt.get("player") or "?"
        if self._detector.record_attack(player):
            self._handle_overspeed(player)

        return False  # 不拦截数据包

    # ═══════════════════════════════════════════════════════════
    # 事件监听
    # ═══════════════════════════════════════════════════════════

    @listen("PlayerJoinEvent")
    async def _on_player_join(self, event):
        blacklist = self._store.load_blacklist()
        if event.player_name in blacklist:
            self.adapter.send_game_command(
                f'kick "{event.player_name}" §c你已被永久封禁：攻速检测严重违规'
            )

    @listen("GameChatEvent")
    async def _on_game_chat(self, event):
        msg = event.message.strip()
        player = event.player_name

        if msg in ("攻速", "aspeed"):
            await self._handle_game_check(player)
        elif msg == "攻速帮助":
            self._send_help(player)
        elif msg == "攻速管理" and self._is_admin(player):
            self._show_game_menu(player)
        elif msg.startswith("攻速踢出 ") and self._is_admin(player):
            self._manual_punish(msg[5:].strip(), player)
        elif msg.startswith("攻速拉黑 ") and self._is_admin(player):
            self._blacklist_add(msg[5:].strip(), player)
        elif msg.startswith("攻速解封 ") and self._is_admin(player):
            self._blacklist_remove(msg[5:].strip(), player)

    # ═══════════════════════════════════════════════════════════
    # QQ 群命令
    # ═══════════════════════════════════════════════════════════

    @command(".攻速管理", description="攻速检测管理菜单", op_only=True)
    async def _cmd_qq_menu(self, ctx):
        args = ctx.args
        if not args:
            await ctx.reply(
                "攻速管理系统\n"
                "1. 排行榜  2. 配置  3. 黑名单  4. 开关\n"
                "5. 惩罚 <玩家>  6. 拉黑 <玩家>  7. 解封 <玩家>\n"
                "用法: .攻速管理 <数字> [参数]"
            )
            return
        try:
            opt = int(args[0])
        except ValueError:
            await ctx.reply("❌ 请输入数字")
            return
        if opt == 1:
            self._print_ranking()
        elif opt == 2:
            self._print_config()
        elif opt == 3:
            self._print_blacklist()
        elif opt == 4:
            self._active = not self._active
            await ctx.reply(f"攻速检测已{'启用' if self._active else '禁用'}")
        elif opt == 5 and len(args) >= 2:
            self._manual_punish(args[1])
            await ctx.reply(f"已对 {args[1]} 执行惩罚")
        elif opt == 6 and len(args) >= 2:
            self._blacklist_add(args[1])
            await ctx.reply(f"已将 {args[1]} 加入黑名单")
        elif opt == 7 and len(args) >= 2:
            self._blacklist_remove(args[1])
            await ctx.reply(f"已解封 {args[1]}")
        else:
            await ctx.reply("❌ 无效选项或缺少参数")

    @command(".攻速踢出", description="手动惩罚玩家", op_only=True,
             argument_hint="<玩家名>")
    async def _cmd_qq_punish(self, ctx):
        if ctx.args:
            self._manual_punish(ctx.args[0])
            await ctx.reply(f"✅ 已对玩家 {ctx.args[0]} 执行惩罚")

    @command(".攻速拉黑", description="永久拉黑玩家", op_only=True,
             argument_hint="<玩家名>")
    async def _cmd_qq_blacklist(self, ctx):
        if ctx.args:
            self._blacklist_add(ctx.args[0])
            await ctx.reply(f"✅ 已拉黑玩家 {ctx.args[0]}")

    @command(".攻速解封", description="解除玩家封禁", op_only=True,
             argument_hint="<玩家名>")
    async def _cmd_qq_unban(self, ctx):
        if ctx.args:
            self._blacklist_remove(ctx.args[0])
            await ctx.reply(f"✅ 已解封玩家 {ctx.args[0]}")

    # ═══════════════════════════════════════════════════════════
    # 核心逻辑
    # ═══════════════════════════════════════════════════════════

    def _handle_overspeed(self, player: str):
        """超速攻击 → 警告 + 扣血，累积违规踢出/封禁。"""
        data = self._store.load_player(player)
        data.setdefault("violations", 0)
        data.setdefault("total_attacks", 0)
        data["violations"] += 1
        data["total_attacks"] += 1
        self._store.save_player(player, data)

        warn = self.config.get("攻速检测.违规警告文案",
                               "§c[攻速检测] 攻击速度异常！")
        warn_text = json.dumps(warn.format(player=player), ensure_ascii=False)
        self.adapter.send_game_command(
            f'tellraw "{player}" {{"rawtext":[{{"text":{warn_text}}}]}}'
        )
        self.adapter.send_game_command(
            f'damage "{player}" {self.config.get("攻速检测.首次惩罚扣血点数", 15)}'
        )

        threshold = self.config.get("攻速检测.历史违规阈值", 3)
        if data["violations"] >= threshold:
            kick_msg = self.config.get("攻速检测.踢出提示文案", "§c你因超速攻击被踢出")
            self.adapter.send_game_command(
                f'kick "{player}" {kick_msg}'
            )

    def _handle_game_check(self, player: str):
        data = self._store.load_player(player)
        rate = self._detector.get_current_rate(player)
        max_rate = self.config.get("攻速检测.窗口最大攻击次数", 8)
        msg = (
            f"§6=== {player} 攻速报告 ===\n"
            f"§e当前攻速: §f{rate:.1f} 次/秒 §7(上限 {max_rate})\n"
            f"§e违规次数: §c{data.get('violations', 0)}\n"
            f"§e累计攻击: §f{data.get('total_attacks', 0)}"
        )
        self.adapter.send_game_message(player, msg)

    def _send_help(self, player: str):
        help_text = (
            "§6=== 攻速检测帮助 ===\n"
            "§f攻速 / aspeed   §7查看自身攻速\n"
            "§f攻速管理          §7管理菜单 (OP)\n"
            "§7输入 §f攻速管理 §7打开管理面板"
        )
        self.adapter.send_game_message(player, help_text)

    def _manual_punish(self, player: str, operator: str = "系统"):
        kick_msg = self.config.get("攻速检测.踢出提示文案", "§c你被管理员踢出")
        self.adapter.send_game_command(f'kick "{player}" {kick_msg}')
        _log.info("[攻速检测] %s 手动踢出 %s", operator, player)

    def _blacklist_add(self, player: str, operator: str = "系统"):
        bl = self._store.load_blacklist()
        bl.add(player)
        self._store.save_blacklist(bl)
        ban_msg = self.config.get("攻速检测.永久封禁文案", "§c你已被永久封禁")
        self.adapter.send_game_command(f'kick "{player}" {ban_msg}')
        _log.info("[攻速检测] %s 拉黑 %s", operator, player)

    def _blacklist_remove(self, player: str, operator: str = "系统"):
        bl = self._store.load_blacklist()
        bl.discard(player)
        self._store.save_blacklist(bl)
        _log.info("[攻速检测] %s 解封 %s", operator, player)

    def _is_admin(self, player_or_qq: str) -> bool:
        admins = self.config.get("攻速检测.白名单管理员", [])
        return player_or_qq in admins

    def _show_game_menu(self, player: str):
        msg = (
            "§6=== 攻速检测管理 ===\n"
            "§f攻速踢出 <玩家>   §7手动惩罚\n"
            "§f攻速拉黑 <玩家>   §7永久封禁\n"
            "§f攻速解封 <玩家>   §7解除封禁"
        )
        self.adapter.send_game_message(player, msg)

    def _console_menu(self, args: list):
        if not args:
            print("攻速管理 1=排行 2=配置 3=黑名单 4=开关 5=惩罚 6=拉黑 7=解封")
            return
        try:
            opt = int(args[0])
        except ValueError:
            print("无效选项")
            return
        if opt == 1:
            self._print_ranking()
        elif opt == 2:
            self._print_config()
        elif opt == 3:
            self._print_blacklist()
        elif opt == 4:
            self._active = not self._active
            print(f"攻速检测已{'启用' if self._active else '禁用'}")
        elif opt == 5 and len(args) >= 2:
            self._manual_punish(args[1])
        elif opt == 6 and len(args) >= 2:
            self._blacklist_add(args[1])
        elif opt == 7 and len(args) >= 2:
            self._blacklist_remove(args[1])
        else:
            print("用法: 攻速管理 <数字> [参数]")

    def _print_ranking(self):
        print("=== 攻速排行榜 ===")
        for fname in sorted(os.listdir(self._store._dir)):  # noqa: PYL-W0212 (same-package internal access — _store is a framework-internal datastore)
            if fname == "_blacklist.json":
                continue
            path = os.path.join(self._store._dir, fname)  # noqa: PYL-W0212 (same-package internal access — _store is a framework-internal datastore)
            try:
                with open(path) as f:
                    d = json.load(f)
                name = fname.replace(".json", "")
                print(f"  {name}: 违规 {d.get('violations', 0)}, 攻击 {d.get('total_attacks', 0)}")
            except Exception:
                pass

    def _print_config(self):
        cfg = self.config.get("攻速检测", {})
        for k, v in cfg.items():
            print(f"  {k}: {v}")

    def _print_blacklist(self):
        bl = self._store.load_blacklist()
        print(f"黑名单 ({len(bl)} 人): {', '.join(sorted(bl)) if bl else '(空)'}")

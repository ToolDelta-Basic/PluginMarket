"""玩家-QQ绑定模块，提供验证码验证流程与绑定管理服务。

安全特性:
  - 绑定码使用 secrets.token_hex() 生成（不可预测）
  - 绑定码 5 分钟 TTL 过期
  - 同一 QQ 号绑定速率限制（每小时 3 次）
"""
import json
import os
import secrets
import time
from typing import Dict, List, Optional

from ...core.module import Module
from ...core.kernel.decorators import command
from ...core.kernel.events import GameChatEvent
from ...core.kernel.sanitize import sanitize_player_name, sanitize_game_command_param
from ...core.kernel.defguard import escape_player_name

# ── 绑定安全限制 ──
_BIND_CODE_TTL = 300          # 验证码有效期（秒）= 5 分钟
_BIND_RATE_MAX = 3             # 每小时最大绑定尝试次数
_BIND_RATE_WINDOW = 3600       # 速率窗口（秒）= 1 小时


class BindingService:
    """绑定数据存取与校验核心。"""

    def __init__(self, data_dir: str):
        self._file = os.path.join(data_dir, "bindings.json")
        self._bindings: Dict[int, str] = {}          # qq -> 游戏名
        self._pending_codes: Dict[str, tuple] = {}   # 游戏名 -> (验证码, 过期时间戳)
        # ── 绑定速率限制 ──
        self._bind_rate: Dict[int, List[float]] = {}  # qq -> [时间戳...]
        self._load()

    # ---------- 文件持久化 ----------
    def _load(self):
        """从文件加载绑定数据。"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._bindings = {
                        int(k): v for k, v in json.load(f).items()
                    }
            except Exception:
                self._bindings = {}

    def _save(self):
        """保存绑定数据到文件。"""
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(
                {str(k): v for k, v in self._bindings.items()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ---------- 业务接口 ----------
    def get_player_by_qq(self, qq_id: int) -> Optional[str]:
        """根据 QQ 号查询绑定的玩家名。"""
        return self._bindings.get(qq_id)

    def get_qq_by_player(self, player_name: str) -> Optional[int]:
        """根据玩家名查询绑定的 QQ 号。"""
        for qq, name in self._bindings.items():
            if name == player_name:
                return qq
        return None

    def is_bound(self, qq_id: int) -> bool:
        """检查 QQ 号是否已绑定。"""
        return qq_id in self._bindings

    def unbind(self, qq_id: int) -> bool:
        """解除 QQ 号的绑定关系，返回是否成功。"""
        if qq_id in self._bindings:
            del self._bindings[qq_id]
            self._save()
            return True
        return False

    def generate_code(self, player_name: str) -> str:
        """为玩家生成 6 位十六进制验证码（5 分钟有效）。

        使用 secrets.token_hex() 生成密码学安全随机码，
        替代可预测的 random.choices()。
        """
        code = secrets.token_hex(3)[:6]  # 6 位十六进制（~16M 组合）
        self._pending_codes[player_name] = (code, time.time() + _BIND_CODE_TTL)
        return code

    def _check_bind_rate(self, qq_id: int) -> bool:
        """检查绑定速率限制（每 QQ 每小时最多 _BIND_RATE_MAX 次）。

        Args:
            qq_id: QQ 号。

        Returns:
            True 如果允许绑定。
        """
        now = time.time()
        hits = self._bind_rate.get(qq_id, [])
        cutoff = now - _BIND_RATE_WINDOW
        hits = [t for t in hits if t >= cutoff]
        if len(hits) >= _BIND_RATE_MAX:
            self._bind_rate[qq_id] = hits
            return False
        hits.append(now)
        self._bind_rate[qq_id] = hits
        return True

    def verify(self, player_name: str, code: str) -> bool:
        """校验验证码，成功返回 True 并移除待验证记录。"""
        entry = self._pending_codes.get(player_name)
        if not entry:
            return False
        stored_code, expire = entry
        if time.time() > expire:
            del self._pending_codes[player_name]
            return False
        if stored_code == code:
            del self._pending_codes[player_name]
            return True
        return False

    def bind(self, qq_id: int, player_name: str):
        """建立 QQ 号与游戏名的绑定关系。"""
        self._bindings[qq_id] = player_name
        self._save()

    def get_bindings(self) -> Dict[int, str]:
        """返回所有绑定关系的副本。"""
        return dict(self._bindings)


class PlayerBindingModule(Module):
    """玩家绑定模块。"""
    background = True
    """玩家-QQ绑定模块，提供 .绑定 命令并监听游戏内 #绑定 请求。"""

    name = "player_binding"
    tier = 100  # TIER_DAEMON  # 需要 adapter 执行游戏命令
    version = (1, 0, 0)
    required_services = ["config", "message", "adapter"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self.binding_service: Optional[BindingService] = None

    def create_exports(self) -> dict:
        """约定: 动态构造绑定服务并返回，框架自动注册到容器。"""
        self.binding_service = BindingService(self.data_dir)
        return {"binding": self.binding_service}

    async def on_init(self):
        """框架已导出 binding 服务，模块只注册命令和事件。"""

        async def _dbg_bindings():
            """调试端点。"""
            all_b = self.binding_service.get_bindings()
            return str({"total": len(all_b)})

        try:
            debug = self.services.get("debug")
            await debug.register_module(
                self.name, {"bindings": _dbg_bindings}
            )
        except KeyError:
            pass

        self.register_command(
            ".绑定", self._cmd_qq_bind,
            description="绑定游戏账号：.绑定 <游戏名> <验证码>",
            argument_hint="<游戏名> <验证码>",
        )
        self.register_command(
            ".解绑", self._cmd_unbind,
            description="解除已绑定的游戏账号",
        )
        self.register_command(
            ".绑定信息", self._cmd_info,
            description="查看当前绑定的游戏账号",
        )

        self.listen("GameChatEvent", self.on_game_chat)

    # ---------- 游戏内监听 ----------
    @staticmethod
    def _build_tellraw(player: str, text: str) -> str:
        """安全构建 tellraw 命令，使用 Python dict → 一次性 json.dumps。

        防止通过玩家名注入 JSON 结构或命令。
        """
        safe_player = sanitize_player_name(player)
        safe_text = sanitize_game_command_param(text, allow_spaces=True)
        payload = {
            "rawtext": [{"text": safe_text}]
        }
        return (
            f'tellraw "{escape_player_name(safe_player)}" '
            + json.dumps(payload, ensure_ascii=False)
        )

    async def on_game_chat(self, event: GameChatEvent):
        """监听游戏内 #绑定 请求，生成验证码并发送 tellraw。"""
        msg = (event.message or "").strip()
        if not msg:
            return
        if msg == "#绑定":
            player = sanitize_player_name(event.player_name)
            existing_qq = self.binding_service.get_qq_by_player(player)
            if existing_qq:
                self.adapter.send_game_message(
                    player, "§c你已经绑定了QQ号，不能重复绑定。"
                )
                return
            code = self.binding_service.generate_code(player)
            # 使用参数化接口构建 tellraw，防止 JSON 注入
            code_msg = (
                f"§a你的绑定验证码是：§e{code}§a，"
                f"请在QQ群发送：.绑定 {player} {code}"
            )
            cmd1 = self._build_tellraw(player, code_msg)
            cmd2 = self._build_tellraw(
                player, "§7验证码有效期为 5 分钟"
            )
            self.adapter.send_game_command(cmd1)
            self.adapter.send_game_command(cmd2)

    # ---------- QQ 命令 ----------
    @command(".绑定")
    async def _cmd_qq_bind(self, ctx):
        """处理 .绑定 命令，校验验证码并完成绑定。"""
        if self.binding_service.is_bound(ctx.user_id):
            await ctx.reply("你已经绑定了游戏账号，不能重复绑定。")
            return

        # ── 绑定速率限制 ──
        if not self.binding_service._check_bind_rate(ctx.user_id):
            await ctx.reply("绑定尝试过于频繁，请稍后再试。")
            return

        if len(ctx.args) < 2:
            await ctx.reply("用法：.绑定 <游戏名> <验证码>")
            return
        player_name = ctx.args[0]
        code = ctx.args[1]
        if not self.binding_service.verify(player_name, code):
            await ctx.reply("验证码错误或已过期，请在游戏内重新发送 #绑定 获取。")
            return
        self.binding_service.bind(ctx.user_id, player_name)
        await ctx.reply(f"绑定成功！你的游戏账号：{player_name}")
        self.adapter.send_game_message(
            player_name, f"§a你的QQ号 {ctx.user_id} 已成功绑定！"
        )

    @command(".解绑")
    async def _cmd_unbind(self, ctx):
        """处理 .解绑 命令，解除绑定关系。"""
        if not self.binding_service.is_bound(ctx.user_id):
            await ctx.reply("你还没有绑定游戏账号。")
            return
        self.binding_service.unbind(ctx.user_id)
        await ctx.reply("已解除绑定。")

    @command(".绑定信息")
    async def _cmd_info(self, ctx):
        """处理 .绑定信息 命令，查询当前绑定账号。"""
        player = self.binding_service.get_player_by_qq(ctx.user_id)
        if not player:
            await ctx.reply(
                "你尚未绑定游戏账号。请在游戏内发送 #绑定 获取验证码。"
            )
        else:
            await ctx.reply(f"你的游戏账号：{player}")

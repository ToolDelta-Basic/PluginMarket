"""玩家-QQ绑定模块，提供验证码验证流程与绑定管理服务。"""
import json
import os
import time
import random
import string
from typing import Optional, Dict

from ...core.module import Module
from ...core.decorators import command
from ...core.events import GameChatEvent


class BindingService:
    """绑定数据存取与校验核心。"""

    def __init__(self, data_dir: str):
        self._file = os.path.join(data_dir, "bindings.json")
        self._bindings: Dict[int, str] = {}          # qq -> 游戏名
        self._pending_codes: Dict[str, tuple] = {}   # 游戏名 -> (验证码, 过期时间戳)
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
        """为玩家生成 6 位数字验证码（5 分钟有效）。"""
        code = "".join(random.choices(string.digits, k=6))
        self._pending_codes[player_name] = (code, time.time() + 300)
        return code

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
    """玩家-QQ绑定模块，提供 .绑定 命令并监听游戏内 #绑定 请求。"""

    name = "player_binding"
    tier = 300  # TIER_APP  # 用户应用层
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
    async def on_game_chat(self, event: GameChatEvent):
        """监听游戏内 #绑定 请求，生成验证码并发送 tellraw。"""
        msg = (event.message or "").strip()
        if not msg:
            return
        if msg == "#绑定":
            player = event.player_name
            existing_qq = self.binding_service.get_qq_by_player(player)
            if existing_qq:
                self.adapter.send_game_message(
                    player, "§c你已经绑定了QQ号，不能重复绑定。"
                )
                return
            code = self.binding_service.generate_code(player)
            # 使用 json.dumps 安全转义玩家名中的特殊字符
            safe_player = json.dumps(player, ensure_ascii=False)
            safe_code = json.dumps(str(code), ensure_ascii=False)
            tellraw = (
                f'/tellraw {safe_player} {{"rawtext":[{{"text":"§a你的绑定验证码是：'
                f'§e{safe_code}§a，请在QQ群发送：.绑定 {safe_player} {safe_code}"}}]}}'
            )
            self.adapter.send_game_command(tellraw)
            self.adapter.send_game_command(
                f'/tellraw {safe_player} {{"rawtext":[{{"text":"§7验证码有效期为 5 分钟"}}]}}'
            )

    # ---------- QQ 命令 ----------
    @command(".绑定")
    async def _cmd_qq_bind(self, ctx):
        """处理 .绑定 命令，校验验证码并完成绑定。"""
        if self.binding_service.is_bound(ctx.user_id):
            await ctx.reply("你已经绑定了游戏账号，不能重复绑定。")
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

"""自主封禁系统：基于游戏指令 + 本地记录实现封禁/解封/踢出。

原猎户座插件不提供 API 入口，本模块使用游戏原生命令驱动封禁逻辑，
配合 PlayerJoinEvent 监听实现进服自动拦截。

命令:
  .封禁 <玩家名> [原因] [时长分钟]  — 封禁玩家（管理员）
  .解封 <玩家名>                      — 解除封禁（管理员）
  .封禁列表                           — 查看封禁列表（管理员）
  .踢出 <玩家名> [原因]              — 踢出玩家（管理员）

所有封禁/解封/踢出操作写入审计日志。
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from ...core.module import Module
from ...core.kernel.decorators import command
from ...core.kernel.events import PlayerJoinEvent
from ...core.kernel.defguard import escape_player_name
from ...core.kernel.sanitize import sanitize_player_name, sanitize_game_command_param
from ...core.kernel.audit import audit_log, AuditLevel

_log = logging.getLogger(__name__)

# ── 安全限制 ──
_MAX_REASON_LENGTH = 500
# 控制字符正则（保留常用换行/制表符）
_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def _sanitize_reason(reason: str) -> str:
    """清洗封禁理由：限制长度 + 移除控制字符。

    Args:
        reason: 原始封禁理由。

    Returns:
        清洗后的安全理由字符串。
    """
    if not reason:
        return ""
    reason = _CONTROL_CHAR_RE.sub("", reason)
    if len(reason) > _MAX_REASON_LENGTH:
        reason = reason[:_MAX_REASON_LENGTH]
    return reason


class BanStore:
    """封禁记录持久化存储，每玩家一个 JSON 文件。"""

    def __init__(self, data_dir: str) -> None:
        self._dir = os.path.join(data_dir, "封禁")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, player: str) -> str:
        """返回指定玩家的封禁记录文件路径。"""
        # 文件名以玩家名命名，转小写统一防大小写绕过
        return os.path.join(self._dir, f"{player.lower()}.json")

    def get(self, player: str) -> Optional[Dict[str, Any]]:
        """获取玩家封禁记录，不存在或已过期返回 None。

        JSON 加载失败时不崩溃，降级返回 None。
        """
        path = self._path(player)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            _log.warning(
                "封禁记录 JSON 损坏 %s: %s，已移除", path, e
            )
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        # 验证 record 是 dict（防止非 dict JSON 导致后续崩溃）
        if not isinstance(record, dict):
            _log.warning("封禁记录格式异常 %s，已移除", path)
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        duration = record.get("duration", -1)
        # 防御性处理 duration <= 0：视为永久封禁（不过期）
        if duration is None or duration <= 0:
            return record
        # duration > 0：检查是否已过期
        end_time = record.get("timestamp", 0) + duration
        if time.time() >= end_time:
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        return record

    def set(self, player: str, record: Dict[str, Any]) -> None:
        """写入封禁记录。

        写入前清洗 reason 字段（长度限制 + 控制字符移除）。
        """
        record.setdefault("timestamp", time.time())
        record["player"] = player
        # ── 清洗封禁理由 ──
        if "reason" in record and record["reason"]:
            record["reason"] = _sanitize_reason(str(record["reason"]))
        try:
            with open(self._path(player), "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except (OSError, TypeError) as e:
            _log.error("写入封禁记录失败 %s: %s", player, e)

    def remove(self, player: str) -> bool:
        """删除封禁记录，返回是否成功。"""
        path = self._path(player)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有有效封禁记录。"""
        result: List[Dict[str, Any]] = []
        for fname in os.listdir(self._dir):
            if not fname.endswith(".json"):
                continue
            player = fname[:-5]
            record = self.get(player)
            if record:
                result.append(record)
            else:
                # 过期记录清理
                full = os.path.join(self._dir, fname)
                try:
                    os.remove(full)
                except OSError:
                    pass
        return result


class OrionBridge(Module):
    """自主封禁模块：使用原生游戏指令 + 本地 JSON 记录。"""

    name = "orion_bridge"
    tier = 100  # TIER_DAEMON  # daemon: 系统守护
    version = (2, 0, 0)
    required_services = ["config", "adapter", "message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._store: Optional[BanStore] = None

    # ── 生命周期 ────────────────────────────────────────────

    async def on_init(self) -> None:
        """初始化封禁存储、注册命令和事件监听。"""

        async def _dbg_status() -> str:
            """调试端点。"""
            bans = self._store.list_all() if self._store else []
            return str({
                "total_bans": len(bans),
                "sample": [
                    f'{b["player"]}({b.get("reason", "")})'
                    for b in bans[:5]
                ],
            })

        try:
            debug = self.services.get("debug")
            await debug.register_module(self.name, {"status": _dbg_status})
        except KeyError:
            pass

        self._store = BanStore(self.data_dir)

        # 注册为全局服务，供其他模块调用
        self._root_services.register("orion_bridge", self, uid=100,
                               _caller="qqlinker_framework.modules.security.orion")

        self.listen("PlayerJoinEvent", self._on_player_join, priority=10)

    # ── 机器可调用接口（其他模块绑定用）────────────────────

    @staticmethod
    def _build_kick_command(player: str, reason: str) -> str:
        """安全构建 kick 命令，使用参数化接口。

        所有参数经过 sanitize_player_name / sanitize_game_command_param
        清洗后再拼入命令字符串。
        """
        safe_player = sanitize_player_name(player)
        safe_reason = sanitize_game_command_param(
            reason, allow_spaces=True
        )
        return f'kick "{escape_player_name(safe_player)}" {safe_reason}'

    def ban_player(
        self, player: str, reason: str = "", duration: int = -1,
    ) -> None:
        """公开封禁 API（供 auditor 等外部模块调用）。

        等效于 add_ban_with_reason，语义更清晰的命名。
        """
        self.add_ban_with_reason(player, reason=reason, duration=duration)

    def add_ban_with_reason(
        self, player: str, reason: str = "", duration: int = -1,
    ) -> None:
        """提供给其他模块调用的编程式封禁接口。

        Args:
            player: 玩家名。
            reason: 封禁原因（经过安全清洗）。
            duration: 时长（分钟），-1 表示永久。
        """
        # 清洗输入
        safe_player = sanitize_player_name(player)
        safe_reason = sanitize_game_command_param(
            reason, allow_spaces=True
        ) or "系统封禁"

        # 防御性校验：duration 必须为 -1（永久）或正整数（分钟）
        if not isinstance(duration, int):
            _log.error("add_ban_with_reason: duration 类型错误 (期望 int, 得到 %s)", type(duration).__name__)
            duration = -1
        if duration < -1 or duration == 0:
            _log.warning("add_ban_with_reason: duration=%d 非法，修正为 -1 (永久)", duration)
            duration = -1
        duration_seconds = -1 if duration <= 0 else duration * 60
        self._store.set(safe_player, {
            "player": safe_player,
            "reason": safe_reason,
            "duration": duration_seconds,
            "operator": "AI_Auditor",
        })
        # 通过参数化接口构建命令
        cmd = self._build_kick_command(
            safe_player, f"§c你已被封禁：{safe_reason}"
        )
        self.adapter.send_game_command(cmd)

        # 审计日志
        audit_log(
            sender="AI_Auditor",
            action="ban_programmatic",
            target=safe_player,
            detail=f"duration={duration}min reason={safe_reason[:100]}",
            level=AuditLevel.WARNING,
        )

        _log.info(
            "编程式封禁 %s (时长=%d分钟): %s",
            safe_player, duration, safe_reason,
        )

    # ── 进服拦截 ────────────────────────────────────────────

    async def _on_player_join(self, event: PlayerJoinEvent) -> None:
        """玩家进服时检查封禁状态，被封则自动踢出。"""
        player = sanitize_player_name(event.player_name)
        record = self._store.get(player)
        if not record:
            return

        reason = sanitize_game_command_param(
            record.get("reason", "已被封禁"), allow_spaces=True
        )
        duration = record.get("duration", -1)
        if duration > 0:
            end_time = record.get("timestamp", 0) + duration
            remain = int(end_time - time.time())
            time_str = self._fmt_duration(remain)
            msg = f"§c你已被封禁至 {time_str}：{reason}"
        else:
            msg = f"§c你已被永久封禁：{reason}"

        cmd = self._build_kick_command(player, msg)
        self.adapter.send_game_command(cmd)
        _log.info("进服拦截 %s: %s", player, reason)

    # ── 命令处理 ────────────────────────────────────────────

    @command(".封禁", op_only=True)
    async def _cmd_ban(self, ctx) -> None:
        """封禁玩家：记录 + 踢出。"""
        args = ctx.args
        if len(args) < 1:
            await ctx.reply("用法：.封禁 <玩家名> [原因] [时长(分钟), -1=永久]")
            return

        player = sanitize_player_name(args[0])
        reason = sanitize_game_command_param(
            args[1] if len(args) > 1 else "管理员操作",
            allow_spaces=True,
        )
        duration = -1  # 默认永久
        if len(args) > 2:
            try:
                duration = int(args[2])
                if duration > 0:
                    duration *= 60  # 分钟 → 秒
                else:
                    duration = -1
            except ValueError:
                await ctx.reply("时长格式错误，请输入整数分钟数或 -1")
                return

        self._store.set(player, {
            "player": player,
            "reason": reason,
            "duration": duration,
            "operator": ctx.nickname,
        })

        # 通过参数化接口构建踢出命令
        time_str = "永久" if duration == -1 else self._fmt_duration(duration)
        cmd = self._build_kick_command(
            player, f"§c你已被封禁至 {time_str}：{reason}"
        )
        self.adapter.send_game_command(cmd)

        # 审计日志
        audit_log(
            sender=str(ctx.user_id),
            action="ban",
            target=player,
            detail=f"duration={duration}s reason={reason[:100]}",
            level=AuditLevel.WARNING,
            group_id=ctx.group_id,
        )

        await ctx.reply(f"✅ 已封禁 {player}（{time_str}）：{reason}")
        _log.info(
            "封禁 %s by %s (时长=%d): %s",
            player, ctx.nickname, duration, reason,
        )

    @command(".解封", op_only=True)
    async def _cmd_unban(self, ctx) -> None:
        """解除玩家封禁。"""
        if len(ctx.args) < 1:
            await ctx.reply("用法：.解封 <玩家名>")
            return

        player = sanitize_player_name(ctx.args[0])
        if self._store.remove(player):
            # 审计日志
            audit_log(
                sender=str(ctx.user_id),
                action="unban",
                target=player,
                detail=f"by_{ctx.nickname}",
                level=AuditLevel.WARNING,
                group_id=ctx.group_id,
            )
            await ctx.reply(f"✅ 已解封 {player}")
            _log.info("解封 %s by %s", player, ctx.nickname)
        else:
            await ctx.reply(f"{player} 没有被封禁记录")

    @command(".封禁列表", op_only=True)
    async def _cmd_banlist(self, ctx) -> None:
        """查看当前封禁列表。"""
        bans = self._store.list_all()
        if not bans:
            await ctx.reply("封禁列表为空")
            return

        lines = [f"封禁列表（共 {len(bans)} 条）："]
        for b in bans[:15]:
            player = b.get("player", "?")
            reason = b.get("reason", "无")
            duration = b.get("duration", -1)
            time_str = "永久" if duration == -1 else self._fmt_duration(duration)
            lines.append(f"  · {player} [{time_str}] {reason}")

        if len(bans) > 15:
            lines.append(f"  ... 及其他 {len(bans) - 15} 条")
        await ctx.reply("\n".join(lines))

    @command(".踢出", op_only=True)
    async def _cmd_kick(self, ctx) -> None:
        """踢出在线玩家（不封禁）。"""
        args = ctx.args
        if len(args) < 1:
            await ctx.reply("用法：.踢出 <玩家名> [原因]")
            return

        player = sanitize_player_name(args[0])
        reason = sanitize_game_command_param(
            args[1] if len(args) > 1 else "管理员操作",
            allow_spaces=True,
        )
        cmd = self._build_kick_command(player, reason)
        self.adapter.send_game_command(cmd)

        # 审计日志
        audit_log(
            sender=str(ctx.user_id),
            action="kick",
            target=player,
            detail=f"reason={reason[:100]}",
            level=AuditLevel.INFO,
            group_id=ctx.group_id,
        )

        await ctx.reply(f"✅ 已踢出 {player}")

    # ── 工具 ────────────────────────────────────────────────

    @staticmethod
    def _fmt_duration(seconds: int) -> str:
        """将秒数格式化为可读的时间字符串。"""
        if seconds <= 0:
            return "永久"
        parts = []
        for unit, secs in [("天", 86400), ("时", 3600), ("分", 60)]:
            val, seconds = divmod(seconds, secs)
            if val:
                parts.append(f"{val}{unit}")
        if seconds:
            parts.append(f"{seconds}秒")
        return "".join(parts) if parts else "0秒"

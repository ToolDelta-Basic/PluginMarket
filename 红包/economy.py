"""经济计分板读写网关。"""

from __future__ import annotations

from typing import Any

from .models import player_identity


class ScoreboardEconomy:
    """集中封装带结果校验的计分板余额变更。"""

    def __init__(self, plugin: Any) -> None:
        """保存插件实例以访问计分板和在线玩家。"""
        self.plugin = plugin

    def get_balance(self, player: Any) -> int | None:
        """读取玩家余额，失败时向玩家说明原因。"""
        try:
            return int(player.getScore(self.plugin.scoreboard_name, timeout=5))
        except TimeoutError:
            player.show("§c查询余额超时，请稍后重试§r")
        except (ValueError, TypeError):
            player.show(
                f"§c无法读取经济计分板 §e「{self.plugin.scoreboard_name}」"
                "§c，请联系管理员§r"
            )
        except Exception as err:
            self.plugin.print_war(f"查询玩家 {player.name} 余额失败: {err}")
            player.show("§c查询余额失败，请稍后重试§r")
        return None

    def change_score(self, target: str, amount: int) -> bool:
        """增减目标分数并返回命令是否成功。"""
        action = "add" if amount >= 0 else "remove"
        value = abs(amount)
        command = (
            f"/scoreboard players {action} {target} "
            f"{self.plugin.scoreboard_name} {value}"
        )
        try:
            result = self.plugin.game_ctrl.sendwscmd_with_resp(command, 5)
            return bool(getattr(result, "SuccessCount", 0))
        except Exception as err:
            self.plugin.print_war(f"执行经济计分板命令失败: {err}")
            return False

    def find_online_player(self, identity: str) -> Any | None:
        """按稳定身份键查找在线玩家。"""
        try:
            players = self.plugin.game_ctrl.players.getAllPlayers()
        except Exception:
            return None
        return next(
            (player for player in players if player_identity(player) == identity),
            None,
        )

    @staticmethod
    def quoted_name(name: str) -> str:
        """转义并引用离线计分板玩家名。"""
        escaped = name.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

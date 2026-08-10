"""红包命令参数校验和缺参询问。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import MAX_SCORE, RedPacketRequest
from .text_validation import require_valid_characters


CANCEL_WORDS = {"q", "取消"}


class CommandCollector:
    """把聊天栏菜单传入的字符串参数整理成创建请求。"""

    def __init__(
        self,
        player: Any,
        args: tuple[Any, ...],
        set_prompting: Callable[[bool], None],
    ) -> None:
        """保存玩家和最多三个命令参数。"""
        values = [str(value) for value in args[:3]]
        self.values = values + [""] * (3 - len(values))
        self.player = player
        self.set_prompting = set_prompting

    def collect(self) -> RedPacketRequest | None:
        """校验已有参数并逐项询问缺失值。"""
        interactive = any(value == "" for value in self.values)
        if interactive:
            self.set_prompting(True)
        try:
            amount = self._value(
                0,
                self._parse_amount,
                "§e请输入红包总金额（正整数）：§r",
            )
            if amount is None:
                return None
            count = self._value(
                1,
                lambda value: self._parse_count(value, amount),
                f"§e请输入红包份数（1～{amount}）：§r",
            )
            if count is None:
                return None
            phrase = self._value(
                2,
                self._parse_phrase,
                "§e请输入红包口令（单个词）：§r",
            )
            if phrase is None:
                return None
            return RedPacketRequest(amount, count, phrase)
        finally:
            if interactive:
                self.set_prompting(False)

    def _value(
        self,
        index: int,
        parser: Callable[[str], Any],
        prompt: str,
    ) -> Any | None:
        """取得并解析一个参数，交互输入失败时允许重试。"""
        supplied = self.values[index]
        if supplied != "":
            try:
                return parser(require_valid_characters(supplied))
            except ValueError as err:
                self.player.show(f"§c{err}§r")
                return None
        while True:
            response = self.player.input(prompt, timeout=60)
            if response is None:
                self.player.show("§c等待输入超时，已取消发送红包§r")
                return None
            response = str(response)
            try:
                require_valid_characters(response)
            except ValueError as err:
                self.player.show(f"§c{err}§r")
                continue
            response = response.strip()
            if response.casefold() in CANCEL_WORDS:
                self.player.show("§7已取消发送红包§r")
                return None
            try:
                return parser(response)
            except ValueError as err:
                self.player.show(f"§c{err}§r")

    @staticmethod
    def _parse_amount(value: str) -> int:
        """解析红包总金额。"""
        try:
            amount = int(value)
        except ValueError as err:
            raise ValueError("红包金额必须是整数") from err
        if not 1 <= amount <= MAX_SCORE:
            raise ValueError(f"红包金额必须在 1～{MAX_SCORE} 之间")
        return amount

    @staticmethod
    def _parse_count(value: str, amount: int) -> int:
        """解析红包份数并确保总金额足够分配。"""
        try:
            count = int(value)
        except ValueError as err:
            raise ValueError("红包份数必须是整数") from err
        if not 1 <= count <= amount:
            raise ValueError(f"红包份数必须在 1～{amount} 之间")
        return count

    @staticmethod
    def _parse_phrase(value: str) -> str:
        """解析单词形式的红包口令。"""
        phrase = value.strip()
        if not 1 <= len(phrase) <= 32:
            raise ValueError("红包口令长度必须为 1～32 个字符")
        if any(character.isspace() for character in phrase):
            raise ValueError("红包口令不能包含空格")
        return phrase

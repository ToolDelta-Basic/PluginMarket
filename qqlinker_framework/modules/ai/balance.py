"""AI 余额管理系统

提供群维度的 TOKEN 余额管理，支持查询、消费、充值。
存储于 data/ai/balances.json，以 group_id 为键。
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Optional

_logger = logging.getLogger(__name__)


class Balancer:
    """群级 TOKEN 余额管理器。

    默认禁用。启用后 AI 工具调用需消耗余额，
    余额不足时通过 reject_service 工具拒绝。

    Attributes:
        _enabled: 余额制是否启用。
        _default_balance: 新建群的默认初始余额。
        _token_price: 每 TOKEN 扣除的余额点数。
        _balances: 内存中的余额映射 {group_id: float}。
        _file: 持久化路径。
        _lock: 异步锁。
    """

    def __init__(
        self,
        data_dir: str,
        *,
        enabled: bool = False,
        default_balance: float = 0.0,
        token_price: float = 1.0,
    ) -> None:
        self._enabled = enabled
        self._default_balance = default_balance
        self._token_price = token_price
        self._balances: Dict[int, float] = {}
        self._file = os.path.join(data_dir, "balances.json")
        self._lock = asyncio.Lock()
        self._stats_dir = os.path.join(data_dir, "统计")
        os.makedirs(self._stats_dir, exist_ok=True)
        self._load()

    # ── 属性访问 ──────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def token_price(self) -> float:
        return self._token_price

    @token_price.setter
    def token_price(self, value: float) -> None:
        self._token_price = value

    # ── 持久化 ────────────────────────────────────────────

    def _load(self) -> None:
        """从磁盘加载余额。"""
        if not os.path.exists(self._file):
            return
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self._balances = {
                    int(k): float(v) for k, v in raw.items()
                }
        except (json.JSONDecodeError, OSError, ValueError) as e:
            _logger.warning("加载余额文件失败: %s", e)

    async def _save(self) -> None:
        """异步持久化余额（通过线程池避免阻塞事件循环）。"""
        async with self._lock:
            data = dict(self._balances)
        try:
            def _do_write():
                tmp = self._file + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._file)
            await asyncio.to_thread(_do_write)
        except Exception as e:
            _logger.error("保存余额文件失败: %s", e)

    # ── 统计记录 ──────────────────────────────────────────

    async def _record_stat(self, group_id: int, action: str,
                           amount: float) -> None:
        """记录消耗统计到 stats/<group_id>.jsonl。"""
        stat_file = os.path.join(self._stats_dir, f"{group_id}.jsonl")
        entry = {
            "ts": time.time(),
            "action": action,
            "amount": amount,
        }
        try:
            def _append():
                with open(stat_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            await asyncio.to_thread(_append)
        except Exception as e:
            _logger.warning("统计记录失败: %s", e)

    # ── 核心操作 ──────────────────────────────────────────

    async def get(self, group_id: int) -> float:
        """查询群余额。余额制未启用时返回无穷大。

        Args:
            group_id: 群号。

        Returns:
            当前余额。若未启用余额制或余额无限，返回 float('inf')。
        """
        if not self._enabled:
            return float("inf")
        async with self._lock:
            return self._balances.get(group_id, self._default_balance)

    async def spend(self, group_id: int, amount: float = 1.0) -> bool:
        """消费指定数量的余额。

        Args:
            group_id: 群号。
            amount: 消费点数（默认 1.0 = 1 TOKEN）。

        Returns:
            True 表示消费成功；False 表示余额不足或余额制未启用。
        """
        if not self._enabled:
            return True  # 未启用时不限制

        async with self._lock:
            current = self._balances.get(group_id, self._default_balance)
            if current < amount:
                return False
            self._balances[group_id] = current - amount

        await self._record_stat(group_id, "spend", amount)
        await self._save()
        return True

    async def recharge(self, group_id: int, amount: float) -> float:
        """为群充值指定点数。

        Args:
            group_id: 群号。
            amount: 充值点数（正数）。

        Returns:
            充值后的余额。
        """
        if amount <= 0:
            raise ValueError("充值点数必须为正数")

        async with self._lock:
            current = self._balances.get(group_id, self._default_balance)
            self._balances[group_id] = current + amount

        await self._record_stat(group_id, "recharge", amount)
        await self._save()
        return self._balances[group_id]

    async def get_stats(self, group_id: int) -> dict:
        """获取群消耗统计。

        Returns:
            {"total_spent": float, "total_recharged": float, "balance": float}
        """
        stat_file = os.path.join(self._stats_dir, f"{group_id}.jsonl")
        total_spent = 0.0
        total_recharged = 0.0
        if os.path.exists(stat_file):
            try:
                with open(stat_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            if entry.get("action") == "spend":
                                total_spent += entry.get("amount", 0)
                            elif entry.get("action") == "recharge":
                                total_recharged += entry.get("amount", 0)
                        except json.JSONDecodeError:
                            continue
            except OSError:
                pass

        balance = await self.get(group_id)
        if balance == float("inf"):
            balance = "∞ (余额制未启用)"
        return {
            "total_spent": total_spent,
            "total_recharged": total_recharged,
            "balance": balance,
        }

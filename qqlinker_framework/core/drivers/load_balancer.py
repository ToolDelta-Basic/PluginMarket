"""多机器人智能负载均衡 + 哈希路由

═══════════════════════════════════════════════════════════════════════════
 LoadBalancer  — 最少队列优先（Least-Queue），按每机器人消息队列深度选最空闲的
 HashRouter    — hash(group_id) % active_count 固定路由，下线自动重哈希
═══════════════════════════════════════════════════════════════════════════
"""
import hashlib
import logging
import time
from typing import Dict, List, Optional, Tuple

from ...services.ws_client import WsClient, CircuitState

_log = logging.getLogger(__name__)


class LoadBalancer:
    """最少队列优先负载均衡器。

    选择算法:
      1. 过滤掉 circuit_breaker OPEN 的机器人
      2. 选 message_mgr._queue.qsize() 最小的
      3. 同队列深度 → 选令牌桶余量最多的
    """

    def __init__(self):
        # 延迟统计: robot_name → {total_ms, count, p50, p95, ...}
        self._latency_stats: Dict[str, dict] = {}
        self._lock = __import__('threading').Lock()

    @staticmethod
    def select_robot(
        group_id: int,
        robots: Dict[str, dict],
        message_mgrs: Dict[str, object],
    ) -> Optional[str]:
        """选择最适合发送消息的机器人。

        Args:
            group_id: 目标群（供未来加权用）。
            robots: robot_registry._robots 或等价的 {name → info} 映射。
            message_mgrs: {robot_name → MessageManager} 映射。

        Returns:
            选中的机器人名称，无可选时返回 None。
        """
        candidates: List[Tuple[int, float, str]] = []  # (qsize, -tokens, name)
        for name, info in robots.items():
            client = info.get("client")
            if client is None:
                continue
            if isinstance(client, WsClient):
                if client._circuit_state == CircuitState.OPEN or not client.available:
                    continue
            # 获取队列深度
            mgr = message_mgrs.get(name)
            if mgr is None:
                qsize = 0
            else:
                try:
                    qsize = mgr._queue.qsize()
                except Exception:
                    qsize = 0
            # 获取令牌余量
            if mgr is not None:
                try:
                    tokens = mgr._tokens
                except Exception:
                    tokens = 0.0
            else:
                tokens = 0.0
            # 按 (qsize ASC, tokens DESC) 排序：越小越好
            candidates.append((qsize, -tokens, name))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def record_latency(self, robot_name: str, latency_ms: float):
        """记录一次成功发送的延迟（毫秒）。"""
        import threading
        with self._lock:
            s = self._latency_stats.setdefault(robot_name, {
                "total_ms": 0.0, "count": 0,
                "samples": [], "last_updated": time.time(),
            })
            s["total_ms"] += latency_ms
            s["count"] += 1
            s["samples"].append(latency_ms)
            if len(s["samples"]) > 100:
                s["samples"] = s["samples"][-100:]
            s["last_updated"] = time.time()

    def get_stats(self) -> dict:
        """返回每个机器人的负载统计。"""
        result = {}
        with self._lock:
            for name, s in self._latency_stats.items():
                count = s["count"]
                avg = s["total_ms"] / count if count > 0 else 0
                samples = sorted(s["samples"]) if s["samples"] else []
                p50 = samples[len(samples) // 2] if samples else 0
                p95 = samples[int(len(samples) * 0.95)] if len(samples) > 1 else p50
                result[name] = {
                    "count": count,
                    "avg_latency_ms": round(avg, 2),
                    "p50_ms": round(p50, 2),
                    "p95_ms": round(p95, 2),
                    "last_updated": s.get("last_updated", 0),
                }
        return result

    def reset(self):
        """重置所有统计数据。"""
        with self._lock:
            self._latency_stats.clear()


class HashRouter:
    """简单哈希路由：hash(group_id) % active_count → 固定机器人。

    机器人下线 → 重新 hash 到剩余的。
    """

    def __init__(self):  # noqa: PYL-R0201
        pass

    @staticmethod
    def _hash_group(group_id: int) -> int:
        """计算群 ID 的哈希值。"""
        h = hashlib.md5(str(group_id).encode()).hexdigest()
        return int(h[:8], 16)

    def get_robot(
        self, group_id: int, robots: Dict[str, dict]
    ) -> Optional[str]:
        """为目标群选择一个固定的机器人（基于哈希）。

        Args:
            group_id: 目标群。
            robots: robot_registry._robots 映射。

        Returns:
            选中的机器人名称，无可选时返回 None。
        """
        active: List[str] = []
        for name, info in robots.items():
            client = info.get("client")
            if client is None:
                continue
            if isinstance(client, WsClient):
                if client._circuit_state == CircuitState.OPEN or not client.available:
                    continue
            active.append(name)
        if not active:
            return None
        idx = self._hash_group(group_id) % len(active)
        return active[idx]

    def rehash_on_removal(
        self, group_id: int, removed: str, robots: Dict[str, dict]
    ) -> Optional[str]:
        """当指定机器人被移除后，重新为群计算路由。"""
        remaining = {
            name: info for name, info in robots.items() if name != removed
        }
        return self.get_robot(group_id, remaining)

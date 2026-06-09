"""多机器人一致性守卫 — 交叉验证、健康互检、发送确认 + 故障转移

═══════════════════════════════════════════════════════════════════════════
 当框架连接了多个 QQ 机器人时，启用以下防御机制：
   1. 去重交叉验证 — N 个机器人中至少 M 个收到同一消息才放行
   2. 发送确认监督 — 发消息后监听回显，失败自动故障转移到下一个机器人
   3. 机器人健康互检 — 定期互发心跳，探测死连接

 SendGuard v2 (多机器人智能发送 + ACK + 故障转移):
   - send_with_ack()         → 选机器人 → 发送 → 等回显 → 失败重试
   - on_echo()               → 收到回显 → 标记确认
   - on_failure()            → 发送失败 → 故障转移
   - _auto_failover()        → 自动切换到下一机器人重试
═══════════════════════════════════════════════════════════════════════════
"""
import logging
import threading
import time
import uuid
from typing import Dict, List, Optional

_log = logging.getLogger(__name__)


class RobotRegistry:
    """多机器人注册表 — 管理所有活跃的机器人连接。"""

    def __init__(self):
        self._robots: Dict[str, dict] = {}  # name → {client, group_ids, last_seen, ...}
        self._lock = threading.Lock()

    def register(self, name: str, client, group_ids: list):
        with self._lock:
            self._robots[name] = {
                "client": client,
                "group_ids": set(group_ids),
                "last_seen": time.time(),
                "msg_count": 0,
            }
        _log.info("[机器人] 已注册: %s (群: %s)", name, ", ".join(map(str, group_ids)))

    def remove(self, name: str):
        with self._lock:
            self._robots.pop(name, None)

    def touch(self, name: str):
        with self._lock:
            if name in self._robots:
                self._robots[name]["last_seen"] = time.time()

    @property
    def count(self) -> int:
        return len(self._robots)

    @property
    def robots(self) -> Dict[str, dict]:
        """返回 robots 字典的浅拷贝（线程安全读取）。"""
        with self._lock:
            return dict(self._robots)

    def get_client(self, name: str):
        """线程安全地获取指定机器人的 WsClient。"""
        with self._lock:
            info = self._robots.get(name)
            return info["client"] if info else None

    def get_overlapping_robots(self, group_id: int) -> List[str]:
        """返回覆盖指定群的所有机器人名称。"""
        with self._lock:
            return [
                name for name, info in self._robots.items()
                if group_id in info["group_ids"]
            ]

    def increment_msg_count(self, name: str):
        """增长机器人消息计数。"""
        with self._lock:
            if name in self._robots:
                self._robots[name]["msg_count"] += 1

    def health_check(self, timeout: float = 30.0) -> Dict[str, str]:
        """返回每个机器人的健康状态: online / timeout / disconnected。"""
        now = time.time()
        result = {}
        with self._lock:
            for name, info in self._robots.items():
                client = info["client"]
                if not client.available:
                    result[name] = "disconnected"
                elif now - info["last_seen"] > timeout:
                    result[name] = "timeout"
                else:
                    result[name] = "online"
        return result


class CrossValidation:
    """跨机器人消息验证 — 去重 + 一致性检查。"""

    def __init__(self, robot_registry: RobotRegistry,
                 quorum: int = 1):
        self._registry = robot_registry
        self._quorum = quorum  # 最少需要几个机器人确认
        self._pending: Dict[str, dict] = {}  # msg_id → {seen_by: set, data: dict, timer: ...}
        self._lock = threading.Lock()

    @staticmethod
    def content_id(raw: dict) -> str:
        """基于消息内容计算逻辑 ID（跨机器人/跨后端去重）。

        当 msg_id 为空或不可靠时，用于 fallback 去重。
        """
        import hashlib
        parts = [
            str(raw.get("group_id", "")),
            str(raw.get("user_id", "")),
            str(raw.get("time", raw.get("self_id", ""))),
            (raw.get("message", raw.get("raw_message", "")) or "")[:20],
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]

    def _effective_quorum(self) -> int:
        """返回实际需要的 quorum 数（不超过在线机器人数）。"""
        online = sum(
            1 for s in self._registry.health_check(timeout=15).values()
            if s == "online"
        )
        return min(self._quorum, online) if online > 0 else 1

    def witness(self, msg_id: str, robot_name: str,
                group_id: int, data: dict) -> Optional[dict]:
        """一个机器人见证了某条消息。

        Returns:
            如果达到有效 quorum 则返回 data（放行），否则返回 None（暂存）。
        """
        # 如果 msg_id 为空或不可靠，用内容 hash 作为 fallback 逻辑 ID
        if not msg_id:
            msg_id = self.content_id(data)

        eff_q = self._effective_quorum()
        with self._lock:
            entry = self._pending.get(msg_id)
            if entry is None:
                # 首次见证
                self._pending[msg_id] = {
                    "seen_by": {robot_name},
                    "data": data,
                    "time": time.time(),
                }
                if eff_q <= 1:
                    del self._pending[msg_id]
                    return data
                return None

            entry["seen_by"].add(robot_name)
            if len(entry["seen_by"]) >= eff_q:
                del self._pending[msg_id]
                return entry["data"]
            return None

    def cleanup_stale(self, timeout: float = 10.0):
        """清理超时未达 quorum 的暂存消息。"""
        now = time.time()
        with self._lock:
            stale = [mid for mid, e in self._pending.items()
                     if now - e["time"] > timeout]
            for mid in stale:
                del self._pending[mid]
            if stale:
                _log.debug("[交叉验证] 清理 %d 条超时消息", len(stale))


class SendGuard:
    """发送确认 + 故障转移 — 发消息后监听回显，失败自动切换到下一个机器人。

    v2 新增:
      - send_with_ack(): 完整的发送→确认→重试→故障转移流程
      - on_echo(): 收到 OneBot 回显/已发送消息的回显 → 标记确认
      - on_failure(): 机器人发送失败 → 触发故障转移
      - 支持多级确认：OneBot 响应 ACK + 其他机器人回显 ACK
    """

    # 回显确认超时（秒）
    ECHO_TIMEOUT = 8.0
    # 已确认记录清理超时（秒）
    CONFIRMED_TTL = 60.0
    # 最大重试次数
    DEFAULT_MAX_RETRIES = 2

    def __init__(self, robot_registry: RobotRegistry,
                 load_balancer=None,
                 hash_router=None,
                 max_retries: int = DEFAULT_MAX_RETRIES):
        self._registry = robot_registry
        self._load_balancer = load_balancer
        self._hash_router = hash_router
        self._max_retries = max_retries

        # 发送记录: {msg_id → {robot, status, time, retries, group_id, message, echo_id, confirm_count}}
        self._sent: Dict[str, dict] = {}
        # 待确认记录: {echo_id → {sender, group_id, confirmations, time, retries, message, msg_id}}
        self._pending: Dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── 消息发送 ACK ────────────────────────────────────────

    def send_with_ack(
        self,
        group_id: int,
        message: str,
        priority: int = 0,
    ) -> bool:
        """发送消息并在其他机器人中确认收到回显。

        选机器人 → 发送 → 注册 echo_id → 等待回显。
        如果超时未确认 → 自动故障转移到下一个机器人重试（最多 max_retries 次）。

        Args:
            group_id: 目标群。
            message: 消息内容。
            priority: 优先级（0=高, 1=普通, 2=低）。

        Returns:
            True 如果至少有一个机器人发送成功且被确认。
        """
        msg_id = f"sg_{uuid.uuid4().hex[:12]}"
        robots_dict = self._registry.robots

        if not robots_dict:
            _log.warning("[SendGuard] 无可用机器人，消息发送失败")
            return False

        # 选择初始机器人
        robot_name = None
        if self._load_balancer is not None:
            # 获取 message_mgrs 映射（从外部注入或从 registry 获取）
            robot_name = self._get_best_robot(group_id, robots_dict)
        elif self._hash_router is not None:
            robot_name = self._hash_router.get_robot(group_id, robots_dict)
        else:
            # Fallback: 选第一个可用的
            for name in self._get_available_robots(robots_dict):
                robot_name = name
                break

        if robot_name is None:
            _log.warning("[SendGuard] 无可用机器人（全部离线或熔断），消息发送失败")
            return False

        # 尝试发送（含故障转移）
        tried: List[str] = []
        current = robot_name
        retries = 0

        with self._lock:
            self._sent[msg_id] = {
                "robot": current,
                "status": "pending",
                "time": time.time(),
                "retries": 0,
                "group_id": group_id,
                "message": message,
            }

        while retries <= self._max_retries:
            if current in tried:
                # 已尝试过，找下一个
                next_robot = self._get_next_robot(current, tried, robots_dict)
                if next_robot is None:
                    with self._lock:
                        if msg_id in self._sent:
                            self._sent[msg_id]["status"] = "failed"
                    _log.error(
                        "[SendGuard] 所有机器人均发送失败 (已尝试: %s, retries=%d)",
                        ", ".join(tried), retries,
                    )
                    return False
                current = next_robot

            tried.append(current)
            echo_id = f"echo_{current}_{msg_id}_{int(time.time()*1000)}"

            # 实际发送
            client = self._registry.get_client(current)
            if client is None or not getattr(client, "available", False):
                _log.warning("[SendGuard] 机器人 %s 不可用，跳过", current)
                retries += 1
                self._on_send_fail(msg_id, current, group_id, message, "unavailable")
                continue

            send_ok = False
            try:
                send_ok = client.send_group_msg(group_id, message)
            except Exception as e:
                _log.error("[SendGuard] 机器人 %s 发送异常: %s", current, e)

            if not send_ok:
                _log.warning("[SendGuard] 机器人 %s 发送失败，触发故障转移", current)
                self._on_send_fail(msg_id, current, group_id, message, "send_failed")
                retries += 1
                continue

            # 注册待确认
            with self._lock:
                self._pending[echo_id] = {
                    "sender": current,
                    "group_id": group_id,
                    "confirmations": set(),
                    "time": time.time(),
                    "retries": retries,
                    "message": message,
                    "msg_id": msg_id,
                }
                self._sent[msg_id]["robot"] = current
                self._sent[msg_id]["retries"] = retries
                self._sent[msg_id]["echo_id"] = echo_id

            _log.info(
                "[SendGuard] %s → group_id=%s (echo=%s, retry=%d/%d)",
                current, group_id, echo_id, retries, self._max_retries,
            )

            # 等待回显确认
            confirmed = self._wait_for_echo(echo_id, self.ECHO_TIMEOUT)
            if confirmed:
                with self._lock:
                    self._sent[msg_id]["status"] = "confirmed"
                    self._sent[msg_id]["confirm_count"] = self._sent[msg_id].get("confirm_count", 0) + 1
                    self._registry.increment_msg_count(current)
                _log.info(
                    "[SendGuard] ✅ 消息 %s 发送成功 (机器人=%s, 确认数=%d)",
                    msg_id, current,
                    self._sent[msg_id].get("confirm_count", 0),
                )
                return True

            # 超时未确认 → 重试
            _log.warning(
                "[SendGuard] 机器人 %s 的消息 %s 超时未确认 (%.1fs)，准备故障转移",
                current, echo_id, self.ECHO_TIMEOUT,
            )
            self._on_send_fail(msg_id, current, group_id, message, "echo_timeout")
            retries += 1

        # 所有重试用尽
        with self._lock:
            if msg_id in self._sent:
                self._sent[msg_id]["status"] = "failed_exhausted"
        _log.error(
            "[SendGuard] ❌ 消息 %s 经 %d 次重试后仍发送失败",
            msg_id, self._max_retries,
        )
        return False

    def _get_best_robot(self, group_id: int, robots_dict: dict) -> Optional[str]:
        """使用负载均衡器选择最佳机器人。"""
        if self._load_balancer is None:
            return None
        # LoadBalancer.select_robot 需要 robots_dict + message_mgrs
        # message_mgrs 通过外部注册提供
        from .. import host as _host_mod
        try:
            return self._load_balancer.select_robot(
                group_id, robots_dict, getattr(self, '_msg_mgrs', {}),
            )
        except Exception as e:
            _log.debug("[SendGuard] 负载均衡器选择失败: %s", e)
            return None

    def _get_next_robot(
        self, current: str, tried: List[str], robots_dict: dict
    ) -> Optional[str]:
        """获取下一个可用的机器人（跳过已尝试和已熔断的）。"""
        available = self._get_available_robots(robots_dict)
        for name in available:
            if name not in tried:
                return name
        return None

    def _get_available_robots(self, robots_dict: dict) -> List[str]:
        """获取所有可用（在线 + 未熔断）的机器人列表。"""
        from ...services.ws_client import WsClient, CircuitState
        available = []
        for name, info in robots_dict.items():
            client = info.get("client")
            if client is None:
                continue
            if isinstance(client, WsClient):
                if client._circuit_state == CircuitState.OPEN:
                    continue
                if not client.available:
                    continue
            available.append(name)
        return available

    def _wait_for_echo(self, echo_id: str, timeout: float) -> bool:
        """轮询等待回显确认（同步阻塞，在 message_mgr 线程中调用）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                entry = self._pending.get(echo_id)
                if entry is None:
                    # 已被清理（可能已被确认但被其他流程移除了）
                    return True
                if len(entry["confirmations"]) > 0:
                    # 收到确认
                    return True
            time.sleep(0.1)
        return False

    def _on_send_fail(self, msg_id: str, robot_name: str,
                      group_id: int, message: str, reason: str):
        """记录发送失败并清理 pending。"""
        with self._lock:
            if msg_id in self._sent:
                self._sent[msg_id]["status"] = f"fail_{reason}"
                self._sent[msg_id]["robot"] = robot_name
        _log.warning(
            "[SendGuard] 故障转移: %s 发送失败 (原因=%s) → 切换到下一个机器人",
            robot_name, reason,
        )
        # 移除该机器人的所有待确认记录
        with self._lock:
            stale = [
                eid for eid, entry in self._pending.items()
                if entry.get("sender") == robot_name
            ]
            for eid in stale:
                del self._pending[eid]

    # ── 回显回调（由 EventBridge/Adapter 调用）────────────────

    def on_echo(self, robot_name: str, echo_data: dict):
        """收到其他机器人的回显 → 标记该消息已确认发送。

        触发场景:
          1. OneBot 返回 status="ok" + echo 字段（直接 ACK）
          2. 其他机器人收到了该消息的群消息回显（间接 ACK）

        Args:
            robot_name: 报告回显的机器人名称。
            echo_data: 回显数据，可能包含 echo_id, message_id 等。
        """
        echo_id = echo_data.get("echo_id") or echo_data.get("echo") or ""
        if not echo_id:
            return

        with self._lock:
            entry = self._pending.get(echo_id)
            if entry is None:
                # echo_id 不匹配任何待确认记录 → 可能是其他来源的 echo
                return
            entry["confirmations"].add(robot_name)
            count = len(entry["confirmations"])
            _log.info(
                "[SendGuard] ✅ 回显确认: %s 的消息 %s 已被 %s 确认 (总确认数=%d)",
                entry["sender"], echo_id, robot_name, count,
            )

    def on_failure(self, robot_name: str, error: str):
        """机器人发送失败 → 触发故障转移。

        由 WsClient / Adapter 在检测到发送异常时调用。

        Args:
            robot_name: 故障的机器人名称。
            error: 错误描述。
        """
        _log.warning("[SendGuard] ⚡ 机器人 %s 上报故障: %s", robot_name, error)
        # 标记该机器人的所有待确认记录为失败
        with self._lock:
            failed = [
                (eid, entry) for eid, entry in self._pending.items()
                if entry.get("sender") == robot_name
            ]
            for eid, entry in failed:
                _log.info(
                    "[SendGuard] 故障转移: %s 的待确认消息 %s → 重新发送",
                    robot_name, eid,
                )
                # 触发自动故障转移
                self._auto_failover(eid, entry)

    def _auto_failover(self, echo_id: str, entry: dict):
        """自动故障转移: 用剩余机器人重试发送。

        Args:
            echo_id: 原 echo_id。
            entry: 待确认记录。
        """
        group_id = entry["group_id"]
        message = entry["message"]
        original_sender = entry["sender"]
        retries = entry.get("retries", 0)

        if retries >= self._max_retries:
            _log.warning(
                "[SendGuard] 消息 %s 已达最大重试次数 (%d)，放弃故障转移",
                echo_id, self._max_retries,
            )
            with self._lock:
                self._pending.pop(echo_id, None)
            return

        # 找下一个可用机器人
        robots_dict = self._registry.robots
        tried = [original_sender]
        next_robot = self._get_next_robot(original_sender, tried, robots_dict)
        if next_robot is None:
            _log.warning("[SendGuard] 无可用机器人进行故障转移")
            with self._lock:
                self._pending.pop(echo_id, None)
            return

        # 发起重试
        new_echo_id = f"echo_{next_robot}_{echo_id}_{int(time.time()*1000)}"
        client = self._registry.get_client(next_robot)
        if client is None or not getattr(client, "available", False):
            _log.warning("[SendGuard] 故障转移目标 %s 不可用", next_robot)
            with self._lock:
                self._pending.pop(echo_id, None)
            return

        try:
            ok = client.send_group_msg(group_id, message)
            if ok:
                with self._lock:
                    self._pending.pop(echo_id, None)
                    self._pending[new_echo_id] = {
                        "sender": next_robot,
                        "group_id": group_id,
                        "confirmations": set(),
                        "time": time.time(),
                        "retries": retries + 1,
                        "message": message,
                        "msg_id": entry.get("msg_id", ""),
                    }
                _log.info(
                    "[SendGuard] 🔄 故障转移: %s → %s (new_echo=%s, retry=%d/%d)",
                    original_sender, next_robot, new_echo_id,
                    retries + 1, self._max_retries,
                )
            else:
                _log.warning("[SendGuard] 故障转移发送失败: %s", next_robot)
                with self._lock:
                    self._pending.pop(echo_id, None)
        except Exception as e:
            _log.error("[SendGuard] 故障转移异常: %s", e)
            with self._lock:
                self._pending.pop(echo_id, None)

    # ── 统计与维护 ────────────────────────────────────────

    def get_send_stats(self) -> dict:
        """返回发送统计。"""
        with self._lock:
            total = len(self._sent)
            confirmed = sum(
                1 for s in self._sent.values()
                if s.get("status") == "confirmed"
            )
            failed = sum(
                1 for s in self._sent.values()
                if s.get("status", "").startswith("fail")
            )
            pending = sum(
                1 for s in self._sent.values()
                if s.get("status") == "pending"
            )
        return {
            "total": total,
            "confirmed": confirmed,
            "failed": failed,
            "pending": pending,
            "success_rate": round(confirmed / total * 100, 1) if total > 0 else 0,
        }

    def set_message_managers(self, mgrs: dict):
        """注入 message_mgr 映射表（供 LoadBalancer 使用）。"""
        self._msg_mgrs = mgrs

    def get_unconfirmed(self, timeout: float = 10.0) -> List[str]:
        """返回超时未确认的消息发送者（可能发送失败）。"""
        now = time.time()
        failed = []
        with self._lock:
            for eid, entry in list(self._pending.items()):
                if now - entry["time"] > timeout and not entry["confirmations"]:
                    failed.append(entry["sender"])
                    _log.warning(
                        "[发送确认] %s 的消息 %s 超时未确认（可能发送失败）",
                        entry["sender"], eid,
                    )
                    del self._pending[eid]
        return failed

    def cleanup(self, timeout: float = 60.0):
        """清理过期的待确认和已确认记录。"""
        now = time.time()
        with self._lock:
            # 清理待确认
            stale_pending = [
                eid for eid, e in self._pending.items()
                if now - e["time"] > timeout
            ]
            for eid in stale_pending:
                del self._pending[eid]
            # 清理已确认的记录
            stale_sent = [
                mid for mid, s in self._sent.items()
                if now - s["time"] > self.CONFIRMED_TTL
            ]
            for mid in stale_sent:
                del self._sent[mid]
            if stale_pending:
                _log.debug("[SendGuard] 清理 %d 条超时待确认记录", len(stale_pending))

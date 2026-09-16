"""Libra 实时在线权限管理器，不依赖 NeOmega。"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Callable

from .abilities import compare_ability_flags, permission_category, read_player_abilities
from .core import normalize_xuid, parse_flags


class RealtimeManager:
    """观察在线 Player.abilities，并把差异交给 PermissionService 写入。"""

    def __init__(self, owner: Any):
        self.owner = owner
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._callbacks: dict[int, Callable[[dict[str, Any]], Any]] = {}
        self._callback_id = 0
        self._last_write: dict[str, float] = {}
        self._lock = threading.RLock()
        self._verification_xuids: set[str] = set()
        self._verification_lock = threading.RLock()

    def _cfg(self) -> dict[str, Any]:
        value = self.owner.cfg.get("实时管理", {})
        return value if isinstance(value, dict) else {}

    def enabled(self) -> bool:
        return bool(self._cfg().get("是否启用", False))

    def _runtime(self) -> dict[str, Any]:
        value = self.owner.state.setdefault("实时管理", {})
        if not isinstance(value, dict):
            value = {}
            self.owner.state["实时管理"] = value
        value.setdefault("是否运行", False)
        value.setdefault("在线玩家", {})
        value.setdefault("待处理权限动作", [])
        value.setdefault("最近权限修正", [])
        value.setdefault("权限观测", {})
        return value

    def _get_current_players(self) -> list[Any] | None:
        """读取 ToolDelta 当前在线玩家；无法读取时返回 None。"""
        players = getattr(getattr(self.owner, "game_ctrl", None), "players", None)
        getter = getattr(players, "getAllPlayers", None)
        if not callable(getter):
            return None
        try:
            values = getter()
            return list(values or [])
        except Exception:
            return None

    def _sync_online_cache(self, players: list[Any] | None = None) -> tuple[dict[str, Any], bool] | None:
        """以 ToolDelta 在线列表校准运行态缓存，并清理离线观测记录。"""
        if players is None:
            players = self._get_current_players()
        if players is None:
            return None

        current: dict[str, Any] = {}
        for player in players:
            try:
                xuid = normalize_xuid(str(getattr(player, "xuid", "")))
            except ValueError:
                continue
            current.setdefault(xuid, player)

        lock = getattr(self.owner, "state_lock", self._lock)
        with lock:
            runtime = self._runtime()
            old_online = runtime.get("在线玩家", {})
            if not isinstance(old_online, dict):
                old_online = {}
            old_observations = runtime.get("权限观测", {})
            if not isinstance(old_observations, dict):
                old_observations = {}

            now = int(time.time())
            online_cache = {
                xuid: {
                    "玩家名称": str(getattr(player, "name", "")),
                    "最后检查时间": old_online.get(xuid, {}).get("最后检查时间", now)
                    if isinstance(old_online.get(xuid), dict)
                    else now,
                }
                for xuid, player in current.items()
            }
            current_xuids = set(current)
            stale_xuids = set(old_observations) - current_xuids
            runtime["在线玩家"] = online_cache
            runtime["权限观测"] = {
                xuid: record for xuid, record in old_observations.items() if xuid in current_xuids
            }
            changed = old_online != online_cache or bool(stale_xuids)
        return current, changed

    def _managed(self, xuid: str) -> bool:
        managed = self.owner.state.get("持续管理玩家", {})
        if isinstance(managed, dict):
            item = managed.get(xuid)
            if isinstance(item, dict):
                return bool(item.get("是否启用", item.get("启用", True)))
            return bool(item)
        if isinstance(managed, list):
            return xuid in managed
        return False

    def _target(self, xuid: str) -> str | None:
        expected = self.owner.state.get("期望权限", {})
        if not isinstance(expected, dict) or not self._managed(xuid):
            return None
        value = expected.get(xuid)
        try:
            return parse_flags(str(value)).raw
        except (TypeError, ValueError):
            return None

    def _emit(self, event: str, **details: Any) -> None:
        payload = {"事件": event, "时间": int(time.time()), **details}
        try:
            self.owner.audit_event(event, **details)
        except Exception:
            pass
        for callback in list(self._callbacks.values()):
            try:
                callback(dict(payload))
            except Exception:
                continue

    def inspect_player(self, player: Any, trigger: str = "周期检查") -> dict[str, Any]:
        try:
            xuid = normalize_xuid(str(getattr(player, "xuid", "")))
        except ValueError:
            return {"状态": "身份无效"}
        name = str(getattr(player, "name", ""))
        observed = read_player_abilities(player)
        runtime = self._runtime()
        runtime["在线玩家"][xuid] = {"玩家名称": name, "最后检查时间": int(time.time())}
        if not observed["就绪"]:
            runtime["权限观测"][xuid] = {"玩家名称": name, "就绪": False, "触发原因": trigger}
            self.owner.save_state()
            return {"状态": "能力未就绪", "XUID": xuid, "玩家名": name}
        record = {
            "玩家名称": name,
            "就绪": True,
            "权限标志": observed["权限标志"],
            "玩家权限等级": observed["玩家权限等级"],
            "命令权限等级": observed["命令权限等级"],
            "触发原因": trigger,
            "观测时间": int(time.time()),
        }
        runtime["权限观测"][xuid] = record
        target = self._target(xuid)
        if not self.enabled():
            self.owner.save_state()
            return {"状态": "实时管理未启用", "XUID": xuid, "玩家名": name, "实际权限": observed["权限标志"], "权限类别": permission_category(observed["权限标志"])}
        if target is None:
            self.owner.save_state()
            return {"状态": "未托管", "XUID": xuid, "玩家名": name, "实际权限": observed["权限标志"], "权限类别": permission_category(observed["权限标志"])}
        if observed["权限标志"] == target:
            self.owner.save_state()
            return {"状态": "一致", "XUID": xuid, "玩家名": name, "实际权限": observed["权限标志"], "权限类别": permission_category(observed["权限标志"]), "目标权限": target}
        differences = compare_ability_flags(observed["权限标志"], target)
        now = time.monotonic()
        cooldown = max(0.0, float(self._cfg().get("单玩家修正冷却时间(秒)", 5)))
        if now - self._last_write.get(xuid, 0.0) < cooldown:
            return {"状态": "冷却中", "XUID": xuid, "玩家名": name, "实际权限": observed["权限标志"], "权限类别": permission_category(observed["权限标志"]), "玩家权限等级": observed["玩家权限等级"], "命令权限等级": observed["命令权限等级"], "差异": differences, "目标权限": target}
        if not bool(self._cfg().get("是否自动修正受管理玩家", True)):
            return {"状态": "待人工处理", "XUID": xuid, "玩家名": name, "实际权限": observed["权限标志"], "权限类别": permission_category(observed["权限标志"]), "玩家权限等级": observed["玩家权限等级"], "命令权限等级": observed["命令权限等级"], "差异": differences, "目标权限": target}
        self._last_write[xuid] = now
        result = self.owner.set_permission(xuid, target, actor="realtime", reason="在线能力不一致", management="auto")
        status = "已提交" if result.get("success") else "修正失败"
        runtime["最近权限修正"].append({"玩家XUID": xuid, "玩家名称": name, "实际权限": observed["权限标志"], "目标权限": target, "差异": differences, "状态": status, "触发原因": trigger, "时间": int(time.time())})
        limit = self._record_limit()
        runtime["最近权限修正"] = runtime["最近权限修正"][-limit:] if limit else []
        self.owner.save_state()
        self._emit("权限修正", XUID=xuid, 玩家名=name, 目标权限=target, 状态=status, 差异=differences)
        if result.get("success"):
            self._schedule_verification(xuid, name, target)
        return {"状态": status, "XUID": xuid, "玩家名": name, "实际权限": observed["权限标志"], "权限类别": permission_category(observed["权限标志"]), "玩家权限等级": observed["玩家权限等级"], "命令权限等级": observed["命令权限等级"], "差异": differences, "目标权限": target, "结果": result}

    def inspect_players(self) -> list[dict[str, Any]]:
        players = self._get_current_players()
        if players is None:
            return []
        synced = self._sync_online_cache(players)
        if synced is None:
            return []
        current, changed = synced
        results = []
        for player in current.values():
            results.append(self.inspect_player(player))
        if changed and not results:
            self.owner.save_state()
        return results

    def handle_unknown_admins(self, admins: list[str]) -> list[dict[str, Any]]:
        raw_policy = self._cfg().get("未授权管理员处理(0:仅提醒,1:设为成员,2:设为访客)", 0)
        try:
            policy = int(raw_policy)
        except (TypeError, ValueError):
            policy = 0
        policy = policy if policy in {0, 1, 2} else 0
        configured = {
            str(x).strip().lower()
            for x in self._cfg().get("管理员XUID", [])
            if str(x).strip()
        }
        flags = {1: "11111100", 2: "00000000"}.get(policy)
        policy_name = {0: "仅提醒", 1: "设为成员", 2: "设为访客"}[policy]
        results = []
        for xuid in admins:
            try:
                normalized = normalize_xuid(xuid)
            except ValueError:
                continue
            if normalized in configured or self._managed(normalized):
                continue
            name = None
            try:
                name = self.owner.resolve_player_name(normalized)
            except Exception:
                pass
            detected_at = int(time.time())
            details = {
                "XUID": normalized,
                "玩家名称": name or "未知玩家",
                "发现时间": detected_at,
                "发现时间文本": datetime.now().astimezone().isoformat(timespec="seconds"),
                "处理策略": policy_name,
                "目标权限": flags,
            }
            # Always publish the discovery event so subscribers can decide how
            # to react independently of Libra's configured remediation policy.
            self._emit("未授权管理员", **details)
            result = None
            if flags is not None:
                result = self.owner.set_permission(normalized, flags, actor="realtime", reason="发现未授权管理员", management="auto")
            results.append({**details, "结果": result})
        return results

    def on_player_join(self, player: Any) -> None:
        delay = max(0.0, float(self._cfg().get("玩家进服检查延迟(秒)", 2)))
        def run() -> None:
            if delay:
                time.sleep(delay)
            if not self._stop.is_set() and self.enabled():
                self.inspect_player(player, trigger="玩家进服")
        threading.Thread(target=run, name="libra-player-permission-check", daemon=True).start()

    def on_player_leave(self, player: Any) -> None:
        try:
            xuid = normalize_xuid(str(getattr(player, "xuid", "")))
        except ValueError:
            return
        runtime = self._runtime()
        for key in ("在线玩家", "权限观测"):
            values = runtime.get(key)
            if isinstance(values, dict):
                values.pop(xuid, None)
        self.owner.save_state()

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._runtime()["是否运行"] = self.enabled()
        self.owner.save_state()
        if not self.enabled():
            return False
        self._thread = threading.Thread(target=self._loop, name="libra-realtime-permission", daemon=True)
        self._thread.start()
        return True

    def _interval(self) -> float:
        """在线权限检查间隔，最少 0.2 秒。"""
        try:
            return max(0.2, float(self._cfg().get("在线权限检查间隔(秒)", 1)))
        except (TypeError, ValueError):
            return 1.0

    def _admin_interval(self) -> float:
        """管理员列表检查间隔，最少 0.2 秒。"""
        try:
            return max(0.2, float(self._cfg().get("管理员列表检查间隔(秒)", 1)))
        except (TypeError, ValueError):
            return 1.0

    def _record_limit(self) -> int:
        try:
            return max(0, int(self._cfg().get("处理记录保留条数", 1000)))
        except (TypeError, ValueError):
            return 1000

    def _verification_delay(self) -> float:
        try:
            return max(0.0, float(self._cfg().get("修改后复核延迟(秒)", 1)))
        except (TypeError, ValueError):
            return 1.0

    def _verification_timeout(self) -> float:
        try:
            return max(0.0, float(self._cfg().get("修改后复核超时时间(秒)", 5)))
        except (TypeError, ValueError):
            return 5.0

    def _schedule_verification(self, xuid: str, name: str, target: str) -> None:
        """Verify an automatic write after the server has applied the change."""
        with self._verification_lock:
            if xuid in self._verification_xuids:
                return
            self._verification_xuids.add(xuid)

        def run() -> None:
            try:
                if self._stop.wait(self._verification_delay()):
                    return
                deadline = time.monotonic() + self._verification_timeout()
                last_actual: str | None = None
                while not self._stop.is_set():
                    players = self._get_current_players() or []
                    player = next(
                        (item for item in players if str(getattr(item, "xuid", "")).strip().lower() == xuid),
                        None,
                    )
                    if player is None:
                        reason = "玩家已离线"
                    else:
                        observed = read_player_abilities(player)
                        last_actual = observed.get("权限标志")
                        if observed.get("就绪") and last_actual == target:
                            self._emit(
                                "权限复核",
                                XUID=xuid,
                                玩家名=name,
                                目标权限=target,
                                实际权限=last_actual,
                                状态="通过",
                            )
                            return
                        reason = "能力尚未同步" if not observed.get("就绪") else "实际权限仍不一致"
                    if time.monotonic() >= deadline:
                        self._emit(
                            "权限复核",
                            XUID=xuid,
                            玩家名=name,
                            目标权限=target,
                            实际权限=last_actual,
                            状态="超时",
                            原因=reason,
                        )
                        return
                    wait_for = min(0.5, self._interval(), max(0.05, deadline - time.monotonic()))
                    if self._stop.wait(wait_for):
                        return
            finally:
                with self._verification_lock:
                    self._verification_xuids.discard(xuid)

        threading.Thread(
            target=run,
            name=f"libra-permission-verify-{xuid}",
            daemon=True,
        ).start()

    def _check_admins_once(self) -> None:
        """读取一次管理员列表，并按策略处理未授权管理员。"""
        admins = self.owner.run_admin_list(show=False)
        if self.owner.state.get("最近列表状态") == "成功":
            self.handle_unknown_admins(admins)

    def _loop(self) -> None:
        immediate = bool(self._cfg().get("启动后立即检查", True))
        now = time.monotonic()
        next_online = now if immediate else now + self._interval()
        next_admin = now if immediate else now + self._admin_interval()
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_online:
                try:
                    self.inspect_players()
                except Exception as exc:
                    self.owner.log_orion("ALERT", f"实时在线权限检查失败：{exc}")
                next_online = now + self._interval()
            if now >= next_admin:
                try:
                    self._check_admins_once()
                except Exception as exc:
                    self.owner.log_orion("ALERT", f"实时管理员列表检查失败：{exc}")
                next_admin = now + self._admin_interval()
            wait_for = max(0.05, min(next_online - time.monotonic(), next_admin - time.monotonic()))
            self._stop.wait(wait_for)
        self._runtime()["是否运行"] = False
        self.owner.save_state()

    def stop(self) -> None:
        self._stop.set()
        self._runtime()["是否运行"] = False
        self.owner.save_state()

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        group = self.owner.cfg.setdefault("实时管理", {})
        group["是否启用"] = bool(enabled)
        try:
            self.owner.save_config()
        except Exception:
            pass
        if enabled:
            self.start()
        else:
            self.stop()
        return self.status()

    def status(self) -> dict[str, Any]:
        synced = self._sync_online_cache()
        runtime = self._runtime()
        if synced is not None:
            current, changed = synced
            if changed:
                self.owner.save_state()
            current_xuids = set(current)
            observations = runtime.get("权限观测", {})
            if not isinstance(observations, dict):
                observations = {}
            observed_count = sum(xuid in current_xuids for xuid in observations)
            ready_count = sum(
                xuid in current_xuids and isinstance(record, dict) and record.get("就绪") is True
                for xuid, record in observations.items()
            )
            online_count = len(current_xuids)
            data_source = "实时"
        else:
            online = runtime.get("在线玩家", {})
            observations = runtime.get("权限观测", {})
            online_count = len(online) if isinstance(online, dict) else 0
            observed_count = len(observations) if isinstance(observations, dict) else 0
            ready_count = sum(
                isinstance(record, dict) and record.get("就绪") is True
                for record in observations.values()
            ) if isinstance(observations, dict) else 0
            data_source = "缓存（无法读取实时在线列表）"
        return {
            "是否启用": self.enabled(),
            "是否运行": bool(runtime.get("是否运行", False)),
            "在线玩家数": online_count,
            "权限观测数": observed_count,
            "已就绪观测数": ready_count,
            "在线数据来源": data_source,
            "在线权限检查间隔(秒)": self._interval(),
            "管理员列表检查间隔(秒)": self._admin_interval(),
            "待处理数量": len(runtime.get("待处理权限动作", [])),
            "最近修正数量": len(runtime.get("最近权限修正", [])),
        }

    def set_managed_rule(self, xuid: str, flags: str, enabled: bool = True, actor: str = "api") -> dict[str, Any]:
        """设置持续管理规则；权限命令成功前不写入规则。"""
        normalized = normalize_xuid(xuid)
        target = parse_flags(flags).raw
        result = self.owner.set_permission(normalized, target, actor=actor, reason="建立持续管理规则", management="manage")
        if not result.get("success"):
            return result
        with self.owner.state_lock:
            managed = self.owner.state.setdefault("持续管理玩家", {})
            managed[normalized] = bool(enabled)
            self.owner.save_state()
        return {**result, "持续管理": bool(enabled), "目标权限": target}

    def pause_managed_rule(self, xuid: str, actor: str = "api") -> dict[str, Any]:
        normalized = normalize_xuid(xuid)
        with self.owner.state_lock:
            managed = self.owner.state.setdefault("持续管理玩家", {})
            if normalized not in managed:
                return {"success": False, "error": "not_managed", "XUID": normalized}
            managed[normalized] = False
            self.owner.save_state()
        self._emit("持续管理暂停", XUID=normalized, 操作人=actor)
        return {"success": True, "XUID": normalized, "持续管理": False}

    def remove_managed_rule(self, xuid: str, actor: str = "api") -> dict[str, Any]:
        normalized = normalize_xuid(xuid)
        with self.owner.state_lock:
            managed = self.owner.state.setdefault("持续管理玩家", {})
            if normalized not in managed:
                return {"success": False, "error": "not_managed", "XUID": normalized}
            managed.pop(normalized, None)
            self.owner.save_state()
        self._emit("持续管理删除", XUID=normalized, 操作人=actor)
        return {"success": True, "XUID": normalized}

    def get_managed_rule(self, xuid: str) -> dict[str, Any] | None:
        try:
            normalized = normalize_xuid(xuid)
        except ValueError:
            return None
        enabled = self._managed(normalized)
        expected = self.owner.state.get("期望权限", {})
        value = expected.get(normalized) if isinstance(expected, dict) else None
        try:
            target = parse_flags(str(value)).raw if value is not None else None
        except ValueError:
            target = None
        if target is None and not enabled:
            return None
        return {"玩家XUID": normalized, "是否启用": enabled, "目标权限": target}

    def set_managed_enabled(self, xuid: str, enabled: bool, actor: str = "api") -> dict[str, Any]:
        normalized = normalize_xuid(xuid)
        managed = self.owner.state.setdefault("持续管理玩家", {})
        if normalized not in managed:
            return {"success": False, "error": "not_managed", "XUID": normalized}
        managed[normalized] = bool(enabled)
        self.owner.save_state()
        self._emit("持续管理状态变更", XUID=normalized, 是否启用=bool(enabled), 操作人=actor)
        return {"success": True, "XUID": normalized, "是否启用": bool(enabled)}

    def list_online_permissions(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        rows = []
        managed_map = self.owner.state.get("持续管理玩家", {})
        runtime = self._runtime()
        synced = self._sync_online_cache()
        if synced is not None and synced[1]:
            self.owner.save_state()
        current_xuids = set(synced[0]) if synced is not None else None
        observations = runtime.get("权限观测", {})
        if not isinstance(observations, dict):
            observations = {}
        for xuid, value in observations.items():
            if current_xuids is not None and xuid not in current_xuids:
                continue
            if not isinstance(value, dict):
                continue
            row = dict(value)
            flags = row.get("权限标志")
            row["XUID"] = xuid
            row["实际权限"] = flags
            row["权限类别"] = permission_category(flags)
            managed = managed_map.get(xuid, False) if isinstance(managed_map, dict) else False
            if isinstance(managed, dict):
                managed = managed.get("是否启用", managed.get("启用", True))
            row["是否托管"] = bool(managed)
            rows.append(row)
        try:
            page = max(1, int(page)); page_size = max(1, int(page_size))
        except (TypeError, ValueError):
            page, page_size = 1, 20
        start = (page - 1) * page_size
        return {"页码": page, "每页数量": page_size, "总数": len(rows), "项目": rows[start:start + page_size]}

    def recent_fix_records(self, limit: int | None = None) -> list[dict[str, Any]]:
        """返回最近的权限修正记录，供控制台菜单渲染。"""
        records = self._runtime().get("最近权限修正", [])
        if not isinstance(records, list):
            return []
        return list(records[-limit:]) if limit else list(records)

    def subscribe(self, callback: Callable[[dict[str, Any]], Any]) -> int:
        self._callback_id += 1
        self._callbacks[self._callback_id] = callback
        return self._callback_id

    def subscribe_unknown_admin(self, callback: Callable[[dict[str, Any]], Any]) -> int:
        """订阅“未授权管理员”发现事件，供其他 ToolDelta 插件直接接入。"""
        def handler(payload: dict[str, Any]) -> Any:
            if payload.get("事件") == "未授权管理员":
                return callback(dict(payload))
            return None
        return self.subscribe(handler)

    def unsubscribe(self, token: int) -> bool:
        return self._callbacks.pop(token, None) is not None

from __future__ import annotations

import copy
import inspect
import time
from datetime import datetime
from typing import Any

try:
    from .core import (build_delete_command, build_list_command, build_set_command, normalize_xuid, parse_flags, plan_admin_diff)
    from .response_parser import extract_admin_xuids, normalize_response
except ImportError:
    from core import (build_delete_command, build_list_command, build_set_command, normalize_xuid, parse_flags, plan_admin_diff)
    from response_parser import extract_admin_xuids, normalize_response


class PermissionService:
    #: 上一次权限写命令的时间戳，用于全局节流；类级声明避免 PYL-W0201。
    _last_mutation_time: float = 0.0

    def _realtime_cfg(self) -> dict[str, Any]:
        value = getattr(self, "cfg", {}).get("实时管理", {})
        return value if isinstance(value, dict) else {}

    def _mutation_interval(self) -> float:
        try:
            return max(0.0, float(self._realtime_cfg().get("权限修改最小间隔(秒)", 0.5)))
        except (TypeError, ValueError):
            return 0.5

    def _retry_count(self, management: str) -> int:
        # Automatic and managed updates are retried; one-off operator commands
        # remain single-shot so the console receives an immediate result.
        if management not in {"auto", "manage"}:
            return 0
        try:
            return max(0, int(self._realtime_cfg().get("失败重试次数", 2)))
        except (TypeError, ValueError):
            return 2

    def _retry_interval(self) -> float:
        try:
            return max(0.0, float(self._realtime_cfg().get("失败重试间隔(秒)", 5)))
        except (TypeError, ValueError):
            return 5.0

    def _wait_mutation_interval(self) -> None:
        """Throttle permission writes globally, including retry attempts."""
        interval = self._mutation_interval()
        last = self._last_mutation_time
        wait_for = interval - (time.monotonic() - last)
        if wait_for > 0:
            time.sleep(wait_for)
        self._last_mutation_time = time.monotonic()

    def _send_mutation(self, command: str, management: str) -> dict[str, Any]:
        """Send a permission mutation with configured pacing and retries."""
        retries = self._retry_count(management)
        last_output: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            self._wait_mutation_interval()
            try:
                output = self._send(command)
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    raise
            else:
                last_error = None
                last_output = output
                if output.get("success") and output.get("confirmed"):
                    return output
            if attempt < retries:
                time.sleep(self._retry_interval())
        if last_error is not None:
            raise last_error
        return last_output or {"success": False, "error_code": "command_failed"}

    def _record_limit(self) -> int:
        try:
            return max(0, int(self._realtime_cfg().get("处理记录保留条数", 1000)))
        except (TypeError, ValueError):
            return 1000

    def _default_flags(self) -> str:
        value = getattr(self, "cfg", {}).get("默认权限", "11111100")
        return str(value) if value is not None else "11111100"

    def _use_magic_command(self) -> bool:
        value = self.cfg.get("是否使用魔法指令模式运行", True)
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "是", "开启"}
        return bool(value)

    def _send(self, command: str) -> dict[str, Any]:
        timeout = int(self.cfg.get("命令超时秒数", 30))
        magic = self._use_magic_command()
        channel = "magic" if magic else "normal"
        sender_name = "sendaicmd_with_resp" if magic else "sendcmd_with_resp"
        sender = getattr(self.game_ctrl, sender_name, None)
        if sender is None:
            raise RuntimeError(f"当前 ToolDelta 不支持 {sender_name}，无法执行权限命令")
        try:
            parameters = inspect.signature(sender).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "timeout" in parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
            response = sender(command, timeout=timeout)
        elif len(parameters) >= 2:
            response = sender(command, timeout)
        else:
            response = sender(command)
        return normalize_response(response, channel)

    def _run_list(self, show: bool = True) -> list[str]:
        try:
            output = self._send(build_list_command())
        except Exception as exc:
            self._audit("管理员列表查询失败", error=str(exc))
            with self._lock:
                self.state["最近列表状态"] = "失败"
                self.state["最近列表错误"] = str(exc)
                self._save_state()
            self._orion("ALERT", f"读取管理员列表失败：{exc}")
            return list(self.state.get("已发现管理员", []))
        if not output.get("success"):
            error = output.get("error_code") or "command_failed"
            with self._lock:
                self.state["最近列表状态"] = "失败"
                self.state["最近列表错误"] = error
                self._save_state()
            self._audit("管理员列表查询失败", error=error, response=output)
            self._orion("ALERT", "当前命令模式无法执行 permission 命令，已保留上一次成功缓存")
            return list(self.state.get("已发现管理员", []))
        if not output.get("payloads"):
            with self._lock:
                self.state["最近列表状态"] = "解析失败"
                self.state["最近列表错误"] = "response_parse_failed"
                self._save_state()
            self._audit("管理员列表解析失败", response=output)
            self._orion("ALERT", "管理员列表响应无法解析，已保留上一次成功缓存")
            return list(self.state.get("已发现管理员", []))
        try:
            admins = extract_admin_xuids(output)
        except ValueError as exc:
            with self._lock:
                self.state["最近列表状态"] = "解析失败"
                self.state["最近列表错误"] = str(exc)
                self._save_state()
            self._audit("管理员列表解析失败", error=str(exc), response=output)
            self._orion("ALERT", "管理员列表响应无法解析，已保留上一次成功缓存")
            return list(self.state.get("已发现管理员", []))
        with self._lock:
            self.state["已发现管理员"] = admins
            self.state["最近成功管理员"] = list(admins)
            self.state["最近列表时间"] = int(time.time())
            self.state["最近列表状态"] = "成功"
            self.state["最近列表错误"] = None
            self._save_state()
        self._audit("list", admins=admins)
        if show:
            self._orion("SCAN", f"发现 {len(admins)} 个管理员 XUID")
            # Resolve names from the XUID pre-plugin's online map and its
            # persisted ``xuids.json`` index in one pass.  Keep the XUID in
            # every line so an unknown or stale identity remains actionable.
            names = self.resolve_player_names(admins)
            for xuid in admins:
                name = names.get(xuid)
                label = f"{name} - {xuid}" if name else f"未记录玩家 - {xuid}"
                self._orion("ADMIN", label)
        return admins

    def _managed_player_conflict(self, normalized: str) -> dict[str, Any] | None:
        """持续管理中的玩家不接受一次性设置，返回拒绝结果；否则返回 None。"""
        realtime_cfg = self.cfg.get("实时管理", {}) if hasattr(self, "cfg") else {}
        realtime_enabled = isinstance(realtime_cfg, dict) and bool(
            realtime_cfg.get("是否启用", False)
        )
        if not realtime_enabled or not hasattr(self, "state"):
            return None
        managed = self.state.get("持续管理玩家", {})
        active = managed.get(normalized) if isinstance(managed, dict) else False
        if isinstance(active, dict):
            active = active.get("是否启用", active.get("启用", True))
        if not active:
            return None
        return {
            "success": False,
            "error": "managed_player",
            "message": "该玩家已启用持续管理，请先暂停管理或更新持续规则",
            "xuid": normalized,
        }

    def _write_permission_state(
        self,
        normalized: str,
        flags: str,
        actor: str,
        reason: str,
        management: str,
        output: dict[str, Any],
    ) -> None:
        record = {"xuid": normalized, "flags": flags, "actor": actor, "reason": reason}
        with self._lock:
            if management != "auto":
                self.state.setdefault("期望权限", {})[normalized] = flags
            if management == "manage":
                self.state.setdefault("持续管理玩家", {})[normalized] = True
            self.state.setdefault("操作记录", []).append(
                {"操作": "设置权限", **record, "响应": output}
            )
            limit = self._record_limit()
            self.state["操作记录"] = self.state["操作记录"][-limit:] if limit else []
            self._save_state()

    def set_permission(self, xuid: str, flags: str | None = None, actor: str = "api", reason: str = "", management: str = "once") -> dict[str, Any]:
        normalized = normalize_xuid(xuid)
        parsed = parse_flags(self._default_flags() if flags is None else flags)
        if management == "once":
            conflict = self._managed_player_conflict(normalized)
            if conflict is not None:
                return conflict
        command = build_set_command(normalized, parsed.raw)
        if not self._mutation_lock.acquire(blocking=False):
            return {"success": False, "error": "busy", "message": "已有权限变更正在执行"}
        try:
            output = self._send_mutation(command, management)
        except Exception as exc:
            self._audit("set_failed", xuid=normalized, flags=parsed.raw, actor=actor, error=str(exc))
            return {"success": False, "error": "command_failed", "message": str(exc), "xuid": normalized}
        finally:
            self._mutation_lock.release()
        if not output.get("success") or not output.get("confirmed"):
            error = output.get("error_code") or "command_failed"
            message = "当前命令模式没有 permission 权限" if error == "permission_denied" else "权限设置命令执行失败"
            self._audit("设置权限失败", xuid=normalized, flags=parsed.raw, actor=actor, error=error, response=output)
            return {"success": False, "error": error, "message": message, "xuid": normalized, "response": output}
        self._write_permission_state(normalized, parsed.raw, actor, reason, management, output)
        self._audit(
            "设置权限",
            命令=command,
            响应=output,
            xuid=normalized,
            flags=parsed.raw,
            actor=actor,
            reason=reason,
        )
        return {"success": True, "action": "set", "xuid": normalized, "flags": parsed.raw, "response": output}

    def revoke_permission(
        self,
        xuid: str,
        actor: str = "api",
        reason: str = "",
        management: str = "once",
    ) -> dict[str, Any]:
        normalized = normalize_xuid(xuid)
        command = build_delete_command(normalized)
        if not self._mutation_lock.acquire(blocking=False):
            return {"success": False, "error": "busy", "message": "已有权限变更正在执行"}
        try:
            output = self._send_mutation(command, management)
        except Exception as exc:
            self._audit("revoke_failed", xuid=normalized, actor=actor, error=str(exc))
            return {"success": False, "error": "command_failed", "message": str(exc), "xuid": normalized}
        finally:
            self._mutation_lock.release()
        if not output.get("success") or not output.get("confirmed"):
            error = output.get("error_code") or "command_failed"
            message = "当前命令模式没有 permission 权限" if error == "permission_denied" else "权限撤销命令执行失败"
            self._audit("撤销权限失败", xuid=normalized, actor=actor, error=error, response=output)
            return {"success": False, "error": error, "message": message, "xuid": normalized, "response": output}
        with self._lock:
            self.state.setdefault("期望权限", {}).pop(normalized, None)
            self.state.setdefault("操作记录", []).append(
                {"操作": "撤销权限", "xuid": normalized, "actor": actor, "reason": reason, "响应": output}
            )
            limit = self._record_limit()
            self.state["操作记录"] = self.state["操作记录"][-limit:] if limit else []
            self._save_state()
        self._audit("撤销权限", command=command, response=output, xuid=normalized, actor=actor, reason=reason)
        return {"success": True, "action": "revoke", "xuid": normalized, "response": output}

    # 保留程序化 API，控制台入口已移除。
    def audit_admins(self) -> dict[str, Any]:
        observed = set(self._run_list(show=False))
        if self.state.get("最近列表状态") != "成功":
            return {"success": False, "error": self.state.get("最近列表错误") or "list_failed", "admins": sorted(observed)}
        configured = {
            str(x).strip().lower()
            for x in self.cfg.get("实时管理", {}).get("管理员XUID", [])
            if str(x).strip()
        }
        unknown = sorted(observed - configured)
        result = {
            "success": True,
            "admins": sorted(observed),
            "unknown": unknown,
            "configured": sorted(configured),
            # Compatibility alias: all configured XUIDs now share one policy.
            "trusted": sorted(configured),
        }
        self._audit("audit", **result)
        return result

    # 保留程序化 API，控制台入口已移除。
    def preview_sync(self, refresh: bool = True) -> dict[str, Any]:
        observed = set(self.list_permissions(refresh=refresh))
        if refresh and self.state.get("最近列表状态") != "成功":
            return {
                "success": False,
                "error": self.state.get("最近列表错误") or "list_failed",
                "to_set": [],
                "to_delete": [],
                "unknown": [],
                "configured": [],
                "protected": [],
            }
        desired = dict(self.state.get("期望权限", {}))
        diff = plan_admin_diff(desired, observed)
        configured = {
            str(x).strip().lower()
            for x in self.cfg.get("实时管理", {}).get("管理员XUID", [])
            if str(x).strip()
        }
        unknown = sorted(observed - configured)
        return {
            "to_set": [{"xuid": xuid, "flags": flags} for xuid, flags in diff.to_set],
            "to_delete": list(diff.to_delete),
            "unknown": unknown,
            "configured": sorted(configured),
            # Compatibility alias: there is no separate protected list anymore.
            "protected": sorted(configured),
        }

    # 保留程序化 API，控制台入口已移除。
    def sync_all(self, remove_unknown: bool = False, actor: str = "api") -> dict[str, Any]:
        plan = self.preview_sync(refresh=True)
        if not plan.get("success", True):
            return {"success": False, "error": plan.get("error", "list_failed"), "plan": plan, "results": []}
        results = [self.set_permission(item["xuid"], item["flags"], actor=actor) for item in plan["to_set"]]
        if remove_unknown:
            configured = {
                str(x).strip().lower()
                for x in self.cfg.get("实时管理", {}).get("管理员XUID", [])
                if str(x).strip()
            }
            results.extend(
                self.revoke_permission(xuid, actor=actor, reason="未知管理员清理")
                for xuid in plan["unknown"]
                if xuid not in configured
            )
        self._audit("sync", actor=actor, remove_unknown=remove_unknown, results=results)
        return {"success": all(item.get("success", False) for item in results), "plan": plan, "results": results}

    def list_admin_details(self, refresh: bool = True) -> dict[str, Any]:
        admins = self.list_permissions(refresh=refresh)
        success = self.state.get("最近列表状态") == "成功"
        names = self.resolve_player_names(admins) if hasattr(self, "resolve_player_names") else {}
        return {
            "success": success,
            "error": None if success else self.state.get("最近列表错误"),
            "admins": [
                {"xuid": xuid, "name": names.get(xuid), "permission": "operator"}
                for xuid in admins
            ],
            "command_mode": "magic" if self._use_magic_command() else "normal",
        }

    def create_snapshot(self, name: str | None = None) -> dict[str, Any]:
        snapshot_name = str(name or "").strip() or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        snapshot = {
            "名称": snapshot_name,
            "时间": int(time.time()),
            "创建时间": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "期望权限": copy.deepcopy(self.state.get("期望权限", {})),
            "持续管理玩家": copy.deepcopy(self.state.get("持续管理玩家", {})),
            "已发现管理员": list(self.state.get("已发现管理员", [])),
        }
        with self._lock:
            self.state.setdefault("权限快照", []).append(snapshot)
            self._save_state()
        self._audit("snapshot", snapshot=snapshot)
        # 保留旧 API 返回键，文件中的快照仍全部使用中文键。
        return {"name": snapshot_name, "名称": snapshot_name, "time": snapshot["时间"], "desired": snapshot["期望权限"], "observed_admins": snapshot["已发现管理员"]}

    def list_snapshots(self, page: int = 1, page_size: int = 20, query: str = "") -> dict[str, Any]:
        """返回分页快照；索引指向状态中的真实位置，便于删除/还原。"""
        snapshots = self.state.get("权限快照", [])
        if not isinstance(snapshots, list):
            snapshots = []
        normalized_query = str(query or "").strip().casefold()
        records = []
        for index, snapshot in enumerate(snapshots):
            if not isinstance(snapshot, dict):
                continue
            name = str(snapshot.get("名称", snapshot.get("name", "")))
            if normalized_query and normalized_query not in name.casefold():
                continue
            records.append({"索引": index, "快照": copy.deepcopy(snapshot)})
        records.sort(key=lambda item: (item["快照"].get("时间", item["快照"].get("time", 0)), item["索引"]), reverse=True)
        try:
            page = max(1, int(page))
            page_size = max(1, int(page_size))
        except (TypeError, ValueError):
            page, page_size = 1, 20
        start = (page - 1) * page_size
        selected = records[start:start + page_size]
        return {"页码": page, "每页数量": page_size, "总数": len(records), "项目": selected, "items": selected, "snapshots": selected}

    def preview_snapshot(self, index: int) -> dict[str, Any]:
        snapshots = self.state.get("权限快照", [])
        try:
            snapshot = snapshots[index]
        except (IndexError, TypeError, KeyError):
            return {"success": False, "error": "snapshot_not_found"}
        if not isinstance(snapshot, dict):
            return {"success": False, "error": "snapshot_invalid"}
        return {"success": True, "index": index, "snapshot": copy.deepcopy(snapshot)}

    def delete_snapshot(self, index: int, actor: str = "api") -> dict[str, Any]:
        snapshots = self.state.get("权限快照", [])
        if not isinstance(snapshots, list) or not 0 <= index < len(snapshots):
            return {"success": False, "error": "snapshot_not_found"}
        with self._lock:
            snapshot = self.state["权限快照"].pop(index)
            self._save_state()
        self._audit("删除快照", actor=actor, index=index, snapshot=snapshot)
        return {"success": True, "index": index, "snapshot": snapshot}

    def restore_snapshot(self, index: int = -1, actor: str = "api") -> dict[str, Any]:
        """Restore the desired permission map from a saved snapshot.

        Restoring changes Libra's desired permission state and does not issue
        any additional server command.
        """
        snapshots = self.state.get("权限快照", [])
        if not isinstance(snapshots, list) or not snapshots:
            return {"success": False, "error": "snapshot_not_found"}
        try:
            snapshot = snapshots[index]
            desired = snapshot.get("期望权限", snapshot.get("desired"))
            if not isinstance(desired, dict):
                raise ValueError
            normalized = {normalize_xuid(x): parse_flags(f).raw for x, f in desired.items()}
            managed = snapshot.get("持续管理玩家", {})
            if not isinstance(managed, dict):
                managed = {}
            managed_normalized = {}
            for key, value in managed.items():
                try:
                    managed_normalized[normalize_xuid(str(key))] = bool(value)
                except ValueError:
                    continue
        except (IndexError, KeyError, TypeError, ValueError):
            return {"success": False, "error": "snapshot_invalid"}
        with self._lock:
            self.state["期望权限"] = normalized
            self.state["持续管理玩家"] = managed_normalized
            self._save_state()
        self._audit("restore_snapshot", actor=actor, index=index, desired=normalized)
        return {"success": True, "desired": normalized, "index": index}

    def get_health(self) -> dict[str, Any]:
        return {
            "ready": hasattr(self, "game_ctrl"),
            "cached_admins": len(self.state.get("已发现管理员", [])),
            "managed_players": len(self.state.get("期望权限", {})),
            "last_list_time": self.state.get("最近列表时间"),
            "last_list_status": self.state.get("最近列表状态"),
            "last_list_error": self.state.get("最近列表错误"),
            "command_channel": "magic" if self._use_magic_command() else "normal",
        }

    def list_permissions(self, refresh: bool = True) -> list[str]:
        """Return the observed administrator XUIDs.

        ``refresh=False`` is useful for other plugins that want a cheap cached read.
        """
        if refresh:
            return self._run_list(show=False)
        return list(self.state.get("已发现管理员", []))


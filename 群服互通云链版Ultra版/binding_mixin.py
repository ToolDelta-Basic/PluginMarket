"""QQ account and game XUID binding support."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from copy import deepcopy
from typing import Any


class QQLinkerBindingMixin:
    """Handles QQ-to-game binding verification and persistence."""

    BINDING_TIMEOUT_MINUTES_DEFAULT = 10

    def init_binding_state(self):
        self.binding_data_path = self.format_data_path("QQ绑定数据.json")
        self.pending_bindings: dict[str, dict[str, Any]] = {}
        self.pending_binding_timers: dict[str, threading.Timer] = {}
        self.pending_bindings_lock = threading.RLock()
        self._ensure_binding_data()

    @staticmethod
    def _binding_default_data() -> dict[str, dict[str, Any]]:
        return {"qq_to_xuids": {}, "xuid_to_qqs": {}, "xuid_names": {}}

    def _ensure_binding_data(self):
        data = self.read_binding_data()
        self.save_binding_data(data)

    def read_binding_data(self) -> dict[str, dict[str, Any]]:
        if not os.path.isfile(self.binding_data_path):
            return self._binding_default_data()
        try:
            with open(self.binding_data_path, "r", encoding="utf-8") as file:
                raw = json.load(file)
        except Exception:
            raw = {}

        data = self._binding_default_data()
        if isinstance(raw, dict):
            data["qq_to_xuids"] = self._normalize_binding_map(
                raw.get("qq_to_xuids"))
            data["xuid_to_qqs"] = self._normalize_binding_map(
                raw.get("xuid_to_qqs"))
            names = raw.get("xuid_names", {})
            if isinstance(names, dict):
                data["xuid_names"] = {
                    str(xuid): str(name)
                    for xuid, name in names.items()
                    if str(xuid).strip() and str(name).strip()
                }
        return data

    @staticmethod
    def _normalize_binding_map(raw: Any) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        if not isinstance(raw, dict):
            return result
        for key, values in raw.items():
            skey = str(key).strip()
            if not skey:
                continue
            if not isinstance(values, list):
                values = [values]
            normalized: list[str] = []
            for value in values:
                svalue = str(value).strip()
                if svalue and svalue not in normalized:
                    normalized.append(svalue)
            result[skey] = normalized
        return result

    def save_binding_data(self, data: dict[str, dict[str, Any]]):
        with open(self.binding_data_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    @staticmethod
    def _binding_qq_key(qqid: int | str) -> str:
        text = str(qqid).strip()
        if not text:
            return ""
        try:
            value = int(text)
        except ValueError:
            return text
        return str(value) if value > 0 else ""

    @staticmethod
    def _binding_xuid_key(xuid: str) -> str:
        return str(xuid).strip()

    @staticmethod
    def _binding_qq_values(values: list[str]) -> list[int]:
        result: list[int] = []
        for value in values:
            try:
                qqid = int(str(value).strip())
            except ValueError:
                continue
            if qqid > 0 and qqid not in result:
                result.append(qqid)
        return result

    def _binding_api_group_id(self, group_id: int | None = None) -> int:
        if group_id is not None:
            return int(group_id)
        return int(self.linked_group or 0)

    def api_get_binding_data(self) -> dict[str, dict[str, Any]]:
        """Return a normalized copy of all QQ/XUID binding data."""
        return deepcopy(self.read_binding_data())

    def api_get_all_bindings(self) -> list[dict[str, Any]]:
        """Return binding relations as flat records for easier iteration."""
        data = self.read_binding_data()
        records: list[dict[str, Any]] = []
        for qq_key, xuids in data["qq_to_xuids"].items():
            try:
                qq_value: int | str = int(qq_key)
            except ValueError:
                qq_value = qq_key
            for xuid in xuids:
                records.append(
                    {
                        "qq": qq_value,
                        "xuid": xuid,
                        "player_name": data["xuid_names"].get(xuid, ""),
                    }
                )
        return records

    def api_get_xuids_by_qq(self, qqid: int | str) -> list[str]:
        """Return all XUIDs bound to a QQ number."""
        qq_key = self._binding_qq_key(qqid)
        if not qq_key:
            return []
        return list(self.read_binding_data()["qq_to_xuids"].get(qq_key, []))

    def api_get_qqs_by_xuid(self, xuid: str) -> list[int]:
        """Return all QQ numbers bound to an XUID."""
        xuid_key = self._binding_xuid_key(xuid)
        if not xuid_key:
            return []
        values = self.read_binding_data()["xuid_to_qqs"].get(xuid_key, [])
        return self._binding_qq_values(values)

    def api_get_player_name_by_xuid(self, xuid: str) -> str | None:
        """Return the latest recorded player name for an XUID."""
        xuid_key = self._binding_xuid_key(xuid)
        if not xuid_key:
            return None
        return self.read_binding_data()["xuid_names"].get(xuid_key)

    def api_get_bound_players_by_qq(
            self, qqid: int | str) -> list[dict[str, str]]:
        """Return player records bound to a QQ number."""
        data = self.read_binding_data()
        result: list[dict[str, str]] = []
        for xuid in data["qq_to_xuids"].get(self._binding_qq_key(qqid), []):
            result.append(
                {
                    "xuid": xuid,
                    "player_name": data["xuid_names"].get(xuid, ""),
                }
            )
        return result

    def api_get_bound_qqs_by_xuid(self, xuid: str) -> list[dict[str, Any]]:
        """Return QQ records bound to an XUID."""
        xuid_key = self._binding_xuid_key(xuid)
        if not xuid_key:
            return []
        data = self.read_binding_data()
        player_name = data["xuid_names"].get(xuid_key, "")
        return [
            {"qq": qqid, "xuid": xuid_key, "player_name": player_name}
            for qqid in self._binding_qq_values(data["xuid_to_qqs"].get(xuid_key, []))
        ]

    def api_get_xuids_by_player_name(
        self,
        player_name: str,
        ignore_case: bool = True,
    ) -> list[str]:
        """Return XUIDs whose latest recorded player name matches."""
        name = str(player_name).strip()
        if not name:
            return []
        data = self.read_binding_data()
        if ignore_case:
            name = name.lower()
            return [
                xuid
                for xuid, stored_name in data["xuid_names"].items()
                if stored_name.lower() == name
            ]
        return [
            xuid
            for xuid, stored_name in data["xuid_names"].items()
            if stored_name == name
        ]

    def api_get_qqs_by_player_name(
        self,
        player_name: str,
        ignore_case: bool = True,
    ) -> list[int]:
        """Return QQ numbers bound to matching player names."""
        qqids: list[int] = []
        for xuid in self.api_get_xuids_by_player_name(
                player_name, ignore_case):
            for qqid in self.api_get_qqs_by_xuid(xuid):
                if qqid not in qqids:
                    qqids.append(qqid)
        return qqids

    def api_is_binding_enabled(self, group_id: int | None = None) -> bool:
        """Return whether QQ/game binding is enabled in config."""
        return self._binding_enabled(self._binding_api_group_id(group_id))

    def api_is_qq_bound(self, qqid: int | str) -> bool:
        """Return whether a QQ number has any binding."""
        return bool(self.api_get_xuids_by_qq(qqid))

    def api_is_xuid_bound(self, xuid: str) -> bool:
        """Return whether an XUID has any binding."""
        return bool(self.api_get_qqs_by_xuid(xuid))

    def api_is_qq_bound_to_xuid(self, qqid: int | str, xuid: str) -> bool:
        """Return whether the exact QQ/XUID relation exists."""
        return self._binding_xuid_key(xuid) in self.api_get_xuids_by_qq(qqid)

    def api_bind_qq_to_xuid(
        self,
        qqid: int | str,
        xuid: str,
        player_name: str = "",
        group_id: int | None = None,
    ) -> tuple[bool, str]:
        """Create or refresh a QQ/XUID binding, respecting multi-bind config."""
        qq_key = self._binding_qq_key(qqid)
        xuid_key = self._binding_xuid_key(xuid)
        if not qq_key or not qq_key.isdigit():
            return False, "QQ号无效"
        if not xuid_key:
            return False, "XUID不能为空"
        name = str(player_name).strip() or xuid_key
        return self._bind_qq_to_xuid(
            self._binding_api_group_id(group_id),
            int(qq_key),
            xuid_key,
            name,
        )

    def api_unbind_qq_from_xuid(
            self, qqid: int | str, xuid: str) -> tuple[bool, str]:
        """Remove one exact QQ/XUID binding relation."""
        qq_key = self._binding_qq_key(qqid)
        xuid_key = self._binding_xuid_key(xuid)
        if not qq_key or not qq_key.isdigit():
            return False, "QQ号无效"
        if not xuid_key:
            return False, "XUID不能为空"
        data = self.read_binding_data()
        if not self._remove_binding_relation(data, qq_key, xuid_key):
            return False, "绑定关系不存在"
        self.save_binding_data(data)
        return True, "已解绑"

    def api_unbind_all_by_qq(self, qqid: int | str) -> tuple[bool, str]:
        """Remove all bindings owned by one QQ number."""
        qq_key = self._binding_qq_key(qqid)
        if not qq_key or not qq_key.isdigit():
            return False, "QQ号无效"
        data = self.read_binding_data()
        xuids = list(data["qq_to_xuids"].get(qq_key, []))
        if not xuids:
            return False, "该 QQ 没有绑定记录"
        for xuid in xuids:
            self._remove_binding_relation(data, qq_key, xuid)
        self.save_binding_data(data)
        return True, f"已解绑 {len(xuids)} 个游戏ID"

    def api_unbind_all_by_xuid(self, xuid: str) -> tuple[bool, str]:
        """Remove all QQ bindings owned by one XUID."""
        xuid_key = self._binding_xuid_key(xuid)
        if not xuid_key:
            return False, "XUID不能为空"
        data = self.read_binding_data()
        qqs = list(data["xuid_to_qqs"].get(xuid_key, []))
        if not qqs:
            return False, "该 XUID 没有绑定记录"
        for qq_key in qqs:
            self._remove_binding_relation(data, qq_key, xuid_key)
        self.save_binding_data(data)
        return True, f"已解绑 {len(qqs)} 个QQ号"

    def api_update_xuid_player_name(
        self,
        xuid: str,
        player_name: str,
    ) -> tuple[bool, str]:
        """Update the latest recorded player name for a bound XUID."""
        xuid_key = self._binding_xuid_key(xuid)
        name = str(player_name).strip()
        if not xuid_key:
            return False, "XUID不能为空"
        if not name:
            return False, "玩家名不能为空"
        data = self.read_binding_data()
        if xuid_key not in data["xuid_to_qqs"]:
            return False, "该 XUID 没有绑定记录"
        data["xuid_names"][xuid_key] = name
        self.save_binding_data(data)
        return True, "已更新玩家名"

    def api_start_binding_request(
        self,
        group_id: int,
        qqid: int | str,
    ) -> tuple[bool, str]:
        """Start the normal QQ binding verification flow for a group member."""
        qq_key = self._binding_qq_key(qqid)
        if not qq_key or not qq_key.isdigit():
            return False, "QQ号无效"
        try:
            group_id = int(group_id)
        except (TypeError, ValueError):
            return False, "群号无效"
        if group_id not in self.group_cfgs:
            return False, "该群未配置群服互通"
        try:
            ok, message = self._start_binding_request(
                group_id,
                int(qq_key),
            )
        except Exception as err:
            return False, f"绑定请求创建失败: {err}"
        return ok, message

    def _remove_binding_relation(
        self,
        data: dict[str, dict[str, Any]],
        qq_key: str,
        xuid: str,
    ) -> bool:
        changed = False
        qq_xuids = data["qq_to_xuids"].get(qq_key, [])
        if xuid in qq_xuids:
            qq_xuids.remove(xuid)
            changed = True
        if qq_xuids:
            data["qq_to_xuids"][qq_key] = qq_xuids
        else:
            data["qq_to_xuids"].pop(qq_key, None)

        xuid_qqs = data["xuid_to_qqs"].get(xuid, [])
        if qq_key in xuid_qqs:
            xuid_qqs.remove(qq_key)
            changed = True
        if xuid_qqs:
            data["xuid_to_qqs"][xuid] = xuid_qqs
        else:
            data["xuid_to_qqs"].pop(xuid, None)
            data["xuid_names"].pop(xuid, None)
        return changed

    def _cleanup_pending_bindings(self):
        now = time.time()
        with self.pending_bindings_lock:
            expired_codes = [
                code
                for code, pending in self.pending_bindings.items()
                if now >= float(pending.get("expire_at", 0))
            ]
        for code in expired_codes:
            pending = self._pop_pending_binding(code)
            if pending is not None:
                self._send_binding_timeout_notice(pending)

    def _new_binding_code(self) -> str:
        self._cleanup_pending_bindings()
        with self.pending_bindings_lock:
            for _ in range(20):
                code = f"{secrets.randbelow(1000000):06d}"
                if code not in self.pending_bindings:
                    return code
        raise RuntimeError("无法生成唯一绑定验证码")

    def _remove_pending_bindings_by_qq(self, group_id: int, qqid: int):
        with self.pending_bindings_lock:
            codes = [
                code
                for code, pending in self.pending_bindings.items()
                if pending.get("group_id") == group_id and pending.get("qqid") == qqid
            ]
        for code in codes:
            self._pop_pending_binding(code)

    def _pop_pending_binding(self, code: str, cancel_timer: bool = True):
        with self.pending_bindings_lock:
            pending = self.pending_bindings.pop(code, None)
            timer = self.pending_binding_timers.pop(code, None)
        if cancel_timer and timer is not None:
            timer.cancel()
        return pending

    def _schedule_binding_timeout(self, code: str, timeout_seconds: int):
        timer = threading.Timer(
            timeout_seconds, self._handle_binding_timeout, args=(code,))
        timer.daemon = True
        with self.pending_bindings_lock:
            self.pending_binding_timers[code] = timer
        timer.start()

    def _handle_binding_timeout(self, code: str):
        pending = self._pop_pending_binding(code, cancel_timer=False)
        if pending is not None:
            self._send_binding_timeout_notice(pending)

    def _send_binding_timeout_notice(self, pending: dict[str, Any]):
        group_id = int(pending["group_id"])
        qqid = int(pending["qqid"])
        timeout_text = self._binding_text(
            group_id,
            "绑定超时提示文本",
            "绑定超时，请重新获取验证码绑定",
        )
        try:
            self._reply_to_qq(group_id, qqid, timeout_text)
        except Exception as err:
            self.print_console_warn(f"绑定超时提示发送失败: {err}")

    def cleanup_binding_state(self):
        with self.pending_bindings_lock:
            timers = list(self.pending_binding_timers.values())
            self.pending_binding_timers.clear()
            self.pending_bindings.clear()
        for timer in timers:
            timer.cancel()

    def _binding_cfg(self) -> dict[str, Any]:
        cfg = self.cfg.get("绑定设置", {})
        if isinstance(cfg, dict):
            return cfg
        return self.binding_default()

    def _binding_enabled(self, group_id: int) -> bool:
        return bool(self._binding_cfg().get("是否开启QQ号与游戏ID绑定功能", False))

    def _binding_text(self, group_id: int, key: str, fallback: str) -> str:
        value = self._binding_cfg().get(key, fallback)
        text = str(value).strip()
        return text or fallback

    def _binding_reject_text(self, group_id: int) -> str:
        return self._binding_text(
            group_id,
            "拒绝绑定提示文本（仅在“是否允许单QQ号可绑定多游戏ID”为否时生效）",
            "您已有绑定账号，请解绑后再绑定",
        )

    def _binding_timeout_minutes(self, group_id: int) -> int:
        return self._normalize_positive_int(
            self._binding_cfg().get(
                "绑定超时时间（单位：分钟）",
                self.BINDING_TIMEOUT_MINUTES_DEFAULT,
            ),
            self.BINDING_TIMEOUT_MINUTES_DEFAULT,
        )

    def _render_binding_text(
            self,
            text: str,
            code: str,
            timeout_minutes: int) -> str:
        return (
            text
            .replace("{auth_code}", code)
            .replace("{time}", str(timeout_minutes))
        )

    def _qq_has_bound_xuid(self, qqid: int) -> bool:
        data = self.read_binding_data()
        return bool(data["qq_to_xuids"].get(str(qqid)))

    def get_group_binding_triggers(self, group_id: int) -> list[str]:
        raw = self._binding_cfg().get("绑定触发词", ["绑定"])
        return self.normalize_string_triggers(raw, ["绑定"])

    def _start_binding_request(
            self, group_id: int, qqid: int) -> tuple[bool, str]:
        if not self._binding_enabled(group_id):
            return False, "QQ绑定功能当前已关闭"

        cfg = self._binding_cfg()
        if (
            not bool(cfg.get("是否允许单QQ号可绑定多游戏ID", False))
            and self._qq_has_bound_xuid(qqid)
        ):
            return False, self._binding_reject_text(group_id)

        code = self._new_binding_code()
        timeout_minutes = self._binding_timeout_minutes(group_id)
        self._remove_pending_bindings_by_qq(group_id, qqid)
        timeout_seconds = timeout_minutes * 60
        with self.pending_bindings_lock:
            self.pending_bindings[code] = {
                "group_id": group_id,
                "qqid": qqid,
                "expire_at": time.time() + timeout_seconds,
            }
        self._schedule_binding_timeout(code, timeout_seconds)

        self._reply_to_qq(
            group_id,
            qqid,
            self._render_binding_text(
                self._binding_text(
                    group_id,
                    "绑定验证码群聊提示文本",
                    "已将验证码发送至您的私信，请在{time}分钟内在游戏中发送验证码以完成绑定。",
                ),
                code,
                timeout_minutes,
            ),
        )
        self.send_private_msg(
            qqid,
            self._render_binding_text(
                self._binding_text(
                    group_id,
                    "绑定验证码私信提示文本",
                    "您的绑定验证码是：{auth_code}。请在{time}分钟内在游戏中发送该验证码已完成绑定。",
                ),
                code,
                timeout_minutes,
            ),
        )
        return True, "绑定验证码已发送"

    def _handle_binding_trigger(
            self,
            group_id: int,
            qqid: int,
            clean_msg: str) -> bool:
        if not self._binding_enabled(group_id):
            return False
        if clean_msg not in self.get_group_binding_triggers(group_id):
            return False

        ok, message = self._start_binding_request(group_id, qqid)
        if not ok:
            self._reply_to_qq(group_id, qqid, message)
        return True

    def send_private_msg(self, qqid: int, msg: str):
        """向指定 QQ 发送私信。"""
        if self.ws is None:
            raise RuntimeError("WebSocket 尚未初始化")
        if not self.available:
            self._print_cloud_status(
                "群服互通 云链连接",
                "忽略发送",
                ["当前未连接云链", f"已忽略发送到 QQ {qqid} 的私信"],
                level="warn",
            )
            return
        payload = {
            "action": "send_private_msg",
            "params": {"user_id": qqid, "message": msg},
        }
        self.ws.send(json.dumps(payload))

    def consume_game_binding_code(self, chat) -> bool:
        msg = str(chat.msg).strip()
        if len(msg) != 6 or not msg.isdigit():
            return False

        pending = self._pop_pending_binding(msg)
        if pending is None:
            self._cleanup_pending_bindings()
            return False

        group_id = int(pending["group_id"])
        qqid = int(pending["qqid"])
        if time.time() >= float(pending.get("expire_at", 0)):
            timeout_text = self._binding_text(
                group_id,
                "绑定超时提示文本",
                "绑定超时，请重新获取验证码绑定",
            )
            chat.player.show(f"§c{timeout_text}")
            self._reply_to_qq(group_id, qqid, timeout_text)
            return True

        if not self._binding_enabled(group_id):
            chat.player.show("§cQQ绑定功能当前已关闭")
            return True

        player_name = chat.player.name
        xuid = str(getattr(chat.player, "xuid", "")).strip()
        if not xuid:
            chat.player.show("§c无法获取你的 XUID，绑定失败")
            self._reply_to_qq(group_id, qqid, "绑定失败：无法获取玩家 XUID")
            return True

        ok, message = self._bind_qq_to_xuid(group_id, qqid, xuid, player_name)
        if not ok:
            chat.player.show(f"§c{message}")
            self._reply_to_qq(group_id, qqid, message)
            return True

        chat.player.show("§aQQ绑定成功")
        success_text = self._binding_text(
            group_id,
            "绑定成功提示文本",
            "恭喜你绑定成功，您的游戏ID为：{player_name}。",
        )
        self._reply_to_qq(
            group_id,
            qqid,
            success_text
            .replace("{player_name}", player_name)
            .replace("{xuid}", xuid)
            .replace("{qq}", str(qqid)),
        )
        return True

    def _bind_qq_to_xuid(
            self,
            group_id: int,
            qqid: int,
            xuid: str,
            player_name: str):
        cfg = self._binding_cfg()
        allow_multi_xuid = bool(cfg.get("是否允许单QQ号可绑定多游戏ID", False))
        allow_multi_qq = bool(cfg.get("是否允许单游戏ID可绑定多QQ号", False))

        data = self.read_binding_data()
        qq_key = str(qqid)
        qq_xuids = data["qq_to_xuids"].setdefault(qq_key, [])
        xuid_qqs = data["xuid_to_qqs"].setdefault(xuid, [])

        if xuid in qq_xuids and qq_key in xuid_qqs:
            data["xuid_names"][xuid] = player_name
            self.save_binding_data(data)
            return True, "绑定关系已存在，已刷新玩家名"

        if not allow_multi_xuid and qq_xuids and xuid not in qq_xuids:
            return False, self._binding_reject_text(group_id)
        if not allow_multi_qq and xuid_qqs and qq_key not in xuid_qqs:
            return False, "绑定失败：该游戏ID已绑定其他 QQ 号"

        if xuid not in qq_xuids:
            qq_xuids.append(xuid)
        if qq_key not in xuid_qqs:
            xuid_qqs.append(qq_key)
        data["xuid_names"][xuid] = player_name
        self.save_binding_data(data)
        return True, "绑定成功"

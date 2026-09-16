"""Libra 状态、审计日志和中文键名持久化。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class StateStore:
    """状态与审计日志的中文键名持久化存储。"""

    _KEYS = {
        "operations": "操作记录",
        "snapshots": "权限快照",
        "last_list_time": "最近列表时间",
        "last_list_status": "最近列表状态",
        "last_list_error": "最近列表错误",
        "last_successful_admins": "最近成功管理员",
        "last_search_results": "最近搜索结果",
        "action": "操作",
        "xuid": "玩家XUID",
        "flags": "权限标志",
        "actor": "操作者",
        "reason": "原因",
        "response": "响应",
        "command": "命令",
        "admins": "管理员",
        "configured": "配置管理员",
        "unknown": "未知管理员",
        "trusted": "受信任管理员",
        "protected": "受保护管理员",
        "time": "时间",
        "event": "事件",
        "error": "错误",
        "success": "成功",
        "desired": "期望权限",
        "observed_admins": "已发现管理员",
        "snapshot": "权限快照",
        "index": "索引",
        "channel": "命令通道",
        "command_mode": "命令模式",
        "messages": "消息",
        "payloads": "结构化结果",
        "text": "原始文本",
        "error_code": "错误代码",
        "result": "结果",
        "permission": "权限类型",
        "name": "玩家名",
        "success_count": "成功数量",
        "confirmed": "已确认执行",
        "to_set": "待设置",
        "to_delete": "待删除",
        "results": "执行结果",
        "remove_unknown": "是否移除未知管理员",
        "managed_players": "管理玩家数",
        "cached_admins": "缓存管理员数",
        "ready": "已就绪",
    }

    def __init__(self, state_path: str | Path, audit_path: str | Path):
        """记录状态文件与审计日志文件的路径。"""
        self.state_path = Path(state_path)
        self.audit_path = Path(audit_path)

    @classmethod
    def empty_state(cls) -> dict[str, Any]:
        """返回空状态骨架，含实时管理的默认结构。"""
        return {
            "期望权限": {},
            "已发现管理员": [],
            "操作记录": [],
            "权限快照": [],
            "最近列表时间": None,
            "最近列表状态": "未查询",
            "最近列表错误": None,
            "最近成功管理员": [],
            "最近搜索结果": [],
            "持续管理玩家": {},
            "实时管理": {
                "是否运行": False,
                "在线玩家": {},
                "待处理权限动作": [],
                "最近权限修正": [],
                "权限观测": {},
            },
        }

    @classmethod
    def _convert_keys(cls, value: Any) -> Any:
        """把英文字段名递归转换成中文键名。"""
        if isinstance(value, dict):
            return {
                cls._KEYS.get(str(k), str(k)): cls._convert_keys(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [cls._convert_keys(item) for item in value]
        return value

    @classmethod
    def _encode(cls, value: Any) -> Any:
        """递归编码为可写入 JSON 的中文键名结构。"""
        if isinstance(value, dict):
            encoded: dict[str, Any] = {}
            for key, item in value.items():
                chinese_key = cls._KEYS.get(str(key), str(key))
                if not any("\u4e00" <= char <= "\u9fff" for char in chinese_key):
                    chinese_key = f"字段：{chinese_key}"
                if chinese_key == "期望权限" and isinstance(item, dict):
                    item = [
                        {"玩家标识": str(xuid), "权限标志": flags}
                        for xuid, flags in item.items()
                    ]
                encoded[chinese_key] = cls._encode(item)
            return encoded
        if isinstance(value, list):
            return [cls._encode(item) for item in value]
        return value

    @classmethod
    def _decode(cls, value: Any) -> Any:
        """递归还原中文键名结构，并把期望权限还原成字典。"""
        if isinstance(value, dict):
            decoded = {
                cls._KEYS.get(str(k), str(k)): cls._decode(v)
                for k, v in value.items()
            }
            if "期望权限" in decoded and isinstance(decoded["期望权限"], list):
                decoded["期望权限"] = {
                    str(item.get("玩家标识")): item.get("权限标志")
                    for item in decoded["期望权限"]
                    if (
                        isinstance(item, dict)
                        and item.get("玩家标识")
                        and item.get("权限标志") is not None
                    )
                }
            return decoded
        if isinstance(value, list):
            return [cls._decode(item) for item in value]
        return value

    def load(self) -> dict[str, Any]:
        """读取状态文件；文件缺失或损坏时回退到空状态。"""
        self._migrate_legacy_files()
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (ValueError, OSError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        state = self.empty_state()
        state.update(self._decode(data))
        if not isinstance(state["期望权限"], dict):
            state["期望权限"] = {}
        if not isinstance(state["已发现管理员"], list):
            state["已发现管理员"] = []
        if not isinstance(state["操作记录"], list):
            state["操作记录"] = []
        if not isinstance(state["权限快照"], list):
            state["权限快照"] = []
        if not isinstance(state["最近成功管理员"], list):
            state["最近成功管理员"] = []
        if not isinstance(state["最近搜索结果"], list):
            state["最近搜索结果"] = []
        return state

    def _migrate_legacy_files(self) -> None:
        """一次性读取旧英文文件并写入中文文件，后续只使用中文文件。"""
        legacy_state = self.state_path.parent / "state.json"
        if not self.state_path.exists() and legacy_state.exists():
            try:
                old = json.loads(legacy_state.read_text(encoding="utf-8"))
                if isinstance(old, dict):
                    self.state_path.parent.mkdir(parents=True, exist_ok=True)
                    self.state_path.write_text(
                        json.dumps(self._encode(old), ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            except (OSError, ValueError, TypeError):
                pass
        legacy_audit = self.audit_path.parent / "audit.jsonl"
        if not self.audit_path.exists() and legacy_audit.exists():
            try:
                with (
                    legacy_audit.open("r", encoding="utf-8") as source,
                    self.audit_path.open("w", encoding="utf-8") as target,
                ):
                    for line in source:
                        try:
                            record = json.loads(line)
                            target.write(
                                json.dumps(self._encode(record), ensure_ascii=False)
                                + "\n"
                            )
                        except (ValueError, TypeError):
                            continue
            except OSError:
                pass

    def save(self, state: dict[str, Any]) -> None:
        """以「临时文件 + 原子替换」的方式写入状态。"""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(self._encode(state), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.state_path)

    def audit(self, event: str, **details: Any) -> None:
        """向审计日志追加一条 JSONL 记录。"""
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"时间": int(time.time()), "事件": event, **self._encode(details)}
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

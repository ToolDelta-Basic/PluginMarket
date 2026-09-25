"""ToolDelta 命令响应的结构化解析。"""
from __future__ import annotations

import json
import re
from typing import Any

try:
    from .core import normalize_xuid
except ImportError:  # 兼容直接运行模块的测试环境
    from core import normalize_xuid

_BLOCK_RE = re.compile(r"###\*", re.S)


def _field(value: Any, name: str, default: Any = None) -> Any:
    """从字典或对象上按名称取值，取不到时返回 ``default``。"""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _try_load_json(value: str) -> Any:
    """尝试解析 JSON 字符串，失败时返回 ``None``。"""
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _collect_texts_and_success(response: Any) -> tuple[list[str], list[bool]]:
    """提取响应里的文本消息与 ``Success`` 布尔值。"""
    messages = _field(response, "OutputMessages", []) or []
    if not isinstance(messages, list):
        messages = [messages]
    texts: list[str] = []
    success_values: list[bool] = []
    for item in messages:
        message = _field(item, "Message", None)
        if message is not None:
            texts.append(str(message))
        success = _field(item, "Success", None)
        if isinstance(success, bool):
            success_values.append(success)
    return texts, success_values


def _decode_block_payloads(text: str) -> list[dict[str, Any]]:
    """解析 ``###*{...}*###`` 包装的 JSON 负载。"""
    payloads: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for match in _BLOCK_RE.finditer(text):
        start = text.find("{", match.end())
        if start < 0:
            continue
        try:
            payload, end = decoder.raw_decode(text[start:])
        except (TypeError, ValueError):
            continue
        marker_end = text.find("*###", start + end)
        if marker_end >= 0 and isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _decode_bare_payloads(texts: list[str]) -> list[dict[str, Any]]:
    """兼容没有 ###* 包装但直接返回 JSON 的版本。"""
    payloads: list[dict[str, Any]] = []
    for candidate in texts:
        payload = _try_load_json(candidate.strip())
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _resolve_outcome(
    response: Any,
    success_values: list[bool],
    payloads: list[dict[str, Any]],
    text: str,
) -> tuple[bool, bool, str | None]:
    """综合 SuccessCount、Success 列表与 JSON 负载判定执行结果与错误码。"""
    success_count = _field(response, "SuccessCount", None)
    confirmed = bool(success_values) and all(success_values)
    if isinstance(success_count, int):
        confirmed = success_count > 0
    success = confirmed or bool(payloads)
    if "commands.generic.error.permissions" in text:
        return False, False, "permission_denied"
    if not success:
        return success, confirmed, "command_failed"
    return success, confirmed, None


def normalize_response(response: Any, channel: str) -> dict[str, Any]:
    """将 Packet_CommandOutput、字典或字符串统一为可序列化结构。"""
    if isinstance(response, str):
        decoded = _try_load_json(response)
        if isinstance(decoded, dict) and "OutputMessages" in decoded:
            return normalize_response(decoded, channel)

    texts, success_values = _collect_texts_and_success(response)
    if isinstance(response, str):
        texts.append(response)
    dataset = _field(response, "DataSet", "") or ""
    if dataset:
        texts.append(str(dataset))
    text = "\n".join(texts)

    payloads = _decode_block_payloads(text)
    if not payloads:
        payloads = _decode_bare_payloads(texts)

    success, confirmed, error_code = _resolve_outcome(
        response, success_values, payloads, text
    )
    return {
        "success": success,
        "confirmed": confirmed,
        "messages": texts,
        "payloads": payloads,
        "text": text,
        "error_code": error_code,
        "channel": channel,
    }


def extract_admin_xuids(parsed: dict[str, Any]) -> list[str]:
    """从 permissions/ops 结构化结果提取 operator XUID。"""
    found: list[str] = []
    payloads = parsed.get("payloads", [])
    recognized = False
    for payload in payloads:
        command = str(payload.get("command", "")).lower()
        result = payload.get("result", [])
        candidates: list[Any] = []
        if command == "permissions":
            recognized = True
            if not isinstance(result, list):
                raise ValueError("permissions.result 必须是列表")
            candidates = [
                item.get("xuid")
                for item in result
                if isinstance(item, dict)
                and str(item.get("permission", "")).lower() == "operator"
            ]
        elif command == "ops":
            recognized = True
            if not isinstance(result, list):
                raise ValueError("ops.result 必须是列表")
            candidates = result
        for value in candidates:
            try:
                xuid = normalize_xuid(str(value))
            except ValueError:
                raise ValueError(f"无效的管理员 XUID: {value}")
            if xuid not in found:
                found.append(xuid)
    if not recognized:
        raise ValueError("响应中没有 ops 或 permissions 数据")
    return found

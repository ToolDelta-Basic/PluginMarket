"""
IPC Bridge — 框架事件序列化/反序列化协议

将框架事件（dataclass）序列化为 JSON-safe dict，通过 IPC 传输后再重建为事件对象。
与 LaneRouter / PipelineEngine 集成，使事件可跨越进程边界。

设计原则:
  - 仅依赖 dataclasses 和内建类型，无外部依赖
  - 序列化 dict 包含 _type 字段以标识原始事件类型
  - deserialize 重建完整事件对象（包括 dataclass 的 init=False 字段）
  - 未知字段自动跳过，向前兼容
"""

from __future__ import annotations

import dataclasses
import importlib
import logging
from typing import Any, Dict, Optional, Type

_log = logging.getLogger(__name__)

# ── 事件类型注册表（事件类名 → 完整模块路径） ──
_EVENT_TYPE_REGISTRY: Dict[str, Type] = {}


def _discover_events():
    """懒加载：从 core.kernel.events 自动发现所有事件类型。"""
    if _EVENT_TYPE_REGISTRY:
        return
    try:
        from ..kernel import events as evt_module
        for name in dir(evt_module):
            obj = getattr(evt_module, name)
            if (
                isinstance(obj, type)
                and dataclasses.is_dataclass(obj)
                and hasattr(obj, 'lane')
            ):
                _EVENT_TYPE_REGISTRY[name] = obj
    except ImportError:
        _log.warning("无法导入 core.kernel.events，EventSerializer 可能不完整")


class EventSerializer:
    """事件序列化器 — 将框架事件转换为 IPC 消息格式。

    用法:
        e = GroupMessageEvent(user_id=1, group_id=2, nickname='test', message='hello')
        d = EventSerializer.serialize(e)
        # {'_type': 'GroupMessageEvent', 'user_id': 1, 'group_id': 2, ...}

        rebuilt = EventSerializer.deserialize(d)
        # GroupMessageEvent(user_id=1, group_id=2, nickname='test', message='hello')
    """

    # 这些字段不会被包含在序列化结果中（由 init=False 检测，但这里做二次保证）
    _SKIP_FIELDS = frozenset({})

    @staticmethod
    def serialize(event) -> dict:
        """将事件对象序列化为 JSON-safe dict。

        Args:
            event: dataclass 事件实例，必须有 lane 属性。

        Returns:
            包含 _type 标记和所有 dataclass 字段的 dict。
        """
        _discover_events()
        cls = type(event)
        result = {"_type": cls.__name__}

        for f in dataclasses.fields(event):
            val = getattr(event, f.name)
            # 递归序列化嵌套 dataclass
            if dataclasses.is_dataclass(val) and not isinstance(val, type):
                result[f.name] = EventSerializer.serialize(val)
            else:
                result[f.name] = EventSerializer._make_json_safe(val)

        return result

    @staticmethod
    def deserialize(data: dict):
        """从 dict 重建事件对象。

        Args:
            data: serialize() 的输出 dict（必须包含 _type）。

        Returns:
            重建的事件对象。

        Raises:
            ValueError: _type 缺失或未知类型。
        """
        _discover_events()
        if '_type' not in data:
            raise ValueError("序列化数据缺少 _type 字段")

        event_type = data['_type']
        cls = _EVENT_TYPE_REGISTRY.get(event_type)

        if cls is None:
            _log.warning("未知事件类型 '%s'，尝试动态导入", event_type)
            cls = EventSerializer._resolve_type(event_type)
            if cls is None:
                raise ValueError(f"无法解析事件类型: {event_type}")

        # 提取 dataclass 的 init 字段名
        field_names = {f.name for f in dataclasses.fields(cls) if f.init}

        # 构建构造函数参数
        kwargs = {}
        for key, value in data.items():
            if key == '_type':
                continue
            if key not in field_names:
                # 跳过未知字段（向前兼容）
                continue
            kwargs[key] = value

        return cls(**kwargs)

    @staticmethod
    def serialize_event(event, topic: str = "") -> dict:
        """序列化事件并附加 IPC 路由元数据。

        Args:
            event: 框架事件对象。
            topic: 可选的 pipeline topic（不填则从 event.lane 推断）。

        Returns:
            包含 _type、_topic、event_id 等元数据的 dict。
        """
        base = EventSerializer.serialize(event)
        base["_topic"] = topic or getattr(event, 'lane', 'general')
        base["_event_id"] = getattr(event, 'event_id', '')
        base["_priority"] = getattr(event, 'priority', 0)
        return base

    @staticmethod
    def deserialize_from_worker(data: dict):
        """从 worker 进程返回的 data dict 重建事件 + 元数据。

        Returns:
            (event, topic, event_id, priority) 元组。
        """
        event = EventSerializer.deserialize(data)
        topic = data.get("_topic", "general")
        event_id = data.get("_event_id", "")
        priority = data.get("_priority", 0)
        return event, topic, event_id, priority

    # ── 内部方法 ──────────────────────────────

    @staticmethod
    def _make_json_safe(value: Any) -> Any:
        """将值转换为 JSON 安全类型。"""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {k: EventSerializer._make_json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [EventSerializer._make_json_safe(v) for v in value]
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return EventSerializer.serialize(value)
        # 兜底：转为字符串
        return str(value)

    @staticmethod
    def _resolve_type(name: str) -> Optional[Type]:
        """尝试从已知路径动态导入事件类型。"""
        candidates = [
            f"core.kernel.events.{name}",
            f"qqlinker_framework.core.kernel.events.{name}",
        ]
        for path in candidates:
            try:
                parts = path.rsplit('.', 1)
                mod = importlib.import_module(parts[0])
                cls = getattr(mod, parts[1], None)
                if cls and dataclasses.is_dataclass(cls):
                    _EVENT_TYPE_REGISTRY[name] = cls
                    return cls
            except ImportError:
                continue
        return None

    @staticmethod
    def register_event_type(name: str, cls: Type):
        """手动注册事件类型（用于外部模块自定义事件）。

        Args:
            name: 事件类型名称（如 'MyCustomEvent'）。
            cls: 事件 dataclass 类。
        """
        _EVENT_TYPE_REGISTRY[name] = cls


# ── IPC 消息构造工厂 ──


class IPCBridgeProtocol:
    """IPC 桥接协议 — 将 event 序列化为 IPC 消息。

    与 core.ipc.protocol 的 make_request/make_event 配合使用。
    """

    @staticmethod
    def make_event_request(event, topic: str = "") -> dict:
        """将事件打包为 IPC 请求。

        格式:
            {
                "id": <uuid>,
                "method": "bridge.process_event",
                "params": { <serialized event> },
                "ts": <timestamp>
            }
        """
        data = EventSerializer.serialize_event(event, topic)
        import uuid
        import time
        return {
            "id": uuid.uuid4().hex,
            "method": "bridge.process_event",
            "params": data,
            "ts": time.time(),
        }

    @staticmethod
    def make_event_notification(event, topic: str = "") -> dict:
        """将事件打包为 IPC 推送通知（不等待响应）。"""
        data = EventSerializer.serialize_event(event, topic)
        return {
            "event": "bridge.event",
            "data": data,
        }

    @staticmethod
    def parse_worker_result(msg: dict):
        """解析 worker 进程返回的结果。

        Returns:
            (event, topic, event_id, priority) 或 (None, error_str, None, None)。
        """
        if "error" in msg:
            err = msg["error"]
            return None, f"IPC_ERROR:{err.get('code','?')}:{err.get('message','?')}", None, None
        if "result" in msg:
            result = msg["result"]
            if isinstance(result, dict) and "_type" in result:
                return EventSerializer.deserialize_from_worker(result)
            return None, f"UNEXPECTED_RESULT:{type(result).__name__}", None, None
        return None, "NO_RESULT", None, None


# ── 默认导出 ──

__all__ = [
    "EventSerializer",
    "IPCBridgeProtocol",
    "_EVENT_TYPE_REGISTRY",
]

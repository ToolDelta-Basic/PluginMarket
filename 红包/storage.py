"""红包状态的安全 JSON 持久化。"""

from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path

from tooldelta.utils.safe_json import safe_json_dump, safe_json_load

from .models import RedPacketState


class RedPacketStore:
    """把红包状态保存到插件数据目录。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> RedPacketState:
        if not self.path.exists():
            state = RedPacketState()
            self.save(state)
            return state
        try:
            raw_state = safe_json_load(str(self.path))
            if not isinstance(raw_state, dict):
                raise ValueError("红包数据根节点必须是对象")
            return RedPacketState.from_dict(raw_state)
        except (JSONDecodeError, KeyError, TypeError, ValueError) as err:
            raise ValueError(f"红包数据文件损坏: {err}") from err

    def save(self, state: RedPacketState) -> None:
        safe_json_dump(state.to_dict(), self.path, indent=2)


from __future__ import annotations

import os

try:
    from .core import load_xuid_map, normalize_xuid, search_player_records
except ImportError:
    from core import load_xuid_map, normalize_xuid, search_player_records


class IdentityIndex:
    # 由 _refresh_identity_index() 写入，在此声明以便静态检查识别该实例属性。
    _identity_records: dict[str, str]

    def _refresh_identity_index(self) -> dict[str, str]:
        records: dict[str, str] = {}
        base = os.path.dirname(str(self.data_path))
        for folder in ("前置-玩家XUID获取", "前置_玩家XUID获取", "XUID获取"):
            path = os.path.join(base, folder, "xuids.json")
            records.update(load_xuid_map(path))
        # get_map() is name -> XUID. Prefer runtime names over saved names,
        # including player names that happen to look like hexadecimal XUIDs.
        if self.xuid_api is not None:
            try:
                mapping = self.xuid_api.get_map()
                if isinstance(mapping, dict):
                    for name, xuid in list(mapping.items()):
                        if not isinstance(name, str) or not name.strip():
                            continue
                        try:
                            records[normalize_xuid(xuid)] = name.strip()
                        except ValueError:
                            continue
            except Exception:
                pass
        self._identity_records = records
        return self._identity_records

    def resolve_player_name(self, xuid: str, refresh: bool = True) -> str | None:
        """从 XUID获取 的在线/离线数据解析名称，未记录时返回 None。"""
        try:
            normalized = normalize_xuid(xuid)
        except ValueError:
            return None
        records = self._refresh_identity_index() if refresh else self._identity_records
        if self.xuid_api is not None:
            try:
                # The pre-plugin also reads offline records from tempjson,
                # which may contain updates not yet written to xuids.json.
                name = self.xuid_api.get_name_by_xuid(normalized, allow_offline=True)
                if isinstance(name, str) and name.strip():
                    return name.strip()
            except Exception:
                pass
        name = records.get(normalized)
        return name.strip() if isinstance(name, str) and name.strip() else None

    def resolve_player_names(self, xuids: list[str]) -> dict[str, str | None]:
        """Resolve several XUIDs in one index refresh for list rendering."""
        self._refresh_identity_index()
        resolved: dict[str, str | None] = {}
        for xuid in xuids:
            try:
                normalized = normalize_xuid(xuid)
            except ValueError:
                continue
            resolved[normalized] = self.resolve_player_name(normalized, refresh=False)
        return resolved

    def search_players(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        """Search the XUID pre-plugin's online/offline identity index."""
        return search_player_records(self._refresh_identity_index(), query, limit)


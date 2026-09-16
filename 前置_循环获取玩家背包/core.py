"""Player inventory querying, cache and broadcast payload construction."""

from __future__ import annotations

import copy
import json
import math
import threading
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Iterable

from tooldelta import utils
from tooldelta.internal.types.inventory_querier import QueriedInventory


class MagicCommandUnavailable(RuntimeError):
    """Compatibility exception for an unavailable command access point."""


class InventoryQueryError(RuntimeError):
    """Raised when a WebSocket inventory command returns an unusable response."""


def validate_cycle_seconds(seconds: float) -> float:
    """Validate and normalize the delay between polling rounds."""
    value = float(seconds)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("轮询间隔必须是大于 0 的有限数字")
    return value


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    """Read a field from either ToolDelta response objects or dictionaries."""
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _player_name(player: Any) -> str:
    """Return a player's display name and reject nameless records."""
    name = getattr(player, "name", None)
    if not isinstance(name, str) or not name:
        raise ValueError("在线玩家对象缺少有效名称")
    return name


def _safe_selector(player: Any) -> str:
    """Return the escaped selector accepted by codebuilder_actorinfo."""
    selector = getattr(player, "safe_name", None)
    if isinstance(selector, str) and selector:
        return selector
    name = _player_name(player)
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _clone_inventory(inventory: QueriedInventory) -> QueriedInventory:
    """Clone a queried inventory so API consumers cannot mutate the cache."""
    return QueriedInventory.from_dict(asdict(inventory))


def inventory_to_dict(inventory: QueriedInventory) -> dict[str, Any]:
    """Convert a queried inventory to the same dictionary shape as DataSet."""
    return copy.deepcopy(asdict(inventory))


def _parse_dataset(dataset: str | bytes | bytearray) -> Any:
    """Parse normal and wrapped JSON text returned in ``DataSet``."""
    if isinstance(dataset, (bytes, bytearray)):
        try:
            text = dataset.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InventoryQueryError("背包返回不是有效 UTF-8") from exc
    else:
        text = dataset

    text = text.lstrip("\ufeff").strip()
    candidates = [text]
    if '\\"' in text:
        candidates.append(
            text.replace('\\"', '"')
            .replace("\\r", "\r")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
        )
    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        current = candidate.lstrip("\ufeff").strip()
        for _ in range(2):
            try:
                payload = json.loads(current)
            except json.JSONDecodeError as exc:
                last_error = exc
                break
            if not isinstance(payload, str):
                return payload
            current = payload.lstrip("\ufeff").strip()
    if last_error is not None:
        raise InventoryQueryError("背包返回不是有效 JSON") from last_error
    raise InventoryQueryError("背包返回 JSON 嵌套层级过深")


def _decode_inventory(response: Any) -> QueriedInventory:
    """Validate a command response and decode its inventory payload."""
    success_count = _get_value(response, "SuccessCount", 0)
    if isinstance(success_count, str):
        try:
            success_count = int(success_count.strip())
        except ValueError:
            success_count = 0
    if not success_count:
        raise InventoryQueryError("查询玩家背包内容失败")

    dataset = _get_value(response, "DataSet", "")
    if isinstance(dataset, (str, bytes, bytearray)):
        payload = _parse_dataset(dataset)
    elif isinstance(dataset, dict):
        payload = dataset
    else:
        raise InventoryQueryError("背包返回缺少 DataSet")

    # ToolDelta's ``queryPlayerInventory`` returns the inventory object
    # directly.  Some launcher builds wrap the same object in an
    # ``{"inventory": ...}`` envelope, so accept both shapes.
    if not isinstance(payload, dict):
        raise InventoryQueryError("背包返回缺少 inventory 字段")
    inventory_data = payload.get("inventory", payload)
    if not isinstance(inventory_data, dict):
        raise InventoryQueryError("背包返回缺少 inventory 字段")
    try:
        return QueriedInventory.from_dict(inventory_data)
    except (KeyError, TypeError, ValueError) as exc:
        raise InventoryQueryError("背包 inventory 字段结构无效") from exc


class InventoryService:
    """Query all online players, maintain a current snapshot and expose APIs."""

    def __init__(
        self,
        game_ctrl: Any,
        players_provider: Callable[[], Iterable[Any]],
        publish: Callable[[dict[str, Any]], Any] | None = None,
        now: Callable[[], str] | None = None,
    ):
        """初始化背包服务：记录依赖、清空缓存并建立并发锁。"""
        self.game_ctrl = game_ctrl
        self.players_provider = players_provider
        self.publish = publish
        self.now = now or (
            lambda: datetime.now().astimezone().isoformat(timespec="seconds")
        )
        self._cache: dict[str, QueriedInventory] = {}
        self._last_failures: dict[str, dict[str, str]] = {}
        self._last_scan_timestamp: str | None = None
        self._lock = threading.RLock()
        # A manual force-update and the periodic worker may be triggered at
        # the same time.  Serialise complete rounds so snapshots cannot
        # overwrite one another out of order.
        self._scan_lock = threading.Lock()

    def query_inventory(self, player_name: str, timeout: float = 1) -> QueriedInventory:
        """Query one currently online player through the WebSocket command channel."""
        player = None
        for candidate in self.players_provider():
            if not getattr(candidate, "online", True):
                continue
            try:
                candidate_name = _player_name(candidate)
            except (TypeError, ValueError):
                continue
            if candidate_name == player_name:
                player = candidate
                break
        if player is None:
            raise ValueError(f"玩家 {player_name} 当前不在线")
        inventory = self._query_player(player, timeout)
        with self._lock:
            self._cache[player_name] = _clone_inventory(inventory)
            self._last_failures.pop(player_name, None)
        return _clone_inventory(inventory)

    def _query_player(self, player: Any, timeout: float) -> QueriedInventory:
        """Send one inventory command over WebSocket and decode its response."""
        sender = getattr(self.game_ctrl, "sendwscmd", None)
        if not callable(sender):
            raise MagicCommandUnavailable("当前接入点不支持 sendwscmd")
        try:
            response = sender(
                f"codebuilder_actorinfo inventory {_safe_selector(player)}",
                True,
                timeout,
            )
        except (AttributeError, NotImplementedError) as exc:
            raise MagicCommandUnavailable(
                "当前接入点不支持 sendwscmd"
            ) from exc
        return _decode_inventory(response)

    def _safe_query(self, player: Any, timeout: float):
        """Convert a per-player exception into a result tuple."""
        try:
            name = _player_name(player)
            return name, self._query_player(player, timeout), None
        except MagicCommandUnavailable:
            raise
        except Exception as exc:  # one player must not abort the whole scan
            # A malformed player object has no stable key that can be exposed
            # in the failure map.  The round continues and valid players are
            # still queried.
            name = getattr(player, "name", None)
            if not isinstance(name, str) or not name:
                return "", None, exc
            return name, None, exc

    def _current_players(self) -> list[Any]:
        """Return unique online players from the provider."""
        result: list[Any] = []
        seen: set[str] = set()
        for player in self.players_provider():
            if not getattr(player, "online", True):
                continue
            try:
                name = _player_name(player)
            except (TypeError, ValueError):
                continue
            if name in seen:
                continue
            seen.add(name)
            result.append(player)
        return result

    def scan(self, timeout: float = 1) -> dict[str, QueriedInventory]:
        """Concurrently query all current players and replace the cache."""
        with self._scan_lock:
            players = self._current_players()
            tasks = [(self._safe_query, (player, timeout)) for player in players]
            results = utils.thread_gather(tasks) if tasks else []
            successes: dict[str, QueriedInventory] = {}
            failures: dict[str, dict[str, str]] = {}
            timestamp = self.now()
            for name, inventory, error in results:
                if error is None and inventory is not None:
                    successes[name] = _clone_inventory(inventory)
                else:
                    reason = (
                        (str(error) or error.__class__.__name__)
                        if error is not None
                        else "未返回库存"
                    )
                    failures[name] = {
                        "错误": reason,
                        "失败原因": reason,
                        "时间": timestamp,
                    }
            with self._lock:
                self._cache = successes
                self._last_failures = failures
                self._last_scan_timestamp = timestamp
            return self.get_cached_inventories()

    def scan_and_publish(self, timeout: float = 1) -> dict[str, Any]:
        """Run a scan, publish both inventory formats and return its snapshot."""
        self.scan(timeout)
        with self._lock:
            objects = {
                name: _clone_inventory(inventory)
                for name, inventory in self._cache.items()
            }
            raw = {name: inventory_to_dict(item) for name, item in objects.items()}
            failures = copy.deepcopy(self._last_failures)
            updated_at = self._last_scan_timestamp or self.now()
        snapshot = {
            "玩家背包": objects,
            "玩家背包字典": raw,
            "失败玩家": failures,
            "更新时间": updated_at,
        }
        if self.publish is not None:
            self.publish(snapshot)
        return snapshot

    def get_cached_inventory(self, player_name: str) -> QueriedInventory | None:
        """Return one cloned cached inventory, or None when unavailable."""
        with self._lock:
            inventory = self._cache.get(player_name)
            return _clone_inventory(inventory) if inventory is not None else None

    def get_cached_inventories(self) -> dict[str, QueriedInventory]:
        """Return cloned cached inventories for all successful players."""
        with self._lock:
            return {
                name: _clone_inventory(inventory)
                for name, inventory in self._cache.items()
            }

    def get_cached_inventories_dict(self) -> dict[str, dict[str, Any]]:
        """Return cached inventories in raw dictionary form."""
        return {
            name: inventory_to_dict(inventory)
            for name, inventory in self.get_cached_inventories().items()
        }

    def get_last_failures(self) -> dict[str, dict[str, str]]:
        """Return failure metadata from the most recent scan."""
        with self._lock:
            return copy.deepcopy(self._last_failures)

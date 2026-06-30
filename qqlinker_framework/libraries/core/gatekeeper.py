import json
import logging
import os
import threading
from typing import Dict, Optional

from ..channel_host import Library

_log = logging.getLogger(__name__)


class UIDStore:
    """用户 UID 等级持久化存储。"""

    def __init__(self, file_path: str):
        self._path = file_path
        self._lock = threading.Lock()
        self._uids: Dict[int, int] = {}  # qq -> uid
        self._load()

    def _load(self) -> None:
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._uids = {int(k): v for k, v in data.items()}
            except Exception:
                self._uids = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._uids, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except OSError as e:
            _log.warning("gatekeeper._save: %s", e)

    def get_uid(self, qq: int) -> int:
        """获取用户 UID 等级。默认 400 (nobody)。"""
        with self._lock:
            return self._uids.get(qq, 400)

    def set_uid(self, qq: int, uid: int) -> None:
        """设置用户 UID 等级。"""
        with self._lock:
            self._uids[qq] = uid
            self._save()

    def remove(self, qq: int) -> bool:
        """移除用户 UID 记录。"""
        with self._lock:
            if qq in self._uids:
                del self._uids[qq]
                self._save()
                return True
            return False

    def list_all(self) -> Dict[int, int]:
        """列出所有用户 UID。"""
        with self._lock:
            return dict(self._uids)


class Gatekeeper:
    """权限守门人 — 管理员列表 + UID 查询。"""

    def __init__(self, config, uid_store: UIDStore):
        self._config = config
        self._uid_store = uid_store

    def get_admins(self) -> list:
        """获取管理员 QQ 列表。"""
        return self._config.get("管理员.管理员QQ", [])

    def is_admin(self, qq: int) -> bool:
        return qq in self.get_admins()

    def lookup_uid(self, qq: int) -> int:
        """查询用户 UID 等级。管理员自动为 100，root 为 0。"""
        stored = self._uid_store.get_uid(qq)
        if stored < 400:
            return stored
        if self.is_admin(qq):
            return 100
        return 400

    def grant_uid(self, qq: int, uid: int) -> None:
        self._uid_store.set_uid(qq, uid)

    def revoke_uid(self, qq: int) -> None:
        self._uid_store.remove(qq)


class GatekeeperLibrary(Library):
    """Gatekeeper 库。"""

    name = "gatekeeper"
    version = "1.6.0"
    dependencies = ["config_store"]

    async def mount(self) -> None:
        data_path = self.services.get("_data_path")
        config = self.services.get("config")

        uid_store = UIDStore(os.path.join(data_path, "注册表", "用户UID.json"))
        gk = Gatekeeper(config, uid_store)

        self.services.register("uid_lookup", gk.lookup_uid, mid=300)
        self.services.register("gatekeeper", gk, mid=100)

    async def unmount(self) -> None:
        pass

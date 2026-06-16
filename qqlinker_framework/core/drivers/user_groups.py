"""用户组注册表 — 用户权限分组管理。

持久化文件：注册表/用户组.json

结构：
{
  "用户组": {
    "服主": {
      "成员": [123456, 789012],
      "权限": {
        "ai":   {"配置读": true, "配置写": true, "卸载": false},
        "game": {"配置读": true, "配置写": true, "卸载": true}
      }
    },
    "管理": {
      "成员": [345678],
      "权限": {
        "ai":   {"配置读": true, "配置写": false, "卸载": false}
      }
    }
  }
}
"""
import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Set

_log = logging.getLogger(__name__)

REGISTRY_DIR = "注册表"
USER_GROUP_FILENAME = "用户组.json"


class UserGroupRegistry:
    """用户组注册表：用户→组→权限映射。"""

    def __init__(self, data_path: str):
        self._file_path = os.path.join(data_path, REGISTRY_DIR, USER_GROUP_FILENAME)
        self._lock = threading.Lock()
        self._groups: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        if os.path.isfile(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._groups = data.get("用户组", {})
            except (json.JSONDecodeError, IOError) as e:
                _log.warning("用户组注册表加载失败: %s", e)
                self._groups = {}
        else:
            self._groups = {}
            self._save()

    def _save(self) -> None:
        try:
            tmp = self._file_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"用户组": self._groups}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._file_path)
        except OSError as e:
            _log.error("用户组注册表保存失败: %s", e)

    # ── 查询 API ──

    def get_user_groups(self, user_id: int) -> List[str]:
        """获取用户所属的所有组名。"""
        with self._lock:
            result = []
            for group_name, group_data in self._groups.items():
                members = group_data.get("成员", [])
                if user_id in members:
                    result.append(group_name)
            return result

    def check_permission(self, user_id: int, module_group: str,
                         action: str) -> bool:
        """检查用户对指定模块组的指定操作是否有权限。

        action: "配置读", "配置写", "卸载"
        """
        with self._lock:
            for group_data in self._groups.values():
                if user_id not in group_data.get("成员", []):
                    continue
                perms = group_data.get("权限", {}).get(module_group, {})
                if perms.get(action, False):
                    return True
            return False

    def get_permissions(self, user_id: int, module_group: str) -> dict:
        """获取用户对指定模块组的所有权限。"""
        result = {"配置读": False, "配置写": False, "卸载": False}
        with self._lock:
            for group_data in self._groups.values():
                if user_id not in group_data.get("成员", []):
                    continue
                perms = group_data.get("权限", {}).get(module_group, {})
                for key in result:
                    if perms.get(key, False):
                        result[key] = True
        return result

    # ── 修改 API ──

    def create_group(self, name: str, members: List[int] = None,
                     permissions: Dict[str, dict] = None) -> bool:
        with self._lock:
            if name in self._groups:
                return False
            self._groups[name] = {
                "成员": members or [],
                "权限": permissions or {},
            }
            self._save()
            return True

    def add_member(self, group_name: str, user_id: int) -> bool:
        with self._lock:
            group = self._groups.get(group_name)
            if group is None:
                return False
            members = group.get("成员", [])
            if user_id not in members:
                members.append(user_id)
                group["成员"] = members
                self._save()
            return True

    def remove_member(self, group_name: str, user_id: int) -> bool:
        with self._lock:
            group = self._groups.get(group_name)
            if group is None:
                return False
            members = group.get("成员", [])
            if user_id in members:
                members.remove(user_id)
                group["成员"] = members
                self._save()
            return True

    def set_permission(self, group_name: str, module_group: str,
                       action: str, allowed: bool) -> bool:
        with self._lock:
            group = self._groups.get(group_name)
            if group is None:
                return False
            perms = group.setdefault("权限", {})
            mod_perms = perms.setdefault(module_group, {})
            mod_perms[action] = allowed
            self._save()
            return True

    def delete_group(self, name: str) -> bool:
        with self._lock:
            if name not in self._groups:
                return False
            del self._groups[name]
            self._save()
            return True

    def list_groups(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._groups)

    def stats(self) -> dict:
        with self._lock:
            total = len(self._groups)
            members = sum(len(g.get("成员", [])) for g in self._groups.values())
            return {"总组数": total, "总成员数": members}

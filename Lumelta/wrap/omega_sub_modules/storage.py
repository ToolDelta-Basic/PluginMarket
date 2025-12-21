from ..loosejson import loads
from ..database import key_value_db
from ..conversion import lua_table_to_python
import os
import json
from typing import Any, Optional

class KVDB:
    def __init__(self, db, omega):
        self.omega = omega
        self.lua_runtime = self.omega.lua_runtime
        self.db = db
        self.empty = self.lua_runtime.eval('""')

    def get(self, key):
        return self.db.get(key) or self.empty

    def delete(self, key):
        self.db.delete(key)

    def set(self, key, value):
        self.db.set(key, value)

    def iter(self, callback):
        for key, value in self.db.iter():
            callback(key, value or self.empty)

class Storage:
    """数据存储操作类"""
    def __init__(self, omega):
        self.omega = omega
    
    def save(self, path: str, data: Any) -> None:
        """将数据以JSON格式保存到文件"""
        path = self.omega.storage_dir_path / path
        # 确保父目录存在
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # 写入JSON数据（带缩进和UTF-8编码）
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(lua_table_to_python(data), f, ensure_ascii=False, indent=4)
    
    def read(self, path: str) -> Optional[Any]:
        """从JSON文件读取数据"""
        path = self.omega.storage_dir_path / path
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return loads(f.read())
        except (FileNotFoundError, json.JSONDecodeError):
            return None  # 对应Lua的nil返回
    
    def save_text(self, path: str, data: str) -> None:
        """将文本数据保存到文件"""
        path = self.omega.storage_dir_path / path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(data)
    
    def read_text(self, path: str) -> Optional[str]:
        """从文本文件读取数据"""
        path = self.omega.storage_dir_path / path
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return None  # 对应Lua的nil返回

    def get_kv_db(self, name, db_type=""):
        path = self.omega.data_dir_path / name
        return KVDB(key_value_db(path, db_type), self.omega)
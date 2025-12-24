from pathlib import Path
#import plyvel
import os, json
from abc import ABC, abstractmethod

class KeyValueDB(ABC):
    @abstractmethod
    def get(self, key):
        pass

    @abstractmethod
    def set(self, key, value):
        pass

    @abstractmethod
    def delete(self, key):
        pass

    @abstractmethod
    def iter(self, fn):
        pass

    def migrate_to(self, new_db):
        def migrate_fn(key, value):
            new_db.set(key, value)
            return True
        self.iter(migrate_fn)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class TextLogDB(KeyValueDB):
    def __init__(self, path):
        self.dir_path = Path(path)
        self.block_path = self.dir_path / "block.json"
        self.log_path = self.dir_path / 'log.log'
        self.data = {}
        os.makedirs(self.dir_path, exist_ok=True)
        self.block_path.touch()
        self.log_path.touch()
        with open(self.log_path, 'r') as f:
            while True:
                key_str = f.readline()
                value_str = f.readline()
                if not key_str or not value_str:
                    break
                try:
                    key = json.loads(key_str)
                    value = json.loads(value_str)
                    self.data[key] = value
                except json.JSONDecodeError:
                    continue

    def set(self, key, value):
        self.data[key] = value
        key_str = json.dumps(key)
        value_str = json.dumps(value)
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(key_str) + '\n')
            f.write(json.dumps(value_str) + '\n')

    def delete(self, key):
        if key in self.data:
            del self.data[key]
        key_str = json.dumps(key)
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(key_str) + '\n')
            f.write(json.dumps("") + '\n')

    def get(self, key):
        return self.data.get(key, "")

    def iter(self):
        for key, value in list(self.data.items()):
            yield key, value

    def close(self):
        pass

class JsonDB(KeyValueDB):
    def __init__(self, path):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            with open(path, 'r') as f:
                try:
                    self.data = json.load(f)
                except json.JSONDecodeError:
                    self.data = {}

    def set(self, key, value):
        self.data[key] = value
        self._save()

    def delete(self, key):
        if key in self.data:
            del self.data[key]
            self._save()

    def get(self, key):
        return self.data.get(key, None)

    def iter(self):
        for key, value in list(self.data.items()):
            yield key, value

    def _save(self):
        with open(self.path, 'w') as f:
            json.dump(self.data, f)
"""
class LevelDB(KeyValueDB):
    def __init__(self, path):
        self.db = plyvel.DB(path, create_if_missing=True)

    def get(self, key):
        value = self.db.get(key.encode('utf-8'))
        return value.decode('utf-8') if value else None

    def set(self, key, value):
        self.db.put(key.encode('utf-8'), value.encode('utf-8'))

    def delete(self, key):
        self.db.delete(key.encode('utf-8'))

    def iter(self):
        it = self.db.iterator()
        for key_bytes, value_bytes in it:
            key = key_bytes.decode('utf-8')
            value = value_bytes.decode('utf-8')
            yield key, value

    def close(self):
        self.db.close()
"""
def key_value_db(path, db_type='text_log'):
    if db_type in ('', 'text_log'):
        return TextLogDB(path)
#    elif db_type == 'level':
#        return LevelDB(path)
    elif db_type == 'json':
        return JsonDB(path)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
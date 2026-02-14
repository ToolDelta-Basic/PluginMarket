from .loosejson import loads
from .conversion import lua_table_to_python, python_to_lua_table
import json

class Json:
    def __init__(self, lua_runtime):
        self.lua_runtime = lua_runtime
        self.empty = self.lua_runtime.eval('""')

    def encode(self, data):
        return json.dumps(lua_table_to_python(data), ensure_ascii=False)
    loose_encode = encode

    def decode(self, data):
        try:
            return python_to_lua_table(loads(data), self.lua_runtime)
        except:
            return self.empty
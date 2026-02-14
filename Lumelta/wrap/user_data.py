from .conversion import python_to_lua_table

class UserData:
    def __init__(self, data, lua_runtime):
        self.lua_runtime = lua_runtime
        self.data = data

    def user_data(self):
        return python_to_lua_table(self.data, self.lua_runtime)

import queue
from ..make import make_game_msg, make_game_msg_receive
from ..conversion import lua_table_to_python, python_to_lua_table
from ..lua import python_index_to_lua_index

class Menu:
    def __init__(self, omega):
        self.omega = omega
        self.lua_runtime = self.omega.lua_runtime
        self.frame = self.omega.frame
        self.chatbar = self.omega.chatbar

    def add_backend_menu_entry(self, options):
        options = lua_table_to_python(options)
        triggers = options["triggers"]
        argument_hint = options["argument_hint"]
        usage = options["usage"]
        result_queue = queue.Queue()
        def callback(data):
            result_queue.put(python_index_to_lua_index(data))
        self.frame.add_console_cmd_trigger(
            triggers,
            argument_hint,
            usage,
            callback
        )
        def entry():
            while True:
                try:
                    data = result_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                yield data
        return entry

    def add_game_menu_entry(self, options):
        options = lua_table_to_python(options)
        triggers = options["triggers"]
        argument_hint = options["argument_hint"]
        usage = options["usage"]
        result_queue = queue.Queue()
        def callback(data):
            result_queue.put(data)
        callback = make_game_msg_receive(callback)
        self.chatbar.add_trigger(
            triggers,
            argument_hint,
            usage,
            callback
        )
        def entry():
            while True:
                try:
                    data = result_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                yield data
        return entry
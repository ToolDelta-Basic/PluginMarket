import threading
import queue
from tooldelta import utils
from .players import Players
from ..user_data import UserData
from ..conversion import python_to_lua_table

class Cmds:
    def __init__(self, omega):
        self.omega = omega
        self.game_ctrl = self.omega.game_ctrl
        self.lua_runtime = self.omega.lua_runtime
        self.result_queue = queue.Queue()

    def send_ws_cmd(self, cmd):
        self.game_ctrl.sendwscmd(cmd)

    def send_ws_cmd_with_resp(self, cmd, callback, timeout=30):
        if not timeout: timeout = 30
        @utils.thread_func(f"omega run command ({cmd})")
        def run():
            command_output = self.game_ctrl.sendwscmd(cmd, True, timeout).as_dict
            user_data = UserData(command_output, self.lua_runtime)
            self.result_queue.put((callback, user_data))
        run()

    def send_wo_cmd(self, cmd, *args):
        self.game_ctrl.sendwocmd(cmd)

    def resp(self):
        while True:
            try:
                cb, output = self.result_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            yield {
                "cb": cb,
                "output": output
            }

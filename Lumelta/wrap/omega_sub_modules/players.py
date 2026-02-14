from ..safe import SafeList
from ..lua import python_index_to_lua_index
from ..make import make_game_msg
from ..conversion import lua_table_to_python
from tooldelta import utils
from tooldelta.constants import PacketIDS
import queue
import time

class PlayerKit:
    def __init__(self, players, player):
        self.players = players
        self.player = player
        self.omega = self.players.omega
        self.frame = self.omega.frame
        self.game_ctrl = self.frame.get_game_control()
        self.unpack = self.players.unpack
        self.result_queue = self.players.result_queue

    def say(self, text, *args):
        self.player.show(text)

    def raw_say(self, raw_text, *args):
        self.game_ctrl.sendwocmd(f"/tellraw {self.player.getSelector()} {raw_text}")

    def intercept_just_next_input(self, callback, timeout=86400):
        if not timeout: timeout = 86400
        @utils.thread_func("player_kit:intercept_just_next_input")
        def run():
            player_input = self.player.input("", timeout)
            player_game_msg = make_game_msg(name=self.get_name()[0], raw_msg=player_input)
            self.result_queue.put((callback, player_game_msg))
        run()

    def title(self, title, subtitle=None):
        self.player.setTitle(title, subtitle)

    def subtitle(self, subtitle, title=None):
        self.player.setTitle(title, subtitle)

    def action_bar(self, text):
        self.player.setActionBar(text)

    def check_condition(self, conditions, callback):
        @utils.thread_func("player_kit:check_condition")
        def run():
            def _run(*conditions):
                @utils.thread_func("check_condition")
                def __run():
                    cmd = f"/testfor {self.player.getSelector()[:-1]},{','.join(conditions)}]"
                    check_condition_result = self.game_ctrl.sendwscmd(cmd, True).as_dict["OutputMessages"][0]["Success"]
                    self.result_queue.put((callback, check_condition_result))
                __run()
            self.result_queue.put((self.unpack, python_index_to_lua_index([_run, conditions])))
        run()

    def get_uuid_string(self):
        return self.player.uuid, True if self.player.uuid else False

    def get_name(self):
        return self.player.name, True if self.player.name else False
    get_username = get_name

    def get_entity_unique_id(self):
        return self.player.unique_id, True if self.player.unique_id else False

    def get_login_time(self):
        return 0, False # ToolDelta没有（？

    def get_platform_chat_id(self):
        return self.player.platform_chat_id, True if self.player.platform_chat_id else False

    def get_build_platform(self):
        return self.player.build_platform, True if self.player.build_platform else False

    def skin_id(self):
        return 0, False # ToolDelta没有（？

    def get_build_ability(self):
        return self.player.abilities.build, True
    
    def set_build_ability(self, allow):
        self.player.abilities.build = allow
        self.player.setAbilities(self.player.abilities)
        return allow

    def get_mine_ability(self):
        return self.player.abilities.mine, True
    
    def set_mine_ability(self, allow):
        self.player.abilities.mine = allow
        self.player.setAbilities(self.player.abilities)
        return allow

    def get_door_and_switches_ability(self):
        return self.player.abilities.doors_and_switches, True
    
    def set_door_and_switches_ability(self, allow):
        self.player.abilities.doors_and_switches = allow
        self.player.setAbilities(self.player.abilities)
        return allow

    def get_open_container_ability(self):
        return self.player.abilities.open_containers, True
    
    def set_open_container_ability(self, allow):
        self.player.abilities.open_containers = allow
        self.player.setAbilities(self.player.abilities)
        return allow

    def get_attack_player_ability(self):
        return self.player.abilities.attack_players, True
    
    def set_attack_player_ability(self, allow):
        self.player.abilities.attack_players = allow
        self.player.setAbilities(self.player.abilities)
        return allow

    def get_attack_mobs_ability(self):
        return self.player.abilities.attack_mobs, True
    
    def set_attack_mobs_ability(self, allow):
        self.player.abilities.attack_mobs = allow
        self.player.setAbilities(self.player.abilities)
        return allow

    def get_operator_command_ability(self):
        return self.player.abilities.operator_commands, True
    
    def set_operator_command_ability(self, allow):
        self.player.abilities.operator_commands = allow
        self.player.setAbilities(self.player.abilities)
        return allow

    def get_teleport_ability(self):
        return self.player.abilities.teleport, True
    
    def set_teleport_ability(self, allow):
        self.player.abilities.teleport = allow
        self.player.setAbilities(self.player.abilities)
        return allow

    def get_flying_status(self):
        return self.player.abilities.flying, True
    
    def get_invulnerable_status(self):
        return self.player.abilities.invulnerable, True

    def get_device_id(self):
        return self.player.device_id, True if self.player.device_id else False

    def get_entity_runtime_id(self):
        return 0, False # ToolDelta没有（？

    def get_entity_metadata(self):
        return {}, False # ToolDelta没有（？

    def is_op(self):
        return self.player.is_op(), True

    def still_online(self):
        return self.player.online, True

class Players:
    def __init__(self, omega):
        self.omega = omega
        self.frame = self.omega.frame
        self.lua_runtime = self.omega.lua_runtime
        self.game_ctrl = self.omega.game_ctrl
        self.players = self.omega.players
        self.info = self.omega.info
        self.packet_handler = self.omega.packet_handler
        self.event_cbs = self.omega.event_cbs
        self.on_player_join_cbs = self.event_cbs.on_player_join_cbs
        self.on_player_leave_cbs = self.event_cbs.on_player_leave_cbs
        self.unpack = self.lua_runtime.eval("""function (args)
            func, data = args[1], args[2]
            func(unpack(data))
        end""")
        self.result_queue = queue.Queue()

    def get_player_by_name(self, name):
        player = self.players.getPlayerByName(name)
        if player:
            return PlayerKit(self, player), True
        return None, False

    def get_player_by_uuid_string(self, uuid_string):
        player = self.players.getPlayerByUUID(uuid_string)
        if player:
            return PlayerKit(self, player), True
        return None, False

    def get_all_online_players(self):
        players = []
        for player in self.players.getAllPlayers():
            players.append(PlayerKit(self, player))
        return SafeList(python_index_to_lua_index(players))

    def make_chat_poller(self):
        result_queue = queue.Queue()
        def callback(data):
            name = data["SourceName"]
            raw_msg = data["Message"]
            type = data["TextType"]
            data = make_game_msg(name=name, raw_msg=raw_msg, type=type)
            result_queue.put(data)
            return False
        self.packet_handler.add_dict_packet_listener(PacketIDS.IDText, callback)
        def entry():
            while True:
                try:
                    data = result_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                yield data
        return entry

    def make_player_change_poller(self):
        result_queue = queue.Queue()
        def callback_join(data):
            name = data.name
            player, _ = self.get_player_by_name(name)
            data = {
                "player": player,
                "action": "online"
            }
            result_queue.put(data)
        self.on_player_join_cbs.append((
            self.info,
            callback_join
        ))
        def callback_leave(data):
            name = data.name
            player, _ = self.get_player_by_name(name)
            data = {
                "player": player,
                "action": "offline"
            }
            result_queue.put(data)
        self.on_player_leave_cbs.append((
            self.info,
            callback_leave
        ))
        for player in self.players.getAllPlayers():
            player = PlayerKit(self, player)
            data = {
                "player": player,
                "action": "exist"
            }
            result_queue.put(data)
        def entry():
            while True:
                try:
                    data = result_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                yield data
        return entry   
    def say_to(self, selector, text):
        self.game_ctrl.say_to(selector, text)

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
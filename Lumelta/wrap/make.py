from .conversion import python_to_lua_table, lua_table_to_python
from .safe import SafeDict, SafeList
from .lua import python_index_to_lua_index
from tooldelta.utils.cfg import _get_cfg_type_name

class GameMsg:
    def __init__(
        self,
        name,
        msg,
        raw_msg,
        type
    ):
        self.name = name
        self.msg = msg
        self.raw_msg = raw_msg
        self.type = type

def make_game_msg(name, args=None, raw_msg=None, type=7):
    data = GameMsg(
        name = name,
        msg = SafeList(python_index_to_lua_index((raw_msg or "").split(" ") if args is None else args)),
        raw_msg = " ".join([arg or "" for arg in (args or [])]) if raw_msg is None else raw_msg,
        type = type
    )
    return data

def make_ud2lua(lua_runtime):
    def ud2lua(ud):
        return python_to_lua_table(ud, lua_runtime)
    return ud2lua

def make_game_msg_receive(func):
    def game_msg_receive(name, args):
        game_msg = make_game_msg(name=name, args=args)
        func(game_msg)
    return game_msg_receive

def make_on_trig_callback(entry, players, is_new):
    def on_trig_callback(chat):
        args = lua_table_to_python(chat.msg) + [""]
        player = chat.name
        if is_new:
            argument_hints = entry.argument_hints
            player = players.getPlayerByName(player)
            if args[0] is None:
                args = args[1:]
            for index, arg in enumerate(list(args)):
                if index < len(argument_hints):
                    _, type, default = argument_hints[index]
                    if arg:
                        try:
                            args[index] = type(arg)
                        except:
                            player.show(f"§c{args[index]} 不是一个{_get_cfg_type_name(type)}")
                            return
                    else:
                        args[index] = default
        entry.func(player, args)
    return on_trig_callback
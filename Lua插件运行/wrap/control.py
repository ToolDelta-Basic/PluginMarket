import importlib
import sys
import os
import json
import time
import queue
import traceback
from pathlib import Path
from lupa import LuaRuntime
from collections import defaultdict
from tooldelta.utils import fmts
from tooldelta.utils.cfg import _get_cfg_type_name, check_auto, get_plugin_config_and_version, upgrade_plugin_config, check_dict
from tooldelta import utils
from tooldelta.plugin_load.classic_plugin import event_cbs
from . import Json, register_module, LumegaPluginConfig, Omega, loads, LumegaPluginConfig, SafeList, SafeDict, python_index_to_lua_index, lua_table_to_python, make_on_trig_callback, loads

from .omega_sub_modules import (
    Storage, Cmds, Players, Listen,
    System, BotAction, AsyncHttp, Cqhttp, 
    Flex, Share, Websocket, Menu, 
    StoragePath, Builder, Common, BotUq
)

def get_builtin_plugin_entry(builtin_plugin_name):
    # 获取当前包的名称
    package = __package__
    # 相对模块路径
    relative_module = f".builtin_plugins.{builtin_plugin_name}"
    
    # 解析为绝对模块名
    abs_module = importlib.util.resolve_name(relative_module, package)
    
    # 删除现有缓存（如果存在）
    if abs_module in sys.modules:
        del sys.modules[abs_module]
    
    # 重新导入模块
    module = importlib.import_module(relative_module, package)
    
    # 获取最新的 entry 对象
    entry = module.entry
    return entry

class ChatbarTriggers(list):
    def __init__(self, data, *args, result_queue = queue.Queue()):
        super().__init__([], *args)
        self.result_queue = result_queue
        for i in data:
            self.append(i)

    def append(self, element):
        super().append(element)
        self.result_queue.put(element)

    """
    def extend(self, iterable):
        old_len = len(self)
        super().extend(iterable)
        new_len = len(self)
        added = new_len - old_len
        if added > 0:
            print(f"提示: 通过extend添加了 {added} 个元素")
    
    def insert(self, index, element):
        super().insert(index, element)
        print(f"提示: 在位置 {index} 插入了一个元素 → {element}")
    
    def __setitem__(self, key, value):
        old_len = len(self)
        super().__setitem__(key, value)
        new_len = len(self)
        added = new_len - old_len
        if added > 0:
            print(f"提示: 通过索引/切片添加了 {added} 个元素")
    
    def __iadd__(self, other):
        old_len = len(self)
        super().__iadd__(other)
        added = len(self) - old_len
        if added > 0:
            print(f"提示: 通过 += 添加了 {added} 个元素")
        return self
    
    def __imul__(self, factor):
        old_len = len(self)
        super().__imul__(factor)
        added = len(self) - old_len
        if added > 0:
            print(f"提示: 通过 *= 添加了 {added} 个元素")
        return self    
    """

class FlexAPI:
    def __init__(self, control):
        self.control = control
        self.expose_apis = defaultdict(queue.Queue)
        self.topics = defaultdict(queue.Queue)
        self.softs = defaultdict(None)

    def null(self, *args):
        pass

    def expose(self, api_name):
        return self.expose_apis[api_name]

    def call(self, api_name, args, cb, timeout = None):
        self.expose_apis[api_name].put((args, cb or self.null))

    def listen(self, topic):
        return self.topics[topic]

    def pub(self, topic, data):
        self.topics[topic].put(data)

    def set(self, key, val):
        self.softs[key] = val

    def get(self, key):
        return self.softs[key], False if self.softs[key] is None else True

class Control:
    def __init__(self, frame, storage_dir_path = "."):
        self.frame = frame
        self.flex_api = FlexAPI(self)
        self.event_cbs = event_cbs
        self.game_ctrl = self.frame.get_game_control()
        self.players = self.frame.get_players()
        self.game_data_handler = self.game_ctrl.game_data_handler
        self.chatbar = self.frame.plugin_group.get_plugin_api("聊天栏菜单")
        self.chatbar_triggers_queue = queue.Queue()
        self.chatbar.chatbar_triggers = ChatbarTriggers(self.chatbar.chatbar_triggers, result_queue=self.chatbar_triggers_queue)
        self.world_interactive = self.frame.plugin_group.get_plugin_api("前置-世界交互")
        self.storage_dir_path = Path(storage_dir_path)
        self.config_dir_path = self.storage_dir_path / "config"
        self.framework_config_file_path = self.config_dir_path / "neomega框架配置.json"
        self.cache_dir_path = self.storage_dir_path / "cache"
        self.code_dir_path = self.storage_dir_path / "lang"
        self.data_dir_path = self.storage_dir_path / "data"
        self.log_dir_path = self.storage_dir_path / "log"
        self.lua_code_dir_path = self.code_dir_path / "LuaLoader"
        for dir_path in [self.config_dir_path, self.cache_dir_path, self.lua_code_dir_path,
                        self.code_dir_path, self.data_dir_path, self.log_dir_path]:
            os.makedirs(dir_path, exist_ok=True)
        self.framework_config = loads(self.framework_config_file_path.read_text(encoding="utf-8"))
        # plugins
        self.builtin_plugins = []
        self.lua_plugins = []
        # 终端模块
        self.terminal_module_config = self.framework_config["终端模块配置"]
        self.terminal_module_plugin_config = LumegaPluginConfig(json.dumps({
        	"名称": self.terminal_module_config["菜单驱动lua脚本路径"],
        	"配置": {},
        	"描述": "终端菜单",
        	"是否禁用": False,
        	"来源": "LuaLoader"
        }))
        self.terminal_module_lua_runtime = self.setup_lua_plugin_runtime(LuaRuntime(unpack_returned_tuples=True), self.terminal_module_plugin_config)
        self.terminal_module_poller = self.terminal_module_lua_runtime.globals().omega.listen.make_mux_poller()
        self.terminal_module_lua_runtime.globals().poller = self.terminal_module_poller
        self.load_lua_plugin_file(
            self.config_dir_path / self.terminal_module_config["菜单驱动lua脚本路径"],
            self.terminal_module_plugin_config,
            lua_runtime = self.terminal_module_lua_runtime
        )
        # 游戏菜单模块
        self.game_menu_module_config = self.framework_config["游戏菜单模块配置"]
        self.game_menu_module_plugin_config = LumegaPluginConfig(json.dumps({
        	"名称": self.game_menu_module_config["菜单驱动lua脚本路径"],
        	"配置": self.game_menu_module_config["菜单选项"],
        	"描述": "游戏菜单",
        	"是否禁用": False,
        	"来源": "LuaLoader"
        }))
        self.game_menu_module_lua_runtime = self.setup_lua_plugin_runtime(LuaRuntime(unpack_returned_tuples=True), self.game_menu_module_plugin_config)
        def game_menu_active_poller():
            while True:
                try:
                    entry = self.chatbar_triggers_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                is_new = hasattr(entry, "argument_hints")
                argument_hint = ""
                if is_new:
                    argument_hint = " ".join([f"[{hint}: {_get_cfg_type_name(type)}]" for hint, type, _ in entry.argument_hints])
                else:
                    argument_hint = entry.argument_hint
                yield SafeDict({
                    "triggers": SafeList(python_index_to_lua_index([str(trigger) for trigger in entry.triggers])),
                    "argument_hint": str(argument_hint),
                    "usage": str(entry.usage),
                    "on_trig_callback": make_on_trig_callback(entry, self.players, is_new)
                })
        self.game_menu_module_lua_runtime.globals().game_menu_active_poller = game_menu_active_poller
        self.load_lua_plugin_file(
            self.config_dir_path / self.game_menu_module_config["菜单驱动lua脚本路径"],
            self.game_menu_module_plugin_config,
            lua_runtime = self.game_menu_module_lua_runtime
        )

    def setup_lua_plugin_runtime(self, lua_runtime, plugin_config):
        # python value
        lua_runtime.globals().plist = list
        lua_runtime.globals().pdict = dict
        lua_runtime.globals().pisinstance = isinstance
        lua_runtime.globals().ptype = type
        lua_runtime.globals().plen = len
        # ud2lua
        userdata2lua = lua_runtime.eval("""function (pdata)
            local data = nil
            if pisinstance(pdata, plist) then
                data = {}
                for i=1, plen(pdata) - 1 do
                    local sub_pdata = pdata[i]
                    local sub_data = userdata2lua(sub_pdata)
                    data[i] = sub_data
                end
            elseif pisinstance(pdata, pdict) then
                data = {}
                local pkeys = plist(pdict.keys(pdata))
                for i=0, plen(pkeys) - 1 do
                    local pkey = pkeys[i]
                    local sub_pdata = pdata[pkey]
                    data[pkey] = userdata2lua(sub_pdata)
                end
            end
            return data or pdata
        end""")
        lua_runtime.globals().userdata2lua = userdata2lua
        lua_runtime.globals()["ud2lua"] = userdata2lua
        # package_path
        package_path = lua_runtime.globals()["package"].path
        package_path += f";{str(Path(self.lua_code_dir_path) / "?.lua")}"
        lua_runtime.globals()["package"].path = package_path
        # setmetatable
        lua_runtime.globals()["osetmetatable"] = lua_runtime.globals()["setmetatable"]
        setmetatable = lua_runtime.eval("""function (t, meta)
            return osetmetatable(t, meta)
        end""")
        lua_runtime.globals()["setmetatable"] = setmetatable
        # table.concat
        lua_runtime.globals()["oconcat"] = lua_runtime.globals()["table"].concat
        lua_runtime.globals()["table"].concat = lua_runtime.eval("""function (...)
            local args = {...}
            args[1] = userdata2lua(args[1])
            return oconcat(table.unpack(args))
        end""")
        # table.insert
        lua_runtime.globals()["oinsert"] = lua_runtime.globals()["table"].insert
        lua_runtime.globals()["table"].insert = lua_runtime.eval("""function (...)
            local args = {...}
            args[1] = userdata2lua(args[1])
            return oinsert(table.unpack(args))
        end""")
        # table.remove
        lua_runtime.globals()["oremove"] = lua_runtime.globals()["table"].remove
        lua_runtime.globals()["table"].remove = lua_runtime.eval("""function (...)
            local args = {...}
            args[1] = userdata2lua(args[1])
            return oremove(table.unpack(args))
        end""")
        # table.sort
        lua_runtime.globals()["osort"] = lua_runtime.globals()["table"].sort
        lua_runtime.globals()["table"].sort = lua_runtime.eval("""function (...)
            local args = {...}
            args[1] = userdata2lua(args[1])
            return osort(table.unpack(args))
        end""")
        # table.unpack
        lua_runtime.globals()["ounpack"] = lua_runtime.globals()["table"].unpack
        lua_runtime.globals()["table"].unpack = lua_runtime.eval("""function (t, start_pos, end_pos)
            return ounpack(userdata2lua(t), start_pos, end_pos)
        end""")
        lua_runtime.globals()["unpack"] = lua_runtime.globals()["table"].unpack
        # ipairs
        lua_runtime.globals()["oipairs"] = lua_runtime.globals()["ipairs"]
        lua_runtime.globals()["ipairs"] = lua_runtime.eval("""function (t)
            return oipairs(userdata2lua(t))
        end""")
        # pairs
        lua_runtime.globals()["opairs"] = lua_runtime.globals()["pairs"]
        lua_runtime.globals()["pairs"] = lua_runtime.eval("""function (t)
            return opairs(userdata2lua(t))
        end""")
        # module
        json_module = Json(lua_runtime)
        omega = Omega(self, lua_runtime, plugin_config)
        register_module(lua_runtime, "json", json_module)
        register_module(lua_runtime, "omega", omega, [Storage, Cmds, Players, Listen, System, BotAction, AsyncHttp, Cqhttp, Flex, Share, Websocket, Menu, StoragePath, Builder, Common, BotUq])
        lua_runtime.globals()["import"] = __import__
        """
        coromega_lib = lua_runtime.require("coromega")[0]
        omega_lib = lua_runtime.require("omega")[0]
        coromega_ctrl = coromega_lib["from"](omega_lib)
        print(coromega_ctrl)
        """
        #print(coromega)
        #coromega[0]["from"](omega)
        #register_module(lua_runtime, "coromega", coromega)
        #lua_runtime.globals()["python_globals_function"] = globals
        """
        class CoromegaCtrl:
            def __init__(self, coromega_ctrl):
                self.coromega_ctrl = coromega_ctrl
            def __getitem__(self, name):
                return self.coromega_ctrl[name]
        """
        """
        if plugin_config.name == "javascript支持.lua":
            javascript.globalThis["omega"] = omega_lib
            javascript.eval_js("await omega.system.print('js')")
            javascript.globalThis["coromega"] = CoromegaCtrl(coromega_ctrl)
            javascript.eval_js("console.log(await (await coromega.print)(coromega, '666'))")
            #javascript.eval_js("coromega.print(1)")
        """
        self.lua_plugins.append((omega, lua_runtime))
        return lua_runtime

    def load_lua_plugin_file(self, plugin_file_path, plugin_config, load_header = "", lua_runtime = None):
        if lua_runtime is None:
            lua_runtime = LuaRuntime(unpack_returned_tuples=True)
            lua_runtime = self.setup_lua_plugin_runtime(lua_runtime, plugin_config)
        with open(plugin_file_path, "r", encoding="utf-8") as plugin_file:
            plugin_content = plugin_file.read()
            def run():
                fmts.print_suc(load_header + f"正在运行 Lua 插件：{plugin_config.name}")
                while True:
                    try:
                        lua_runtime.execute(plugin_content)
                        break
                    except Exception as e:
                        fmts.print_err(f"Lua 插件 {plugin_config.name} 发生错误：{str(e)}\n{traceback.format_exc()}")
                        fmts.print_inf("将在5秒后尝试重载此 Lua 插件")
                        time.sleep(5)
                        fmts.print_suc(f"正在重载 Lua 插件：{plugin_config.name}")
            coro_thread = utils.createThread(
                run,
                (),
                f"Lumega - {plugin_config.name}"
            )

    def load_builtin_plugin(self, plugin_config, load_header = ""):
        fmts.print_suc(load_header + f"正在运行 Built-In 插件：{plugin_config.name}")
        builtin_plugin_entry = get_builtin_plugin_entry(plugin_config.name)
        # get_plugin_config_and_version
        def _get_plugin_config_and_version(
            plugin_name: str,
            standard_type,
            default: dict,
            default_vers,
        ):
            """
            获取插件配置文件及版本
        
            Args:
                plugin_name (str): 插件名
                standard_type (dict): 标准类型
                default (dict): 默认配置
                default_vers (tuple[int, int, int]): 默认版本
        
            Returns:
                    tuple[dict[str, Any], tuple[int, int, int]]: 配置文件内容及版本
            """
            if plugin_name == builtin_plugin_entry.name:
                # 详情见 插件编写指南.md
                assert isinstance(standard_type, dict)
                path = plugin_config.file_path
                cfgGet = plugin_config.config
                check_dict(standard_type, cfgGet)
                cfgVers = tuple(int(c) for c in cfgGet.get("Version", "0.0.1").split("."))
                return cfgGet, cfgVers
            return get_plugin_config_and_version(plugin_name, standard_type, default, default_vers)
        builtin_plugin_entry.get_plugin_config_and_version = _get_plugin_config_and_version
        # upgrade_plugin_config
        def _upgrade_plugin_config(
            plugin_name: str,
            configs: dict,
            version,
        ):
            """
            获取插件配置文件及版本
        
            Args:
                plugin_name (str): 插件名
                configs (dict): 配置内容
                default_vers (tuple[int, int, int]): 版本
            """
            if plugin_name == builtin_plugin_entry.name:
                path = plugin_config.file_path
                plugin_config.config = configs
                plugin_config.config["Version"] = ".".join([str(n) for n in version])
                write_default_cfg_file(f"{path}.json", plugin_config.to_json(), force=True)
            else:
                upgrade_plugin_config(plugin_name, configs, version)
        builtin_plugin_entry.upgrade_plugin_config = _upgrade_plugin_config
        self.builtin_plugins.append(builtin_plugin_entry)

    def stop(self):
        for i in range(len(self.builtin_plugins) - 1):
            del self.builtin_plugins[i]
        for omega, _ in self.lua_plugins:
            omega.listen.stop_all_pollers()
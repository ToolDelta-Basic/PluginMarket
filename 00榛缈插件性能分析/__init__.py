if __name__ == "plugins_required":
    from 前置_聊天栏菜单 import ChatbarMenu
elif __name__ != "__main__":
    from typing import Callable, Union, Any
    from types import FunctionType, MethodType
    from tooldelta import cfg as config
    from tooldelta import utils
    from tooldelta import plugin_entry, Plugin, ToolDelta, Player, Chat, FrameExit, fmts, InternalBroadcast
    from tooldelta.constants import PacketIDS
    from tooldelta.plugin_load.exceptions import NotValidPluginError, PluginAPINotFoundError, PluginAPIVersionError, PluginSkip
    from tooldelta.mc_bytes_packet.base_bytes_packet import BaseBytesPacket
    from tooldelta.plugin_load.classic_plugin.event_cbs import on_chat_cbs, ON_ERROR_CB, on_active_cbs, on_frame_exit_cbs, on_player_join_cbs, on_player_leave_cbs, on_preload_cbs, on_reloaded_cbs, dict_packet_funcs, bytes_packet_funcs, broadcast_listener
    import time
    import importlib


    class HazelmeowPluginPerformanceAnalyzer(Plugin):
        name = "榛缈插件性能分析"
        author = "Hazelmeow"
        version = (0, 1, 0)


        def __init__(self, frame: ToolDelta) -> None:
            super().__init__(frame)
            self.ListenPreload(self.on_preload)
            self.ListenChat(self.on_chat)
            self.ListenFrameExit(self.on_frame_exit)
            self.make_data_path()

            self.analyzing = False
            self.analyze_start_time = 0
            self.data: list[dict] = []

            self.execute_name_2_orig_func = {
                "preload": self.frame.plugin_group.execute_preload,
                "active": self.frame.plugin_group.execute_init,
                "player_join": self.frame.plugin_group.execute_player_join,
                "chat": self.frame.plugin_group.execute_chat,
                "player_leave": self.frame.plugin_group.execute_player_leave,
                "frame_exit": self.frame.plugin_group.execute_frame_exit,
                "reloaded": self.frame.plugin_group.execute_reloaded,
                "dict": self.frame.plugin_group.handle_dict_packets,
                "bytes": self.frame.plugin_group.handle_bytes_packets
            }
            self.execute_name_2_cbs = {
                "preload": on_preload_cbs,
                "active": on_active_cbs,
                "player_join": on_player_join_cbs,
                "chat": on_chat_cbs,
                "player_leave": on_player_leave_cbs,
                "frame_exit": on_frame_exit_cbs,
                "reloaded": on_reloaded_cbs,
            }
            self.execute_name_2_packet_funcs = {
                "dict": dict_packet_funcs,
                "bytes": bytes_packet_funcs
            }
            self.broadcast_listeners = broadcast_listener

            # Injecting ToolDelta!!
            self._orig_import_module = importlib.import_module
            self._orig_broadcast_event = self.frame.plugin_group.brocast_event
            self.frame.plugin_group.execute_preload = self._execute_preload
            self.frame.plugin_group.execute_init = self._execute_active
            self.frame.plugin_group.execute_player_join = self._execute_player_join
            self.frame.plugin_group.execute_chat = self._execute_chat
            self.frame.plugin_group.execute_player_leave = self._execute_player_leave
            self.frame.plugin_group.execute_frame_exit = self._execute_frame_exit
            self.frame.plugin_group.execute_reloaded = self._execute_reloaded
            self.frame.plugin_group.handle_dict_packets = self._execute_dict_packet
            self.frame.plugin_group.handle_bytes_packets = self._execute_bytes_packet
            self.frame.plugin_group.brocast_event = self._broadcast_event

            DEFAULT_CFG_VER = (0, 0, 2)
            DEFAULT_CFG = {
                "最久分析时间 (秒)": 300,
                "分析使用广播的插件": False,
                "分析监听数据包的插件": False,
                "启动时自动开始分析": True
            }
            DEFAULT_CFG_TYPECHECKING = {
                "最久分析时间 (秒)": config.PInt,
                "分析使用广播的插件": bool,
                "分析监听数据包的插件": bool,
                "启动时自动开始分析": bool,
            }

            config.check_auto(DEFAULT_CFG_TYPECHECKING, DEFAULT_CFG)
            cfg, cfgver = config.get_plugin_config_and_version(
                self.name, DEFAULT_CFG_TYPECHECKING, DEFAULT_CFG, DEFAULT_CFG_VER
            )
            self.max_record_sec = cfg["最久分析时间 (秒)"]
            self.analyze_packet = cfg["分析监听数据包的插件"]
            self.analyze_broadcast = cfg["分析使用广播的插件"]
            if bool(cfg["启动时自动开始分析"]):
                self.start_analyze()


        def on_preload(self):
            self.chatbar: "ChatbarMenu" = self.GetPluginAPI("聊天栏菜单", (0, 2, 3))
            self.orig_on_player_message = self.chatbar.on_player_message
            self.frame.add_console_cmd_trigger(
                ["perf "], "<start/end>", "开始/停止 记录插件执行时间", self.on_console
            )
            self.frame.add_console_cmd_trigger(
                ["pf switch"], "<packet/broadcast>", "切换 是否显示 数据包/广播 插件", self.on_console_switch
            )
            setattr(self.chatbar, f"_self_perf", self)
            for index, (plugin, func) in enumerate(on_chat_cbs):
                if func == self.chatbar.on_player_message:
                    on_chat_cbs[index] = plugin, MethodType(self.on_player_message, self.chatbar)


        def on_frame_exit(self, frame_exit: FrameExit):
            importlib.import_module = self._orig_import_module


        def on_console(self, args: list[str]):
            if (len(args) == 0) or (args[0] == ""):
                fmts.print_err('语法错误: 意外的 "": 出现在 "perf >><<"')
                return
            if (len(args) > 1):
                fmts.print_err('语法错误: 意外的 "%s": 出现在 "perf %s >>%s<< %s"'\
                    % (args[1], args[0], args[1], " ".join(args[2:]))
                )
                return
            if args[0] not in ["start", "end"]:
                fmts.print_err('语法错误: 意外的 "%s": 出现在 "perf >>%s<<"'\
                    % (args[0], args[0])
                )
                return

            action = args[0]
            if action == "start":
                self.start_analyze()
            if action == "end":
                self.end_analyze()


        def on_console_switch(self, args: list[str]):
            if (len(args) == 0) or (args[0] == ""):
                fmts.print_err('语法错误: 意外的 "": 出现在 "perf switch >><<"')
                return
            if (len(args) > 1):
                fmts.print_err('语法错误: 意外的 "%s": 出现在 "perf switch %s >>%s<< %s"'\
                    % (args[1], args[0], args[1], " ".join(args[2:]))
                )
                return
            if args[0] not in ["packet", "broadcast"]:
                fmts.print_err('语法错误: 意外的 "%s": 出现在 "perf switch >>%s<<"'\
                    % (args[0], args[0])
                )
                return

            action = args[0]
            if action == "packet":
                self.analyze_packet = not self.analyze_packet
                fmts.print_suc(f"{self.name}: 将{'会' if self.analyze_packet else '不'}对数据包插件进行分析.")
            if action == "broadcast":
                self.analyze_broadcast = not self.analyze_broadcast
                fmts.print_suc(f"{self.name}: 将{'会' if self.analyze_broadcast else '不'}对广播插件进行分析.")


        def start_analyze(self):
            if self.analyzing:
                fmts.print_err(f"{self.name}: 当前正在分析.")
                return
            fmts.print_suc(f"{self.name}: 开始分析插件性能.")
            self.data.clear()
            self.analyze_start_time = time.time()
            self.analyzing = True
            self.auto_stop_analyze()


        def end_analyze(self):
            if not self.analyzing:
                fmts.print_err(f"{self.name}: 当前不在分析.")
                return
            fmts.print_suc(f"{self.name}: 终止分析插件性能.")
            self.analyzing = False


        @utils.thread_func(f"{name}: 自动停止分析")
        def auto_stop_analyze(self):
            time.sleep(self.max_record_sec +0.1)
            if self.analyzing and ((time.time() -self.analyze_start_time) >= self.max_record_sec):
                self.end_analyze()


        def on_chat(self, chat: Chat):
            # time.sleep(0.01)
            pass

        def _any(self, x) -> Any:
            return x

        def _execute_preload(self, onerr: ON_ERROR_CB):
            self._execute("preload", None, onerr)

        def _execute_active(self, onerr: ON_ERROR_CB):
            self._execute("active", None, onerr)

        def _execute_player_join(self, player: Player, onerr: ON_ERROR_CB):
            self._execute("player_join", player, onerr)

        def _execute_chat(self, chat: Chat, onerr: ON_ERROR_CB):
            self._execute("chat", chat, onerr)

        def _execute_player_leave(self, player: Player, onerr: ON_ERROR_CB):
            self._execute("player_leave", player, onerr)

        def _execute_frame_exit(self, evt: FrameExit, onerr: ON_ERROR_CB):
            self._execute("frame_exit", evt, onerr)

        def _execute_reloaded(self, onerr: ON_ERROR_CB):
            self._execute("reloaded", None, onerr)

        def _execute_dict_packet(
            self, pktID: PacketIDS, pkt: dict, onerr: ON_ERROR_CB
        ) -> bool:
            return self._execute_packet("dict", pktID, pkt, onerr)

        def _execute_bytes_packet(
            self, pktID: PacketIDS, pkt: BaseBytesPacket, onerr: ON_ERROR_CB
        ) -> bool:
            return self._execute_packet("bytes", pktID, pkt, onerr)

        def _create_base_data(self, message):
            plugin_data = {}
            base_data = {"message": message, "timestamp": time.time(), "plugin": plugin_data}
            self.data.append(base_data)
            return plugin_data

        @staticmethod
        def _before_func_call(plugin_data, plugin_name, thread):
            plugin_data[plugin_name] = {"start": time.time(), "end": None, "exc": None, "thread": thread}

        @staticmethod
        def _after_func_call(plugin_data, plugin_name, exc = None):
            plugin_data[plugin_name]["end"] = time.time()
            if exc:
                plugin_data[plugin_name]["exc"] = str(exc)

        @staticmethod
        def _check_plugin_env(plugin, exc):
            if isinstance(exc, PluginAPINotFoundError):
                fmts.print_err(
                    f"插件 {plugin.name} 需要前置组件 {exc.name}"
                )
                raise SystemExit from exc
            if isinstance(exc, PluginAPIVersionError):
                fmts.print_err(
                    f"插件 {plugin.name} 需要前置组件 {exc.name} v{exc.m_ver}, 但是现有版本过低 v{exc.n_ver}"
                )
                raise SystemExit from exc

        @staticmethod
        def _print_plugin_data(message, plugin_data, blocked, in_thread_func):
            if not in_thread_func:
                string = ""
                time_spend_ms_total = 0
                count = 0
                for plugin_name, data in plugin_data.items():
                    thread_name = data["thread"]
                    if thread_name:
                        continue
                    count += 1
                    plugin_name_last = plugin_name
                    time_spend_ms = (data["end"] -data["start"]) *1000
                    time_spend_ms_total += time_spend_ms
                    exception = data["exc"]
                    string += "\n    - §1FINISH" if (exception is None) else "\n    -  §4ERROR"
                    string +=f" {plugin_name} ({time_spend_ms:.2f}ms)"

                if blocked:
                    string += f"\n  Blocked by plugin {plugin_name}"

                if count == 1:
                    string = f"§b[ SUM  ]{message} ({plugin_name_last}) ({time_spend_ms_total:.2f}ms)"
                else:
                    string = f"§1§l[ SUM  ]{message} ({time_spend_ms_total:.2f}ms) (without @utils.thread_func)§r" +string
                fmts.print_with_info(string, "§1 PERF ")

            else:
                string = ""
                if len(plugin_data) > 1:
                    raise NotImplementedError
                plugin_name, data = list(plugin_data.items())[0]
                thread_name = data["thread"]

                if (submodule := data.get("submodule")):
                    if len(submodule) > 1:
                        raise NotImplementedError
                    plugin_name, data = list(submodule.items())[0]

                time_spend_ms = (data["end"] -data["start"]) *1000
                exception = data["exc"]

                string = f"§2§l[THREAD]{message} ({plugin_name}) ({time_spend_ms:.2f}ms) (in thread {thread_name})"
                if exception:
                    string = string.replace("§2§l", "§4")

                fmts.print_with_info(string, "§2§l PERF ")


        def _execute(self,
            execute_name: str,
            param,
            onerr: ON_ERROR_CB,
        ) -> None:
            if execute_name not in [
                "preload",
                "active", "player_join",
                "chat", "player_leave",
                "frame_exit", "reloaded"
            ]:
                raise Exception(f"{self.name}: 执行名称不正确.")
            if not self.analyzing:
                if param is None:
                    self.execute_name_2_orig_func[execute_name](onerr)
                else:
                    self.execute_name_2_orig_func[execute_name](param, onerr)
                return
            match execute_name:
                case "preload":
                    message = "[F LOAD]"
                case "active":
                    message = "[ACTIVE]"
                case "player_join":
                    message = "[P JOIN] %s" % param.name
                case "chat":
                    message = "[P CHAT] <%s> %s" % (param.player.name, param.msg)
                case "player_leave":
                    message = "[P LEAV] %s" % param.name
                case "frame_exit":
                    message = "[F EXIT] %s" % param.reason
                case "reloaded":
                    message = "[RELOAD]"

            self.analyzer(message, self.execute_name_2_cbs[execute_name], param, onerr)


        def _execute_packet(self,
            execute_name: str,
            pktID,
            pkt,
            onerr: ON_ERROR_CB,
        ) -> bool:
            if execute_name not in [
                "dict", "bytes"
            ]:
                raise Exception(f"{self.name}: 执行名称不正确.")
            try:
                analyzing = self.analyzing and self.analyze_packet
            except Exception:
                fmts.print_war("不该发生这情况... self 被替换")
                analyzing = False
            if not analyzing:
                return bool(self.execute_name_2_orig_func[execute_name](pktID, pkt, onerr))
            message = f"[PK {pktID:>03}]"

            func_list = self.execute_name_2_packet_funcs[execute_name].get(pktID).copy()
            if not func_list:
                return False

            for index, func in enumerate(func_list):
                plugin = func.__self__
                if not isinstance(plugin, Plugin):
                    plugin.name = plugin.__class__.__name__
                func_list[index] = (plugin, func)
            return self.analyzer(message, func_list, pkt, onerr, True)[-1]


        def _broadcast_event(self,
            evt: InternalBroadcast
        ) -> list:
            analyzing = self.analyzing and self.analyze_broadcast
            if not analyzing:
                return self._orig_broadcast_event(evt)
            message = f"[EVTPUB] {evt.evt_name}"

            func_list = self._any(self.broadcast_listeners.get(evt.evt_name)).copy()
            for index, func in enumerate(func_list):
                plugin = func.__self__
                if not isinstance(plugin, Plugin):
                    plugin.name = plugin.__class__.__name__
                func_list[index] = (plugin, func)
            return self.analyzer(message, func_list, evt, None, True)


        def import_module(self, name, package = None):
            if not self.analyzing:
                return self._orig_import_module(name, package)
            message = "[IMPORT]"

            plugin = self._any(fmts)
            plugin.name = name
            return self.analyzer(message, [(plugin, lambda *args: self._orig_import_module(name, package))], (name, package), None)[0]


        def analyzer(self, message: str, func_list: list[tuple[Plugin, Callable]], param, onerr, block = False) -> list:
            plugin_data = self._create_base_data(message)
            plugin = self
            return_list = []
            res = False
            try:
                for plugin, func in func_list:
                    func_is_utils_thread = (func.__closure__) and ("_orig" in dir(func))
                    if not func_is_utils_thread:
                        res = self._analyzer(message, func, plugin, plugin_data, param, False)
                        return_list.append(res)
                    else:
                        utils.thread_func(func._usage)(self._analyzer)(message, func._orig, plugin, plugin_data, param, func._usage)

                    if block and bool(res):
                        return return_list

                return return_list

            except Exception as exc:
                if onerr is not None:
                    onerr(plugin.name, exc)

            finally:
                self._print_plugin_data(message, plugin_data, block and bool(res), False)
                return return_list


        def _analyzer(self, message, func, plugin, plugin_data, param, thread):
            args = []
            if thread:
                args.append(plugin)
            if param is not None:
                args.append(param)

            self._before_func_call(plugin_data, plugin.name, thread)

            if thread and (param is not None):
                if isinstance(param, Chat):
                    param._plugin_data = plugin_data[plugin.name] # type: ignore

            try:
                res = func(*args)

            except BaseException as exc:
                self._after_func_call(plugin_data, plugin.name, exc)
                self._check_plugin_env(plugin, exc)
                raise

            else:
                self._after_func_call(plugin_data, plugin.name)

            finally:
                if thread:
                    self._print_plugin_data(message, {plugin.name: plugin_data[plugin.name]}, False, thread)
            return res


        @staticmethod
        @utils.thread_func("聊天栏菜单执行")
        def on_player_message(self, chat: Chat, *a): # type: ignore
            self = getattr(self, f"_self_perf")
            if not self.analyzing:
                self.orig_on_player_message(chat)
                return
            msg = chat.msg
            player = chat.player
            plugin_data = chat._plugin_data # type: ignore
            submodule_data = {}
            plugin_data["submodule"] = submodule_data
            player_is_op = player.is_op()
            if self.chatbar.prefixs:
                for prefix in self.chatbar.prefixs:
                    if msg.startswith(prefix):
                        msg = msg[len(prefix) :]
                        break
                else:
                    return

            for trigger in self.chatbar.chatbar_triggers:
                for trigger_str in trigger.triggers:
                    if msg.startswith(trigger_str):
                        if (not player_is_op) and trigger.op_only:
                            player.show("§c创造模式或者OP才可以使用该菜单项")
                            return
                        args = msg.removeprefix(trigger_str).split()
                        plugin = trigger.func.__self__

                        try:
                            submodule_data[plugin.name] = {"start": time.time(), "end": None, "exc": None}
                            with utils.ChatbarLock(player.name):
                                if "StandardChatbarTriggers" in trigger.__class__.__name__:
                                    func = trigger.execute # type: ignore
                                    args = (player, args)
                                else:
                                    func = trigger.func
                                    args = (player.name, args)
                                func(*args) # type: ignore

                        except BaseException as exc:
                            submodule_data[plugin.name]["end"] = time.time()
                            submodule_data[plugin.name]["exc"] = str(exc)
                            raise

                        else:
                            submodule_data[plugin.name]["end"] = time.time()


    entry = plugin_entry(HazelmeowPluginPerformanceAnalyzer)
    importlib.import_module = entry.import_module




else:
    pass
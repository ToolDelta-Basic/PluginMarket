if __name__ == "plugins_required":
    from 前置_聊天栏菜单 import ChatbarMenu
elif __name__ != "__main__":
    from typing import Callable
    from types import FunctionType, MethodType
    from tooldelta import cfg as config
    from tooldelta import utils
    from tooldelta import plugin_entry, Plugin, ToolDelta, Player, Chat, FrameExit, fmts
    from tooldelta.constants import PacketIDS
    from tooldelta.plugin_load.classic_plugin.event_cbs import on_chat_cbs, ON_ERROR_CB
    import time


    class HazelmeowPluginPerformanceAnalyzer(Plugin):
        name = "榛缈插件性能分析"
        author = "Hazelmeow"
        version = (0, 0, 1)


        def __init__(self, frame: ToolDelta) -> None:
            super().__init__(frame)
            self.ListenPreload(self.on_preload)
            self.ListenChat(self.on_chat)
            self.make_data_path()

            DEFAULT_CFG = {
                "最久分析时间 (秒)": 60
            }
            DEFAULT_CFG_TYPECHECKING = {
                "最久分析时间 (秒)": config.PInt,
            }

            config.check_auto(DEFAULT_CFG_TYPECHECKING, DEFAULT_CFG)
            cfg, _ = config.get_plugin_config_and_version(
                self.name, DEFAULT_CFG_TYPECHECKING, DEFAULT_CFG, (0, 0, 1)
            )
            self.max_record_sec = int(cfg["最久分析时间 (秒)"])
            self.analyze_start_time = 0
            self.analyzing = False
            self.data: list[dict] = []


        def on_preload(self):
            self.chatbar: "ChatbarMenu" = self.GetPluginAPI("聊天栏菜单", (0, 2, 3))
            self.orig_execute_chat = self.frame.plugin_group.execute_chat
            self.orig_on_player_message = self.chatbar.on_player_message
            self.frame.add_console_cmd_trigger(
                ["perf"], "<start/end>", "开始/停止 记录插件执行时间", self.on_console
            )
            # Injecting ToolDelta!!
            self.frame.plugin_group.execute_chat = self._execute_chat
            for index, (plugin, func) in enumerate(on_chat_cbs):
                if func == self.chatbar.on_player_message:
                    on_chat_cbs[index] = plugin, MethodType(self.on_player_message, self.chatbar)


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


        def _execute_chat(self,
            chat: Chat,
            onerr: ON_ERROR_CB,
        ) -> None:
            if not self.analyzing:
                chat.self = self # type: ignore
                self.orig_execute_chat(chat, onerr)
                return
            message = "<%s> %s" % (chat.player.name, chat.msg)
            plugin_data = {}
            base_data = {"message": message, "timestamp": time.time(), "plugin": plugin_data}
            self.data.append(base_data)
            try:
                for plugin, func in on_chat_cbs:
                    func_is_utils_thread = (func.__closure__) and ("_orig" in dir(func))
                    if not func_is_utils_thread:
                        # fmts.print_with_info(f"§b{message} {plugin.name}", "§b PERF START ")
                        plugin_data[plugin.name] = {"start": time.time(), "end": None, "exc": None, "thread": False}
                        try:
                            func(chat)
                        except BaseException as exc:
                            plugin_data[plugin.name]["end"] = time.time()
                            plugin_data[plugin.name]["exc"] = str(exc)
                            time_spend_ms = (plugin_data[plugin.name]["end"] -plugin_data[plugin.name]["start"]) *1000
                            fmts.print_with_info(f"§c{message} {plugin.name} ({time_spend_ms:.2f}ms)", "§c PERF  EXC  ")
                            raise
                        else:
                            plugin_data[plugin.name]["end"] = time.time()
                            time_spend_ms = (plugin_data[plugin.name]["end"] -plugin_data[plugin.name]["start"]) *1000
                            fmts.print_with_info(f"§1{message} {plugin.name} ({time_spend_ms:.2f}ms)", "§1 PERF FINISH")
                    else:
                        def thread_fun(func, plugin, chat):
                            # fmts.print_with_info(f"§b{message} {plugin.name} (in {func._usage} thread)", "§b PERF START ")
                            plugin_data[plugin.name] = {"start": time.time(), "end": None, "exc": None, "thread": True}
                            chat.plugin_data = plugin_data[plugin.name]
                            chat.self = self
                            try:
                                func._orig(plugin, chat)
                            except BaseException as exc:
                                plugin_data[plugin.name]["end"] = time.time()
                                plugin_data[plugin.name]["exc"] = str(exc)
                                time_spend_ms = (plugin_data[plugin.name]["end"] -plugin_data[plugin.name]["start"]) *1000
                                fmts.print_with_info(f"§c{message} {plugin.name} (in {func._usage} thread) ({time_spend_ms:.2f}ms)", "§c PERF  EXC  ")
                                raise
                            else:
                                plugin_data[plugin.name]["end"] = time.time()
                                time_spend_ms = (plugin_data[plugin.name]["end"] -plugin_data[plugin.name]["start"]) *1000
                                fmts.print_with_info(f"§b{message} {plugin.name} (in {func._usage} thread) ({time_spend_ms:.2f}ms)", "§1 PERF FINISH")
                            finally:
                                if (submodule := plugin_data[plugin.name].get("submodule")):
                                    for submodule_name, submodule_data in submodule.items():
                                        time_spend_ms = (submodule_data["end"] -submodule_data["start"]) *1000
                                        if submodule_data["exc"] is None:
                                            fmts.print_with_info(f"§b    - {submodule_name} (in chatbar menu) ({time_spend_ms:.2f}ms)", "§1 PERF FINISH")
                                        else:
                                            fmts.print_with_info(f"§c    - {submodule_name} (in chatbar menu) ({time_spend_ms:.2f}ms)", "§c PERF  EXC  ")
                        utils.thread_func(func._usage)(thread_fun)(func, plugin, chat)
                time_spend_ms = sum((p['end'] -p['start']) for p in plugin_data.values() if (not p["thread"])) *1000
                fmts.print_with_info(f"§2{message} all plugins (without @utils.thread) ({time_spend_ms:.2f}ms)", "§2 PERF  SUM  ")
            except Exception as exc:
                onerr(plugin.name, exc)


        @staticmethod
        @utils.thread_func("聊天栏菜单执行")
        def on_player_message(self, chat: Chat): # type: ignore
            if not chat.self.analyzing: # type: ignore
                chat.self.orig_on_player_message(chat) # type: ignore
                return
            player = chat.player
            msg = chat.msg
            plugin_data = chat.plugin_data # type: ignore
            submodule_data = {}
            plugin_data["submodule"] = submodule_data
            if self.prefixs:
                for prefix in self.prefixs:
                    if msg.startswith(prefix):
                        msg = msg[len(prefix) :]
                        break
                else:
                    return
            player_is_op = player.is_op()
            for trigger in self.chatbar_triggers:
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
                                    func = trigger.execute
                                    args = (player, args)
                                else:
                                    func = trigger.func
                                    args = (player.name, args)
                                func(*args)
                        except BaseException as exc:
                            submodule_data[plugin.name]["end"] = time.time()
                            submodule_data[plugin.name]["exc"] = str(exc)
                            raise
                        else:
                            submodule_data[plugin.name]["end"] = time.time()


    entry = plugin_entry(HazelmeowPluginPerformanceAnalyzer)




else:
    pass
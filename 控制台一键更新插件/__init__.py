from tooldelta import Plugin, plugin_entry
from tooldelta.utils import fmts, thread_func, ToolDeltaThread
from tooldelta.plugin_manager import plugin_manager


class FastUpdatePlugins(Plugin):
    name = "控制台一键更新插件"
    author = "ToolDelta"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)

    def on_def(self):
        self.frame.add_console_cmd_trigger(
            ["up"], None, "一键更新所有插件", self.on_update_all_plugins
        )

    def on_update_all_plugins(self, _):
        fmts.print_inf("正在获取更新列表..")
        plugin_manager.update_all_plugins(plugin_manager.get_all_plugin_datas())
        resp = input(fmts.fmt_info("是否立即重载 (§ay§r/§cn§r)? 请输入: "))
        if resp.strip() == "y":
            self.reload_sys()
        else:
            fmts.print_inf("可以在稍后重载系统以使更新的插件生效。")

    @thread_func("一键更新插件重载", thread_level=ToolDeltaThread.SYSTEM)
    def reload_sys(self):
        self.frame.reload()


entry = plugin_entry(FastUpdatePlugins)

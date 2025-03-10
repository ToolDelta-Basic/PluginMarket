import psutil
import os
from tooldelta import Plugin, utils, Print, Config, plugin_entry

BYTES2MB = 1048576


class EmergencyMetaMana(Plugin):
    name = "性能管理"
    author = "SuperScript"
    version = (0, 0, 3)

    def __init__(self, f):
        super().__init__(f)
        CFG = {
            "当内存占用超过多少百分比时提示警告": 80,
            "当内存占用超过多少百分比时停机": 95,
        }
        cfg, _ = Config.getPluginConfigAndVersion(
            self.name, Config.auto_to_std(CFG), CFG, self.version
        )
        self.mem_warn = cfg["当内存占用超过多少百分比时提示警告"]
        self.mem_exit = cfg["当内存占用超过多少百分比时停机"]
        self.ListenPreload(self.on_def)

    def on_def(self):
        self.memory_mana()
        self.warn_lck = False
        self.hi_used = 0
        self.frame.add_console_cmd_trigger(
            ["性能", "top"], "[参数 或 -help]", "查看系统性能情况", self.chk_proc
        )
        Print.print_inf("在控制台输入 性能 以查看当前系统的性能.")

    @utils.timer_event(20, "内存告急停机检测")
    def memory_mana(self):
        vm = psutil.virtual_memory()
        if vm.percent < self.mem_warn * 100:
            self.warn_lck = False
            self.hi_used = 0
        elif vm.percent > self.mem_warn and (
            not self.warn_lck or vm.percent > self.hi_used
        ):
            self.hi_used = vm.percent
            self.warn_lck = True
            Print.print_war(
                f"系统可用内存告急({vm.available / BYTES2MB:.2f}MB/{vm.total / BYTES2MB:.2f}MB 可用, {vm.percent:.2f}%)"
            )
        if vm.percent > self.mem_exit:
            Print.print_err(
                f"已超过最大可用内存限额({vm.available / BYTES2MB:.2f}MB/{vm.total / BYTES2MB:.2f}MB 可用, {vm.percent:.2f}%), 系统将退出"
            )
            for k, _ in utils.TMPJson.get_tmps():
                utils.TMPJson.unloadPathJson(k)
            os._exit(0)

    def chk_proc(self, args):
        vm = psutil.virtual_memory()
        Print.print_inf(
            f"当前可用内存{vm.available / BYTES2MB:.2f}MB, 空闲{vm.free / BYTES2MB:.2f}MB (总共{vm.total / BYTES2MB:.2f}MB), {vm.percent:.2f}%",
            need_log=False,
        )
        cpup = psutil.cpu_percent()
        Print.print_inf(f"当前CPU使用率: {round(cpup, 2)}%", need_log=False)
        cl = self.test_hc()
        if len(args) != 1:
            Print.print_inf("top 命令帮助:", need_log=False)
            Print.print_inf(" top 0: 仅查看CPU使用率和内存情况", need_log=False)
            Print.print_inf(
                " top 1: 查看JSON文件缓存区正在缓存状态的文件列表", need_log=False
            )
            Print.print_inf(
                " top 2: 查看ToolDelta中运行的正常线程的列表", need_log=False
            )
            return
        if args[0] == "1":
            Print.print_inf(
                f"当前有{len(cl)}个处于缓存区的JSON缓存文件:", need_log=False
            )
            Print.print_inf(" " + "\n ".join(self.test_hc()), need_log=False)
        elif args[0] == "2":
            if not hasattr(utils, "get_threads_list"):
                Print.print_war("该功能现在不可用")
            else:
                lst = utils.tooldelta_thread.get_threads_list()
                Print.print_inf(
                    f"当前有{len(lst)}在 ToolDelta 中运行的正常线程:", need_log=False
                )
                for thr in lst:
                    Print.print_inf(
                        f" - {thr.usage or thr.func.__name__}", need_log=False
                    )

    def test_hc(self):
        return list(utils.TMPJson.get_tmps().keys())


entry = plugin_entry(EmergencyMetaMana)

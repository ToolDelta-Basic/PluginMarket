import psutil
import os
from tooldelta import Plugin, utils, fmts, cfg, plugin_entry

BYTES2MB = 1048576


def pretty_show_bytes(bytes: int):
    if bytes < 1024:
        return f"{bytes}B"
    elif bytes < 1048576:
        return f"{bytes / 1024:.1f}KB"
    else:
        return f"{bytes / 1048576:.1f}MB"


class EmergencyMetaMana(Plugin):
    name = "性能管理"
    author = "SuperScript"
    version = (0, 0, 4)

    def __init__(self, f):
        super().__init__(f)
        CFG = {
            "当内存占用超过多少百分比时提示警告": 80,
            "当内存占用超过多少百分比时停机": 95,
        }
        config, _ = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(CFG), CFG, self.version
        )
        self.mem_warn = config["当内存占用超过多少百分比时提示警告"] / 100
        self.mem_exit = config["当内存占用超过多少百分比时停机"] / 100
        self.ListenPreload(self.on_def)

    def on_def(self):
        announce_bar = self.GetPluginAPI("更好的公告栏", force=False)
        if announce_bar is not None:
            announce_bar.regist_formatter(
                "[RAM]", lambda: pretty_show_bytes(psutil.virtual_memory().used)
            )
            fmts.print_suc("性能管理: 已将 2 个格式加入公告栏插件")
        self.memory_mana()
        self.warn_lck = False
        self.hi_used = 0
        self.frame.add_console_cmd_trigger(
            ["性能", "top"], "[参数 或 -help]", "查看系统性能情况", self.chk_proc
        )
        fmts.print_inf("在控制台输入 性能 以查看当前系统的性能.")

    @utils.timer_event(60, "内存告急停机检测")
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
            fmts.print_war(
                f"系统可用内存告急({vm.available / BYTES2MB:.2f}MB/{vm.total / BYTES2MB:.2f}MB 可用, {vm.percent:.2f}%)"
            )
        if vm.percent > self.mem_exit:
            fmts.print_err(
                f"已超过最大可用内存限额({vm.available / BYTES2MB:.2f}MB/{vm.total / BYTES2MB:.2f}MB 可用, {vm.percent:.2f}%), 系统将退出"
            )
            self.exit()

    @utils.thread_func("强制停机", thread_level=utils.ToolDeltaThread.SYSTEM)
    def exit(self):
        self.frame.system_exit("性能管理系统强制关机")
        os._exit(0)

    def chk_proc(self, args):
        vm = psutil.virtual_memory()
        fmts.print_inf(
            f"当前可用内存{vm.available / BYTES2MB:.2f}MB, 空闲{vm.free / BYTES2MB:.2f}MB (总共{vm.total / BYTES2MB:.2f}MB), {vm.percent:.2f}%",
            need_log=False,
        )
        cpup = psutil.cpu_percent()
        fmts.print_inf(f"当前CPU使用率: {round(cpup, 2)}%", need_log=False)
        cl = self.test_hc()
        if len(args) != 1:
            fmts.print_inf("top 命令帮助:", need_log=False)
            fmts.print_inf(" top 0: 仅查看CPU使用率和内存情况", need_log=False)
            fmts.print_inf(
                " top 1: 查看JSON文件缓存区正在缓存状态的文件列表", need_log=False
            )
            fmts.print_inf(
                " top 2: 查看ToolDelta中运行的正常线程的列表", need_log=False
            )
            fmts.print_inf(
                " top 3: 查看ToolDelta中运行的定时任务的列表", need_log=False
            )
            return
        if args[0] == "1":
            fmts.print_inf(
                f"当前有{len(cl)}个处于缓存区的JSON缓存文件:", need_log=False
            )
            fmts.print_inf(" " + "\n ".join(self.test_hc()), need_log=False)
        elif args[0] == "2":
            if not hasattr(utils.tooldelta_thread, "get_threads_list"):
                fmts.print_war("该功能现在不可用")
            else:
                lst = utils.tooldelta_thread.get_threads_list()
                fmts.print_inf(
                    f"当前有{len(lst)}在 ToolDelta 中运行的正常线程:", need_log=False
                )
                for thr in lst:
                    fmts.print_inf(
                        f" - {thr.usage or thr.func.__name__}", need_log=False
                    )
        elif args[0] == "3":
            tabl = utils.timer_events.timer_events_table
            for k, v in sorted(tabl.items(), key=lambda x: x[0]):
                fmts.print_inf(f"§b每 {k} 秒执行一次的定时任务:")
                for v1 in v:
                    fmts.print_inf(f"  {v1[0]}")

    def test_hc(self):
        return list(utils.tempjson.get_tmps().keys())


entry = plugin_entry(EmergencyMetaMana)

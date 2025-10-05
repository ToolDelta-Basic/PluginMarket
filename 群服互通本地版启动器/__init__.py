import importlib
from tooldelta import Plugin, plugin_entry, TYPE_CHECKING
from tooldelta.utils import urlmethod
from . import cfg_mgr, proc_mgr

importlib.reload(cfg_mgr)
importlib.reload(proc_mgr)


class QQLinkerLauncher(Plugin):
    version = (0, 1, 1)
    name = "云链群服本地版启动器"

    def __init__(self, f):
        super().__init__(f)
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.mConfig = cfg_mgr.ConfigMgr(self)
        self.mProc = proc_mgr.ProcMgr(self)

    def on_preload(self):
        self.qqlink = self.GetPluginAPI("群服互通")
        if TYPE_CHECKING:
            from ..群服互通云链版 import QQLinker  # type: ignore

            self.qqlink: QQLinker
        self.launch()

    def on_active(self):
        self.qqlink.manual_launch()

    def launch(self):
        if not proc_mgr.has_proc():
            openat_port = urlmethod.get_free_port(3005)
            self.mConfig.flush_config_yaml(openat_port=openat_port)
            self.mProc.launch(openat_port)
        else:
            self.mProc.launch()
        self.qqlink.set_manual_launch(proc_mgr.get_port())
        self.mProc.wait_ok()


entry = plugin_entry(QQLinkerLauncher, "群服互通本地版启动器")

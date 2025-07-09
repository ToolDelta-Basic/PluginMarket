import json
import threading
from tooldelta import Plugin
from tooldelta.utils import fmts


class LogRecord:
    plugin: Plugin
    system_name: str

    _mu: threading.Lock
    _id: int

    def __init__(self, plugin: Plugin, system_name: str) -> None:
        self.plugin = plugin
        self.system_name = system_name
        self._mu = threading.Lock()
        self._id = 0

    def _create_log(self, content: dict | str):
        path = self.plugin.format_data_path(f"{self.system_name}_{self._id}.log")
        with open(path, "w+", encoding="utf-8") as file:
            if isinstance(content, str):
                file.write(content)
            else:
                file.write(json.dumps(content, ensure_ascii=False))
        fmts.print_war(f"献给机械の花束: 错误日志已生成到路径 {path} 中")

    def create_log(self, content: dict | str):
        with self._mu:
            self._create_log(content)
            self._id += 1

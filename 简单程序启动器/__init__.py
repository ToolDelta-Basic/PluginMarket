import subprocess
from tooldelta import Plugin, Frame, plugin_entry


class SimpleProgramRunner(Plugin):
    name = "简单程序启动器"
    author = "Eternal Crystal"
    version = (0, 0, 1)

    def __init__(self, _: Frame):
        self.on_def()

    def on_def(self):
        args: list[str] = [
            self.format_data_path("your_program_path"),
            "some_args",
        ]
        subprocess.Popen(args).wait()


entry = plugin_entry(SimpleProgramRunner, "简单程序启动器")

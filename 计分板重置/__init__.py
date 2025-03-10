from tooldelta import (
    Plugin,
    Config,
    game_utils,
    utils,
    Print,
    TYPE_CHECKING,
    plugin_entry,
)

from data_operation import *
import os


class NewPlugin(Plugin):
    name = "计分板重置"
    author = "猫七街"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        config = {"白名单计分板": ["coin"]}
        self.config, _ = Config.get_plugin_config_and_version(
            self.name, {}, config, self.version
        )
        self.ListenPreload(self.on_def)

    def clear(self, args):
        # [计分板名字, 计分板显示名字, dummy]
        data_path = os.path.join(self.data_path, "服务器计分板.json")
        scoreboards = self.game_ctrl.sendwscmd(
            "/scoreboard objectives list", waitForResp=True
        ).as_dict  # type: ignore
        scoreboards.pop("CommandOrigin")
        scoreboards = scoreboards["OutputMessages"]
        data = {}
        for scoreboard in scoreboards:
            if scoreboard["Message"] == f"§a%commands.scoreboard.objectives.list.count":
                continue

            try:
                scoreboard = scoreboard["Parameters"]

            except:
                pass
            if scoreboard[0] in self.config["白名单计分板"]:
                continue
            data[scoreboard[0]] = scoreboard[1]

        save_data(data_path, data)
        for scoreboard, _ in data.items():
            self.game_ctrl.sendwscmd(f'/scoreboard objectives remove "{scoreboard}"')

        Print.print_suc("重置完成")

    def create(self, args):
        data_path = os.path.join(self.data_path, "服务器计分板.json")
        data = load_data(data_path)
        if not data:
            Print.print_err("没有保存的计分板")
            return

        for scoreboard, show in data.items():
            self.game_ctrl.sendwscmd(
                f'/scoreboard objectives add "{scoreboard}" dummy "{show}"'
            )

        Print.print_suc("计分板重新创建完成")
        return

    def on_def(self):
        self.frame.add_console_cmd_trigger(
            ["重置计分板"], "[]", "用于将计分板数据全部重置", self.clear
        )
        self.frame.add_console_cmd_trigger(
            ["创建计分板"], "[]", "用于重新创建计分板", self.create
        )


entry = plugin_entry(NewPlugin)

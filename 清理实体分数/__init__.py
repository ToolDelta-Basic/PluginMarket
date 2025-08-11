from tooldelta import Plugin, fmts, plugin_entry
import time


class resetscore(Plugin):
    name = "清理实体分数"
    author = "ZTAI"
    version = (1, 0, 0)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)

    def console_clean(self, args: list[str]):
        fmts.print_inf("§e┃ §f开始获取需要清理的实体…")
        resp = self.game_ctrl.sendwscmd_with_resp("/scoreboard players list")
        if not resp or "OutputMessages" not in resp.as_dict:
            fmts.print_err("无法获取计分板数据")
            return

        messages = str(resp.as_dict["OutputMessages"])
        messages = messages.replace("'", "")
        gets = [get.strip() for get in messages.split(",")]
        targets = []
        for target in gets:
            if target.startswith("-") and target[1:].isdigit():
                if len(target) > 10:
                    targets.append(target)
        if not targets:
            fmts.print_inf("§a┃ §f未发现需要清理的实体")
            return

        total = len(targets)
        fmts.print_inf(f"§a┃ §f共发现 §e{total} §f个实体需要清理")
        self.game_ctrl.sendwscmd("/scoreboard objectives add 临时计分板 dummy")

        for idx, uuid in enumerate(targets, 1):
            self.game_ctrl.sendwscmd(f'/scoreboard players set "{uuid}" 临时计分板 1')
            fmts.print_inf(
                f"§7实体: §f{uuid}\n§7赋分进度：§a{idx}/{total} ({idx / total * 100:.1f}%)"
            )
            time.sleep(0.05)

        for idx, uuid in enumerate(targets, 1):
            self.game_ctrl.sendwscmd(f'/scoreboard players reset "{uuid}"')
            fmts.print_inf(
                f"§7实体: §f{uuid}\n§7清理进度：§c{idx}/{total} ({idx / total * 100:.1f}%)"
            )
            time.sleep(0.05)

        fmts.print_inf("§a┃ §f清理完成")
        self.game_ctrl.sendwscmd("/scoreboard objectives remove 临时计分板")

    def on_def(self):
        self.frame.add_console_cmd_trigger(
            ["清理实体分数"],
            None,
            "清理计分板中冗余的实体分数（UUID 实体）",
            self.console_clean,
        )


entry = plugin_entry(resetscore, "清理实体分数")

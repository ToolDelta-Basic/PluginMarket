import os
from dataclasses import dataclass
from tooldelta import Plugin, utils, fmts, Chat, Player, plugin_entry

EVT_SYSTEM_LAUNCH = "系统启动"
EVT_TIMER = "定时执行"
EVT_MSG = "触发词"
EVT_PLAYERJOIN = "玩家进服"
EVT_PLAYERLEAVE = "玩家退出"
EVT_PLAYERDEATH = "玩家死亡"
VALID_EVENTS = (
    EVT_SYSTEM_LAUNCH,
    EVT_TIMER,
    EVT_MSG,
    EVT_PLAYERJOIN,
    EVT_PLAYERLEAVE,
    EVT_PLAYERDEATH,
)


@dataclass
class MCFunction:
    fname: str
    content: str
    event: str
    extras: dict

    def execute(self, game_ctrl, repls: dict[str, str]):
        for cmd in self.content.split("\n"):
            if cmd.strip().startswith("#"):
                continue
            else:
                game_ctrl.sendwocmd(utils.simple_fmt(repls, cmd))


class MCFunctionExecutor(Plugin):
    name = "MCFunction计划任务"
    author = "SuperScript"
    version = (0, 0, 1)
    time_counter = 0

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)

    def on_def(self):
        self.events: dict[str, list[MCFunction]] = {i: [] for i in VALID_EVENTS}
        self.read_files()
        self.triggers_prepared = self.prepare_triggers()

    def on_inject(self):
        self.execute_timer()
        for evt in self.events[EVT_SYSTEM_LAUNCH]:
            evt.execute(self.game_ctrl, {})

    def on_player_join(self, playerf: Player):
        player = playerf.name
        for evt in self.events[EVT_PLAYERJOIN]:
            evt.execute(self.game_ctrl, {"[玩家名]": player})

    def on_player_leave(self, playerf: Player):
        player = playerf.name
        for evt in self.events[EVT_PLAYERLEAVE]:
            evt.execute(self.game_ctrl, {"[玩家名]": player})

    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg

        if msg not in self.triggers_prepared:
            return
        for evt in self.events[EVT_MSG]:
            evt.execute(self.game_ctrl, {"[玩家名]": player})

    def on_player_death(self, player: str, killer, _):
        for evt in self.events[EVT_PLAYERDEATH]:
            evt.execute(self.game_ctrl, {"[玩家名]": player, "[击杀者]": killer})

    @staticmethod
    def parse_comments(content: str):
        kws: dict[str, str] = {}
        pre_arg = None
        for line in content.split("\n"):
            if not line.strip().startswith("#"):
                continue
            for maybe_arg in line.split():
                if pre_arg is not None:
                    kws[pre_arg] = maybe_arg
                    pre_arg = None
                elif len(maybe_arg) > 1 and maybe_arg[-1] in [":", "："]:
                    pre_arg = maybe_arg[:-1]
        return kws

    def prepare_triggers(self):
        return [evt.extras["trigger"] for evt in self.events[EVT_MSG]]

    def read_files(self):
        for filename in os.listdir(self.data_path):
            if filename.endswith(".mcfunction"):
                with open(
                    os.path.join(self.data_path, filename), encoding="utf-8"
                ) as f:
                    content = f.read()
                filename = filename[:-11]
                kws = self.parse_comments(content)
                if kws.get("事件") is None:
                    fmts.print_war(
                        f"Mcf文件 {filename} 没有设定事件类型, 假定为系统启动事件"
                    )
                    kws["事件"] = EVT_SYSTEM_LAUNCH
                if kws["事件"] not in VALID_EVENTS:
                    fmts.print_war(f"Mcf文件 任务类型 {kws['事件']} 未知, 不予识别")
                    continue
                if kws["事件"] == EVT_TIMER:
                    _timer = kws.get("间隔")
                    if _timer is None:
                        fmts.print_war(
                            f"Mcf文件 {filename} 为定时任务却没有设定间隔, 默认为60s"
                        )
                        timer = 60
                    elif _timer[-1] in ("s", "秒"):
                        _timer = _timer[-1]
                    if (timer := utils.try_int(_timer)) is None:
                        fmts.print_err(
                            f"Mcf文件 {filename} 为定时任务, 却无法识别间隔"
                        )
                        raise SystemExit
                    self.events[EVT_TIMER].append(
                        MCFunction(filename, content, kws["事件"], {"delay": timer})
                    )
                elif kws["事件"] == EVT_MSG:
                    msg = kws.get("触发词")
                    if msg is None:
                        fmts.print_err(
                            f"Mcf文件 {filename} 为玩家发言任务却没有设定触发词"
                        )
                        raise SystemExit
                    self.events[EVT_MSG].append(
                        MCFunction(filename, content, kws["事件"], {"trigger": msg})
                    )
                elif kws["事件"] == EVT_SYSTEM_LAUNCH:
                    self.events[EVT_SYSTEM_LAUNCH].append(
                        MCFunction(filename, content, kws["事件"], {})
                    )
        fmts.print_suc(
            f"MCF计划任务: 成功加载了 {', '.join(f'§f{len(j)}§a个{i}任务' for i, j in self.events.items())}"
        )

    @utils.timer_event(1, "MCFunction计划任务")
    def execute_timer(self):
        self.time_counter += 1
        for evt in self.events[EVT_TIMER]:
            if self.time_counter % evt.extras["delay"] == 0:
                evt.execute(self.game_ctrl, {})


entry = plugin_entry(MCFunctionExecutor)

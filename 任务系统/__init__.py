import os, time  # noqa: E401
from dataclasses import dataclass
from tooldelta import (
    Plugin,
    utils,
    TYPE_CHECKING,
    cfg as config,
    fmts,
    game_utils,
    Player,
    plugin_entry,
)


@dataclass
class Quest:
    tag_name: str
    "标签名, 即文件夹/文件名去json"
    show_name: str
    "展示名"
    description: str
    "描述"
    detect_cmds: list[str]
    "检测命令"
    need_items: dict[str, list]
    "需要的物品"
    cooldown: int
    "任务冷却的秒数"
    exec_cmds_when_finished: list[str]
    "完成时执行的指令"
    items_give_when_finished: dict
    "完成时给予的物品"
    start_quest_when_finished: list[str]
    "完成时开始的任务"
    command_block_only: bool
    "只能由命令方块来完成任务"
    # EXTRA
    need_quests_prefix: list[str] | None

    def __hash__(self) -> int:
        return id(self)


class TaskSystem(Plugin):
    name = "任务系统"
    author = "SuperScript"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.QUEST_PATH = os.path.join(self.data_path, "任务")
        self.QUEST_DATA_PATH = os.path.join(self.data_path, "任务数据")
        self.tmpjson = utils.tempjson
        self.in_plot_running = {}
        self.quests: dict[str, Quest] = {}
        for ipath in [self.QUEST_PATH, self.QUEST_DATA_PATH]:
            os.makedirs(ipath, exist_ok=True)
        CFG_STD = {
            "任务设置": {
                "任务列表显示格式": config.JsonList(str),
                "接到新任务时执行的指令": config.JsonList(str),
                "任务无法提交的显示": {
                    "格式": str,
                },
                "任务完成执行的指令": config.JsonList(str),
            }
        }
        CFG_DEFAULT = {
            "任务设置": {
                "任务列表显示格式": [
                    "§7▶ 当前正在进行的任务:",
                    " §f[i] §7- §f[任务显示名]\n  §7[任务描述] ",
                    "§7在15s内输入§f任务前的序号§r§7可以提交此任务 §f其他§7以退出",
                ],
                "接到新任务时执行的指令": [
                    "/execute as @a[name=[玩家名]] at @s run playsound note.pling @s ~~~ 1 1.4",
                    '/tellraw @a[name=[玩家名]] {"rawtext":[{"text":"§d▶ §e收到新任务 §f[任务显示名]\n  §7[任务描述] \n§3输入§b.rw§3以提交任务"}]}',
                ],
                "任务无法提交的显示": {
                    "格式": "§c任务无法达成， 原因:\n [原因]",
                },
                "任务无法开始的显示": {"格式": "§c任务无法开始， 原因:\n [原因]"},
                "任务完成执行的指令": [
                    '/tellraw @a[name=[玩家名]] {"rawtext":[{"text":"§a任务完成"}]}',
                    "/execute as @a[name=[玩家名]] at @s run playsound random.levelup @s",
                ],
            },
        }
        QUEST_STD = {
            "显示名": str,
            "描述": str,
            "检测的指令": config.JsonList(str),
            "需要的物品": config.AnyKeyValue(config.JsonList((str, int))),
            "只能由命令方块触发完成": bool,
            "任务模式(-1=一次性 0=可重复做 >0为任务冷却秒数)": int,
            "任务完成": {
                "执行的指令": config.JsonList(str),
                "给予的物品": config.AnyKeyValue(config.JsonList((str, int), 2)),
                "开启的新任务": config.JsonList(str),
            },
        }
        self.cfg, _ = config.get_plugin_config_and_version(
            self.name, CFG_STD, CFG_DEFAULT, self.version
        )
        total_quest_files = 0
        for cfg_quest_dir in os.listdir(self.QUEST_PATH):
            try:
                sub_path = os.path.join(self.QUEST_PATH, cfg_quest_dir)
                if not os.path.isdir(sub_path):
                    continue
                for file in os.listdir(sub_path):
                    cfg = config.get_cfg(os.path.join(sub_path, file), QUEST_STD)
                    tag_name = f"{cfg_quest_dir}/{file[:-5]}"
                    self.quests[tag_name] = Quest(
                        tag_name,
                        cfg["显示名"],
                        cfg["描述"],
                        cfg["检测的指令"],
                        cfg["需要的物品"],
                        cfg["任务模式(-1=一次性 0=可重复做 >0为任务冷却秒数)"],
                        cfg["任务完成"]["执行的指令"],
                        cfg["任务完成"]["给予的物品"],
                        cfg["任务完成"]["开启的新任务"],
                        cfg["只能由命令方块触发完成"],
                        cfg.get("需要完成的前置任务"),
                    )
                    total_quest_files += 1
            except config.ConfigError as err:
                fmts.print_err(f"任务系统: 任务配置文件 {file} 出错: ")
                fmts.print_err(err.args[0])
        for quest in self.quests.values():
            for i in quest.start_quest_when_finished:
                try:
                    if (quest := self.get_quest(i)) is None:
                        file = i
                        raise config.ConfigError(f"任务 {i} 不存在")
                    if quest.need_quests_prefix:
                        for i in quest.need_quests_prefix:
                            if self.get_quest(i) is None:
                                file = i
                                raise config.ConfigError(f"要求的前置任务 {i} 不存在")
                except config.ConfigError as err:
                    fmts.print_err(f"任务系统: 任务配置文件 {file} 出错: ")
                    fmts.print_err(err.args[0])
        fmts.print_with_info(
            f"§a共加载 §b{total_quest_files}§a 个任务文件.", "§b Task §r"
        )
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)

    def on_def(self):
        self.interper = self.GetPluginAPI("ZBasic", (0, 0, 1), False)
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.cb2bot = self.GetPluginAPI("Cb2Bot通信")
        if TYPE_CHECKING:
            from ZBasic_Lang_中文编程 import ToolDelta_ZBasic
            from 前置_聊天栏菜单 import ChatbarMenu
            from 前置_Cb2Bot通信 import TellrawCb2Bot

            self.interper: ToolDelta_ZBasic
            self.chatbar: ChatbarMenu
            self.cb2bot: TellrawCb2Bot
        self.cb2bot.regist_message_cb("quest.ok", self.on_quest_ok)
        self.cb2bot.regist_message_cb("quest.start", self.on_quest_start)

    def show_succ(self, player, msg):
        self.game_ctrl.say_to(player, f"§7<§a§o√§r§7> §a{msg}")

    def show_warn(self, player, msg):
        self.game_ctrl.say_to(player, f"§7<§6§o!§r§7> §6{msg}")

    def show_fail(self, player, msg):
        self.game_ctrl.say_to(player, f"§7<§c§o!§r§7> §c{msg}")

    def show_inf(self, player, msg):
        self.game_ctrl.say_to(player, f"§7<§f§o!§r§7> §f{msg}")

    @utils.thread_func("自定义RPG-剧情与任务的游戏初始化")
    def on_inject(self):
        self.cmp_scripts = {}
        self.chatbar.add_trigger(
            [".rw", ".任务"],
            None,
            "查看正在进行的任务列表",
            lambda player, _: self.list_player_quests(player),
        )
        self.chatbar.add_trigger(
            [".addrw", ".添加任务"],
            "[任务名]",
            "向玩家添加任务",
            self.force_add_quest_menu,
            lambda x: x == 1,
            True,
        )
        for player in self.game_ctrl.allplayers:
            self.init_player(player)

    @utils.thread_func("自定义RPG-初始化玩家剧情任务数据")
    def on_player_join(self, playerf: Player):
        player = playerf.name
        self.init_player(player)

    def on_quest_ok(self, args: list[str]):
        target, quest_name = args
        quest = self.get_quest(quest_name)
        if quest is not None:
            self.quest_ok(target, quest)

    def on_quest_start(self, args: list[str]):
        target, quest_name = args
        quest = self.get_quest(quest_name)
        if quest is not None:
            self.add_quest(target, quest)

    def init_player(self, player: str):
        quest_path = os.path.join(self.QUEST_DATA_PATH, player + ".json")
        o = self.tmpjson.load_and_read(quest_path, False)
        if o is None:
            self.tmpjson.write(quest_path, self.init_quest_file())

    def init_quest_file(self):
        return {"in_quests": [], "quests_ok": {}}

    def read_quests(self, player: str) -> list[Quest]:
        o = self.tmpjson.load_and_read(
            os.path.join(self.QUEST_DATA_PATH, player + ".json")
        )
        output = []
        o = o or {"in_quests": []}
        for i in o["in_quests"]:
            output.append(self.get_quest(i))
        return output

    def read_quests_finished(self, player: str) -> dict[Quest, int]:
        o = self.tmpjson.load_and_read(
            os.path.join(self.QUEST_DATA_PATH, player + ".json")
        )
        output = {}
        for k, v in o["quests_ok"].items():
            quest = self.get_quest(k)
            if quest:
                output[quest] = v
        return output

    @utils.thread_func("管理员向玩家添加任务")
    def force_add_quest_menu(self, player: str, args: list[str]):
        # with utils.ChatbarLock(player, lambda _: print(utils.chatbar_lock_list)):
        if (quest := self.get_quest(args[0])) is None:
            self.game_ctrl.say_to(player, "§c任务标签名不存在")
            return
        onlines = self.game_ctrl.allplayers.copy()
        self.show_inf(player, "§6选择一个玩家以向他添加任务：")
        for i, j in enumerate(onlines):
            self.game_ctrl.say_to(player, f" §a{i + 1}§7 - §f{j}")
        resp = utils.try_int(game_utils.waitMsg(player))
        self.show_inf(player, "§7输入玩家名前的§6序号§7：")
        if resp is None:
            self.game_ctrl.say_to(player, "§c序号错误， 已退出")
            return
        if resp not in range(1, len(onlines) + 1):
            self.game_ctrl.say_to(player, "§c序号不在范围内， 已退出")
            return
        getting = onlines[resp - 1]
        self.game_ctrl.say_to(
            player,
            f"§6向玩家{getting}添加任务"
            + ["§c失败", "§a成功"][self.add_quest(getting, quest)],
        )

    def get_quest(self, tag_name: str):
        return self.quests.get(tag_name)

    def add_quest(self, player: str, quest: Quest):
        quests = self.read_quests(player)
        if quest in quests:
            self.show_fail(player, "§c当前任务正在进行中， 无法重复领取")
            return 0
        else:
            quest_time = self.read_quests_finished(player).get(quest, None)
            quest_mode = quest.cooldown
            if quest_mode == -1 and quest_time is not None:
                self.game_ctrl.say_to(
                    player,
                    utils.simple_fmt(
                        {"[玩家名]": player, "[原因]": "§c你已经完成该任务"},
                        self.cfg["任务设置"]["任务无法开始的显示"]["格式"],
                    ),
                )
                return 0
            elif (
                quest_time is not None
                and quest_mode > 0
                and time.time() - quest_time < quest.cooldown
            ):
                fmt_text = r"%d §c天 §6%H §c时 §6%M §c分"
                self.game_ctrl.say_to(
                    player,
                    utils.simple_fmt(
                        {
                            "[原因]": ""
                            + self.sec_to_timer(
                                quest.cooldown - int(time.time()) + quest_time, fmt_text
                            )
                        },
                        self.cfg["任务设置"]["任务无法开始的显示"]["格式"],
                    ),
                )
                return 0
            for cmd in self.cfg["任务设置"]["接到新任务时执行的指令"]:
                s_cmd = utils.simple_fmt(
                    {
                        "[任务显示名]": quest.show_name,
                        "[任务描述]": quest.description,
                        "[玩家名]": player,
                    },
                    cmd,
                )
                self.game_ctrl.sendwocmd(s_cmd)
            path = os.path.join(self.QUEST_DATA_PATH, player + ".json")
            o = self.tmpjson.load_and_read(path)
            o["in_quests"].append(quest.tag_name)
            self.tmpjson.write(path, o)
            return 1

    def detect_quest(self, player, quest: Quest):
        if quest.command_block_only:
            return False, "§6无法手动提交该任务"
        if quest.need_quests_prefix:
            err_strs = []
            player_finished_quests = self.read_quests_finished(player)
            for quest_name in quest.need_quests_prefix:
                if (
                    need_quest := self.get_quest(quest_name)
                ) not in player_finished_quests:
                    assert need_quest
                    err_strs.append(need_quest.show_name)
            if err_strs:
                return False, "需要完成任务:\n  " + "\n  ".join(err_strs)
        if quest.need_items:
            err_strs = []
            for item_name, (item_id, *ext_data) in quest.need_items.items():
                if len(ext_data) == 2:
                    count, data = ext_data
                else:
                    count = ext_data[0]
                    data = 0
                if (
                    item_count_now := game_utils.getItem(player, item_id, data)
                ) < count:
                    err_strs.append(
                        f"§f{item_name} §7(§c{item_count_now}§7/§f{count}§7)"
                    )
            if err_strs:
                return False, "缺少物品: \n  " + "\n  ".join(err_strs)
        if quest.detect_cmds:
            for cmd in quest.detect_cmds:
                if not game_utils.isCmdSuccess(
                    utils.simple_fmt({"[玩家名]": player}, cmd)
                ):
                    return False, "§6未达成条件"
        return True, None

    @utils.thread_func("列出任务列表")
    def list_player_quests(self, player: str):
        # with utils.ChatbarLock(player):
        player_quests = self.read_quests(player)
        if not player_quests:
            self.show_fail(player, "你没有正在进行的任务")
            return
        else:
            self.game_ctrl.say_to(player, self.cfg["任务设置"]["任务列表显示格式"][0])
            for i, quest_data in enumerate(player_quests):
                if quest_data is None:
                    self.game_ctrl.say_to(
                        player,
                        utils.simple_fmt(
                            {
                                "[任务显示名]": "§c<任务失效>§f",
                                "[任务描述]": "--",
                                "[i]": i + 1,
                            },
                            self.cfg["任务设置"]["任务列表显示格式"][1],
                        ),
                    )
                else:
                    self.game_ctrl.say_to(
                        player,
                        utils.simple_fmt(
                            {
                                "[任务显示名]": quest_data.show_name,
                                "[任务描述]": quest_data.description,
                                "[i]": i + 1,
                            },
                            self.cfg["任务设置"]["任务列表显示格式"][1],
                        ),
                    )
            self.game_ctrl.say_to(
                player,
                utils.simple_fmt(
                    {"[任务数量]": len(player_quests)},
                    self.cfg["任务设置"]["任务列表显示格式"][2],
                ),
            )
            resp = game_utils.waitMsg(player)
            if resp is None:
                return
            resp = utils.try_int(resp.strip("[]"))
            if resp is None:
                self.game_ctrl.say_to(player, "§c序号不合法")
                return
            if resp not in range(1, len(player_quests) + 1):
                self.show_fail(player, "序号超出范围")
                return
            getting_quest = player_quests[resp - 1]
            if getting_quest is None:
                self.show_fail(player, "无法完成失效的任务")
                return
            ok, reason = self.detect_quest(player, getting_quest)
            if not ok:
                self.game_ctrl.say_to(
                    player,
                    utils.simple_fmt(
                        {"[玩家名]": player, "[原因]": reason},
                        self.cfg["任务设置"]["任务无法提交的显示"]["格式"],
                    ),
                )
                return
            else:
                self.quest_ok(player, getting_quest)

    def quest_ok(self, player: str, quest: Quest):
        self.game_ctrl.sendwocmd(
            f"/execute as @a[name={player}] at @s run playsound random.levelup @s"
        )
        self.game_ctrl.say_to(player, "§a۞ §l任务完成 §r§e奖励已下发~")
        for cmd in quest.exec_cmds_when_finished:
            self.game_ctrl.sendwocmd(utils.simple_fmt({"[玩家名]": player}, cmd))
        for item_name, (item_id, count) in quest.items_give_when_finished.items():
            self.game_ctrl.sendwocmd(f"give @a[name={player}] {item_id} {count}")
            self.game_ctrl.say_to(player, f" §7 + {count}x§f{item_name}")
        path = os.path.join(self.QUEST_DATA_PATH, player + ".json")
        o = self.tmpjson.load_and_read(path)
        o["quests_ok"][quest.tag_name] = int(time.time())
        o["in_quests"].remove(quest.tag_name)
        self.tmpjson.write(path, o)
        self.show_succ(player, "任务已提交, 请退出聊天栏")
        for new_quest in quest.start_quest_when_finished:
            new_quest = self.get_quest(new_quest)
            assert new_quest
            self.add_quest(player, new_quest)

    def sec_to_timer(self, timesec: int, fmt: str):
        days, left = divmod(timesec, 86400)
        hrs, left = divmod(left, 3600)
        mins, secs = divmod(left, 60)
        if secs > 0 and mins == 0:
            mins = 1
        return utils.simple_fmt({"%d": days, "%H": hrs, "%M": mins, "%S": secs}, fmt)


entry = plugin_entry(TaskSystem)

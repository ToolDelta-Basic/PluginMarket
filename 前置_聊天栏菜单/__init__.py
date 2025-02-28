from tooldelta import plugins, Plugin, Config, launch_cli, Utils

from dataclasses import dataclass
from collections.abc import Callable


plugins.checkSystemVersion((0, 7, 5))

@dataclass
class ChatbarTriggersSimple:
    triggers: list[str]
    usage: str
    func: Callable
    op_only: bool
    argument_hint = ""
    args_pd = staticmethod(lambda _,: True)

@dataclass
class ChatbarTriggers:
    triggers: list[str]
    argument_hint: str | None
    usage: str
    func: Callable
    args_pd: Callable
    op_only: bool


# 使用 api = plugins.get_plugin_api("聊天栏菜单") 来获取到这个api
@plugins.add_plugin_as_api("聊天栏菜单")
class ChatbarMenu(Plugin):
    """
    使用如下方法对接到这个组件:

    >>> menu = plugins.get_plugin_api("聊天栏菜单")

    你可以用它来添加菜单触发词, 像这样:
    menu.add_trigger(["触发词1", "触发词2..."], "功能提示", "<参数提示>", 监听方法[, 参数判定方法(传入参数列表的长度)])

    >>> def MoYu(args):
            print("你摸了: ", " 和 ".join(args))
    >>> menu.add_trigger(["摸鱼", "摸鱼鱼"], "<鱼的名字>", "随便摸一下鱼", MoYu, lambda a: a >= 1)
    """

    name = "聊天栏菜单"
    author = "SuperScript"
    version = (0, 3, 0)
    description = "前置插件, 提供聊天栏菜单功能"

    def __init__(self, frame):
        super().__init__(frame)
        self.chatbar_triggers: list[ChatbarTriggers | ChatbarTriggersSimple] = []
        DEFAULT_CFG = {
            "help菜单样式": {
                "菜单头": "§7>>> §l§bＴｏｏｌＤｅｌｔａ\n§r§l===============================",
                "菜单列表": " - [菜单指令][参数提示] §7§o[菜单功能说明]",
                "菜单尾": "§r§l==========[[当前页数] §7/ [总页数]§f]===========\n§r>>> §7输入 .help <页数> 可以跳转到该页",
            },
            "/help触发词": [".help"],
            "被识别为触发词的前缀(不填则为无命令前缀)": [".", "。", "·"],
            "单页内最多显示数": 6,
        }
        STD_CFG_TYPE = {
            "help菜单样式": {"菜单头": str, "菜单列表": str, "菜单尾": str},
            "/help触发词": Config.JsonList(str),
            "单页内最多显示数": Config.PInt,
            "被识别为触发词的前缀(不填则为无命令前缀)": Config.JsonList(str)
        }
        self.cfg, _ = Config.get_plugin_config_and_version(
            self.name, STD_CFG_TYPE, DEFAULT_CFG, (0, 0, 1)
        )
        self.prefixs = self.cfg["被识别为触发词的前缀(不填则为无命令前缀)"]

    # ----API----
    def add_trigger(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable | None,
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only=False,
    ):
        """
        添加菜单触发词项.
        Args:
            triggers (list[str]): 所有命令触发词
            argument_hint (str | None): 提示词(命令参数)
            usage (str): 显示的命令说明
            func (Callable | None): 菜单触发回调, 回调参数为(玩家名: str, 命令参数: list[str])
            args_pd ((int) -> bool): 判断方法 (参数数量:int) -> 参数数量是否合法: bool
            op_only (bool): 是否仅op可触发; 目前认为创造模式的都是OP, 你也可以自行更改并进行PR
        """
        for tri in triggers:
            if tri.startswith("."):
                triggers[triggers.index(tri)] = tri[1:]

        if func is None:

            def call_none(*args):
                return None

            self.chatbar_triggers.append(
                ChatbarTriggers(
                    triggers, argument_hint, usage, call_none, args_pd, op_only
                )
            )
            return
        self.chatbar_triggers.append(
            ChatbarTriggers(triggers, argument_hint, usage, func, args_pd, op_only)
        )

    def add_simple_trigger(
        self,
        triggers: list[str],
        usage: str,
        func: Callable | None,
        op_only=False,
    ):
        """
        添加简单的不需要带参的菜单触发词项.
        Args:
            triggers (list[str]): 所有命令触发词
            usage (str): 显示的命令说明
            func (Callable | None): 菜单触发回调, 回调参数为(玩家名: str, 命令参数: list[str])
            op_only (bool): 是否仅op可触发; 目前认为创造模式的都是OP, 你也可以自行更改并进行PR
        """
        for tri in triggers:
            if tri.startswith("."):
                triggers[triggers.index(tri)] = tri[1:]
        if func is None:

            def call_none(*args):
                return None

            self.chatbar_triggers.append(
                ChatbarTriggersSimple(
                    triggers, usage, call_none, op_only
                )
            )
            return
        self.chatbar_triggers.append(
            ChatbarTriggersSimple(triggers, usage, func, op_only)
        )

    # ------------

    def on_def(self):
        if isinstance(self.frame.launcher, launch_cli.FrameNeOmgAccessPoint):
            self.is_op = lambda player: self.frame.launcher.is_op(player)
        else:

            def get_success_count(player: str) -> bool:
                result = self.game_ctrl.sendcmd(f"/testfor @a[name={player},m=1]", True)
                if result is not None and result.SuccessCount is not None:
                    return bool(result.SuccessCount)
                return False  # 或者任何你认为合适的默认值

            self.is_op = get_success_count

    def show_menu(self, player: str, page: int):
        # page min = 1
        player_is_op = self.is_op(player)
        all_menu_args = self.chatbar_triggers
        if not player_is_op:
            # 仅 OP 可见的部分 过滤掉
            all_menu_args = list(filter(lambda x: not x.op_only, all_menu_args))
        lmt = self.cfg["单页内最多显示数"]
        total = len(all_menu_args)
        max_page = (total + lmt - 1) // lmt
        if page < 1:
            page_split_index = 0
        elif page > max_page:
            page_split_index = max_page - 1
        else:
            page_split_index = page - 1
        diplay_menu_args = all_menu_args[
            page_split_index * lmt : (page_split_index + 1) * lmt
        ]
        self.game_ctrl.say_to(player, self.cfg["help菜单样式"]["菜单头"])
        for tri in diplay_menu_args:
            self.game_ctrl.say_to(
                player,
                Utils.simple_fmt(
                    {
                        "[菜单指令]": ("§e" if tri.op_only else "")
                        + " / ".join(tri.triggers)
                        + "§r",
                        "[参数提示]": (
                            " " + tri.argument_hint if (isinstance(tri, ChatbarTriggers) and tri.argument_hint) else ""
                        ),
                        "[菜单功能说明]": (
                            "" if tri.usage is None else "以" + tri.usage
                        ),
                    },
                    self.cfg["help菜单样式"]["菜单列表"],
                ),
            )
        self.game_ctrl.say_to(
            player,
            Utils.simple_fmt(
                {"[当前页数]": page_split_index + 1, "[总页数]": max_page},
                self.cfg["help菜单样式"]["菜单尾"],
            ),
        )

    @Utils.thread_func("聊天栏菜单执行")
    def on_player_message(self, player: str, msg: str):
        if self.prefixs:
            for prefix in self.prefixs:
                if msg.startswith(prefix):
                    msg = msg[len(prefix):]
                    break
            else:
                return
        player_is_op = self.is_op(player)
        # 这是查看指令帮助的触发词
        for tri in self.cfg["/help触发词"]:
            if msg.startswith(tri):
                with Utils.ChatbarLock(player, self.on_menu_warn):
                    # 这是 help 帮助的触发词
                    m = msg.split()
                    if len(m) == 1:
                        self.show_menu(player, 1)
                    else:
                        if (page_num := Utils.try_int(m[1])) is None:
                            self.game_ctrl.say_to(
                                player, "§chelp 命令应为1个参数: <页数: 正整数>"
                            )
                        else:
                            self.show_menu(player, page_num)
                return
        # 这是一般菜单触发词
        for tri in self.chatbar_triggers:
            for trigger in tri.triggers:
                if msg.startswith(trigger):
                    if (not player_is_op) and tri.op_only:
                        self.game_ctrl.say_to(
                            player, "§c创造模式或者OP才可以使用该菜单项"
                        )
                        return
                    args = msg.removeprefix(trigger).split()
                    if " " in trigger:
                        with Utils.ChatbarLock(player, self.on_menu_warn):
                            tri_split_num = len(trigger.split()) - 1
                            args = args[tri_split_num:]
                            if not tri.args_pd(len(args)):
                                self.game_ctrl.say_to(player, "§c菜单参数数量错误")
                                return
                            tri.func(player, args)
                    else:
                        with Utils.ChatbarLock(player, self.on_menu_warn):
                            if not tri.args_pd(len(args)):
                                self.game_ctrl.say_to(player, "§c菜单参数数量错误")
                                return
                            tri.func(player, args)

    def on_menu_warn(self, player: str):
        self.game_ctrl.say_to(player, "§c退出当前菜单才能继续唤出菜单")

import re
import time
from tooldelta import (
    ToolDelta,
    Plugin,
    Player,
    cfg,
    utils,
    fmts,
    game_utils,
    plugin_entry,
    TYPE_CHECKING,
)


class CustomChatbarMenu(Plugin):
    name = "自定义聊天栏菜单"
    author = "SuperScript"
    version = (0, 1, 4)
    description = "自定义ToolDelta的聊天栏菜单触发词等"
    args_match_rule = re.compile(r"(\[参数:([0-9]+)\])")
    scb_simple_rule = re.compile(r"\[计分板:([^\[\]]+)\]")
    scb_replace_simple_rule = re.compile(r"\[计分板替换:([^\[\(\)\]]+)\(([^\)]+)\)\]")
    scb_replace_next_rule = re.compile(r"([0-9~\-]+):([^ ]+)")
    _counter = 0

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        STD_CFG = {
            "菜单项": cfg.JsonList(
                {
                    "触发词": cfg.JsonList(str),
                    "功能简介": str,
                    "需要的参数(没有则填[])": cfg.JsonList(
                        {
                            "参数名": str,
                            "类型": str,
                            "默认值(没有则为null)": (int, float, str, bool, type(None)),
                        }
                    ),
                    "触发后执行的指令": cfg.JsonList(str),
                    "仅OP可用": bool,
                    cfg.KeyGroup("仅创造模式可用"): bool,
                },
            )
        }
        DEFAULT_CFG = {
            "菜单项": [
                {
                    "说明": "返回重生点",
                    "触发词": ["kill", "自尽"],
                    "需要的参数(没有则填[])": [],
                    "功能简介": "返回重生点",
                    "触发后执行的指令": [
                        "td:/show §c5秒后准备自尽..",
                        "sleep 5",
                        "/kill [玩家名]",
                        "/title [玩家名] actionbar 自尽成功",
                    ],
                    "仅OP可用": False,
                },
                {
                    "说明": "一个测试菜单参数项的触发词菜单项",
                    "触发词": ["测试参数"],
                    "需要的参数(没有则填[])": [
                        {
                            "参数名": "填一个整数",
                            "类型": "int",
                            "默认值(没有则为null)": None
                        },
                        {
                            "参数名": "随便填",
                            "类型": "str",
                            "默认值(没有则为null)": None
                        },
                        {
                            "参数名": "填true或false，默认为false",
                            "类型": "bool",
                            "默认值(没有则为null)": False
                        },
                    ],
                    "功能简介": "测试触发词参数",
                    "触发后执行的指令": [
                        "/w [玩家名] 触发词测试成功: 参数1=[参数:1], 参数2=[参数:2], 参数3=[参数:3]",
                        "/w [玩家名] 这个菜单项仅供测试和学习如何使用参数， 可删除"
                    ],
                    "仅OP可用": True,
                },
                {
                    "说明": "一个个人档案的示例",
                    "触发词": ["个人档案", "prof"],
                    "需要的参数(没有则填[])": [],
                    "功能简介": "查看个人档案",
                    "触发后执行的指令": [
                        "td:/show §e| §l个人档案§r§e |",
                        "td:/show §7▶ §e金币: [计分板:金币]",
                        "td:/show §7▶ §d在线时长: [计分板:在线时长]",
                        "td:/show §7▶ §6您的性别: [计分板替换:性别(0:未知 1:男 2:女)]",
                        "td:/show §7▶ §c金币称号: [计分板替换:金币(0~1000:平民 1001~10000:公民 10001~80000:中产 80001~150000:富婆)]",
                    ],
                    "仅OP可用": False,
                },
                {
                    "说明": "给予创造玩家一些建筑材料",
                    "触发词": ["建材", "bblocks"],
                    "需要的参数(没有则填[])": [],
                    "功能简介": "查看个人档案",
                    "触发后执行的指令": [
                        "/give [玩家名] brick_block",
                        "/give [玩家名] planks",
                        "/give [玩家名] sealantern",
                        "/give [玩家名] logs",
                        "/give [玩家名] quartz_block"
                    ],
                    "仅OP可用": False,
                    "仅创造模式可用": True,
                }
            ]
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, STD_CFG, DEFAULT_CFG, self.version
        )
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu

            self.chatbar: ChatbarMenu

    @utils.thread_func("初始化菜单项")
    def on_inject(self):
        for menu in self.cfg["菜单项"]:
            self.regist_to_menu(menu)

    def regist_to_menu(self, menu: dict):
        cmds = menu["触发后执行的指令"]
        creative_only = menu.get("仅创造模式可用", False)

        def generate_argument_hint():
            hints_list = []
            for hint_object in menu["需要的参数(没有则填[])"]:
                hint_name: str = hint_object["参数名"]
                hint_type_: str = hint_object["类型"]
                hint_default = hint_object["默认值(没有则为null)"]
                if hint_type_ not in ("str", "int", "float", "bool"):
                    self.print(f"§e{menu['功能简介']} 的参数类型错误: '{hint_type_}'")
                    raise SystemExit
                hint_type: type = {
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                }[hint_type_]
                if not isinstance(hint_default, hint_type | None):
                    self.print(
                        f"§e{menu['功能简介']} 的参数 {hint_name} 的默认值和所给类型不匹配"
                    )
                    raise SystemExit
                hints_list.append((hint_name, hint_type, hint_default))
            return hints_list

        @utils.thread_func("自定义聊天栏菜单执行")
        def _menu_cb_func(player: Player, args: tuple):
            if creative_only:
                if player.name not in game_utils.getTarget("@a[m=1]"):
                    player.show("§c该命令仅创造模式玩家可用")
                    return
            for cmd in cmds:
                f_cmd = utils.simple_fmt(
                    {"[玩家名]": player.name},
                    self.args_replace(list(args), cmd, player.name),
                )
                if f_cmd.startswith("td:/show "):
                    player.show(f_cmd[8:])
                elif f_cmd.startswith("sleep "):
                    time.sleep(utils.try_int(f_cmd[6:]) or 0)
                else:
                    self.game_ctrl.sendwscmd(f_cmd)

        self.chatbar.add_new_trigger(
            menu["触发词"],
            generate_argument_hint(),
            menu["功能简介"],
            _menu_cb_func,
            op_only=menu["仅OP可用"],
        )

    def args_replace(self, args: list, sub: str, user: str):
        res = self.args_match_rule.findall(sub)
        for varsub, var_arg in res:
            try:
                var_value = args[int(var_arg) - 1]
                sub = sub.replace(varsub, var_value)
            except IndexError:
                fmts.print_err("聊天栏菜单: 菜单的参数项提供异常!")
                self.game_ctrl.say_to(
                    "@a", "聊天栏菜单: 菜单的参数项提供异常， 请联系管理员以修复"
                )
                raise SystemExit
        res = self.scb_simple_rule.findall(sub)
        for scb_name in res:
            try:
                score = str(game_utils.getScore(scb_name, user, 3))
            except ValueError:
                score = "<未知>"
                fmts.print_war(f"自定义聊天栏菜单: 获取 {scb_name}:{user} 的分数失败")
            except TimeoutError:
                score = "<未知>"
            sub = sub.replace(f"[计分板:{scb_name}]", score)
        res = self.scb_replace_simple_rule.findall(sub)
        for scb_name, scb_repl in res:
            try:
                repl_text = "<未知分数>"
                score = game_utils.getScore(scb_name, user, 3)
                repl_text = f"<未知替换样式:{score}>"
                res2 = self.scb_replace_next_rule.findall(scb_repl)
                for scb_num_repl, scb_str_repl in res2:
                    if "~" not in scb_num_repl:
                        if score == int(scb_num_repl):
                            repl_text = scb_str_repl
                            break
                    elif scb_num_repl.count("~") != 1:
                        repl_text = "<错误的替换样式:波浪号过多>"
                        break
                    else:
                        score_front, score_back = scb_num_repl.split("~")
                        score_front, score_back = int(score_front), int(score_back)
                        if score in range(score_front, score_back + 1):
                            repl_text = scb_str_repl
                            break
            except ValueError:
                score = None
                fmts.print_war(f"自定义聊天栏菜单: 获取 {scb_name}:{user} 的分数失败")
            except TimeoutError:
                score = None
                fmts.print_war(f"自定义聊天栏菜单: 获取 {scb_name}:{user} 的分数超时")
            sub = sub.replace(f"[计分板替换:{scb_name}({scb_repl})]", repl_text)
        return sub


entry = plugin_entry(CustomChatbarMenu)

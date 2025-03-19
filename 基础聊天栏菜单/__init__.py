from tooldelta import Plugin, Config, Utils, Chat, plugin_entry, game_utils
from dataclasses import dataclass
from collections.abc import Callable
import json
from kimi import askai

# ------------------------------- 服务器基本常量定义 -------------------------------

CURRENCY_SCOREBOARD = "金币" # 金币计分板
ONLINE_TIME_SCOREBOARD = "§l§b在§e线§d时§a间"  # 在线时间计分板
DEFAULT_HUB_COORDS = [1015, 235, 108]  # 主城坐标
DEFAULT_SHOP_COORDS = [928, 235, -81]  # 商店坐标
HUB_COORDS_FILE = "hub_coords.json"  # 主城坐标文件（可以不管）
SHOP_COORDS_FILE = "shop_coords.json"  # 商店坐标文件（可以不管）
MAX_TRANSFER_AMOUNT = 10000  # 最大转账金额

# --------------------------------- 聊天栏菜单插件 ---------------------------------

@dataclass
class ChatbarTriggersSimple:
    triggers: list[str]
    usage: str
    func: Callable
    op_only: bool
    argument_hint = ""
    args_pd = staticmethod(lambda _,: True)

# ------------------------------- 一个更复杂的菜单项 -------------------------------

@dataclass
class ChatbarTriggers:
    triggers: list[str]
    argument_hint: str | None
    usage: str
    func: Callable
    args_pd: Callable
    op_only: bool

class ChatbarMenu(Plugin):
    name = "基础聊天栏菜单"
    author = "帥気的男主角" # 别骂了别骂了
    version = (0, 3, 0)
    description = "为服务器提供聊天栏菜单功能"

    def __init__(self, frame):
        super().__init__(frame)
        self.chatbar_triggers: list[ChatbarTriggers | ChatbarTriggersSimple] = []
        
        # 配置常量
        self.currency_scoreboard = CURRENCY_SCOREBOARD
        self.online_time_scoreboard = ONLINE_TIME_SCOREBOARD
        self.hub_coords = self._load_coordinates(HUB_COORDS_FILE, "main_hub", DEFAULT_HUB_COORDS)
        self.shop_coords = self._load_coordinates(SHOP_COORDS_FILE, "shop", DEFAULT_SHOP_COORDS)
        self.max_transfer_amount = MAX_TRANSFER_AMOUNT
        
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
            "被识别为触发词的前缀(不填则为无命令前缀)": Config.JsonList(str),
        }
        self.cfg, _ = Config.get_plugin_config_and_version(
            self.name, STD_CFG_TYPE, DEFAULT_CFG, (0, 0, 1)
        )
        self.prefixs = self.cfg["被识别为触发词的前缀(不填则为无命令前缀)"]
        self.ListenChat(self.on_player_message)

        # 添加菜单项
        self.add_simple_trigger(["help"], "显示帮助菜单", self.show_help)
        self.add_trigger(["money"], "[玩家名] [金额]", "转账金币", self.transfer_money, lambda x: x == 2)
        self.add_simple_trigger(["me"], "显示个人信息", self.show_me)
        self.add_simple_trigger(["hub"], "传送回主城", self.send_to_hub)
        self.add_simple_trigger(["clear"], "清除服务器掉落物", self.clear_drops)
        self.add_trigger(["time"], "[时间]", "修改时间", self.change_time, lambda x: x == 1)
        self.add_simple_trigger(["kill"], "杀死自己", self.kill_self)
        self.add_simple_trigger(["survive"], "更换生存模式", self.change_to_survival)
        self.add_simple_trigger(["shop"], "传送商店", self.teleport_to_shop)
        self.add_simple_trigger(["ai"], "与AI对话", self.handle_ai_command)
        self.add_simple_trigger(["omg"], "omg菜单", self.show_help)
    
    def _load_coordinates(self, filename, key, default_coords):
        """从JSON文件中加载坐标，如果文件不存在或解析失败则返回默认值"""
        try:
            with open(filename, "r") as f:
                data = json.load(f)
                return data.get(key, default_coords)
        except (FileNotFoundError, json.JSONDecodeError):
            return default_coords

    # 添加菜单项
    def add_trigger(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable | None,
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only=False,
    ):
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

    # 添加简单菜单项
    def add_simple_trigger(
        self,
        triggers: list[str],
        usage: str,
        func: Callable | None,
        op_only=False,
    ):
        for tri in triggers:
            if tri.startswith("."):
                triggers[triggers.index(tri)] = tri[1:]
        if func is None:
            def call_none(*args):
                return None
            self.chatbar_triggers.append(
                ChatbarTriggersSimple(triggers, usage, call_none, op_only)
            )
            return
        self.chatbar_triggers.append(
            ChatbarTriggersSimple(triggers, usage, func, op_only)
        )

    # 显示菜单
    def show_menu(self, player: str, page: int, is_op: bool):
        all_menu_args = self.chatbar_triggers
        if not is_op:
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
                            " " + tri.argument_hint
                            if (isinstance(tri, ChatbarTriggers) and tri.argument_hint)
                            else ""
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

    # 聊天栏菜单执行
    @Utils.thread_func("聊天栏菜单执行")
    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg
        if self.prefixs:
            for prefix in self.prefixs:
                if msg.startswith(prefix):
                    msg = msg[len(prefix) :]
                    break
            else:
                return
        player_is_op = chat.player.is_op()
        for tri in self.cfg["/help触发词"]:
            if msg.startswith(tri):
                with Utils.ChatbarLock(player, self.on_menu_warn):
                    m = msg.split()
                    if len(m) == 1:
                        self.show_menu(player, 1, player_is_op)
                    else:
                        if (page_num := Utils.try_int(m[1])) is None:
                            self.game_ctrl.say_to(
                                player, "§chelp 命令应为1个参数: <页数: 正整数>"
                            )
                        else:
                            self.show_menu(player, page_num, player_is_op)
                return
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

    # 菜单退出提示
    def on_menu_warn(self, player: str):
        self.game_ctrl.say_to(player, "§c退出当前菜单才能继续唤出菜单")

    # --------------------------------- 菜单项功能 ---------------------------------

    # 显示帮助菜单
    def show_help(self, player: str, args: list[str]):
        help_message = [
            "§7>>> §l§b服务器§a命令大全",
            "§r§l=========================",
            "§e.help §r- 显示帮助菜单",
            "§e.money [玩家名] [金额] §r- 转账金币",
            "§e.r §r举报玩家",
            "§e.me §r- 显示个人信息",
            "§e.hub §r- 传送回主城",
            "§e.clear §r- 清除服务器掉落物",
            "§e.time [时间] §r- 修改时间",
            "§e.kill §r- 杀死自己",
            "§e.survive §r- 更换生存模式",
            "§e.shop §r- 传送商店",
            "§e.ai §r- 与AI对话",
            "§r§l=========================",
        ]
        for msg in help_message:
            self.game_ctrl.say_to(player, msg)

    # 转账金币
    def transfer_money(self, player: str, args: list[str]):
        target_player = args[0]
        amount = int(args[1])
        player_money = game_utils.getScore(self.currency_scoreboard, player)
        
        if player_money >= amount and self.max_transfer_amount >= amount and amount > 0:
            self.game_ctrl.sendcmd(f"/scoreboard players remove {player} {self.currency_scoreboard} {amount}")
            self.game_ctrl.sendcmd(f"/scoreboard players add {target_player} {self.currency_scoreboard} {amount}")
            self.game_ctrl.say_to(player, f"§e成功向 {target_player} 转账 {amount} 金币")
            self.game_ctrl.say_to(target_player, f"§e{player} 向你转账了 {amount} 金币")
        elif amount > self.max_transfer_amount:
            self.game_ctrl.say_to(player, f"§c你转账的金额过大，一次最多转账§c{self.max_transfer_amount}")
        elif amount <= 0:
            self.game_ctrl.say_to(player, "§c你转账的金额不能为负数或零")
        else:
            self.game_ctrl.say_to(player, "§c你吗，你没钱还想转账？")

    # 显示个人信息
    def show_me(self, player: str, args: list[str]):
        player_info = f'''
        §e玩家昵称: §b{player},
        §e星梦币: §b{game_utils.getScore(self.currency_scoreboard, player)},
        §e在线时间: §b{game_utils.getScore(self.online_time_scoreboard, player)}
        '''
        self.game_ctrl.say_to(player, f"{player_info}")

    # 传送回主城
    def send_to_hub(self, player: str, args: list[str]):
        x, y, z = self.hub_coords
        self.game_ctrl.sendcmd(f"/execute as {player} at @s in overworld run tp @s {x} {y} {z}")
        self.game_ctrl.say_to(player, f"§e你已被传送回主城！")

    # 清除服务器掉落物
    def clear_drops(self, player: str, args: list[str]):
        self.game_ctrl.sendcmd("/kill @e[type=item]")
        self.game_ctrl.say_to(player, "§e服务器掉落物已清除")


    # 修改时间
    def change_time(self, player: str, args: list[str]):
        time_value = args[0]
        self.game_ctrl.sendcmd(f"/time set {time_value}")
        self.game_ctrl.say_to("@a", f"§e{player} 修改了时间为 {time_value}")

    # 自己杀自己~
    def kill_self(self, player: str, args: list[str]):
        self.game_ctrl.sendcmd(f"/kill {player}")
        self.game_ctrl.say_to(player, "§e你已被杀死")

    # 更换生存模式
    def change_to_survival(self, player: str, args: list[str]):
        self.game_ctrl.sendcmd(f"/gamemode survival {player}")
        self.game_ctrl.say_to(player, "§e你已切换到生存模式")

    # 传送到商店
    def teleport_to_shop(self, player: str, args: list[str]):
        x, y, z = self.shop_coords
        self.game_ctrl.sendcmd(f"/execute as {player} at @s in overworld run tp @s {x} {y} {z}")
        self.game_ctrl.say_to(player, f"§e你已被传送到商店！")


    # 与AI对话
    def handle_ai_command(self, player: str, args: list[str]):
        text = " ".join(args)
        response = askai(text)
        self.game_ctrl.sendcmd(f"/tellraw @a {{\"rawtext\":[{{\"text\":\"§e{player} 与 AI 对话: §b{text}§e\nAI 回答: §b{response}\"}}]}}")

entry = plugin_entry(ChatbarMenu, "聊天栏菜单")

'''
为了能让代码跑起来，这里放一个佛像，运行不了多拜一拜
                     _ooOoo_
                    o8888888o
                    88" . "88
                    (| -_- |)
                     O\ = /O
                 ____/`---'\____
               .   ' \\| |// `.
                / \\||| : |||// \
              / _||||| -:- |||||- \
                | | \\\ - /// | |
              | \_| ''\---/'' | |
               \ .-\__ `-` ___/-. /
            ___`. .' /--.--\ `. . __
         ."" '< `.___\_<|>_/___.' >'"".
        | | : `- \`.;`\ _ /`;.`/ - ` : | |
          \ \ `-. \_ __\ /__ _/ .-` / /
  ======`-.____`-.___\_____/___.-`____.-'======
                     `=---='
'''
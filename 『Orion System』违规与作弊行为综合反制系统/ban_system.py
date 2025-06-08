"""『Orion System 猎户座』封禁面板"""

from tooldelta import Player, fmts, TYPE_CHECKING
from functools import partial
from typing import Literal, Any
import re
import os

from ban_utils import OrionUtils

# 仅类型检查用
if TYPE_CHECKING:
    from __init__ import Orion_System


class BanSystem:
    """封禁系统操作面板"""

    # We are now waiting for CQHTTP support !!!!!

    BAN_MENU = {
        "Exit": {
            "Info": "§a❀ §b输入 §c. §b退出",
            "Success": "§a❀ 已退出封禁系统",
        },
        "Error": {
            "TimeoutError": "§c❀ 回复超时！ 已退出封禁系统",
            "InputError": "§c❀ 您的输入有误",
        },
        "TopMenu": """
§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§d❐§f 『§6Orion System §d猎户座§f』 §b封禁§e管§a理 §d系统
§l§b[ §e1§b ] §r§e根据在线玩家名称和xuid封禁
§l§b[ §e2§b ] §r§e根据历史进服玩家名称和xuid封禁
§l§b[ §e3§b ] §r§e根据历史进服玩家设备号封禁
§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§a❀ §b输入 §e[1-3]§b 之间的数字以选择 封禁模式""",
        "Xuid": {
            "Menu_1": """
§a❀ 已发现以下xuid和玩家名称~
§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§b[ §a序号§b ] §r§axuid - 玩家名称""",
            "Menu_2": "§l§b[ §e{}§b ] §r§e{} - {}",
            "Menu_3": """§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§a[ §e-§a ] §b上页§r§f▶ §7{}/{} §f◀§l§b下页 §a[ §e+ §a]
§a❀ §b输入 §e[{}-{}]§b 之间的数字以选择 封禁的xuid和玩家名称
§a❀ §b输入 §exuid、玩家名称或玩家部分名称 可尝试搜索
§a❀ §b如果您要搜索的玩家名称为数字 §e请在输入文本最前面添加反斜杠\\""",
            "Error": {
                "WhitelistError": "§6❀ 发现 xuid - {} (玩家名称 - {}) 位于反制白名单内，请先将其移出白名单！",
                "ForeverError": "§6❀ xuid - {} (玩家名称 - {}) 已经为永久封禁，无需重复封禁",
                "NotOnlineError": "§c❀ 未发现任何在线玩家",
                "NotQueryError": "§c❀ 未查询到任何xuid记录",
                "QueryFailError": "§c❀ 查询xuid记录失败，原因：{}",
                "NotFoundError": "§c❀ 找不到您输入的xuid或玩家名称",
            },
            "Success": {
                "SearchSuccess": "\n§a❀ 您选择了 xuid - {} (玩家名称 - {})",
                "BanSuccess": {
                    "Player": "由于{}，您被系统封禁至：{}",
                    "Message": "\n§a❀ 封禁成功：已封禁 xuid - {} (玩家名称 - {}) 至 {}",
                    "TerminalFromGame": "\n§a❀ [来自游戏内 {} 的消息] 封禁成功：已封禁 xuid - {} (玩家名称 - {}) 至 {}",
                },
            },
        },
        "DeviceID": {
            "Menu_1": """
§a❀ 已发现以下设备号~
§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§b[ §a序号§b ] §r§a设备号 - {xuid: [玩家名称与改名记录]}""",
            "Menu_2": "§l§b[ §e{}§b ] §r§e{} - {}",
            "Menu_3": """§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§a[ §e-§a ] §b上页§r§f▶ §7{}/{} §f◀§l§b下页 §a[ §e+ §a]
§a❀ §b输入 §e[{}-{}]§b 之间的数字以选择 封禁的设备号
§a❀ §b输入 §e设备号、玩家名称或玩家部分名称 可尝试搜索
§a❀ §b如果您要搜索的玩家名称为数字 §e请在输入文本最前面添加反斜杠\\""",
            "Error": {
                "ForeverError": "§6❀ 设备号 - {} (使用此设备加入游戏的玩家xuid和名称记录 - {}) 已经为永久封禁，无需重复封禁",
                "NotQueryError": "§c❀ 未查询到任何设备号记录",
                "QueryFailError": "§c❀ 查询设备号记录失败，原因：{}",
                "NotFoundError": "§c❀ 找不到您输入的设备号或玩家名称",
            },
            "Success": {
                "SearchSuccess": "\n§a❀ 您选择了 设备号 - {} (使用此设备加入游戏的玩家xuid和名称记录 - {})",
                "BanSuccess": {
                    "Player": "由于{}，您被系统封禁至：{}",
                    "Message": "\n§a❀ 封禁成功：已封禁 设备号 - {} (使用此设备加入游戏的玩家xuid和名称记录 - {}) 至 {}",
                    "TerminalFromGame": "\n§a❀ [来自游戏内 {} 的消息] 封禁成功：已封禁 设备号 - {} (使用此设备加入游戏的玩家xuid和名称记录 - {}) 至 {}",
                },
            },
        },
        "Page": {
            "Info": """§a❀ §b输入 §d- §e转到上一页
§a❀ §b输入 §d+ §e转到下一页
§a❀ §b输入 §d正整数+页 §e转到对应页""",
            "Error": {
                "FristPageError": "§6❀ 已经是第一页啦~",
                "FinalPageError": "§6❀ 已经是最后一页啦~",
                "PageNotFoundError": "§6❀ 不存在第{}页！请重新输入！",
            },
        },
        "Time": {
            "Info": """§a❀ §b请按照以下格式输入封禁时间：
§6 · §f封禁时间 = -1  §e永久封禁
§6 · §f封禁时间 = 正整数  §e封禁<正整数>秒
§6 · §f封禁时间 = 0年0月5日6时7分8秒  §e封禁对应的时间""",
            "Error": "§c❀ 您输入的封禁时间有误",
            "Success": "\n§a❀ 您输入的封禁时间为 {}秒",
        },
        "Reason": {
            "Info": "§a❀ §b请输入封禁原因：",
            "DefaultReason": "游戏内违规行为",
        },
    }

    UNBAN_MENU = {
        "Exit": {
            "Info": "§a❀ §b输入 §c. §b退出",
            "Success": "§a❀ 已退出解封系统",
        },
        "Error": {
            "TimeoutError": "§c❀ 回复超时！ 已退出解封系统",
            "InputError": "§c❀ 您的输入有误",
        },
        "TopMenu": """
§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§d❐§f 『§6Orion System §d猎户座§f』 §b解封§e管§a理 §d系统
§l§b[ §e1§b ] §r§e根据玩家名称和xuid解封
§l§b[ §e2§b ] §r§e根据设备号解封
§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§a❀ §b输入 §e[1-2]§b 之间的数字以选择 解封模式""",
        "Xuid": {
            "Menu_1": """
§a❀ 已发现以下xuid和玩家名称~
§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§b[ §a序号§b ] §r§axuid - 玩家名称""",
            "Menu_2": "§l§b[ §e{}§b ] §r§e{} - {}",
            "Menu_3": """§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§a[ §e-§a ] §b上页§r§f▶ §7{}/{} §f◀§l§b下页 §a[ §e+ §a]
§a❀ §b输入 §e[{}-{}]§b 之间的数字以选择 解封的xuid和玩家名称
§a❀ §b输入 §exuid、玩家名称或玩家部分名称 可尝试搜索
§a❀ §b如果您要搜索的玩家名称为数字 §e请在输入文本最前面添加反斜杠\\""",
            "Error": {
                "NotBanError": "§6❀ 目前没有正在封禁的xuid和玩家名称",
                "NotFoundError": "§c❀ 找不到您输入的xuid或玩家名称",
            },
            "UnbanSuccess": {
                "Message": "\n§a❀ 解封成功: 已解封 xuid - {} (玩家名称 - {})",
                "TerminalFromGame": "\n§a❀ [来自游戏内 {} 的消息] 解封成功: 已解封 xuid - {} (玩家名称 - {})",
            },
        },
        "DeviceID": {
            "Menu_1": """
§a❀ 已发现以下设备号~
§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§b[ §a序号§b ] §r§a设备号 - {xuid: [玩家名称与改名记录]}""",
            "Menu_2": "§l§b[ §e{}§b ] §r§e{} - {}",
            "Menu_3": """§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§a[ §e-§a ] §b上页§r§f▶ §7{}/{} §f◀§l§b下页 §a[ §e+ §a]
§a❀ §b输入 §e[{}-{}]§b 之间的数字以选择 解封的设备号
§a❀ §b输入 §e设备号、玩家名称或玩家部分名称 可尝试搜索
§a❀ §b如果您要搜索的玩家名称为数字 §e请在输入文本最前面添加反斜杠\\""",
            "Error": {
                "NotQueryError": "§c❀ 未查询到任何设备号记录",
                "QueryFailError": "§c❀ 查询设备号记录失败，原因：{}",
                "NotBanError": "§6❀ 目前没有正在封禁的设备号",
                "NotFoundError": "§c❀ 找不到您输入的设备号或玩家名称",
            },
            "UnbanSuccess": {
                "Message": "\n§a❀ 解封成功: 已解封 设备号 - {} (使用此设备加入游戏的玩家xuid和名称记录 - {})",
                "TerminalFromGame": "\n§a❀ [来自游戏内 {} 的消息] 解封成功: 已解封 设备号 - {} (使用此设备加入游戏的玩家xuid和名称记录 - {})",
            },
        },
        "Page": {
            "Info": """§a❀ §b输入 §d- §e转到上一页
§a❀ §b输入 §d+ §e转到下一页
§a❀ §b输入 §d正整数+页 §e转到对应页""",
            "Error": {
                "FristPageError": "§6❀ 已经是第一页啦~",
                "FinalPageError": "§6❀ 已经是最后一页啦~",
                "PageNotFoundError": "§6❀ 不存在第{}页！请重新输入！",
            },
        },
    }

    def __init__(self, plugin: "Orion_System") -> None:
        """
        初始化封禁面板
        Args:
            plugin: 插件实例
        """
        self.plugin = plugin
        self.cfg = plugin.config_mgr
        self.utils = plugin.utils
        self.data_path = plugin.data_path
        self.lock_ban_xuid = plugin.lock_ban_xuid
        self.lock_ban_device_id = plugin.lock_ban_device_id
        self.sendwocmd = plugin.game_ctrl.sendwocmd

    def entry(self) -> None:
        """封禁面板的入口，注册控制台和游戏内封禁触发词"""
        # 在控制台菜单注册封禁/解封系统触发词
        if self.cfg.is_terminal_ban_system:
            self.plugin.frame.add_console_cmd_trigger(
                self.cfg.terminal_ban_trigger_words,
                [],
                "封禁玩家-来自<『Orion System』违规与作弊行为综合反制系统>",
                self.ban_player_by_terminal,
            )
            self.plugin.frame.add_console_cmd_trigger(
                self.cfg.terminal_unban_trigger_words,
                [],
                "解封玩家-来自<『Orion System』违规与作弊行为综合反制系统>",
                self.unban_player_by_terminal,
            )

        # 在游戏内聊天栏菜单注册封禁/解封系统触发词
        if self.cfg.is_game_ban_system:
            self.plugin.chatbar.add_new_trigger(
                self.cfg.game_ban_trigger_words,
                [],
                "封禁玩家-来自<『Orion System』违规与作弊行为综合反制系统>",
                self.ban_player_by_game,
                op_only=True,
            )
            self.plugin.chatbar.add_new_trigger(
                self.cfg.game_unban_trigger_words,
                [],
                "解封玩家-来自<『Orion System』违规与作弊行为综合反制系统>",
                self.unban_player_by_game,
                op_only=True,
            )

    def ban_player_by_terminal(self, _: tuple) -> None:
        """
        控制台玩家封禁-回调函数数据转移
        Args:
            _ (tuple): 触发词后续的文本切片，本插件不需要使用
        """
        self.ban(mode=1)

    def unban_player_by_terminal(self, _: tuple) -> None:
        """
        控制台玩家解封-回调函数数据转移
        Args:
            _ (tuple): 触发词后续的文本切片，本插件不需要使用
        """
        self.unban(mode=1)

    def ban_player_by_game(self, player: Player, _: tuple) -> None:
        """
        游戏内玩家封禁-回调函数数据转移
        Args:
            player (Player): 触发者的玩家对象
            _ (tuple): 触发词后续的文本切片，本插件不需要使用
        """
        self.ban(mode=2, OBJ=player)

    def unban_player_by_game(self, player: Player, _: tuple) -> None:
        """
        游戏内玩家解封-回调函数数据转移
        Args:
            player (Player): 触发者的玩家对象
            _ (tuple): 触发词后续的文本切片，本插件不需要使用
        """
        self.unban(mode=2, OBJ=player)

    @staticmethod
    def print_U(message: str, mode: int, OBJ: Player | Any | None) -> None:
        r"""
        统一化输出方法，使得控制台菜单/游戏内聊天栏菜单使用同一套封禁系统代码
        Args:
            message (str): 输出文本
            mode (int): 输出模式，包括:
                - mode = 1: 控制台输出
                - mode = 2: 游戏内输出
                - mode = 3: CQHTTP输出(waiting for CQHTTP support now !!!!!)
                - mode = N: ???
            OBJ (Player | Any | None): 部分输出方法所需要的对象属性(如游戏内输出需要玩家对象)
        Warning:
            如果message最前面有NN，将不会输出任何文本
            如果message包括换行符或\n，将分行输出文本(绕过可能的网易屏蔽词)
        """
        message = OrionUtils.text_format(message)
        if message not in (None, ""):
            for line in message.split("\n"):
                if mode == 1:
                    fmts.print_inf(line)
                elif mode == 2:
                    OBJ.show(line)

    def input_U(self, message: str, mode: int, OBJ: Player | Any | None) -> str | None:
        """
        统一化输入方法，使得控制台菜单/游戏内聊天栏菜单使用同一套封禁系统代码
        Args:
            message (str): 输出文本
            mode (int): 输入模式，包括:
                - mode = 1: 控制台输入
                - mode = 2: 游戏内输入
                - mode = 3: CQHTTP输入(waiting for CQHTTP support now !!!!!)
                - mode = N: ???
            OBJ (Player | Any | None): 部分输入方法所需要的对象属性(如游戏内输入需要玩家对象)
        Returns:
            input_message (str | None): 输入文本，如果等待输入超时，将返回None
        """
        message = OrionUtils.text_format(message)
        if message in (None, ""):
            message = "请输入："
        if mode == 1:
            return input(fmts.fmt_info(message))
        if mode == 2:
            return OBJ.input(message, timeout=self.cfg.ban_player_by_game_timeout)

    def ban(self, mode: int, OBJ: Player | Any | None = None) -> None:
        """
        猎户座--封禁管理系统面板
        Args:
            mode (int): 输入模式，包括:
                - mode = 1: 控制台输入
                - mode = 2: 游戏内输入
            OBJ (Player | Any | None): 部分输入方法所需要的对象属性(如游戏内输入需要玩家对象)
        """
        # 通过functools.partial创建预绑定mode和OBJ属性的函数
        self.print = partial(self.print_U, mode=mode, OBJ=OBJ)
        self.input = partial(self.input_U, mode=mode, OBJ=OBJ)
        BAN_MENU = self.BAN_MENU

        self.print(BAN_MENU["TopMenu"])
        choice = self.input(BAN_MENU["Exit"]["Info"])

        # 如果输入超时(返回None值)，退出系统
        if choice is None:
            self.print(BAN_MENU["Error"]["TimeoutError"])

        # 如果输入.或。，退出系统
        elif choice in (".", "。"):
            self.print(BAN_MENU["Exit"]["Success"])

        # 选择1: 封禁--在线xuid和玩家名称
        elif choice == "1":
            allplayers = self.plugin.game_ctrl.allplayers.copy()
            xuid_data = {}
            for player in allplayers:
                xuid_data[self.plugin.xuid_getter.get_xuid_by_name(player)] = player
            if xuid_data == {}:
                self.print(BAN_MENU["Xuid"]["Error"]["NotOnlineError"])
                return
            (ban_xuid, ban_name) = self.get_ID(xuid_data, "Xuid", 1, mode)
            if ban_xuid is None or ban_name is None:
                return
            # 如果玩家位于白名单内，不能执行封禁
            if ban_name in self.cfg.whitelist:
                self.print(
                    BAN_MENU["Xuid"]["Error"]["WhitelistError"].format(
                        ban_xuid, ban_name
                    )
                )
                return
            # 搜索xuid和玩家名称成功
            self.print(
                BAN_MENU["Xuid"]["Success"]["SearchSuccess"].format(ban_xuid, ban_name)
            )
            ban_time = self.get_time()
            if ban_time is None:
                return
            # 输入封禁时间成功
            self.print(BAN_MENU["Time"]["Success"].format(ban_time))
            ban_reason = self.get_reason()
            if ban_reason is None:
                return
            (timestamp_now, date_now) = OrionUtils.now()
            path = f"{self.data_path}/{self.cfg.xuid_dir}/{ban_xuid}.json"
            with self.lock_ban_xuid:
                ban_data = OrionUtils.disk_read(path)
                (timestamp_end, date_end) = OrionUtils.calculate_ban_end_time(
                    ban_data, ban_time, timestamp_now
                )
                if timestamp_end is False or date_end is False:
                    self.print(
                        BAN_MENU["Xuid"]["Error"]["ForeverError"].format(
                            ban_xuid, ban_name
                        )
                    )
                    return
                OrionUtils.disk_write(
                    path,
                    {
                        "xuid": ban_xuid,
                        "name": ban_name,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                )
            info = BAN_MENU["Xuid"]["Success"]["BanSuccess"]
            self.utils.kick(ban_name, info["Player"].format(ban_reason, date_end))
            self.print(info["Message"].format(ban_xuid, ban_name, date_end))
            if mode == 2:
                fmts.print_inf(
                    info["TerminalFromGame"].format(
                        OBJ.name, ban_xuid, ban_name, date_end
                    )
                )

        # 选择2: 封禁--历史全部xuid和玩家名称
        elif choice == "2":
            path_xuid = "插件数据文件/前置-玩家XUID获取/xuids.json"
            try:
                with self.lock_ban_xuid:
                    xuid_data = OrionUtils.disk_read_need_exists(path_xuid)
            except FileNotFoundError:
                self.print(BAN_MENU["Xuid"]["Error"]["NotQueryError"])
                return
            except Exception as error:
                self.print(BAN_MENU["Xuid"]["Error"]["QueryFailError"].format(error))
                return
            if xuid_data == {}:
                self.print(BAN_MENU["Xuid"]["Error"]["NotQueryError"])
                return
            (ban_xuid, ban_name) = self.get_ID(xuid_data, "Xuid", 1, mode)
            if ban_xuid is None or ban_name is None:
                return
            # 如果玩家位于白名单内，不能执行封禁
            if ban_name in self.cfg.whitelist:
                self.print(
                    BAN_MENU["Xuid"]["Error"]["WhitelistError"].format(
                        ban_xuid, ban_name
                    )
                )
                return
            # 搜索xuid和玩家名称成功
            self.print(
                BAN_MENU["Xuid"]["Success"]["SearchSuccess"].format(ban_xuid, ban_name)
            )
            ban_time = self.get_time()
            if ban_time is None:
                return
            # 输入封禁时间成功
            self.print(BAN_MENU["Time"]["Success"].format(ban_time))
            ban_reason = self.get_reason()
            if ban_reason is None:
                return
            (timestamp_now, date_now) = OrionUtils.now()
            path = f"{self.data_path}/{self.cfg.xuid_dir}/{ban_xuid}.json"
            with self.lock_ban_xuid:
                ban_data = OrionUtils.disk_read(path)
                (timestamp_end, date_end) = OrionUtils.calculate_ban_end_time(
                    ban_data, ban_time, timestamp_now
                )
                if timestamp_end is False or date_end is False:
                    self.print(
                        BAN_MENU["Xuid"]["Error"]["ForeverError"].format(
                            ban_xuid, ban_name
                        )
                    )
                    return
                OrionUtils.disk_write(
                    path,
                    {
                        "xuid": ban_xuid,
                        "name": ban_name,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                )
            info = BAN_MENU["Xuid"]["Success"]["BanSuccess"]
            self.utils.kick(ban_name, info["Player"].format(ban_reason, date_end))
            self.print(info["Message"].format(ban_xuid, ban_name, date_end))
            if mode == 2:
                fmts.print_inf(
                    info["TerminalFromGame"].format(
                        OBJ.name, ban_xuid, ban_name, date_end
                    )
                )

        # 选择3: 封禁--历史全部设备号
        elif choice == "3":
            path_device_id = f"{self.data_path}/{self.cfg.player_data_file}"
            try:
                with self.lock_ban_device_id:
                    device_id_data = OrionUtils.disk_read_need_exists(path_device_id)
            except FileNotFoundError:
                self.print(BAN_MENU["DeviceID"]["Error"]["NotQueryError"])
                return
            except Exception as error:
                self.print(
                    BAN_MENU["DeviceID"]["Error"]["QueryFailError"].format(error)
                )
                return

            if device_id_data == {}:
                self.print(BAN_MENU["DeviceID"]["Error"]["NotQueryError"])
                return
            (ban_device_id, ban_xuid_history_name) = self.get_ID(
                device_id_data, "DeviceID", 1, mode
            )
            if ban_device_id is None or ban_xuid_history_name is None:
                return
            # 搜索设备号成功
            self.print(
                BAN_MENU["DeviceID"]["Success"]["SearchSuccess"].format(
                    ban_device_id, ban_xuid_history_name
                )
            )
            # 收集设备号对应的全部xuid，以便踢出
            ban_xuid_list = []
            for xuid in ban_xuid_history_name.keys():
                ban_xuid_list.append(xuid)
            ban_time = self.get_time()
            if ban_time is None:
                return
            # 输入封禁时间成功
            self.print(BAN_MENU["Time"]["Success"].format(ban_time))
            ban_reason = self.get_reason()
            if ban_reason is None:
                return
            (timestamp_now, date_now) = OrionUtils.now()
            path = f"{self.data_path}/{self.cfg.device_id_dir}/{ban_device_id}.json"
            with self.lock_ban_device_id:
                ban_data = OrionUtils.disk_read(path)
                (timestamp_end, date_end) = OrionUtils.calculate_ban_end_time(
                    ban_data, ban_time, timestamp_now
                )
                if timestamp_end is False or date_end is False:
                    self.print(
                        BAN_MENU["DeviceID"]["Error"]["ForeverError"].format(
                            ban_device_id, ban_xuid_history_name
                        )
                    )
                    return
                OrionUtils.disk_write(
                    path,
                    {
                        "device_id": ban_device_id,
                        "xuid_and_player": ban_xuid_history_name,
                        "ban_start_real_time": date_now,
                        "ban_start_timestamp": timestamp_now,
                        "ban_end_real_time": date_end,
                        "ban_end_timestamp": timestamp_end,
                        "ban_reason": ban_reason,
                    },
                )
            info = BAN_MENU["DeviceID"]["Success"]["BanSuccess"]
            for ban_xuid in ban_xuid_list:
                self.utils.kick(ban_xuid, info["Player"].format(ban_reason, date_end))
            self.print(
                info["Message"].format(ban_device_id, ban_xuid_history_name, date_end)
            )
            if mode == 2:
                fmts.print_inf(
                    info["TerminalFromGame"].format(
                        OBJ.name, ban_device_id, ban_xuid_history_name, date_end
                    )
                )

        else:
            self.print(BAN_MENU["Error"]["InputError"])

    def unban(self, mode: int, OBJ: Player | Any | None = None) -> None:
        """
        猎户座--解封管理系统面板
        Args:
            mode (int): 输入模式，包括:
                - mode = 1: 控制台输入
                - mode = 2: 游戏内输入
            OBJ (Player | Any | None): 部分输入方法所需要的对象属性(如游戏内输入需要玩家对象)
        """
        # 通过functools.partial创建预绑定mode和OBJ属性的函数
        self.print = partial(self.print_U, mode=mode, OBJ=OBJ)
        self.input = partial(self.input_U, mode=mode, OBJ=OBJ)
        UNBAN_MENU = self.UNBAN_MENU

        self.print(UNBAN_MENU["TopMenu"])
        choice = self.input(UNBAN_MENU["Exit"]["Info"])

        # 如果输入超时(返回None值)，退出系统
        if choice is None:
            self.print(UNBAN_MENU["Error"]["TimeoutError"])

        # 如果输入.或。，退出系统
        elif choice in (".", "。"):
            self.print(UNBAN_MENU["Exit"]["Success"])

        # 选择1: 解封--xuid和玩家名称
        elif choice == "1":
            all_xuid_json = os.listdir(f"{self.data_path}/{self.cfg.xuid_dir}")
            xuid_data = {}
            for xuid_json in all_xuid_json:
                xuid = xuid_json.replace(".json", "")
                try:
                    xuid_data[xuid] = self.plugin.xuid_getter.get_name_by_xuid(
                        xuid, True
                    )
                except ValueError:
                    continue
            if xuid_data == {}:
                self.print(UNBAN_MENU["Xuid"]["Error"]["NotBanError"])
                return
            (unban_xuid, unban_name) = self.get_ID(xuid_data, "Xuid", 2, mode)
            if unban_xuid is None or unban_name is None:
                return
            os.remove(f"{self.data_path}/{self.cfg.xuid_dir}/{unban_xuid}.json")
            info = UNBAN_MENU["Xuid"]["UnbanSuccess"]
            self.print(info["Message"].format(unban_xuid, unban_name))
            if mode == 2:
                fmts.print_inf(
                    info["TerminalFromGame"].format(OBJ.name, unban_xuid, unban_name)
                )

        # 选择2: 解封--设备号
        elif choice == "2":
            path_device_id = f"{self.data_path}/{self.cfg.player_data_file}"
            try:
                with self.lock_ban_device_id:
                    player_data = OrionUtils.disk_read_need_exists(path_device_id)
            except FileNotFoundError:
                self.print(UNBAN_MENU["DeviceID"]["Error"]["NotQueryError"])
                return
            except Exception as error:
                self.print(
                    UNBAN_MENU["DeviceID"]["Error"]["QueryFailError"].format(error)
                )
                return
            if player_data == {}:
                self.print(UNBAN_MENU["DeviceID"]["Error"]["NotQueryError"])
                return

            all_device_id_json = os.listdir(
                f"{self.data_path}/{self.cfg.device_id_dir}"
            )
            device_id_data = {}
            for device_id_json in all_device_id_json:
                device_id = device_id_json.replace(".json", "")
                try:
                    device_id_data[device_id] = player_data.get(device_id, "")
                except ValueError:
                    continue
            if device_id_data == {}:
                self.print(UNBAN_MENU["DeviceID"]["Error"]["NotBanError"])
                return
            (unban_device_id, unban_xuid_history_name) = self.get_ID(
                device_id_data, "DeviceID", 2, mode
            )
            if unban_device_id is None or unban_xuid_history_name is None:
                return
            os.remove(
                f"{self.data_path}/{self.cfg.device_id_dir}/{unban_device_id}.json"
            )
            info = UNBAN_MENU["DeviceID"]["UnbanSuccess"]
            self.print(info["Message"].format(unban_device_id, unban_xuid_history_name))
            if mode == 2:
                fmts.print_inf(
                    info["TerminalFromGame"].format(
                        OBJ.name, unban_device_id, unban_xuid_history_name
                    )
                )

        else:
            self.print(UNBAN_MENU["Error"]["InputError"])

    def get_ID(
        self,
        ID_dict: dict[str, str | dict[str, list[str]]],
        ID_type: str,
        ban_type: int,
        mode: int,
    ) -> tuple[str, str | dict[str, list[str]]] | tuple[None, None]:
        """
        获取玩家标识数据
        Args:
            ID_dict (dict[str, str | dict[str, list[str]]]): 全部玩家或在线玩家的标识数据:
                - 若为xuid，则字典格式为 {xuid: 玩家名称}
                - 若为device_id，则字典格式为 {device_id: {xuid: [玩家全部历史名称]}}
            ID_type (str): 玩家标识数据类型，包括:
                - "Xuid": 玩家唯一标识符
                - "DeviceID": 玩家设备号
            ban_type (int): 执行类型，包括:
                - 1: 封禁
                - 2: 解封
            mode (int): 输出模式，包括:
                - 1: 控制台输出
                - 2: 游戏内输出
        Returns:
            tuple: 包含最终搜索选中的封禁ID和封禁玩家数据的元组
                - str: 封禁ID
                - str | dict[str, list[str]]: 封禁玩家数据:
                    - 若为xuid，则数据为玩家名称
                    - 若为device_id，则数据为{xuid: [玩家全部历史名称]}
        """
        if ban_type == 1:
            MENU = self.BAN_MENU
        elif ban_type == 2:
            MENU = self.UNBAN_MENU
        if mode == 1:
            per_page = self.cfg.terminal_items_per_page
        elif mode == 2:
            per_page = self.cfg.game_items_per_page

        user_search = ""
        page = 1
        while True:
            # 移除输入文本中的反斜杠\，反斜杠用于绕过原有匹配项，比如玩家名称为<纯数字>或者<数字+页>时的搜索
            user_search = user_search.replace("\\", "")
            # 收集匹配的ID数据
            matched_ID_dict = {}
            # 收集匹配的已染色ID数据(用于显示给用户，如用户输入s将会把所有玩家名称中的s染成蓝色，其余部分为黄色)
            colored_matched_ID_dict = {}
            if ID_type == "Xuid":
                for xuid, name in ID_dict.items():
                    if user_search in name:
                        matched_ID_dict[xuid] = name
                        colored_matched_ID_dict[xuid] = name.replace(
                            user_search, f"§b{user_search}§e"
                        )
            elif ID_type == "DeviceID":
                for device_id, player_data in ID_dict.items():
                    colored_data = "{"
                    for xuid, name_list in player_data.items():
                        for name in name_list:
                            if user_search in name:
                                matched_ID_dict[device_id] = player_data
                                # 只对玩家名称中的字符串进行染色，不染xuid，所以把玩家名称列表拿出来单独替换，并重新组装成字符串
                                s = str(name_list).replace(
                                    user_search, f"§b{user_search}§e"
                                )
                                colored_data = colored_data + f"'{xuid}': {s}, "
                                colored_data = colored_data[:-2] + "}"
                                colored_matched_ID_dict[device_id] = colored_data
                                break

            # 如果根据用户输入内容，无法搜索到任何匹配项，退出系统
            if matched_ID_dict == {}:
                self.print(MENU[ID_type]["Error"]["NotFoundError"])
                return (None, None)

            # 获取面板的页码标识和翻页相关信息
            (total_pages, start_index, end_index) = OrionUtils.paginate(
                len(matched_ID_dict), per_page, page
            )
            self.print(MENU[ID_type]["Menu_1"])
            for i in range(start_index, end_index + 1):
                self.print(
                    MENU[ID_type]["Menu_2"].format(
                        i,
                        list(colored_matched_ID_dict.keys())[i - 1],
                        list(colored_matched_ID_dict.values())[i - 1],
                    )
                )
            self.print(
                MENU[ID_type]["Menu_3"].format(
                    page, total_pages, start_index, end_index
                )
            )
            self.print(MENU["Page"]["Info"])
            user_input = self.input(MENU["Exit"]["Info"])
            # 如果输入超时(返回None值)，退出系统
            if user_input is None:
                self.print(MENU["Error"]["TimeoutError"])
                return (None, None)
            # 如果输入.或。，退出系统
            if user_input in (".", "。"):
                self.print(MENU["Exit"]["Success"])
                return (None, None)
            # 如果输入-，尝试翻到上一页
            if user_input == "-":
                if page > 1:
                    page -= 1
                else:
                    self.print(MENU["Page"]["Error"]["FristPageError"])
            # 如果输入+，尝试翻到下一页
            elif user_input == "+":
                if page < total_pages:
                    page += 1
                else:
                    self.print(MENU["Page"]["Error"]["FinalPageError"])
            # 如果输入<正整数+页>，尝试翻到对应页
            elif bool(re.fullmatch(r"^[1-9]\d*页$", user_input)):
                page_num = int(re.fullmatch(r"^([1-9]\d*)页$", user_input).group(1))
                if 1 <= page_num <= total_pages:
                    page = page_num
                else:
                    self.print(
                        MENU["Page"]["Error"]["PageNotFoundError"].format(page_num)
                    )
            else:
                try:
                    # 如果输入整数，尝试匹配对应索引的玩家
                    user_input = int(user_input)
                    if user_input in range(start_index, end_index + 1):
                        ban_ID = list(matched_ID_dict.keys())[user_input - 1]
                        ban_player_data = list(matched_ID_dict.values())[user_input - 1]
                        return (ban_ID, ban_player_data)
                    self.print(MENU["Error"]["InputError"])
                    return (None, None)
                except ValueError:
                    # 如果用户直接输入了ID，则直接获取相关信息
                    if user_input in ID_dict.keys():
                        ban_ID = user_input
                        ban_player_data = ID_dict[user_input]
                        return (ban_ID, ban_player_data)
                    # 如果用户输入不符合以上规则，根据用户输入重新开始搜索
                    user_search = user_input
                    page = 1

    def get_time(self) -> int | Literal["Forever"] | None:
        """
        获取封禁时间
        Returns:
            ban_time (int | Literal["Forever"] | None): 封禁时间(秒)或永久封禁
        """
        MENU = self.BAN_MENU
        self.print(MENU["Time"]["Info"])
        user_input = self.input(MENU["Exit"]["Info"])
        if user_input is None:
            self.print(MENU["Error"]["TimeoutError"])
            return None
        if user_input in (".", "。"):
            self.print(MENU["Exit"]["Success"])
            return None
        ban_time = OrionUtils.ban_time_format(user_input)
        if ban_time == 0:
            self.print(MENU["Time"]["Error"])
            return None
        return ban_time

    def get_reason(self) -> str | None:
        """
        获取封禁原因
        Returns:
            ban_reason (str | None): 封禁原因，若直接回车则返回默认封禁原因(游戏内违规行为)
        """
        MENU = self.BAN_MENU
        self.print(MENU["Reason"]["Info"])
        user_input = self.input(MENU["Exit"]["Info"]) or MENU["Reason"]["DefaultReason"]
        if user_input is None:
            self.print(MENU["Error"]["TimeoutError"])
            return None
        if user_input in (".", "。"):
            self.print(MENU["Exit"]["Success"])
            return None
        ban_reason = user_input
        return ban_reason

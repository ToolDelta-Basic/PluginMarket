"""『Orion System 猎户座』一些实用的插件方法"""

from tooldelta import fmts, game_utils, TYPE_CHECKING
from tooldelta.utils import tempjson
from typing import Literal, Any
import time
import re
import math

# 仅类型检查用
if TYPE_CHECKING:
    from .__init__ import Orion_System


class OrionUtils:
    """包括一些实用的插件方法"""

    def __init__(self, plugin: "Orion_System") -> None:
        """
        初始化插件实用方法
        Args:
            plugin: 插件实例
        """
        self.plugin = plugin
        self.cfg = plugin.config_mgr
        self.sendwocmd = plugin.game_ctrl.sendwocmd

    @staticmethod
    def disk_read(path: str) -> dict[Any, Any]:
        """
        快速磁盘读取操作
        Args:
            path (str): 磁盘路径
        Returns:
            data (dict[Any, Any]): 对应文件的数据
        """
        data = tempjson.load_and_read(
            path, need_file_exists=False, default={}, timeout=2
        )
        tempjson.unload_to_path(path)
        return data

    @staticmethod
    def disk_read_need_exists(path: str) -> dict[Any, Any]:
        """
        快速磁盘读取操作(需要文件存在)
        Args:
            path (str): 磁盘路径
        Returns:
            data (dict[Any, Any]): 对应文件的数据
        """
        data = tempjson.load_and_read(
            path, need_file_exists=True, default={}, timeout=2
        )
        tempjson.unload_to_path(path)
        return data

    @staticmethod
    def disk_write(path: str, data: dict[Any, Any]) -> None:
        """
        快速磁盘写入操作
        Args:
            path (str): 磁盘路径
            data (dict[Any, Any]): 需要写入的数据
        """
        tempjson.load_and_write(
            path,
            data,
            need_file_exists=False,
            timeout=2,
        )
        tempjson.flush(path)
        tempjson.unload_to_path(path)

    @staticmethod
    def now() -> tuple[int, str]:
        """
        获取当前时间戳和时间的元组
        Returns:
            tuple: 包含当前时间戳和时间的元组
                - int: 当前时间戳
                - str: 当前时间
        """
        timestamp_now = int(time.time())
        date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
        return (timestamp_now, date_now)

    def kick(self, player: str, reason: str) -> None:
        """
        执行kick命令并尝试隐藏踢出信息
        Args:
            player (str): 玩家名称或xuid
            reason (str): 踢出原因
        """
        if self.cfg.is_hide_ban_info:
            reason += self.cfg.hide_netease_banned_word
        self.sendwocmd(f'/kick "{player}" {reason}')

    def in_whitelist(self, name: str) -> bool:
        """
        判断玩家是否位于白名单内
        Args:
            name (str): 玩家名称
        Returns:
            in_whitelist_or_not (bool): 布尔值
        """
        try:
            if (name in self.cfg.whitelist) or (
                game_utils.is_op(name) and self.cfg.ban_ignore_op
            ):
                return True
        except (ValueError, KeyError):
            return False
        return False

    def clean_text(self, text: str) -> str:
        r"""
        移除字符串内的某些字符，包括:
            1. 删除空白字符，如空格、全角空格、换行符、制表符
            2. 删除§染色符号和后续那一个字符
            3. 将字符串中的全部英文字母转换为大写，抹去大小写的差异
            4. 删除配置中的特定字符，如!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~，。！？；：‘’“”【】（）《》、·—～…・丨
        Args:
            text (str): 字符串
        Returns:
            text (str): 修饰完毕后的字符串
        """
        if self.cfg.is_remove_space:
            text = re.sub(r"[\s\u3000]+", "", text, flags=re.UNICODE)
        pattern = re.compile(f"[{re.escape(self.cfg.other_remove)}]")
        text = pattern.sub("", text)
        if self.cfg.is_remove_double_s:
            text = re.sub(r"§.", "", text)
        if self.cfg.is_distinguish_upper_or_lower_on_chat is False:
            text = text.upper()
        return text

    def print_inf(
        self,
        info: dict[str, str | list[str]],
        info_args: tuple = (),
    ) -> None:
        r"""
        快速控制台/游戏内输出操作
        Args:
            info (dict[str, str | list[str]]): 输出文本的字典，来源于插件配置，一般包括<控制台>和<游戏内>输出
            info_args (tuple): 如果info的值中存在诸如{}的format占位符，则进行替换，若不填(即为空元组)则忽略
        Warning:
            如果info_args的元素数量小于format占位符(IndexError)，将不会输出任何文本
            如果info的值最前面有NN，将不会输出任何文本
            如果info的值包括换行符或\n，将分行输出文本(绕过可能的网易屏蔽词)
        """
        terminal = info.get("控制台")
        game = info.get("游戏内")
        if isinstance(terminal, str):
            terminal_info = OrionUtils.text_format(terminal, info_args)
            if terminal_info not in (None, ""):
                for line in terminal_info.split("\n"):
                    fmts.print_inf(line)
        if isinstance(game, list):
            game_info = OrionUtils.text_format(game[1], info_args)
            selector = game[0]
            if game_info not in (None, ""):
                for line in game_info.split("\n"):
                    self.plugin.game_ctrl.say_to(selector, line)

    @staticmethod
    def text_format(
        text: str,
        text_args: tuple = (),
    ) -> str:
        """
        格式化文本
        Args:
            text (str): 文本内容
            text_args (tuple): 如果text中存在诸如{}的format占位符，则进行替换，若不填(即为空元组)则忽略
        Returns:
            text (str): 格式化后的文本内容
        Warning:
            如果text_args的元素数量小于format占位符(IndexError)，返回空字符串
            如果text最前面有NN，返回空字符串
        """
        if text is None or text.startswith("NN") or text == "":
            return ""
        if text_args is None or text_args == ():
            return text
        try:
            return text.format(*text_args)
        except IndexError:
            return ""

    @staticmethod
    def ban_time_format(ban_time: str | int | None) -> int | Literal["Forever"]:
        """
        格式化玩家封禁时间
        将配置的封禁时间转换为整数或字符串"Forever"
        Args:
            ban_time (str | int): 封禁时间(来源于插件配置)
        Returns:
            ban_time (int | Literal["Forever"]): 封禁时间(秒)或者永久封禁
        """
        # ban_time in (-1, "-1", "Forever"):永久封禁
        if ban_time in (-1, "-1", "Forever"):
            return "Forever"

        # ban_time in (0, "0", "") or ban_time is None:仅踢出游戏，不作封禁，玩家可以立即重进
        if ban_time in (0, "0", "") or ban_time is None:
            return 0

        # isinstance(ban_time, int) and ban_time > 0:封禁玩家对应时间(单位:秒)
        if isinstance(ban_time, int) and ban_time > 0:
            return ban_time

        # isinstance(ban_time, str):封禁时间为字符串，将尝试进行转换
        if isinstance(ban_time, str):
            try:
                if int(ban_time) > 0:
                    return int(ban_time)
                fmts.print_inf("§6警告：无法解析您输入的封禁时间")
                return 0
            except ValueError:
                ban_time = ban_time.replace(" ", "")
                matches_time_units = re.findall(r"(\d+)(年|月|日|时|分|秒)", ban_time)
                if not matches_time_units:
                    fmts.print_inf(
                        f"§6警告：封禁时间({ban_time})中无法匹配到任何时间单位，合法的时间单位为(年|月|日|时|分|秒)"
                    )
                    return 0

                ban_time_after_matched = "".join(
                    f"{value}{unit}" for value, unit in matches_time_units
                )
                if ban_time_after_matched != ban_time:
                    fmts.print_inf(f"§6警告：封禁时间({ban_time})中存在无法解析的字符")
                    return 0

                time_units = {}
                for value_str, unit in matches_time_units:
                    value = int(value_str)
                    time_units[unit] = value

                years = time_units.get("年", 0)
                months = time_units.get("月", 0)
                days = time_units.get("日", 0)
                hours = time_units.get("时", 0)
                minutes = time_units.get("分", 0)
                seconds = time_units.get("秒", 0)

                total_days = years * 360 + months * 30 + days
                return (total_days * 86400) + hours * 3600 + minutes * 60 + seconds

        else:
            fmts.print_inf("§6警告：无法解析您输入的封禁时间")
            return 0

    @staticmethod
    def calculate_ban_end_time(
        ban_data: dict[Any, Any] | None,
        ban_time: int | Literal["Forever"],
        timestamp_now: int,
    ) -> (
        tuple[Literal["Forever"], Literal["Forever"]]
        | tuple[Literal[False], Literal[False]]
        | tuple[int, str]
    ):
        """
        计算玩家封禁结束时的时间戳和时间
        Args:
            ban_data (dict[Any, Any]): 封禁数据，可通过磁盘读取
            ban_time (int | Literal["Forever"]): 封禁时间(秒)或者永久封禁
            timestamp_now (int): 现在的时间戳(一般是UTC+8)
        Returns:
            tuple: 包含封禁结束时的时间戳和时间的元组
                - Literal["Forever"] | Literal[False] | int: 封禁结束时的时间戳(一般是UTC+8)
                - Literal["Forever"] | Literal[False] | str: 封禁结束时的时间(一般是UTC+8)
        """
        if ban_time == "Forever":
            return ("Forever", "Forever")
        if ban_data == {} or ban_data is None:
            pre_ban_timestamp = timestamp_now
        else:
            if ban_data["ban_end_timestamp"] == "Forever":
                return (False, False)
            if ban_data["ban_end_timestamp"] < timestamp_now:
                pre_ban_timestamp = timestamp_now
            else:
                pre_ban_timestamp = ban_data["ban_end_timestamp"]
        timestamp_end = pre_ban_timestamp + ban_time
        return (
            timestamp_end,
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_end)),
        )

    @staticmethod
    def fix_json(json_str: str) -> str:
        """
        修复数据包中的破损json字符串(在json字符串最后面补充缺失的括号)，一般是由于Text数据包的超长文本导致json字符串被截断
        Args:
            json_str (str): 需要修复的json字符串
        Returns:
            fixed_json_str (str): 修复完成的json字符串
        """
        # 统计未闭合的括号数量
        stack = []
        # 忽略json.loads后仍位于字符串内的文本，包括玩家直接输入的括号
        in_string = False
        # 忽略某些特殊符号，如\\n
        escape = False
        for char in json_str:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
            elif char == '"' and not escape:
                in_string = not in_string
            elif not in_string:
                if char in "{[":
                    stack.append(char)
                elif char in "}]":
                    if stack and (
                        (char == "}" and stack[-1] == "{")
                        or (char == "]" and stack[-1] == "[")
                    ):
                        stack.pop()
        # 添加缺失的闭合符号（按逆序）
        closing_map = {"{": "}", "[": "]"}
        missing_closures = "".join(closing_map[c] for c in reversed(stack))
        # 修复步骤：
        # 1. 先补全最后一个未闭合的字符串
        # 2. 然后添加计算出的缺失括号
        fixed_str = json_str.rstrip()
        # 检查最后一个字符串是否闭合
        quote_count = fixed_str.count('"')
        if quote_count % 2 != 0:
            fixed_str += '"'  # 补全字符串的闭合引号
        return fixed_str + missing_closures

    @staticmethod
    def paginate(total_len: int, per_page: int, page: int) -> tuple[int, int, int]:
        """
        计算页码相关信息，可用于封禁面板的页码标识和翻页
        Args:
            total_len (int): 项目总元素数量
            per_page (int): 每页显示几项
            page (int): 当前页码
        Returns:
            tuple: 包含总页码数、当前页码的起始索引、当前页码的结束索引的元组
                - int: 总页码数
                - int: 当前页码的起始索引
                - int: 当前页码的结束索引
        """
        total_pages = math.ceil(total_len / per_page)
        start_index = (page - 1) * per_page + 1
        end_index = min(start_index + per_page - 1, total_len)
        return (total_pages, start_index, end_index)

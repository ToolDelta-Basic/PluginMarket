from __future__ import annotations

import datetime
import importlib
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from tooldelta import Plugin, cfg, plugin_entry, utils
from tooldelta.constants import PacketIDS
from tooldelta.internal.launch_cli import FrameFateArk
from tooldelta.internal.types import Packet_CommandOutput


@dataclass
class _NtpState:
    """NTP 时间同步的模块级状态容器。

    用 dataclass 替代 global 语句修改模块级变量,
    既保持线程安全又符合静态检查规范。
    """

    time_offset: datetime.timedelta = datetime.timedelta(0)
    offset_lock: threading.Lock = field(default_factory=threading.Lock)


_ntp_state = _NtpState()


def _import_ntplib():
    """尝试在当前环境中导入 ntplib。

    导入成功会将 ntplib 注入 sys.modules 供后续使用。
    若首次导入失败,返回 None,由调用方决定是否安装。
    """
    if "ntplib" in sys.modules:
        return sys.modules["ntplib"]
    try:
        return importlib.import_module("ntplib")
    except ModuleNotFoundError:
        return None


ntplib = _import_ntplib()


OBJECTIVE_NAME = "公告"
MAX_COMMAND_RETRIES = 5
RETRY_DELAY_STEP_SECONDS = 3

NTP_SERVERS = [
    "ntp1.aliyun.com",
    "ntp2.aliyun.com",
    "ntp3.aliyun.com",
    "ntp.tencent.com",
    "cn.ntp.org.cn",
    "0.cn.pool.ntp.org",
]
NTP_TIMEOUT = 3

DEFAULT_CONFIG = {
    "标题": "公告栏",
    "刷新时间": 1,
    "TPS连续为0显示未知次数": 3,
    "公告栏内容": [
        "§7***************",
        "§7| §7{year}/{month}/{day} {week_day}",
        "§b| §7已运行{run_time}",
        "§b| §7{time_cn} §{time_color}{hour}:{minute}:{second}",
        "§b",
        "§b| §f延迟 : {tps}§r",
        "§b| §f在线 §r§7: §e{num_players}",
        "§r§7",
        "§r§7***************",
    ],
}

CONFIG_SCHEMA = cfg.auto_to_std(DEFAULT_CONFIG)
CONFIG_SCHEMA["刷新时间"] = cfg.PNumber
CONFIG_SCHEMA["TPS连续为0显示未知次数"] = cfg.PInt


def _get_beijing_timezone() -> datetime.tzinfo:
    """获取北京时区(UTC+8)对象。

    Returns:
        北京时区的 tzinfo 对象。
    """
    return datetime.timezone(datetime.timedelta(hours=8))


def _set_time_offset(offset: datetime.timedelta) -> None:
    """线程安全地写入 NTP 时间偏移量。

    Args:
        offset: NTP 服务器返回的时间偏移量。
    """
    with _ntp_state.offset_lock:
        _ntp_state.time_offset = offset


def _get_synced_now(tz: datetime.tzinfo) -> datetime.datetime:
    """获取经 NTP 校正后的当前时间(未同步则使用系统时间)。

    Args:
        tz: 目标时区。

    Returns:
        校正后的当前时间。
    """
    with _ntp_state.offset_lock:
        offset = _ntp_state.time_offset
    return datetime.datetime.now(tz) + offset


def _sleep_before_retry(retry_count: int) -> None:
    """根据重试次数递增地休眠一段时间,以便再次重试。

    Args:
        retry_count: 当前重试次数(从 1 开始)。
    """
    time.sleep(retry_count * RETRY_DELAY_STEP_SECONDS)


def _is_command_success(response: Packet_CommandOutput | None) -> bool:
    """判断命令是否执行成功。

    Args:
        response: 命令返回对象,可能为 None。

    Returns:
        True 表示执行成功,否则为 False。
    """
    return bool(response and response.SuccessCount != 0)


def get_tps_color(tps: float) -> str:
    """根据 TPS 值返回对应的 Minecraft 颜色代码。

    Args:
        tps: 当前 TPS 数值。

    Returns:
        Minecraft 颜色代码字符串。
    """
    if tps > 14:
        return "§a"
    if tps > 10:
        return "§6"
    return "§c"


def get_time_display(now_time: datetime.datetime) -> tuple[str, str]:
    """根据当前时间返回对应的时段名称与颜色代码。

    Args:
        now_time: 当前时间。

    Returns:
        (时段名称, 颜色代码) 的二元组。
    """
    hour = int(now_time.strftime("%H"))
    if 4 <= hour < 7:
        return "清晨", "9"
    if 7 <= hour < 11:
        return "早晨", "a"
    if 11 <= hour < 13:
        return "午时", "c"
    if 13 <= hour < 17:
        return "下午", "g"
    if 17 <= hour < 22:
        return "夜晚", "b"
    if 22 <= hour <= 23 or 0 <= hour < 4:
        return "深夜", "3"
    return "未知", "f"


def _iter_scoreboard_entries(texts: list[str]) -> Iterator[tuple[int, str]]:
    """以倒序索引方式遍历计分板文本,使其在侧边栏中按从上到下顺序显示。

    Args:
        texts: 公告栏文本列表(按从上到下顺序)。

    Yields:
        (score, text) 二元组,score 从大到小递减。
    """
    total = len(texts)
    for index, text in enumerate(texts):
        yield total - index - 1, text


class BetterAnnounce(Plugin):
    """ToolDelta 公告栏插件。

    通过计分板侧边栏显示包含时间、TPS、在线人数等信息的公告内容,
    支持租赁服、NeoForge/FrameFateArk 启动器的不同命令发送模式。
    时间在 on_preload 阶段异步通过 NTP 服务器同步一次,
    若同步失败则回退使用系统时间。
    """

    name = "公告栏"
    author = "Mono"
    version = (1, 2, 0)

    def __init__(self, frame):
        """初始化插件实例并注册生命周期监听器。

        Args:
            frame: ToolDelta 框架实例。
        """
        super().__init__(frame)
        self.config: dict[str, Any] = {}
        self.announce_templates: list[str] = []
        self.refresh_interval: int | float = 1
        self.title: str = "公告栏"
        self.zero_tps_unknown_count: int = 3
        self.tps_calculator: Any = None
        self.is_first_refresh: bool = True
        self.start_time: float = time.time()
        self.created_score_entries: dict[Any, str] = {}
        self.latest_texts: list[str] = []
        self.last_tps_value: float | None = None
        self.same_tps_value_count: int = 0
        self.is_rental_server: bool = False
        self.can_use_ai_command: bool = False

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPacket([PacketIDS.IDSetScore], self.on_set_score)

    def on_preload(self) -> None:
        """预加载阶段:读取配置、初始化状态、检测服务器环境与命令模式,
        并启动后台 NTP 时间同步线程。
        """
        self.config, _ = self.get_config_and_version(CONFIG_SCHEMA, DEFAULT_CONFIG)
        self.announce_templates = self.config["公告栏内容"]
        self.refresh_interval = self.config["刷新时间"]
        self.title = self.config["标题"]
        self.zero_tps_unknown_count = self.config["TPS连续为0显示未知次数"]

        self.tps_calculator = self.GetPluginAPI("tps计算器", (0, 0, 1), True)
        self.is_first_refresh = True
        self.start_time = time.time()
        self.created_score_entries = {}
        self.latest_texts = []
        self.last_tps_value = None
        self.same_tps_value_count = 0

        self.is_rental_server = self._is_rental_server()
        self.can_use_ai_command = isinstance(self.frame.launcher, FrameFateArk)
        self.print(
            "§7命令发送模式: "
            f"有返回={self._response_command_method_name()}, "
            f"无返回={self._no_response_command_method_name()}"
        )

        self._start_ntp_sync()

    def _start_ntp_sync(self) -> None:
        """启动后台线程进行 NTP 时间同步,不阻塞 on_preload 流程。

        若 ntplib 未安装,先尝试通过 pip 模块支持插件安装;
        安装失败或 ntplib 不可用时打印提示并使用系统时间。
        """
        if ntplib is None and not self._try_install_ntplib():
            self.print_war("§6NTP 时间同步未启用,将使用系统时间")
            return
        thread = threading.Thread(
            target=self._sync_ntp_time,
            name="NTP时间同步",
            daemon=True,
        )
        thread.start()

    def _try_install_ntplib(self) -> bool:
        """尝试通过 pip 模块支持插件自动安装 ntplib。

        Returns:
            True 表示安装并成功导入 ntplib;False 表示失败。
        """
        pip_api = self.GetPluginAPI("pip", (0, 0, 1), False)
        if pip_api is None:
            self.print_war("§6未找到 pip 模块支持插件,无法自动安装 ntplib")
            return False
        try:
            pip_api.require({"ntplib": "ntplib"})
        except Exception as err:
            self.print_err(f"§cntplib 安装失败: {err}")
            return False
        try:
            importlib.invalidate_caches()
            module = importlib.import_module("ntplib")
            sys.modules["ntplib"] = module
            globals()["ntplib"] = module
        except ImportError as err:
            self.print_err(f"§cntplib 安装后导入失败: {err}")
            return False
        return True

    def _sync_ntp_time(self) -> None:
        """从 NTP 服务器同步时间并计算时间偏移量。

        依次尝试 NTP_SERVERS 中的服务器,首个成功即返回;
        所有服务器均失败时打印提示并保持使用系统时间(偏移量为 0)。
        """
        if ntplib is None:
            self.print_war("§6ntplib 不可用,跳过 NTP 时间同步")
            return

        client = ntplib.NTPClient()
        for server in NTP_SERVERS:
            try:
                response = client.request(server, version=3, timeout=NTP_TIMEOUT)
                offset = datetime.timedelta(seconds=response.offset)
                _set_time_offset(offset)
                self.print_suc(
                    f"§aNTP 时间同步成功 §f(服务器: {server}, "
                    f"偏移: {offset.total_seconds():.3f}s)"
                )
                return
            except Exception as err:
                self.print_war(f"§6NTP 服务器 §e{server}§6 同步失败: {err}")
        self.print_war("§6所有 NTP 服务器同步均失败,将使用系统时间")

    def on_active(self) -> None:
        """激活阶段:重建公告栏计分板目标并启动文字刷新线程。"""
        time.sleep(1)
        self.refresh_scoreboard_objective()
        time.sleep(1)
        self.refresh_scoreboard_text()

    def _is_rental_server(self) -> bool:
        """判断当前是否运行在租赁服环境。

        Returns:
            True 表示是租赁服,否则为 False。
        """
        server_number = getattr(self.frame.launcher, "serverNumber", None)
        return str(server_number).isdigit()

    def _response_command_method_name(self) -> str:
        """返回当前环境下"可获取返回值"的命令发送方式名称(用于日志)。"""
        if self.can_use_ai_command:
            return "sendaicmd"
        if self.is_rental_server:
            return "sendwocmd(无返回)"
        return "sendwscmd"

    def _no_response_command_method_name(self) -> str:
        """返回当前环境下"不获取返回值"的命令发送方式名称(用于日志)。"""
        if self.is_rental_server:
            return "sendwocmd"
        if self.can_use_ai_command:
            return "sendaicmd"
        return "sendwscmd"

    def _can_get_command_response(self) -> bool:
        """判断当前环境是否能够获取命令返回值。"""
        return self.can_use_ai_command or not self.is_rental_server

    def _send_command_with_response(
        self, command: str, timeout: float = 30
    ) -> Packet_CommandOutput | None:
        """发送命令并尝试获取返回值,根据环境选择最优方式。

        Args:
            command: 要发送的命令字符串。
            timeout: 等待返回值的超时时间(秒)。

        Returns:
            命令返回对象;若环境无法获取返回值则为 None。
        """
        if self.can_use_ai_command:
            return self.game_ctrl.sendaicmd(command, waitForResp=True, timeout=timeout)
        if self.is_rental_server:
            self.game_ctrl.sendwocmd(command)
            return None
        return self.game_ctrl.sendwscmd(command, waitForResp=True, timeout=timeout)

    def _send_command_without_response(self, command: str) -> None:
        """发送命令且不等待返回值,根据环境选择最优方式。

        Args:
            command: 要发送的命令字符串。
        """
        if self.is_rental_server:
            self.game_ctrl.sendwocmd(command)
            return
        if self.can_use_ai_command:
            self.game_ctrl.sendaicmd(command)
            return
        self.game_ctrl.sendwscmd(command)

    def _run_command_with_retry(
        self,
        action_name: str,
        command: str,
        timeout: float = 3,
    ) -> None:
        """带重试机制地执行命令,直到成功或达到最大重试次数。

        Args:
            action_name: 操作名称(用于日志显示)。
            command: 要执行的命令字符串。
            timeout: 每次尝试的超时时间(秒)。

        Raises:
            TimeoutError: 达到最大重试次数仍失败时抛出。
        """
        for retry_count in range(1, MAX_COMMAND_RETRIES + 1):
            response = self._send_command_with_response(command, timeout)
            if _is_command_success(response):
                self.print(f"§a{action_name}成功")
                return

            self._print_retry_message(action_name, retry_count)
            _sleep_before_retry(retry_count)

        self.print(f"§c多次尝试{action_name}失败§f")
        raise TimeoutError(f"多次尝试{action_name}失败")

    def _print_retry_message(self, action_name: str, retry_count: int) -> None:
        """打印重试提示信息。

        Args:
            action_name: 操作名称。
            retry_count: 当前重试次数。
        """
        retry_delay = retry_count * RETRY_DELAY_STEP_SECONDS
        self.print(f"§c{action_name}失败§f,将在§e{retry_delay}s§f后重试")

    def refresh_scoreboard_objective(self) -> None:
        """刷新公告栏计分板目标:删除并重新创建,再设置到侧边栏显示。"""
        if not self._can_get_command_response():
            self._refresh_scoreboard_objective_without_response()
            return

        if not self._scoreboard_objective_exists():
            self.print("§e公告栏不存在,尝试创建公告栏")
            self._send_command_without_response(
                f"/scoreboard objectives add {OBJECTIVE_NAME} dummy {self.title}"
            )

        steps = [
            ("删除公告栏", f"/scoreboard objectives remove {OBJECTIVE_NAME}"),
            (
                "创建公告栏",
                f"/scoreboard objectives add {OBJECTIVE_NAME} dummy {self.title}",
            ),
            (
                "显示公告栏",
                f"/scoreboard objectives setdisplay sidebar {OBJECTIVE_NAME}",
            ),
        ]

        for index, (action_name, command) in enumerate(steps, 1):
            self.print(f"§e尝试{action_name}[{index}/{len(steps)}]")
            self._run_command_with_retry(action_name, command)
            time.sleep(0.3)

    def _scoreboard_objective_exists(self) -> bool:
        """检查公告栏计分板目标是否已存在。

        Returns:
            True 表示已存在。

        Raises:
            KeyError: 无法获取计分板列表时抛出。
        """
        response = self._send_command_with_response(
            "/scoreboard objectives list", timeout=5
        )
        if response is None:
            raise KeyError("获取计分板列表失败")

        return any(
            message.Success
            and message.Parameters
            and message.Parameters[0] == OBJECTIVE_NAME
            for message in response.OutputMessages
        )

    def _refresh_scoreboard_objective_without_response(self) -> None:
        """在无返回值模式下直接重建公告栏计分板目标。"""
        self.print("§e当前命令模式无返回信息,将直接重建公告栏")
        commands = [
            f"/scoreboard objectives remove {OBJECTIVE_NAME}",
            f"/scoreboard objectives add {OBJECTIVE_NAME} dummy {self.title}",
            f"/scoreboard objectives setdisplay sidebar {OBJECTIVE_NAME}",
        ]
        for command in commands:
            self._send_command_without_response(command)
            time.sleep(0.3)

    def get_tps_text(self, color: bool = False) -> str:
        """获取当前 TPS 的显示文本,可附带颜色代码。

        当 TPS 持续为 0 达到阈值次数时显示"未知",避免误报。

        Args:
            color: 是否附带颜色代码。

        Returns:
            TPS 显示文本。
        """
        if self.tps_calculator is None:
            return "§c无前置tps计算器"

        tps = round(float(self.tps_calculator.get_tps()), 1)
        if tps == self.last_tps_value:
            self.same_tps_value_count += 1
        else:
            self.last_tps_value = tps
            self.same_tps_value_count = 1

        if tps == 0 and self.same_tps_value_count >= self.zero_tps_unknown_count:
            return "§7未知" if color else "未知"

        tps_text = str(tps)
        if color:
            return get_tps_color(tps) + tps_text
        return tps_text

    @utils.thread_func("计分板公告文字刷新")
    def refresh_scoreboard_text(self) -> None:
        """在独立线程中按刷新间隔周期性更新公告栏文字内容。

        使用 NTP 校正后的时间(若同步成功),否则使用系统时间。
        """
        beijing_timezone = _get_beijing_timezone()
        while True:
            now_time = _get_synced_now(beijing_timezone)
            time_name, time_color = get_time_display(now_time)
            tps_text = self.get_tps_text(True)
            current_texts = self._build_scoreboard_texts(
                now_time, time_name, time_color, tps_text
            )
            self._sync_scoreboard_texts(current_texts)
            self.is_first_refresh = False
            time.sleep(self.refresh_interval)

    def _build_scoreboard_texts(
        self,
        now_time: datetime.datetime,
        time_name: str,
        time_color: str,
        tps_text: str,
    ) -> list[str]:
        """根据模板与当前动态数据构造公告栏每一行的文本。

        Args:
            now_time: 当前时间。
            time_name: 时段名称。
            time_color: 时段颜色代码。
            tps_text: TPS 显示文本。

        Returns:
            替换占位符后的文本列表。
        """
        return [
            utils.simple_fmt(
                {
                    "{num_players}": len(self.game_ctrl.allplayers),
                    "{week_day}": "周" + "一二三四五六日"[now_time.weekday()],
                    "{tps}": tps_text,
                    "{year}": now_time.strftime("%Y"),
                    "{month}": now_time.strftime("%m"),
                    "{day}": now_time.strftime("%d"),
                    "{time_cn}": time_name,
                    "{time_color}": time_color,
                    "{hour}": now_time.strftime("%H"),
                    "{minute}": now_time.strftime("%M"),
                    "{second}": now_time.strftime("%S"),
                    "{run_time}": self._format_runtime(),
                },
                template,
            )
            for template in self.announce_templates
        ]

    def _format_runtime(self) -> str:
        """格式化插件已运行时长。

        Returns:
            形如 "X天Y小时Z分" 的字符串。
        """
        elapsed_seconds = int(time.time() - self.start_time)
        days, remaining_seconds = divmod(elapsed_seconds, 86400)
        hours, remaining_seconds = divmod(remaining_seconds, 3600)
        minutes = remaining_seconds // 60
        return f"{days}天{hours}小时{minutes}分"

    def _sync_scoreboard_texts(self, current_texts: list[str]) -> None:
        """将最新文本同步到计分板,仅更新发生变化的行。

        Args:
            current_texts: 当前帧的文本列表。
        """
        old_texts = list(reversed(self.latest_texts))
        for score, text in _iter_scoreboard_entries(current_texts):
            if self.is_first_refresh:
                self._set_scoreboard_text_first_run(text, score)
                continue

            if score < len(old_texts) and old_texts[score] == text:
                continue

            if score < len(old_texts):
                self._reset_scoreboard_text(old_texts[score])
            self._set_scoreboard_text(text, score)

        self.latest_texts = current_texts

    def _set_scoreboard_text_first_run(self, text: str, score: int) -> None:
        """首次刷新时设置计分板文本,支持重试机制。

        Args:
            text: 要设置的文本。
            score: 对应的分数(行位置)。
        """
        command = f'/scoreboard players set "{text}" {OBJECTIVE_NAME} {score}'
        if not self._can_get_command_response():
            self._send_command_without_response(command)
            return

        self._run_command_with_retry(f"设置公告栏内容['{text}']", command)

    def _set_scoreboard_text(self, text: str, score: int) -> None:
        """设置计分板文本(非首次刷新,使用无返回值方式以提升性能)。

        Args:
            text: 要设置的文本。
            score: 对应的分数(行位置)。
        """
        self._send_command_without_response(
            f'/scoreboard players set "{text}" {OBJECTIVE_NAME} {score}'
        )

    def _reset_scoreboard_text(self, text: str) -> None:
        """重置指定文本对应的计分板项。

        Args:
            text: 需要重置的文本。
        """
        self._send_command_without_response(
            f'/scoreboard players reset "{text}" {OBJECTIVE_NAME}'
        )

    def on_set_score(self, packet: dict) -> bool:
        """监听计分板数据包,记录由本插件创建的计分项以避免冲突堆积。

        Args:
            packet: IDSetScore 数据包。

        Returns:
            始终返回 False 以继续传递数据包。
        """
        if not isinstance(packet, dict) or packet.get("ActionType") is None:
            return False

        entries = packet["Entries"]
        if packet["ActionType"] == 1:
            self._record_created_entries(entries)
        else:
            self._remove_deleted_entries(entries)

        if len(self.created_score_entries) > 3:
            self._clear_recorded_score_entries()
        return False

    def _record_created_entries(self, entries: list[dict[str, Any]]) -> None:
        """记录新建的计分板项。

        Args:
            entries: 数据包中的计分项列表。
        """
        for item in entries:
            if item["ObjectiveName"] == OBJECTIVE_NAME:
                self.created_score_entries[item["EntryID"]] = item["DisplayName"]

    def _remove_deleted_entries(self, entries: list[dict[str, Any]]) -> None:
        """移除已删除的计分板项记录。

        Args:
            entries: 数据包中的计分项列表。
        """
        for item in entries:
            self.created_score_entries.pop(item["EntryID"], None)

    def _clear_recorded_score_entries(self) -> None:
        """清理所有由本插件创建的计分项,避免计分板堆积。"""
        for text in list(self.created_score_entries.values()):
            self._reset_scoreboard_text(text)
        self.created_score_entries = {}


entry = plugin_entry(BetterAnnounce)

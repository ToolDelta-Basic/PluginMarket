"""Cloud-linked quest system plugin."""

import copy
import os
import time
import threading
from dataclasses import dataclass
from typing import Any
from tooldelta import (
    cfg as config,
    utils,
    fmts,
    game_utils,
    Plugin,
    Player,
    TYPE_CHECKING,
    plugin_entry,
)


CONFIG_FILE_DIR = "插件配置文件"
DYNAMIC_LOAD_SETTINGS_KEY = "动态载入设置"
DYNAMIC_LOAD_ENABLED_KEY = "是否启用动态载入配置文件（仅用于本插件）"
DYNAMIC_LOAD_INTERVAL_KEY = "动态载入检测时间间隔（单位：秒）"
DYNAMIC_LOAD_DEFAULT_INTERVAL = 5


@dataclass
class Quest:
    """Runtime definition for one configured quest."""

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


class TaskSystemCloudInterop(Plugin):
    """ToolDelta plugin that manages cloud-linked quest workflows."""

    name = "任务系统云链联动版"
    author = "SuperScript"
    version = (0, 0, 5)

    def __init__(self, frame):
        super().__init__(frame)
        self._config_reload_stop = threading.Event()
        self._config_file_state = None
        self.QUEST_PATH = os.path.join(self.data_path, "任务")
        self.QUEST_DATA_PATH = os.path.join(self.data_path, "任务数据")
        self.tmpjson = utils.tempjson
        self.quest_data_paths: set[str] = set()
        self.in_plot_running = {}
        self.quests: dict[str, Quest] = {}
        for ipath in [self.QUEST_PATH, self.QUEST_DATA_PATH]:
            os.makedirs(ipath, exist_ok=True)
        CFG_STD = {
            DYNAMIC_LOAD_SETTINGS_KEY: {
                DYNAMIC_LOAD_ENABLED_KEY: bool,
                DYNAMIC_LOAD_INTERVAL_KEY: config.PInt,
            },
            "任务设置": {
                "任务列表显示格式": config.JsonList(str),
                "接到新任务时执行的指令": config.JsonList(str),
                "任务无法提交的显示": {
                    "格式": str,
                },
                "任务完成执行的指令": config.JsonList(str),
                "任务无法开始的显示": {
                    "格式": str,
                },
            }
        }
        CFG_DEFAULT = {
            DYNAMIC_LOAD_SETTINGS_KEY: {
                DYNAMIC_LOAD_ENABLED_KEY: True,
                DYNAMIC_LOAD_INTERVAL_KEY: DYNAMIC_LOAD_DEFAULT_INTERVAL,
            },
            "任务设置": {
                "任务列表显示格式": [
                    "§7▶ 当前正在进行的任务:",
                    " §f[i] §7- §f[任务显示名]\n  §7[任务描述] ",
                    "§7在15s内输入§f任务前的序号§r§7可以提交此任务 §f其他§7以退出",
                ],
                "接到新任务时执行的指令": [
                    (
                        "/execute as @a[name=[玩家名]] at @s run playsound "
                        "note.pling @s ~~~ 1 1.4"
                    ),
                    (
                        '/tellraw @a[name=[玩家名]] '
                        '{"rawtext":[{"text":"§d▶ §e收到新任务 §f[任务显示名]\n'
                        '  §7[任务描述] \n§3输入§b.rw§3以提交任务"}]}'
                    ),
                ],
                "任务无法提交的显示": {
                    "格式": "§c任务无法达成， 原因:\n [原因]",
                },
                "任务无法开始的显示": {
                    "格式": "§c任务无法开始， 原因:\n [原因]"},
                "任务完成执行的指令": [
                    '/tellraw @a[name=[玩家名]] {"rawtext":[{"text":"§a任务完成"}]}',
                    "/execute as @a[name=[玩家名]] at @s run playsound random.levelup @s",
                ],
            },
        }
        self._cfg_std = CFG_STD
        self._cfg_default = CFG_DEFAULT
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
        self._quest_std = QUEST_STD
        self.load_runtime_config(announce=False)
        self.load_quest_configs(announce=True)
        self.refresh_config_file_state()
        self.config_thread = utils.createThread(
            self.config_reload_task,
            usage="任务系统配置热更新任务",
        )
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenFrameExit(self.on_frame_exit)

    # --- Config hot reload ---

    @classmethod
    def _merge_config_with_default(cls, raw: Any, default: Any):
        """Implement the merge config with default operation."""
        if isinstance(default, dict):
            result = {
                key: cls._merge_config_with_default(
                    raw.get(key) if isinstance(raw, dict) else None,
                    value,
                )
                for key, value in default.items()
            }
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key not in result:
                        result[key] = copy.deepcopy(value)
            return result
        return copy.deepcopy(
            raw) if raw is not None else copy.deepcopy(default)

    @staticmethod
    def _trim_fixed_keys(raw: Any, default: dict[str, Any]) -> dict[str, Any]:
        """Implement the trim fixed keys operation."""
        raw = raw if isinstance(raw, dict) else {}
        return {
            key: copy.deepcopy(raw.get(key, value))
            for key, value in default.items()
        }

    @staticmethod
    def _normalize_bool(value: Any, fallback: bool) -> bool:
        """Normalize bool values."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("true", "1", "yes", "y", "on", "启用", "是", "真"):
                return True
            if text in ("false", "0", "no", "n", "off", "禁用", "否", "假"):
                return False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return bool(value)
        return bool(fallback)

    @staticmethod
    def _normalize_positive_int(value: Any, fallback: int) -> int:
        """Normalize positive int values."""
        if isinstance(value, bool):
            return fallback
        try:
            result = int(value)
        except (TypeError, ValueError):
            return fallback
        return result if result > 0 else fallback

    @staticmethod
    def _normalize_str(
            value: Any,
            fallback: str,
            *,
            allow_empty: bool = False) -> str:
        """Normalize str values."""
        if value is None:
            return fallback
        text = str(value)
        if text or allow_empty:
            return text
        return fallback

    @classmethod
    def _normalize_string_list(
        cls,
        value: Any,
        fallback: list[str],
        *,
        allow_empty: bool = False,
    ) -> list[str]:
        """Normalize string list values."""
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = value
        else:
            return copy.deepcopy(fallback)

        result: list[str] = []
        for item in candidates:
            text = cls._normalize_str(item, "", allow_empty=True).strip()
            if text and text not in result:
                result.append(text)
        if result or allow_empty:
            return result
        return copy.deepcopy(fallback)

    @classmethod
    def _normalize_format_config(
        cls,
        value: Any,
        fallback: dict[str, str],
    ) -> dict[str, str]:
        """Normalize format config values."""
        value = value if isinstance(value, dict) else {}
        return {
            "格式": cls._normalize_str(
                value.get("格式"),
                fallback["格式"],
                allow_empty=False,
            )
        }

    @classmethod
    def _normalize_runtime_config(
        cls,
        raw_cfg: Any,
        default_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize runtime config values."""
        merged_cfg = cls._merge_config_with_default(raw_cfg, default_cfg)
        normalized = cls._trim_fixed_keys(merged_cfg, default_cfg)

        dynamic_default = default_cfg[DYNAMIC_LOAD_SETTINGS_KEY]
        dynamic = cls._trim_fixed_keys(
            normalized.get(DYNAMIC_LOAD_SETTINGS_KEY),
            dynamic_default,
        )
        dynamic[DYNAMIC_LOAD_ENABLED_KEY] = cls._normalize_bool(
            dynamic.get(DYNAMIC_LOAD_ENABLED_KEY),
            dynamic_default[DYNAMIC_LOAD_ENABLED_KEY],
        )
        dynamic[DYNAMIC_LOAD_INTERVAL_KEY] = cls._normalize_positive_int(
            dynamic.get(DYNAMIC_LOAD_INTERVAL_KEY),
            dynamic_default[DYNAMIC_LOAD_INTERVAL_KEY],
        )
        normalized[DYNAMIC_LOAD_SETTINGS_KEY] = dynamic

        task_default = default_cfg["任务设置"]
        task_settings = cls._trim_fixed_keys(
            normalized.get("任务设置"),
            task_default,
        )
        list_format = cls._normalize_string_list(
            task_settings.get("任务列表显示格式"),
            task_default["任务列表显示格式"],
        )
        task_settings["任务列表显示格式"] = (
            list_format
            if len(list_format) >= 3
            else copy.deepcopy(task_default["任务列表显示格式"])
        )
        task_settings["接到新任务时执行的指令"] = cls._normalize_string_list(
            task_settings.get("接到新任务时执行的指令"),
            task_default["接到新任务时执行的指令"],
            allow_empty=True,
        )
        task_settings["任务完成执行的指令"] = cls._normalize_string_list(
            task_settings.get("任务完成执行的指令"),
            task_default["任务完成执行的指令"],
            allow_empty=True,
        )
        task_settings["任务无法提交的显示"] = cls._normalize_format_config(
            task_settings.get("任务无法提交的显示"),
            task_default["任务无法提交的显示"],
        )
        task_settings["任务无法开始的显示"] = cls._normalize_format_config(
            task_settings.get("任务无法开始的显示"),
            task_default["任务无法开始的显示"],
        )
        normalized["任务设置"] = task_settings
        return normalized

    def load_runtime_config(self, announce: bool = False):
        """Load runtime config data."""
        try:
            raw_cfg, _ = config.get_plugin_config_and_version(
                self.name, {}, self._cfg_default, self.version
            )
            merged_cfg = self._normalize_runtime_config(
                raw_cfg, self._cfg_default)
            config.check_auto(self._cfg_std, merged_cfg)
        except Exception as err:
            fmts.print_err(f"{self.name} 主配置文件自动更新失败，已使用默认配置: {err}")
            merged_cfg = self._normalize_runtime_config({}, self._cfg_default)
            config.check_auto(self._cfg_std, merged_cfg)
        config.upgrade_plugin_config(self.name, merged_cfg, self.version)
        self.cfg = merged_cfg
        if announce:
            fmts.print_suc(f"{self.name} 主配置文件已热更新")

    def load_quest_configs(self, announce: bool = False):  # skipcq: PY-R1000
        """Load quest configs data."""
        quests: dict[str, Quest] = {}
        total_quest_files = 0
        for cfg_quest_dir in os.listdir(self.QUEST_PATH):
            file = ""
            try:
                sub_path = os.path.join(self.QUEST_PATH, cfg_quest_dir)
                if not os.path.isdir(sub_path):
                    continue
                for file in os.listdir(sub_path):
                    if not file.endswith(".json"):
                        continue
                    cfg = config.get_cfg(
                        os.path.join(
                            sub_path,
                            file),
                        self._quest_std)
                    tag_name = f"{cfg_quest_dir}/{file[:-5]}"
                    quests[tag_name] = Quest(
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
                fmts.print_err(f"任务系统云链联动版: 任务配置文件 {file} 出错: ")
                fmts.print_err(err.args[0])
        old_quests = self.quests
        self.quests = quests
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
                    fmts.print_err(f"任务系统云链联动版: 任务配置文件 {file} 出错: ")
                    fmts.print_err(err.args[0])
        if not self.quests and old_quests:
            self.quests = old_quests
            fmts.print_err(f"{self.name}: 任务配置热更新未加载到有效任务，已保留旧任务表")
            return
        if announce:
            fmts.print_with_info(
                f"§a共加载 §b{total_quest_files}§a 个任务文件.", "§b Task §r"
            )

    def config_file_path(self) -> str:
        """Implement the config file path operation."""
        return os.path.join(CONFIG_FILE_DIR, f"{self.name}.json")

    @staticmethod
    def file_state(path: str) -> tuple[int, int] | None:
        """Implement the file state operation."""
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def quest_config_state(self) -> tuple[tuple[str, tuple[int, int]], ...]:
        """Implement the quest config state operation."""
        states: list[tuple[str, tuple[int, int]]] = []
        for root, _dirs, files in os.walk(self.QUEST_PATH):
            for filename in files:
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(root, filename)
                state = self.file_state(path)
                if state is not None:
                    states.append(
                        (os.path.relpath(
                            path, self.QUEST_PATH), state))
        return tuple(sorted(states))

    def refresh_config_file_state(self):
        """Implement the refresh config file state operation."""
        self._config_file_state = self.file_state(self.config_file_path())
        self._quest_config_state = self.quest_config_state()

    def is_dynamic_config_reload_enabled(self) -> bool:
        """Implement the is dynamic config reload enabled operation."""
        settings = self.cfg.get(DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return True
        return bool(settings.get(DYNAMIC_LOAD_ENABLED_KEY, True))

    def dynamic_config_reload_interval(self) -> int:
        """Implement the dynamic config reload interval operation."""
        settings = self.cfg.get(DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return DYNAMIC_LOAD_DEFAULT_INTERVAL
        try:
            interval = int(settings.get(DYNAMIC_LOAD_INTERVAL_KEY,
                           DYNAMIC_LOAD_DEFAULT_INTERVAL))
        except (TypeError, ValueError):
            return DYNAMIC_LOAD_DEFAULT_INTERVAL
        return interval if interval > 0 else DYNAMIC_LOAD_DEFAULT_INTERVAL

    def config_reload_task(self):
        """Implement the config reload task operation."""
        while not self._config_reload_stop.wait(
                self.dynamic_config_reload_interval()):
            if not self.is_dynamic_config_reload_enabled():
                self.refresh_config_file_state()
                continue
            current_cfg_state = self.file_state(self.config_file_path())
            current_quest_state = self.quest_config_state()
            if (
                current_cfg_state == self._config_file_state
                and current_quest_state == self._quest_config_state
            ):
                continue
            try:
                if current_cfg_state != self._config_file_state:
                    self.load_runtime_config(announce=True)
                if current_quest_state != self._quest_config_state:
                    self.load_quest_configs(announce=True)
                self.refresh_config_file_state()
            except Exception as err:
                self._config_file_state = current_cfg_state
                self._quest_config_state = current_quest_state
                fmts.print_err(f"{self.name} 配置文件热更新失败: {err}")

    def api_reload_task_config(self) -> tuple[bool, str]:
        """Expose the api reload task config API operation."""
        try:
            self.load_runtime_config(announce=False)
            self.load_quest_configs(announce=False)
            self.refresh_config_file_state()
        except Exception as err:
            return False, f"任务系统配置重载失败: {err}"
        return True, f"任务系统配置已重载，当前加载 {len(self.quests)} 个任务"

    # --- API ---

    def get_quest(self, tag_name: str) -> Quest | None:
        """
        根据任务名获取任务对象

        Args:
            tag_name (str): 任务名

        Returns:
            Quest | None: 任务对象 (或找不到任务)
        """
        return self.quests.get(tag_name)

    def get_online_player(self, player_name: str) -> Player | None:
        """Return online player data."""
        return self.frame.get_players().getPlayerByName(player_name)

    @staticmethod
    def get_quest_label(quest: Quest) -> str:
        """Return quest label data."""
        if quest.show_name == quest.tag_name:
            return quest.tag_name
        return f"{quest.show_name} ({quest.tag_name})"

    def find_quest(self, quest_query: str) -> tuple[Quest | None, str]:
        """Implement the find quest operation."""
        quest_query = quest_query.strip()
        if not quest_query:
            return None, "任务标识不能为空"
        if quest := self.get_quest(quest_query):
            return quest, ""

        exact_matches = [
            i for i in self.quests.values() if i.show_name == quest_query]
        if len(exact_matches) == 1:
            return exact_matches[0], ""
        if len(exact_matches) > 1:
            labels = "、".join(self.get_quest_label(i)
                              for i in exact_matches[:5])
            return None, f"匹配到多个同名任务，请改用任务标签名：{labels}"

        query_lower = quest_query.casefold()
        fuzzy_matches = [
            i
            for i in self.quests.values()
            if query_lower in i.tag_name.casefold()
            or query_lower in i.show_name.casefold()
        ]
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0], ""
        if len(fuzzy_matches) > 1:
            labels = "、".join(self.get_quest_label(i)
                              for i in fuzzy_matches[:5])
            if len(fuzzy_matches) > 5:
                labels += "……"
            return None, f"匹配到多个任务：{labels}"
        return None, f"任务不存在：{quest_query}"

    def can_add_quest(self, player: Player, quest: Quest) -> tuple[bool, str]:
        """Implement the can add quest operation."""
        quests = self.read_quests(player)
        if quest in quests:
            return False, "当前任务正在进行中，无法重复领取"
        quest_time = self.read_quests_finished(player).get(quest, None)
        quest_mode = quest.cooldown
        if quest_mode == -1 and quest_time is not None:
            return False, "你已经完成该任务"
        if (
            quest_time is not None
            and quest_mode > 0
            and time.time() - quest_time < quest.cooldown
        ):
            fmt_text = r"%d 天 %H 时 %M 分"
            left_time = self.sec_to_timer(
                quest.cooldown - int(time.time()) + quest_time, fmt_text
            )
            return False, f"该任务仍在冷却中，还需等待：{left_time}"
        return True, ""

    def get_online_player_task_progress(
        self, player_name: str
    ) -> tuple[bool, dict | str]:
        """Return online player task progress data."""
        player = self.get_online_player(player_name)
        if player is None:
            return False, f"玩家不在线或不存在：{player_name}"
        in_progress = []
        for quest in self.read_quests(player):
            if quest is None:
                continue
            in_progress.append(
                {
                    "tag_name": quest.tag_name,
                    "show_name": quest.show_name,
                    "description": quest.description,
                }
            )
        completed = []
        for quest, finished_time in sorted(
            self.read_quests_finished(player).items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            completed.append(
                {
                    "tag_name": quest.tag_name,
                    "show_name": quest.show_name,
                    "description": quest.description,
                    "finished_time": finished_time,
                }
            )
        return True, {
            "player_name": player.name,
            "in_progress": in_progress,
            "completed": completed,
        }

    def add_quest_to_online_player(
        self, player_name: str, quest_query: str
    ) -> tuple[bool, str]:
        """Implement the add quest to online player operation."""
        player = self.get_online_player(player_name)
        if player is None:
            return False, f"玩家不在线或不存在：{player_name}"
        quest, err = self.find_quest(quest_query)
        if quest is None:
            return False, err
        ok, reason = self.can_add_quest(player, quest)
        if not ok:
            return False, reason
        if not self.add_quest(player, quest):
            return False, f"下发任务失败：{self.get_quest_label(quest)}"
        return True, f"已向玩家 {player.name} 下发任务：{self.get_quest_label(quest)}"

    def finish_quest_for_online_player(
        self, player_name: str, quest_query: str
    ) -> tuple[bool, str]:
        """Implement the finish quest for online player operation."""
        player = self.get_online_player(player_name)
        if player is None:
            return False, f"玩家不在线或不存在：{player_name}"
        quest, err = self.find_quest(quest_query)
        if quest is None:
            return False, err
        if not self.is_quest_in_progress(player, quest):
            return False, f"该任务未解锁或已经完成：{self.get_quest_label(quest)}"
        if not self.finish_quest(player, quest):
            return False, f"完成任务失败：{self.get_quest_label(quest)}"
        return True, f"已为玩家 {player.name} 完成任务：{self.get_quest_label(quest)}"

    def list_available_quests(self) -> list[dict[str, str]]:
        """Implement the list available quests operation."""
        quests = sorted(self.quests.values(), key=lambda item: item.tag_name)
        return [
            {
                "tag_name": quest.tag_name,
                "show_name": quest.show_name,
                "description": quest.description,
            }
            for quest in quests
        ]

    def add_quest(self, player: Player, quest: Quest) -> bool:
        """
        向玩家下发任务

        Args:
            player (Player): 玩家对象
            quest (Quest): 任务对象

        Returns:
            bool: 是否下发成功
        """
        ok, reason = self.can_add_quest(player, quest)
        if not ok:
            player.show(
                utils.simple_fmt(
                    {"[玩家名]": player.name, "[原因]": f"§c{reason}"},
                    self.cfg["任务设置"]["任务无法开始的显示"]["格式"],
                ),
            )
            return False
        for cmd in self.cfg["任务设置"]["接到新任务时执行的指令"]:
            s_cmd = utils.simple_fmt(
                {
                    "[任务显示名]": quest.show_name,
                    "[任务描述]": quest.description,
                    "[玩家名]": player.name,
                },
                cmd,
            )
            self.game_ctrl.sendwocmd(s_cmd)
        o = self.read_player_quest_data(player)
        o["in_quests"].append(quest.tag_name)
        self.write_player_quest_data(player, o)
        return True

    def is_quest_in_progress(self, player: Player, quest: Quest) -> bool:
        """Implement the is quest in progress operation."""
        o = self.read_player_quest_data(player)
        return quest.tag_name in o["in_quests"]

    def detect_quest(  # skipcq: PY-R1000
        self, player: Player, quest: Quest, allow_command_block: bool = False
    ) -> tuple[bool, str]:
        """
        检测任务是否可以提交

        Args:
            player (Player): 玩家对象
            quest (Quest): 任务对象

        Returns:
            tuple[bool, str]: 是否可提交; 无法提交的信息
        """
        o = self.read_player_quest_data(player)
        if quest.tag_name not in o["in_quests"]:
            if quest.tag_name in o["quests_ok"]:
                return False, "§6该任务已经完成"
            return False, "§6该任务未解锁或已经完成"
        if quest.cooldown == -1 and quest.tag_name in o["quests_ok"]:
            return False, "§6该任务已经完成"
        if quest.command_block_only and not allow_command_block:
            return False, "§6无法手动提交该任务"
        if quest.need_quests_prefix:
            err_strs = []
            player_finished_quests = self.read_quests_finished(player)
            for quest_name in quest.need_quests_prefix:
                need_quest = self.get_quest(quest_name)
                if need_quest is None:
                    err_strs.append(f"{quest_name} (任务配置不存在)")
                    continue
                if need_quest not in player_finished_quests:
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
                if (item_count_now := player.getItemCount(item_id, data)) < count:
                    err_strs.append(
                        f"§f{item_name} §7(§c{item_count_now}§7/§f{count}§7)"
                    )
            if err_strs:
                return False, "缺少物品: \n  " + "\n  ".join(err_strs)
        if quest.detect_cmds:
            for cmd in quest.detect_cmds:
                if not game_utils.isCmdSuccess(
                    utils.simple_fmt({"[玩家名]": player.name}, cmd)
                ):
                    return False, "§6未达成条件"
        return True, ""

    def finish_quest(self, player: Player, quest: Quest) -> bool:
        """
        令玩家完成任务 (强制性, 无论条件是否满足)

        Args:
            player (Player): 玩家对象
            quest (Quest): 任务对象
        """
        o = self.read_player_quest_data(player)
        if quest.tag_name not in o["in_quests"]:
            if quest.tag_name in o["quests_ok"]:
                self.show_fail(player, "该任务已经完成")
                return False
            self.show_fail(player, "该任务未解锁或已经完成")
            return False
        if quest.cooldown == -1 and quest.tag_name in o["quests_ok"]:
            self.show_fail(player, "该任务已经完成")
            return False
        o["quests_ok"][quest.tag_name] = int(time.time())
        o["in_quests"] = [tag_name for tag_name in o["in_quests"]
                          if tag_name != quest.tag_name]
        self.write_player_quest_data(player, o)
        self.game_ctrl.sendwocmd(
            f"/execute as @a[name={player.name}] at @s run playsound random.levelup @s"
        )
        player.show("§a۞ §l任务完成 §r§e奖励已下发~")
        for cmd in quest.exec_cmds_when_finished:
            self.game_ctrl.sendwocmd(
                utils.simple_fmt({"[玩家名]": player.name}, cmd))
        for item_name, (item_id,
                        count) in quest.items_give_when_finished.items():
            self.game_ctrl.sendwocmd(
                f"give @a[name={player.name}] {item_id} {count}")
            player.show(f" §7 + {count}x§f{item_name}")
        self.show_succ(player, "任务已提交, 请退出聊天栏")
        for new_quest_name in quest.start_quest_when_finished:
            new_quest = self.get_quest(new_quest_name)
            if new_quest is None:
                fmts.print_err(
                    f"{self.name}: 完成任务后开始的任务不存在: {new_quest_name}"
                )
                continue
            self.add_quest(player, new_quest)
        return True

    # -------------

    def on_def(self):
        """Implement the on def operation."""
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

    def show_succ(self, player: Player, msg):
        """Implement the show succ operation."""
        player.show(f"§7<§a§o√§r§7> §a{msg}")

    def show_warn(self, player: Player, msg):
        """Implement the show warn operation."""
        player.show(f"§7<§6§o!§r§7> §6{msg}")

    def show_fail(self, player: Player, msg):
        """Implement the show fail operation."""
        player.show(f"§7<§c§o!§r§7> §c{msg}")

    def show_inf(self, player: Player, msg):
        """Implement the show inf operation."""
        player.show(f"§7<§f§o!§r§7> §f{msg}")

    @utils.thread_func("任务的游戏初始化")
    def on_inject(self):
        """Implement the on inject operation."""
        self.cmp_scripts = {}
        self.chatbar.add_new_trigger(
            [".rw", ".任务"],
            [],
            "查看正在进行的任务列表",
            lambda player, _: self.list_player_quests(player),
        )
        self.chatbar.add_new_trigger(
            [".addrw", ".添加任务"],
            [("任务标签名", str, None)],
            "向玩家添加任务",
            self.force_add_quest_menu,
            op_only=True,
        )
        for player in self.frame.get_players().getAllPlayers():
            self.init_player(player)

    @utils.thread_func("初始化玩家剧情任务数据")
    def on_player_join(self, player: Player):
        """Implement the on player join operation."""
        self.init_player(player)

    def on_quest_ok(self, args: list[str]):
        """Implement the on quest ok operation."""
        target_name, quest_name = args
        quest = self.get_quest(quest_name)
        target = self.frame.get_players().getPlayerByName(target_name)
        if target is None:
            self.print(f"§6on_quest_ok: 玩家 {target_name} 不存在")
            return
        if quest is not None:
            ok, reason = self.detect_quest(
                target, quest, allow_command_block=True)
            if not ok:
                self.show_fail(target, reason)
                return
            self.finish_quest(target, quest)

    def on_quest_start(self, args: list[str]):
        """Implement the on quest start operation."""
        target_name, quest_name = args
        quest = self.get_quest(quest_name)
        target = self.frame.get_players().getPlayerByName(target_name)
        if target is None:
            self.print(f"§6on_quest_ok: 玩家 {target_name} 不存在")
            return
        if quest is not None:
            self.add_quest(target, quest)

    def init_player(self, player: Player):
        """Implement the init player operation."""
        quest_path = self.get_player_quest_data_path(player)
        if not os.path.isfile(quest_path):
            self.write_player_quest_data(player, self.init_quest_file())
        else:
            self.read_player_quest_data(player)

    def init_quest_file(self):
        """Implement the init quest file operation."""
        return {"in_quests": [], "quests_ok": {}}

    def get_player_quest_data_path(self, player: Player) -> str:
        """Return player quest data path data."""
        path = os.path.join(self.QUEST_DATA_PATH, player.xuid + ".json")
        self.quest_data_paths.add(path)
        return path

    def read_player_quest_data(self, player: Player) -> dict:
        """Implement the read player quest data operation."""
        data = self.tmpjson.load_and_read(
            self.get_player_quest_data_path(player),
            need_file_exists=False,
            default=self.init_quest_file(),
        )
        if not isinstance(data, dict):
            return self.init_quest_file()
        if not isinstance(data.get("in_quests"), list):
            data["in_quests"] = []
        if not isinstance(data.get("quests_ok"), dict):
            data["quests_ok"] = {}
        return data

    def write_player_quest_data(self, player: Player, data: dict):
        """Implement the write player quest data operation."""
        path = self.get_player_quest_data_path(player)
        self.tmpjson.load_and_write(path, data, need_file_exists=False)
        self.tmpjson.flush(path)

    def on_frame_exit(self, _):
        """Implement the on frame exit operation."""
        self._config_reload_stop.set()
        for path in tuple(self.quest_data_paths):
            try:
                self.tmpjson.unload(path)
            except Exception:
                pass

    def read_quests(self, player: Player) -> list[Quest]:
        """Implement the read quests operation."""
        o = self.read_player_quest_data(player)
        output = []
        o = o or {"in_quests": []}
        for i in o["in_quests"]:
            output.append(self.get_quest(i))
        return output

    def read_quests_finished(self, player: Player) -> dict[Quest, int]:
        """Implement the read quests finished operation."""
        o = self.read_player_quest_data(player)
        output = {}
        for k, v in o["quests_ok"].items():
            quest = self.get_quest(k)
            if quest:
                output[quest] = v
        return output

    @utils.thread_func("管理员向玩家添加任务")
    def force_add_quest_menu(self, player: Player, args: tuple):
        # with utils.ChatbarLock(player, lambda _:
        # print(utils.chatbar_lock_list)):
        """Implement the force add quest menu operation."""
        (quest_tagname,) = args
        if (quest := self.get_quest(quest_tagname)) is None:
            player.show("§c任务标签名不存在")
            return
        onlines = self.frame.get_players().getAllPlayers()
        self.show_inf(player, "§6选择一个玩家以向他添加任务：")
        for i, j in enumerate(onlines):
            player.show(f" §a{i + 1}§7 - §f{j.name}")
        resp = utils.try_int(player.input())
        self.show_inf(player, "§7输入玩家名前的§6序号§7：")
        if resp is None:
            player.show("§c序号错误， 已退出")
            return
        if resp not in range(1, len(onlines) + 1):
            player.show("§c序号不在范围内， 已退出")
            return
        getting = onlines[resp - 1]
        player.show(
            f"§6向玩家{getting}添加任务"
            + ["§c失败", "§a成功"][self.add_quest(getting, quest)],
        )

    @utils.thread_func("列出任务列表")
    def list_player_quests(self, player: Player):
        # with utils.ChatbarLock(player):
        """Implement the list player quests operation."""
        player_quests = self.read_quests(player)
        if not player_quests:
            self.show_fail(player, "你没有正在进行的任务")
            return
        else:
            player.show(self.cfg["任务设置"]["任务列表显示格式"][0])
            for i, quest_data in enumerate(player_quests):
                if quest_data is None:
                    player.show(
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
                    player.show(
                        utils.simple_fmt(
                            {
                                "[任务显示名]": quest_data.show_name,
                                "[任务描述]": quest_data.description,
                                "[i]": i + 1,
                            },
                            self.cfg["任务设置"]["任务列表显示格式"][1],
                        ),
                    )
            resp = player.input(
                utils.simple_fmt(
                    {"[任务数量]": len(player_quests)},
                    self.cfg["任务设置"]["任务列表显示格式"][2],
                )
            )
            if resp is None:
                return
            resp = utils.try_int(resp.strip("[]"))
            if resp is None:
                player.show("§c序号不合法")
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
                player.show(
                    utils.simple_fmt(
                        {"[玩家名]": player.name, "[原因]": reason},
                        self.cfg["任务设置"]["任务无法提交的显示"]["格式"],
                    ),
                )
                return
            else:
                self.finish_quest(player, getting_quest)

    def sec_to_timer(self, timesec: int, fmt: str):
        """Implement the sec to timer operation."""
        days, left = divmod(timesec, 86400)
        hrs, left = divmod(left, 3600)
        mins, secs = divmod(left, 60)
        if secs > 0 and mins == 0:
            mins = 1
        return utils.simple_fmt(
            {"%d": days, "%H": hrs, "%M": mins, "%S": secs}, fmt)


entry = plugin_entry(
    TaskSystemCloudInterop,
    "任务系统云链联动版",
    (0, 0, 1),
)

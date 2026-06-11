import copy
import os
import time
import threading
from typing import Any

from tooldelta import Player, Plugin, cfg, fmts, game_utils, plugin_entry, utils


CONFIG_FILE_DIR = "插件配置文件"
DYNAMIC_LOAD_SETTINGS_KEY = "动态载入设置"
DYNAMIC_LOAD_ENABLED_KEY = "是否启用动态载入配置文件（仅用于本插件）"
DYNAMIC_LOAD_INTERVAL_KEY = "动态载入检测时间间隔（单位：秒）"
DYNAMIC_LOAD_DEFAULT_INTERVAL = 5


class WhitelistAndOpCheck(Plugin):
    """负责白名单与 OP 状态校验，并对外暴露管理接口。"""

    name = "白名单&管理员检测云链联动版"
    author = "猫七街"
    version = (1, 1, 4)
    description = "白名单与管理员状态检测，并向其他插件暴露可复用的管理 API。"

    DEFAULT_CFG = {
        DYNAMIC_LOAD_SETTINGS_KEY: {
            DYNAMIC_LOAD_ENABLED_KEY: True,
            DYNAMIC_LOAD_INTERVAL_KEY: DYNAMIC_LOAD_DEFAULT_INTERVAL,
        },
        "检查时间（秒）": 60.0,
        "白名单": {
            "开启状态": False,
            "踢出提示词": "请先加入白名单",
            "白名单玩家": {"xuid1": "player_name1", "xuid2": "player_name2"},
        },
        "管理员检测": {
            "开启状态": False,
            "提示词": "你没有管理员权限",
            "管理员列表": {"xuid1": "player_name1", "xuid2": "player_name2"},
        },
    }

    STD_CFG = {
        DYNAMIC_LOAD_SETTINGS_KEY: {
            DYNAMIC_LOAD_ENABLED_KEY: bool,
            DYNAMIC_LOAD_INTERVAL_KEY: cfg.PInt,
        },
        "检查时间（秒）": float,
        "白名单": {"开启状态": bool, "踢出提示词": str, "白名单玩家": {}},
        "管理员检测": {"开启状态": bool, "提示词": str, "管理员列表": {}},
    }

    def __init__(self, frame):
        """初始化运行时状态并注册插件生命周期回调。"""
        super().__init__(frame)
        self.get_xuid = None
        self.bot_name = ""
        self._stop_event = threading.Event()
        self._config_file_state = None
        self._cfg = self.load_config()
        self.refresh_config_file_state()
        self.config_thread = utils.createThread(
            self.config_reload_task,
            usage="白名单&管理员检测配置热更新任务",
        )

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenFrameExit(self.on_frame_exit)

    @classmethod
    def merge_with_default(cls, raw: Any, default: Any):
        """递归合并用户配置和默认配置。"""
        if isinstance(default, dict):
            result = {
                key: cls.merge_with_default(
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
        return copy.deepcopy(raw) if raw is not None else copy.deepcopy(default)

    @staticmethod
    def trim_fixed_keys(raw: Any, default: dict[str, Any]) -> dict[str, Any]:
        raw = raw if isinstance(raw, dict) else {}
        return {
            key: copy.deepcopy(raw.get(key, value))
            for key, value in default.items()
        }

    @staticmethod
    def normalize_bool(value: Any, fallback: bool) -> bool:
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
    def normalize_positive_int(value: Any, fallback: int) -> int:
        if isinstance(value, bool):
            return fallback
        try:
            result = int(value)
        except (TypeError, ValueError):
            return fallback
        return result if result > 0 else fallback

    @staticmethod
    def normalize_positive_float(value: Any, fallback: float) -> float:
        if isinstance(value, bool):
            return fallback
        try:
            result = float(value)
        except (TypeError, ValueError):
            return fallback
        return result if result > 0 else fallback

    @staticmethod
    def normalize_str(value: Any, fallback: str, *, allow_empty: bool = False) -> str:
        if value is None:
            return fallback
        text = str(value)
        if text or allow_empty:
            return text
        return fallback

    @classmethod
    def normalize_player_mapping(cls, raw: Any, fallback: dict[str, str]) -> dict[str, str]:
        source = raw if isinstance(raw, dict) else fallback
        result: dict[str, str] = {}
        for xuid, player_name in source.items():
            xuid_text = str(xuid).strip()
            if not xuid_text:
                continue
            result[xuid_text] = cls.normalize_str(player_name, "", allow_empty=True)
        return result

    @classmethod
    def normalize_config(cls, raw_cfg: Any) -> dict[str, Any]:
        merged_cfg = cls.merge_with_default(raw_cfg, cls.DEFAULT_CFG)
        normalized = cls.trim_fixed_keys(merged_cfg, cls.DEFAULT_CFG)

        dynamic_default = cls.DEFAULT_CFG[DYNAMIC_LOAD_SETTINGS_KEY]
        dynamic = cls.trim_fixed_keys(
            normalized.get(DYNAMIC_LOAD_SETTINGS_KEY),
            dynamic_default,
        )
        dynamic[DYNAMIC_LOAD_ENABLED_KEY] = cls.normalize_bool(
            dynamic.get(DYNAMIC_LOAD_ENABLED_KEY),
            dynamic_default[DYNAMIC_LOAD_ENABLED_KEY],
        )
        dynamic[DYNAMIC_LOAD_INTERVAL_KEY] = cls.normalize_positive_int(
            dynamic.get(DYNAMIC_LOAD_INTERVAL_KEY),
            dynamic_default[DYNAMIC_LOAD_INTERVAL_KEY],
        )
        normalized[DYNAMIC_LOAD_SETTINGS_KEY] = dynamic

        normalized["检查时间（秒）"] = cls.normalize_positive_float(
            normalized.get("检查时间（秒）"),
            cls.DEFAULT_CFG["检查时间（秒）"],
        )

        whitelist_default = cls.DEFAULT_CFG["白名单"]
        whitelist = cls.trim_fixed_keys(normalized.get("白名单"), whitelist_default)
        whitelist["开启状态"] = cls.normalize_bool(
            whitelist.get("开启状态"),
            whitelist_default["开启状态"],
        )
        whitelist["踢出提示词"] = cls.normalize_str(
            whitelist.get("踢出提示词"),
            whitelist_default["踢出提示词"],
        )
        whitelist["白名单玩家"] = cls.normalize_player_mapping(
            whitelist.get("白名单玩家"),
            whitelist_default["白名单玩家"],
        )
        normalized["白名单"] = whitelist

        admin_default = cls.DEFAULT_CFG["管理员检测"]
        admin_check = cls.trim_fixed_keys(normalized.get("管理员检测"), admin_default)
        admin_check["开启状态"] = cls.normalize_bool(
            admin_check.get("开启状态"),
            admin_default["开启状态"],
        )
        admin_check["提示词"] = cls.normalize_str(
            admin_check.get("提示词"),
            admin_default["提示词"],
        )
        admin_check["管理员列表"] = cls.normalize_player_mapping(
            admin_check.get("管理员列表"),
            admin_default["管理员列表"],
        )
        normalized["管理员检测"] = admin_check

        return normalized

    def load_config(self) -> dict[str, Any]:
        """读取配置文件并做结构校验，失败时退回默认值。"""
        try:
            raw_cfg, _ = cfg.get_plugin_config_and_version(
                self.name,
                {},
                self.DEFAULT_CFG,
                self.version,
            )
            merged_cfg = self.normalize_config(raw_cfg)
            cfg.check_auto(self.STD_CFG, merged_cfg)
        except Exception as err:
            fmts.print_err(f"加载配置文件出错: {err}")
            merged_cfg = self.normalize_config({})
            cfg.check_auto(self.STD_CFG, merged_cfg)
        cfg.upgrade_plugin_config(self.name, merged_cfg, self.version)
        return merged_cfg

    def save_cfg(self):
        """把当前内存中的配置写回插件配置文件。"""
        cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
        self.refresh_config_file_state()

    def config_file_path(self) -> str:
        return os.path.join(CONFIG_FILE_DIR, f"{self.name}.json")

    @staticmethod
    def file_state(path: str) -> tuple[int, int] | None:
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def refresh_config_file_state(self):
        self._config_file_state = self.file_state(self.config_file_path())

    def is_dynamic_config_reload_enabled(self) -> bool:
        settings = self._cfg.get(DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return True
        return bool(settings.get(DYNAMIC_LOAD_ENABLED_KEY, True))

    def dynamic_config_reload_interval(self) -> int:
        settings = self._cfg.get(DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return DYNAMIC_LOAD_DEFAULT_INTERVAL
        try:
            interval = int(settings.get(DYNAMIC_LOAD_INTERVAL_KEY, DYNAMIC_LOAD_DEFAULT_INTERVAL))
        except (TypeError, ValueError):
            return DYNAMIC_LOAD_DEFAULT_INTERVAL
        return interval if interval > 0 else DYNAMIC_LOAD_DEFAULT_INTERVAL

    def reload_runtime_config(self, announce: bool = False):
        self._cfg = self.load_config()
        self.refresh_config_file_state()
        if announce:
            fmts.print_suc(f"{self.name} 配置文件已热更新")

    def config_reload_task(self):
        while not self._stop_event.wait(self.dynamic_config_reload_interval()):
            if not self.is_dynamic_config_reload_enabled():
                self.refresh_config_file_state()
                continue
            current_state = self.file_state(self.config_file_path())
            if current_state == self._config_file_state:
                continue
            try:
                self.reload_runtime_config(announce=True)
            except Exception as err:
                self._config_file_state = current_state
                fmts.print_err(f"{self.name} 配置文件热更新失败: {err}")

    def api_reload_checker_config(self) -> tuple[bool, str, dict[str, int | float | bool]]:
        try:
            self.reload_runtime_config(announce=False)
        except Exception as err:
            return False, f"白名单&管理员检测配置重载失败: {err}", self.get_runtime_status()
        return True, "白名单&管理员检测配置已重载", self.get_runtime_status()

    def on_preload(self):
        """在 preload 阶段获取 XUID 查询前置插件。"""
        self.get_xuid = self.GetPluginAPI("XUID获取")

    def on_active(self):
        """在插件激活后挂载控制台入口并启动周期检测。"""
        self.bot_name = self.resolve_bot_name()
        self.frame.add_console_cmd_trigger(
            ["白名单"],
            None,
            "在控制台修改白名单（需要玩家先登录一次服务器）",
            self.console_manage_whitelist,
        )
        self.frame.add_console_cmd_trigger(
            ["OP操作"],
            None,
            "在控制台修改服务器 OP（需要玩家先登录一次服务器）",
            self.console_manage_admins,
        )
        self.start_periodic_check()

    def on_frame_exit(self, _):
        self._stop_event.set()

    def resolve_bot_name(self) -> str:
        """尽量用通用 ToolDelta 能力识别机器人名，避免绑定 NeOmega 接入点。"""
        bot_name = getattr(self.game_ctrl, "bot_name", "")
        if bot_name:
            return bot_name

        get_bot_name = getattr(self.frame.launcher, "get_bot_name", None)
        if callable(get_bot_name):
            try:
                bot_name = get_bot_name()
            except Exception:
                bot_name = ""
            if bot_name:
                return bot_name

        omega = getattr(self.frame.launcher, "omega", None)
        if omega is None:
            return ""
        try:
            return getattr(omega.get_bot_basic_info(), "BotName", "") or ""
        except Exception:
            return ""

    def on_player_join(self, player: Player):
        """玩家进服时按当前配置执行白名单和管理员状态检查。"""
        if self._is_bot_player(player.name):
            return
        if self._cfg["白名单"]["开启状态"]:
            self.enforce_whitelist(player.name, player.xuid)
        if self._cfg["管理员检测"]["开启状态"]:
            self.enforce_admin_state(player.name, player.xuid)

    def _is_bot_player(self, player_name: str) -> bool:
        """判断给定玩家名是否就是当前机器人自己。"""
        return bool(self.bot_name) and player_name == self.bot_name

    def resolve_player_xuid(self, player_name: str) -> tuple[str | None, str]:
        """根据玩家名解析 XUID，失败时返回错误信息。"""
        try:
            player_xuid = self.get_xuid.get_xuid_by_name(
                player_name,
                allow_offline=True,
            )
        except Exception:
            return None, "玩家未加入过服务器或无法获取 XUID"
        return player_xuid, ""

    def add_whitelist_player(self, player_name: str) -> tuple[bool, str]:
        """把玩家加入白名单。"""
        return self.add_player_mapping(
            player_name,
            "白名单",
            "白名单玩家",
            "玩家已存在白名单中",
            "已添加玩家 {player_name} 到白名单",
        )

    def remove_whitelist_player(self, player_name: str) -> tuple[bool, str]:
        """把玩家从白名单中移除。"""
        return self.remove_player_mapping(
            player_name,
            "白名单",
            "白名单玩家",
            "玩家不存在白名单中",
            "已从白名单中移除玩家 {player_name}",
        )

    def add_admin_player(self, player_name: str) -> tuple[bool, str]:
        """把玩家登记为服务器管理员。"""
        return self.add_player_mapping(
            player_name,
            "管理员检测",
            "管理员列表",
            "玩家已经是服务器管理员",
            "已添加玩家 {player_name} 为服务器管理员",
        )

    def remove_admin_player(self, player_name: str) -> tuple[bool, str]:
        """把玩家从服务器管理员名单中移除。"""
        return self.remove_player_mapping(
            player_name,
            "管理员检测",
            "管理员列表",
            "玩家不是服务器管理员",
            "已将玩家 {player_name} 从服务器管理员中移除",
        )

    def add_player_mapping(
        self,
        player_name: str,
        section: str,
        key: str,
        duplicate_message: str,
        success_message: str,
    ) -> tuple[bool, str]:
        """向指定映射表添加一个以 XUID 为键的玩家条目。"""
        player_xuid, error = self.resolve_player_xuid(player_name)
        if player_xuid is None:
            return False, error
        mapping = self._cfg[section][key]
        if player_xuid in mapping:
            return False, duplicate_message
        mapping[player_xuid] = player_name
        self.save_cfg()
        return True, success_message.format(player_name=player_name)

    def remove_player_mapping(
        self,
        player_name: str,
        section: str,
        key: str,
        missing_message: str,
        success_message: str,
    ) -> tuple[bool, str]:
        """从指定映射表移除一个以 XUID 为键的玩家条目。"""
        player_xuid, error = self.resolve_player_xuid(player_name)
        if player_xuid is None:
            return False, error
        mapping = self._cfg[section][key]
        if player_xuid not in mapping:
            return False, missing_message
        mapping.pop(player_xuid)
        self.save_cfg()
        return True, success_message.format(player_name=player_name)

    def set_whitelist_enabled(self, enabled: bool) -> tuple[bool, str]:
        """切换白名单检测开关。"""
        self._cfg["白名单"]["开启状态"] = enabled
        self.save_cfg()
        return True, f"白名单检测已{'开启' if enabled else '关闭'}"

    def set_admin_check_enabled(self, enabled: bool) -> tuple[bool, str]:
        """切换管理员检测开关。"""
        self._cfg["管理员检测"]["开启状态"] = enabled
        self.save_cfg()
        return True, f"管理员检测已{'开启' if enabled else '关闭'}"

    def set_check_interval(self, seconds: float) -> tuple[bool, str]:
        """更新周期检测的轮询间隔。"""
        if seconds <= 0:
            return False, "检测周期必须大于 0"
        self._cfg["检查时间（秒）"] = float(seconds)
        self.save_cfg()
        return True, f"检测周期已设置为 {seconds} 秒"

    def get_runtime_status(self) -> dict[str, int | float | bool]:
        """返回给其他插件使用的当前运行状态摘要。"""
        return {
            "check_interval": self._cfg["检查时间（秒）"],
            "whitelist_enabled": self._cfg["白名单"]["开启状态"],
            "whitelist_count": len(self._cfg["白名单"]["白名单玩家"]),
            "admin_check_enabled": self._cfg["管理员检测"]["开启状态"],
            "admin_count": len(self._cfg["管理员检测"]["管理员列表"]),
        }

    def enforce_whitelist(self, player_name: str, player_xuid: str):
        """对白名单未命中的玩家执行踢出。"""
        if player_xuid in self._cfg["白名单"]["白名单玩家"]:
            return
        self.game_ctrl.sendwocmd(
            f"kick {player_xuid} {self._cfg['白名单']['踢出提示词']}"
        )

    def enforce_admin_state(self, player_name: str, player_xuid: str):
        """同步服务器 OP 状态与插件配置中的管理员登记状态。"""
        is_registered_admin = player_xuid in self._cfg["管理员检测"]["管理员列表"]
        is_server_op = game_utils.is_op(player_name)

        if is_server_op and not is_registered_admin:
            self.game_ctrl.sendwocmd(f"/say 检测到存在非法管理员：{player_name}")
            self.game_ctrl.sendwocmd(f"/deop {player_name}")
            self.game_ctrl.sendwocmd(
                f"/tell {player_name} {self._cfg['管理员检测']['提示词']}"
            )
            return

        if not is_server_op and is_registered_admin:
            self.game_ctrl.sendwocmd(f"/op {player_name}")

    def console_manage_whitelist(self, _args: list[str]):
        """打开控制台白名单管理菜单。"""
        self.console_manage_player_mapping(
            title="白名单",
            add_action=self.add_whitelist_player,
            remove_action=self.remove_whitelist_player,
            add_prompt="请输入要添加的玩家昵称：",
            remove_prompt="请输入要移除的玩家昵称：",
        )

    def console_manage_admins(self, _args: list[str]):
        """打开控制台服务器管理员管理菜单。"""
        self.console_manage_player_mapping(
            title="服务器管理员",
            add_action=self.add_admin_player,
            remove_action=self.remove_admin_player,
            add_prompt="请输入要添加的玩家昵称：",
            remove_prompt="请输入要移除的玩家昵称：",
        )

    def console_manage_player_mapping(
        self,
        title: str,
        add_action,
        remove_action,
        add_prompt: str,
        remove_prompt: str,
    ):
        """复用同一套控制台交互来管理白名单和管理员列表。"""
        option_add = f"添加{title}"
        option_remove = f"移除{title}"
        while True:
            fmts.print_inf("选择你要进行的操作：")
            fmts.print_inf(f"1. {option_add}")
            fmts.print_inf(f"2. {option_remove}")
            fmts.print_inf("q. 退出操作")
            choice = input().strip().lower()
            if choice == "q":
                fmts.print_inf("已退出操作")
                return
            if choice == "1":
                player_name = input(fmts.fmt_info(add_prompt)).strip()
                ok, message = add_action(player_name)
                self.print_console_result(ok, message)
                return
            if choice == "2":
                player_name = input(fmts.fmt_info(remove_prompt)).strip()
                ok, message = remove_action(player_name)
                self.print_console_result(ok, message)
                return
            fmts.print_err("无效的选项")

    @staticmethod
    def print_console_result(ok: bool, message: str):
        """统一输出控制台操作结果，减少重复分支。"""
        if ok:
            fmts.print_suc(message)
        else:
            fmts.print_err(message)

    @utils.thread_func("循环检测白名单和管理员")
    def start_periodic_check(self):
        """按配置周期轮询在线玩家，补做白名单和管理员状态校验。"""
        while not self._stop_event.wait(float(self._cfg["检查时间（秒）"])):
            for player in self.frame.get_players().getAllPlayers():
                if self._is_bot_player(player.name):
                    continue
                if self._cfg["白名单"]["开启状态"]:
                    self.enforce_whitelist(player.name, player.xuid)
                if self._cfg["管理员检测"]["开启状态"]:
                    self.enforce_admin_state(player.name, player.xuid)


entry = plugin_entry(WhitelistAndOpCheck, "白名单&管理员检测云链联动版")

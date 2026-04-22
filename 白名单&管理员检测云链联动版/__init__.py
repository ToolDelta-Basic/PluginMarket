import time
from typing import Any

from tooldelta import Player, Plugin, cfg, fmts, game_utils, plugin_entry, utils
from tooldelta.internal.launch_cli import FrameNeOmgAccessPoint


class WhitelistAndOpCheck(Plugin):
    name = "白名单&管理员检测云链联动版"
    author = "猫七街"
    version = (1, 1, 2)
    description = "白名单与管理员状态检测，并向其他插件暴露可复用的管理 API。"

    DEFAULT_CFG = {
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
        "检查时间（秒）": float,
        "白名单": {"开启状态": bool, "踢出提示词": str, "白名单玩家": {}},
        "管理员检测": {"开启状态": bool, "提示词": str, "管理员列表": {}},
    }

    def __init__(self, frame):
        super().__init__(frame)
        self.get_xuid = None
        self.neomega = None
        self.bot_name = ""
        self._cfg = self.load_config()

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)

    @classmethod
    def merge_with_default(cls, raw: Any, default: Any):
        if isinstance(default, dict):
            result = {
                key: cls.merge_with_default(None, value)
                for key, value in default.items()
            }
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key in result:
                        result[key] = cls.merge_with_default(value, result[key])
                    else:
                        result[key] = value
            return result
        return raw if raw is not None else default

    def load_config(self) -> dict[str, Any]:
        try:
            raw_cfg, _ = cfg.get_plugin_config_and_version(
                self.name,
                {},
                self.DEFAULT_CFG,
                self.version,
            )
            merged_cfg = self.merge_with_default(raw_cfg, self.DEFAULT_CFG)
            cfg.check_auto(self.STD_CFG, merged_cfg)
        except Exception as err:
            fmts.print_err(f"加载配置文件出错: {err}")
            merged_cfg = self.merge_with_default({}, self.DEFAULT_CFG)
        cfg.upgrade_plugin_config(self.name, merged_cfg, self.version)
        return merged_cfg

    def save_cfg(self):
        cfg.upgrade_plugin_config(self.name, self._cfg, self.version)

    def on_preload(self):
        self.get_xuid = self.GetPluginAPI("XUID获取")

    def on_active(self):
        self.neomega = self.require_neomega()
        self.bot_name = self.neomega.get_bot_basic_info().BotName
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

    def require_neomega(self):
        if isinstance(self.frame.launcher, FrameNeOmgAccessPoint):
            return self.frame.launcher.omega
        raise ValueError("此启动框架无法使用 NeOmega API")

    def on_player_join(self, player: Player):
        if self._is_bot_player(player.name):
            return
        if self._cfg["白名单"]["开启状态"]:
            self.enforce_whitelist(player.name, player.xuid)
        if self._cfg["管理员检测"]["开启状态"]:
            self.enforce_admin_state(player.name, player.xuid)

    def _is_bot_player(self, player_name: str) -> bool:
        return bool(self.bot_name) and player_name == self.bot_name

    def resolve_player_xuid(self, player_name: str) -> tuple[str | None, str]:
        try:
            player_xuid = self.get_xuid.get_xuid_by_name(player_name, allow_offline=True)
        except Exception:
            return None, "玩家未加入过服务器或无法获取 XUID"
        return player_xuid, ""

    def add_whitelist_player(self, player_name: str) -> tuple[bool, str]:
        return self.add_player_mapping(
            player_name,
            "白名单",
            "白名单玩家",
            "玩家已存在白名单中",
            "已添加玩家 {player_name} 到白名单",
        )

    def remove_whitelist_player(self, player_name: str) -> tuple[bool, str]:
        return self.remove_player_mapping(
            player_name,
            "白名单",
            "白名单玩家",
            "玩家不存在白名单中",
            "已从白名单中移除玩家 {player_name}",
        )

    def add_admin_player(self, player_name: str) -> tuple[bool, str]:
        return self.add_player_mapping(
            player_name,
            "管理员检测",
            "管理员列表",
            "玩家已经是服务器管理员",
            "已添加玩家 {player_name} 为服务器管理员",
        )

    def remove_admin_player(self, player_name: str) -> tuple[bool, str]:
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
        self._cfg["白名单"]["开启状态"] = enabled
        self.save_cfg()
        return True, f"白名单检测已{'开启' if enabled else '关闭'}"

    def set_admin_check_enabled(self, enabled: bool) -> tuple[bool, str]:
        self._cfg["管理员检测"]["开启状态"] = enabled
        self.save_cfg()
        return True, f"管理员检测已{'开启' if enabled else '关闭'}"

    def set_check_interval(self, seconds: float) -> tuple[bool, str]:
        if seconds <= 0:
            return False, "检测周期必须大于 0"
        self._cfg["检查时间（秒）"] = float(seconds)
        self.save_cfg()
        return True, f"检测周期已设置为 {seconds} 秒"

    def get_runtime_status(self) -> dict[str, int | float | bool]:
        return {
            "check_interval": self._cfg["检查时间（秒）"],
            "whitelist_enabled": self._cfg["白名单"]["开启状态"],
            "whitelist_count": len(self._cfg["白名单"]["白名单玩家"]),
            "admin_check_enabled": self._cfg["管理员检测"]["开启状态"],
            "admin_count": len(self._cfg["管理员检测"]["管理员列表"]),
        }

    def enforce_whitelist(self, player_name: str, player_xuid: str):
        if player_xuid in self._cfg["白名单"]["白名单玩家"]:
            return
        self.game_ctrl.sendwocmd(
            f"kick {player_xuid} {self._cfg['白名单']['踢出提示词']}"
        )

    def enforce_admin_state(self, player_name: str, player_xuid: str):
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
        self.console_manage_player_mapping(
            title="白名单",
            add_action=self.add_whitelist_player,
            remove_action=self.remove_whitelist_player,
            add_prompt="请输入要添加的玩家昵称：",
            remove_prompt="请输入要移除的玩家昵称：",
        )

    def console_manage_admins(self, _args: list[str]):
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
        while True:
            time.sleep(float(self._cfg["检查时间（秒）"]))
            for player in self.frame.get_players().getAllPlayers():
                if self._is_bot_player(player.name):
                    continue
                if self._cfg["白名单"]["开启状态"]:
                    self.enforce_whitelist(player.name, player.xuid)
                if self._cfg["管理员检测"]["开启状态"]:
                    self.enforce_admin_state(player.name, player.xuid)


entry = plugin_entry(WhitelistAndOpCheck, "白名单&管理员检测云链联动版")

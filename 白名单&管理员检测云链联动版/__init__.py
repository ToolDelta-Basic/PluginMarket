from tooldelta import (
    Plugin,
    cfg,
    fmts,
    game_utils,
    utils,
    Player,
    plugin_entry,
)

from tooldelta.internal.launch_cli import FrameNeOmgAccessPoint
import time


class whitelist_and_opcheck(Plugin):
    name = "白名单&管理员检测云链联动版"
    author = "猫七街"
    version = (1, 1, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.bot = None
        self._default_cfg = {
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
        self._std_cfg = {
            "检查时间（秒）": float,
            "白名单": {"开启状态": bool, "踢出提示词": str, "白名单玩家": {}},
            "管理员检测": {"开启状态": bool, "提示词": str, "管理员列表": {}},
        }
        try:
            raw_cfg, _ = cfg.get_plugin_config_and_version(
                self.name, {}, self._default_cfg, self.version
            )
            self._cfg = self.merge_with_default(raw_cfg, self._default_cfg)
            cfg.check_auto(self._std_cfg, self._cfg)
            cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
        except Exception as e:
            fmts.print_err(f"加载配置文件出错: {e}")
            self._cfg = self.merge_with_default({}, self._default_cfg)
            cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)

    # ---------------- API ----------------
    @classmethod
    def merge_with_default(cls, raw: dict | None, default: dict):
        result = {}
        for key, value in default.items():
            if isinstance(value, dict):
                next_raw = raw.get(key, {}) if isinstance(raw, dict) else {}
                result[key] = cls.merge_with_default(
                    next_raw if isinstance(next_raw, dict) else {},
                    value,
                )
            else:
                if isinstance(raw, dict) and key in raw:
                    result[key] = raw[key]
                else:
                    result[key] = value
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key not in result:
                    result[key] = value
        return result

    def save_cfg(self):
        cfg.upgrade_plugin_config(self.name, self._cfg, self.version)

    def resolve_player_xuid(self, player_name: str) -> tuple[str | None, str]:
        try:
            player_uuid = self.get_xuid.get_xuid_by_name(player_name, allow_offline=True)
            return player_uuid, ""
        except Exception:
            return None, "玩家未加入过服务器或无法获取 XUID"

    def add_whitelist_player(self, player_name: str) -> tuple[bool, str]:
        player_uuid, error = self.resolve_player_xuid(player_name)
        if player_uuid is None:
            return False, error
        if player_uuid in self._cfg["白名单"]["白名单玩家"]:
            return False, "玩家已存在白名单中"
        self._cfg["白名单"]["白名单玩家"][player_uuid] = player_name
        self.save_cfg()
        return True, f"已添加玩家 {player_name} 到白名单"

    def remove_whitelist_player(self, player_name: str) -> tuple[bool, str]:
        player_uuid, error = self.resolve_player_xuid(player_name)
        if player_uuid is None:
            return False, error
        if player_uuid not in self._cfg["白名单"]["白名单玩家"]:
            return False, "玩家不存在白名单中"
        self._cfg["白名单"]["白名单玩家"].pop(player_uuid)
        self.save_cfg()
        return True, f"已从白名单中移除玩家 {player_name}"

    def add_admin_player(self, player_name: str) -> tuple[bool, str]:
        player_uuid, error = self.resolve_player_xuid(player_name)
        if player_uuid is None:
            return False, error
        if player_uuid in self._cfg["管理员检测"]["管理员列表"]:
            return False, "玩家已经是服务器管理员"
        self._cfg["管理员检测"]["管理员列表"][player_uuid] = player_name
        self.save_cfg()
        return True, f"已添加玩家 {player_name} 为服务器管理员"

    def remove_admin_player(self, player_name: str) -> tuple[bool, str]:
        player_uuid, error = self.resolve_player_xuid(player_name)
        if player_uuid is None:
            return False, error
        if player_uuid not in self._cfg["管理员检测"]["管理员列表"]:
            return False, "玩家不是服务器管理员"
        self._cfg["管理员检测"]["管理员列表"].pop(player_uuid)
        self.save_cfg()
        return True, f"已将玩家 {player_name} 从服务器管理员中移除"

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

    def get_runtime_status(self) -> dict:
        return {
            "check_interval": self._cfg["检查时间（秒）"],
            "whitelist_enabled": self._cfg["白名单"]["开启状态"],
            "whitelist_count": len(self._cfg["白名单"]["白名单玩家"]),
            "admin_check_enabled": self._cfg["管理员检测"]["开启状态"],
            "admin_count": len(self._cfg["管理员检测"]["管理员列表"]),
        }

    def on_def(self):
        self.get_xuid = self.GetPluginAPI("XUID获取")

    def get_neomega(self):
        if isinstance(self.frame.launcher, FrameNeOmgAccessPoint):
            return self.frame.launcher.omega

        else:
            raise ValueError("此启动框架无法使用 NeOmega API")

    def on_player_join(self, player: Player):
        player_name = player.name
        xuid = player.xuid

        if self._cfg["白名单"]["开启状态"]:
            self.whitelist_check(player_name, xuid)

        if self._cfg["管理员检测"]["开启状态"]:
            self.operation_check(player_name)

    def whitelist_check(self, player_name: str | None, xuid: str):
        player = self.player(player_name)
        player_uuid = player[1]
        if player_name == self.bot.BotName:
            return

        if player_uuid not in self._cfg["白名单"]["白名单玩家"]:
            self.game_ctrl.sendwocmd(
                f"kick {xuid} " + self._cfg["白名单"]["踢出提示词"]
            )
            return

        return

    def operation_check(self, player_name: str | None):
        player = self.player(player_name)
        player_uuid = player[1]
        if player_name == self.bot.BotName:
            return

        flag = game_utils.is_op(player_name)
        if flag:
            if player_uuid not in self._cfg["管理员检测"]["管理员列表"]:
                self.game_ctrl.sendwocmd(f"/say 检测到存在非法管理员：{player_name}")
                self.game_ctrl.sendwocmd(f"/deop {player_name}")
                self.game_ctrl.sendwocmd(
                    f"/tell {player_name} {self._cfg['管理员检测']['提示词']}"
                )
                return

        else:
            if player_uuid in self._cfg["管理员检测"]["管理员列表"]:
                self.game_ctrl.sendwocmd(f"/op {player_name}")
                return

        return

    def whitelist_console_set(self, args: list):
        fmts.print_inf("选择你要进行的操作：")
        fmts.print_inf("1. 添加玩家到白名单")
        fmts.print_inf("2. 从白名单中移除玩家")
        fmts.print_inf("q. 退出操作")
        while True:
            choice = input()
            if choice == "q":
                fmts.print_inf("已退出操作")
                return

            if choice == "1":
                player_name = input(fmts.fmt_info("请输入要添加的玩家昵称："))
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    fmts.print_err("玩家未加入过服务器")
                    return

                if player_uuid in self._cfg["白名单"]["白名单玩家"]:
                    fmts.print_inf("玩家已存在白名单中")
                    return

                self._cfg["白名单"]["白名单玩家"][player_uuid] = player_name
                cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
                fmts.print_suc(f"已添加玩家{player_name}到白名单")
                return

            if choice == "2":
                player_name = input(fmts.fmt_info("请输入玩家昵称："))
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    player_uuid = ""
                if player_uuid not in self._cfg["白名单"]["白名单玩家"]:
                    fmts.print_inf("玩家不存在白名单中")
                    return

                self._cfg["白名单"]["白名单玩家"].pop(player_uuid)
                cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
                fmts.print_suc(f"已从白名单中移除玩家{player_name}")
                return

            fmts.print_err("无效的选项")
            fmts.print_inf("选择你要进行的操作：")
            fmts.print_inf("1. 添加玩家到白名单")
            fmts.print_inf("2. 从白名单中移除玩家")
            fmts.print_inf("q. 退出操作")

    def operation_console(self, args: list):
        fmts.print_inf("选择你要进行的操作：")
        fmts.print_inf("1. 添加OP")
        fmts.print_inf("2. 移除OP")
        fmts.print_inf("q. 退出操作")
        while True:
            choice = input()
            if choice == "q":
                fmts.print_inf("已退出操作")
                return

            if choice == "1":
                player_name = input(fmts.fmt_info("请输入要添加的玩家昵称："))
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    fmts.print_err("玩家未加入过服务器")
                    return

                if player_uuid in self._cfg["管理员检测"]["管理员列表"]:
                    fmts.print_err("玩家已经是OP")
                    return

                self._cfg["管理员检测"]["管理员列表"][player_uuid] = player_name
                cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
                fmts.print_suc(f"已添加玩家{player_name}为OP")
                return

            if choice == "2":
                player_name = input(fmts.fmt_info("请输入玩家昵称："))
                try:
                    player_uuid = self.get_xuid.get_xuid_by_name(player_name)

                except:
                    player_uuid = ""

                if player_uuid not in self._cfg["管理员检测"]["管理员列表"]:
                    fmts.print_inf("玩家不是OP")
                    return

                self._cfg["管理员检测"]["管理员列表"].pop(player_uuid)
                cfg.upgrade_plugin_config(self.name, self._cfg, self.version)
                fmts.print_inf(f"已将玩家{player_name}从OP中移除")
                return
            fmts.print_err("无效的选项")
            fmts.print_inf("选择你要进行的操作：")
            fmts.print_inf("1. 添加OP")
            fmts.print_inf("2. 移除OP")
            fmts.print_inf("q. 退出操作")

    def auto_check(self):
        while True:
            time.sleep(self._cfg["检查时间（秒）"])
            players = self.frame.get_players().getAllPlayers()
            for player in players:
                name = player.name
                xuid = player.xuid
                if self._cfg["白名单"]["开启状态"]:
                    self.whitelist_check(name, xuid)

                if self._cfg["管理员检测"]["开启状态"]:
                    self.operation_check(name)

    def player(self, player_name: str | None = None, player_uuid: str | None = None):
        if player_name is not None:
            player = [player_name, None]
            try:
                player_uuid = self.get_xuid.get_xuid_by_name(
                    player_name, allow_offline=True
                )
            except Exception as e:
                # 增强异常处理：避免 KeyError
                if player_name in self.game_ctrl.players_uuid:
                    player_uuid = self.game_ctrl.players_uuid[player_name]
                else:
                    fmts.print_err(f"玩家 {player_name} 未在线或不存在")
                    player_uuid = ""
            player[1] = player_uuid
            return player
        elif player_uuid is not None:
            player = [None, player_uuid]
            try:
                player_name = self.get_xuid.get_name_by_xuid(player_uuid)
            except Exception as e:
                # 增强异常处理：避免 AttributeError
                if hasattr(self, "neomega"):
                    player_name = self.neomega.get_player_by_uuid(player_uuid).name
                else:
                    fmts.print_err(f"无效的 UUID: {player_uuid}")
                    player_name = ""
            player[0] = player_name
            return player
        else:
            fmts.print_err("player() 方法需要至少一个参数")
            return [None, None]

    def on_inject(self):
        neomega = self.get_neomega()
        self.neomega = self.get_neomega()
        self.bot = neomega.get_bot_basic_info()
        self.frame.add_console_cmd_trigger(
            ["白名单"],
            None,
            "在控制台修改白名单（需要玩家先登录一次服务器）",
            self.whitelist_console_set,
        )
        self.frame.add_console_cmd_trigger(
            ["OP操作"],
            None,
            "在控制台修改服务器OP（需要玩家先登录一次服务器）",
            self.operation_console,
        )
        self.auto_check_task = utils.createThread(
            self.auto_check, (), "循环检测白名单和管理员"
        )


entry = plugin_entry(whitelist_and_opcheck, "白名单&管理员检测云链联动版")

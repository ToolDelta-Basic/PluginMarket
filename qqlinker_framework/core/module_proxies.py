import inspect
import logging
from typing import Any


class _ConfigProxy:
    """配置代理: self.config.键 自动调用 config.get("键")。

    传入 caller_mid 防止越权。
    """

    __slots__ = ("_cfg", "_caller_mid")

    def __init__(self, config_svc, caller_mid=400):
        self._cfg = config_svc
        self._caller_mid = caller_mid

    def __getattr__(self, key: str):
        if key.startswith("_"):
            raise AttributeError(key)
        return self._cfg.get(key, requester_uid=self._caller_mid)

    def get(self, key: str, default=None):
        """获取配置值。"""
        return self._cfg.get(key, default, requester_uid=self._caller_mid)

    def set(self, key: str, value):
        """设置配置值。"""
        return self._cfg.set(key, value, requester_uid=self._caller_mid)

    def save(self):
        """保存配置。"""
        return self._cfg.save()

    def register_section(self, section: str, defaults: dict):
        """传入 caller_mid 阻止低权限模块注册高权限配置节。"""
        return self._cfg.register_section(section, defaults, caller_uid=self._caller_mid)

    def get_data_dir(self):
        """获取数据目录路径。"""
        return self._cfg.get_data_dir()


class _GroupConfigProxy:
    """群配置代理: self.group_config.get(group_id, key) / .for_group(group_id)。

    传入 caller_mid 防止越权。
    """

    __slots__ = ("_gcfg", "_caller_mid")

    def __init__(self, group_config_svc, caller_mid=400):
        self._gcfg = group_config_svc
        self._caller_mid = caller_mid

    def __getattr__(self, key: str):
        """代理底层 GroupConfigManager 的属性。"""
        if key.startswith("_"):
            raise AttributeError(key)
        return getattr(self._gcfg, key)

    def get(self, group_id: int, key: str, default=None):
        """获取指定群的配置值。"""
        return self._gcfg.get(group_id, key, default, requester_uid=self._caller_mid)

    def for_group(self, group_id: int) -> "_SingleGroupConfigProxy":
        """返回单群配置代理。"""
        return _SingleGroupConfigProxy(self._gcfg, group_id, caller_mid=self._caller_mid)

    def get_module_config(self, group_id: int, section: str) -> dict:
        """获取指定群的模块节配置。"""
        return self._gcfg.get_group_module_config(group_id, section, requester_uid=self._caller_mid)

    def register_module_schema(self, section: str, defaults: dict, scope: str):
        """注册模块配置 schema。"""
        return self._gcfg.register_module_schema(section, defaults, scope)


class _SingleGroupConfigProxy:
    """单群配置代理。"""

    __slots__ = ("_gcfg", "_group_id", "_caller_mid")

    def __init__(self, gcfg, group_id: int, caller_mid=400):
        self._gcfg = gcfg
        self._group_id = group_id
        self._caller_mid = caller_mid

    def get(self, key: str, default=None):
        """获取单群配置值。"""
        return self._gcfg.get(self._group_id, key, default, requester_uid=self._caller_mid)


class _GameProxy:
    """游戏操作代理: self.game.say/send/cmd/players。

    cmd() 强制 mid 检查 — mid≤100 (daemon+) 放行。
    """

    __slots__ = ("_adapter", "_caller_mid", "_config")

    def __init__(self, adapter, caller_mid=400, config=None):
        self._adapter = adapter
        self._caller_mid = caller_mid
        self._config = config

    def _check_cmd_permission(self) -> bool:
        """检查当前调用者是否有权限执行游戏命令。"""
        if self._caller_mid <= 100:
            return True
        if not self._config:
            return False
        whitelist = self._config.get("游戏管理.允许执行命令的模块", [])
        if not isinstance(whitelist, list):
            whitelist = []
        if not whitelist:
            return False
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            mod = frame_locals.get('self')
            if mod is not None and hasattr(mod, 'name') and hasattr(mod, 'mid'):
                if mod.mid == self._caller_mid:
                    return mod.name in whitelist
        return False

    def say(self, target: str, text: str):
        """向游戏内目标发送消息。"""
        if self._adapter:
            self._adapter.send_game_message(target, text)

    def cmd(self, command: str):
        """发送游戏指令（需 mid 白名单检查）。"""
        if not self._check_cmd_permission():
            logging.getLogger(__name__).warning(
                "游戏命令拒绝: mid=%d 不在白名单中 (cmd=%s)",
                self._caller_mid, command[:80],
            )
            return
        if self._adapter:
            self._adapter.send_game_command(command)

    def title(self, target: str, text: str):
        """显示标题栏消息。"""
        if self._adapter:
            self._adapter.send_game_title(target, text)

    def subtitle(self, target: str, text: str):
        """显示副标题消息。"""
        if self._adapter:
            self._adapter.send_game_subtitle(target, text)

    def actionbar(self, target: str, text: str):
        """显示行动栏消息。"""
        if self._adapter:
            self._adapter.send_game_actionbar(target, text)

    @property
    def players(self) -> list:
        """在线玩家列表。"""
        return self._adapter.get_online_players() if self._adapter else []

    def cmd_with_resp(self, cmd: str, timeout: float = 5.0):
        """发送指令并等响应。"""
        if self._adapter:
            return self._adapter.send_game_command_with_resp(cmd, timeout)
        return None


class _QQProxy:
    """QQ 操作代理: self.qq.send_group(gid, text) / self.qq.send_private(uid, text)。

    消息发送只走 message 服务。
    """

    __slots__ = ("_adapter", "_services", "_caller_mid")

    def __init__(self, adapter, services=None, caller_mid=400):
        self._adapter = adapter
        self._services = services
        self._caller_mid = caller_mid

    @property
    def _msg(self):
        """动态获取 message 服务。"""
        if self._services:
            try:
                return self._services.get("message")
            except (KeyError, PermissionError):
                return None
        return None

    async def send_group(self, group_id: int, text: str):
        """发送群消息（仅通过 MessageManager）。"""
        if self._msg:
            await self._msg.send_group(group_id, text, requester_uid=self._caller_mid)
        else:
            logging.getLogger(__name__).error(
                "QQ代理: message 服务不可用，消息发送被拒绝 (group_id=%s, mid=%d)",
                group_id, self._caller_mid,
            )

    async def send_private(self, user_id: int, text: str):
        """发送私聊消息（仅通过 MessageManager）。"""
        if self._msg:
            await self._msg.send_private(user_id, text, requester_uid=self._caller_mid)
        else:
            logging.getLogger(__name__).error(
                "QQ代理: message 服务不可用，消息发送被拒绝 (user_id=%s, mid=%d)",
                user_id, self._caller_mid,
            )

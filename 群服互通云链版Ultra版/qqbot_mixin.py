"""QQ 官方机器人通道与 Ultra 运行时的适配层。"""

import json
import os

from tooldelta import utils

from .qqbot_client import QQBotClient


class QQLinkerQQBotMixin:
    """管理官机连接，并把官方群事件适配到 Ultra 消息流水线。"""

    QQBOT_OPENID_FILE = "qqbot_openid.json"
    QQBOT_BINDING_UNAVAILABLE_MESSAGE = (
        "因官方机器人无法获取QQ号，所以无法使用绑定功能，如需使用，请使用云链通道"
    )
    QQBOT_ADMIN_MENU_UNAVAILABLE_MESSAGE = (
        "因官方机器人无法获取QQ号，所以无法使用管理员菜单功能，如需使用，请使用云链通道"
    )

    def on_qqbot_error(self, error_code, message, details=None) -> None:
        """使用与云链一致的状态卡片输出官机连接错误码。"""
        lines = [f"错误码: {error_code}", str(message)]
        lines.extend(str(item) for item in (details or []))
        self._print_cloud_status(
            "群服互通 官机连接",
            "异常",
            lines,
            level="error",
        )

    @staticmethod
    def _normalize_qqbot_member_role(role) -> str:
        '''把官机平台成员角色规范化为 owner、admin 或 member。'''
        role_text = str(role or "member").strip().lower()
        if role_text in {"owner", "creator", "群主", "4"}:
            return "owner"
        if role_text in {"admin", "administrator", "管理员", "2"}:
            return "admin"
        return "member"

    def _qqbot_member_role(self, group_id: int, user_id: int) -> str | None:
        '''获取官机群会话中缓存的成员角色。'''
        roles = getattr(self, "_qqbot_member_roles", {})
        return roles.get((int(group_id), int(user_id)))

    def _is_qqbot_member_identity(self, group_id: int, user_id: int) -> bool:
        """判断该会话身份是否来自无法提供真实 QQ 号的官机通道。"""
        return self._qqbot_member_role(group_id, user_id) is not None

    def _qqbot_real_qq_unavailable_message(
        self,
        group_id: int,
        user_id: int,
        feature: str,
    ) -> str | None:
        """返回官机身份调用真实 QQ 号功能时应展示的说明。"""
        if not self._is_qqbot_member_identity(group_id, user_id):
            return None
        if feature == "binding":
            return self.QQBOT_BINDING_UNAVAILABLE_MESSAGE
        if feature == "admin_menu":
            return self.QQBOT_ADMIN_MENU_UNAVAILABLE_MESSAGE
        return (
            "因官方机器人无法获取QQ号，所以无法使用该功能，"
            "如需使用，请使用云链通道"
        )

    def _reject_qqbot_real_qq_feature(
        self,
        group_id: int,
        user_id: int,
        feature: str,
    ) -> bool:
        """拦截官机通道中必须依赖真实 QQ 号的功能。"""
        message = self._qqbot_real_qq_unavailable_message(
            group_id,
            user_id,
            feature,
        )
        if message is None:
            return False
        self._reply_to_qq(group_id, user_id, message)
        return True

    def is_group_owner(self, group_id: int, qqid: int):
        '''判断会话成员是否为官机群主或其他通道群主。'''
        if self._qqbot_member_role(group_id, qqid) == "owner":
            return True
        return super().is_group_owner(group_id, qqid)

    def is_group_super_admin(self, group_id: int, qqid: int):
        '''判断会话成员是否具备最高群管理权限。'''
        if self._qqbot_member_role(group_id, qqid) == "owner":
            return True
        return super().is_group_super_admin(group_id, qqid)

    def is_group_admin(self, group_id: int, qqid: int):
        '''判断会话成员是否为官机群主、管理员或其他通道管理员。'''
        if self._qqbot_member_role(group_id, qqid) in {"owner", "admin"}:
            return True
        return super().is_group_admin(group_id, qqid)

    def has_group_permission(
        self,
        group_id: int,
        qqid: int,
        permission_name: str,
    ) -> bool:
        '''按官机成员角色和群配置判断指定功能权限。'''
        role = self._qqbot_member_role(group_id, qqid)
        if role == "owner":
            return True
        if role == "admin":
            permission_cfg = self._permission_cfg_for_group(group_id)
            if permission_cfg is None:
                return False
            feature_permissions = permission_cfg.get("各功能权限设置", {})
            item = feature_permissions.get(permission_name, {})
            return isinstance(item, dict) and bool(
                item.get("是否允许普通管理员使用", False))
        return super().has_group_permission(group_id, qqid, permission_name)

    def qqbot_channel_enabled(self) -> bool:
        '''返回配置是否启用了 QQ 官方机器人通道。'''
        settings = getattr(self, "cfg", {}).get("官机设置", {})
        return isinstance(settings, dict) and bool(
            settings.get("是否启用该通道", False))

    def qqbot_channel_available(self) -> bool:
        '''返回官机通道是否已启用且客户端已经创建。'''
        client = getattr(self, "_qqbot_client", None)
        return self.qqbot_channel_enabled() and client is not None

    def _qqbot_openid_file_path(self) -> str:
        '''返回官方群 OpenID 映射文件的数据目录路径。'''
        return self.format_data_path(self.QQBOT_OPENID_FILE)

    def _load_qqbot_openid_map(self) -> dict[str, str]:
        '''从插件数据目录读取并清洗群号与 OpenID 映射。'''
        try:
            with open(
                self._qqbot_openid_file_path(),
                encoding="utf-8",
            ) as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(group_id): str(openid)
            for group_id, openid in data.items()
            if str(group_id).isdigit() and str(openid)
        }

    def _save_qqbot_openid_map(self, data: dict[str, str]) -> None:
        '''把群号与官方群 OpenID 映射保存到插件数据目录。'''
        path = self._qqbot_openid_file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def start_qqbot_connection(self) -> None:
        '''根据配置创建并启动 QQ 官方机器人客户端。'''
        if not self.qqbot_channel_enabled():
            self.stop_qqbot_connection()
            return
        settings = self.cfg.get("官机设置", {})
        app_id = str(settings.get("AppID", "")).strip()
        app_secret = str(settings.get("AppSecret", "")).strip()
        if not app_id or not app_secret:
            self.stop_qqbot_connection()
            self.print_console_warn(
                "官机通道已启用，但 AppID 或 AppSecret 为空，未启动该通道")
            self.on_qqbot_error(
                "QQBOT-1002",
                "官机连接配置不完整",
                ["AppID 或 AppSecret 为空"],
            )
            return

        self.stop_qqbot_connection()
        openid_map = self._load_qqbot_openid_map()
        try:
            client = QQBotClient(
                app_id=app_id,
                client_secret=app_secret,
                openid_map=openid_map,
                group_ids=list(self.group_order),
                log_cb=self.print_console_info,
                websocket_module=self._websocket_module,
                error_cb=self.on_qqbot_error,
            )
            client.on_group_message = self.dispatch_qqbot_group_message
            client.on_openid_discovered = self.on_qqbot_openid_discovered
            self._qqbot_client = client
            client.start_receiver()
            self.print_console_success("QQ 官方机器人通道已启动")
        except Exception as error:
            self._qqbot_client = None
            self.on_qqbot_error(
                "QQBOT-1003",
                "QQ 官方机器人通道启动失败",
                [
                    f"异常类型: {type(error).__name__}",
                    f"异常信息: {error}",
                ],
            )

    def stop_qqbot_connection(self) -> None:
        '''停止并移除当前 QQ 官方机器人客户端。'''
        client = getattr(self, "_qqbot_client", None)
        self._qqbot_client = None
        if client is not None:
            client.stop_receiver()

    def reload_qqbot_connection(self) -> None:
        '''重新加载 QQ 官方机器人连接。'''
        self.stop_qqbot_connection()
        if self.qqbot_channel_enabled():
            self.start_qqbot_connection()

    def on_qqbot_openid_discovered(self, group_id, openid) -> None:
        '''持久化客户端发现的群 OpenID 映射。'''
        data = self._load_qqbot_openid_map()
        data[str(group_id)] = str(openid)
        self._save_qqbot_openid_map(data)
        client = getattr(self, "_qqbot_client", None)
        if client is not None:
            client.replace_openid_map(data)
        self.print_console_success(f"官机通道已绑定群 {group_id}")

    def dispatch_qqbot_group_message(self, *args) -> None:
        """把官机消息交给独立工作线程，避免菜单等待阻塞网关接收。"""
        utils.createThread(
            self.on_qqbot_group_message,
            args=args,
            usage="QQ官方机器人消息处理",
        )

    def on_qqbot_group_message(
        self,
        group_id,
        user_id,
        nickname,
        content,
        is_bot=False,
        raw_openid="",
        role="member",
    ) -> None:
        '''把官机群消息转换成 OneBot 风格事件并交给消息流水线。'''
        if is_bot:
            return
        group_id = int(group_id)
        user_id = int(user_id)
        role = self._normalize_qqbot_member_role(role)
        roles = getattr(self, "_qqbot_member_roles", None)
        if roles is None:
            roles = {}
            self._qqbot_member_roles = roles
        roles[(group_id, user_id)] = role
        user_names = getattr(self, "_qqbot_user_names", None)
        if user_names is None:
            user_names = {}
            self._qqbot_user_names = user_names
        display_name = str(nickname or "QQ成员").strip() or "QQ成员"
        user_names[user_id] = display_name
        if raw_openid:
            self._qqbot_user_openids[user_id] = str(raw_openid)
        data = {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "group_id": group_id,
            "user_id": user_id,
            "message": str(content),
            "raw_message": str(content),
            "sender": {
                "user_id": user_id,
                "nickname": display_name,
                "card": display_name,
                "role": str(role),
            },
            "qqbot_user_openid": str(raw_openid),
            "source_channel": "qqbot",
        }
        self.process_group_message_data(data)

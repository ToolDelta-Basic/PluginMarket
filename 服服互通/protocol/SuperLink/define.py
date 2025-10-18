from enum import Enum
from tooldelta.utils.cfg_meta import JsonSchema, field


class SuperLinkConfig(JsonSchema):
    display_name: str = field("此租赁服的公开显示名", "自动生成")
    channel_name: str = field("登入后自动连接到的频道大区名", "公共大区")
    channel_password: str = field("频道密码", "")


class MsgTypeEnum(str, Enum):
    AUTH_FAILED = "server.auth_failed"
    AUTH_SUCCESS = "server.auth_success"

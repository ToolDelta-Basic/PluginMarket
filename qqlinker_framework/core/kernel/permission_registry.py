"""
PermissionRegistry — 内置权限注册表 + 用户可扩展。

每个权限键映射到最小 mid 和描述。模块在 required_permissions 中声明。
"""
from typing import Dict, Optional

MID_KERNEL = 0
MID_DAEMON = 100
MID_SERVICE = 200
MID_APP = 300
MID_NOBODY = 400

# 内置基础权限注册表
BUILTIN_PERMISSIONS: Dict[str, dict] = {
    # ── 配置读写 ──
    "config:read:核心":     {"min_mid": MID_APP,     "desc": "读取网络连接、去重等核心配置"},
    "config:read:安全":     {"min_mid": MID_DAEMON,  "desc": "读取 API 密钥、SSRF 防护等"},
    "config:read:管理":     {"min_mid": MID_DAEMON,  "desc": "读取模块管理、AI 等管理配置"},
    "config:write:模块":    {"min_mid": MID_APP,     "desc": "写入自身模块的配置节"},
    "config:write:安全":    {"min_mid": MID_DAEMON,  "desc": "写入安全配置（含密钥）"},
    "config:write:管理":    {"min_mid": MID_DAEMON,  "desc": "写入管理配置"},
    "config:write:核心":    {"min_mid": MID_KERNEL,  "desc": "写入核心配置"},
    # ── 消息发送 ──
    "message:send:group":   {"min_mid": MID_APP,     "desc": "发送群消息"},
    "message:send:private": {"min_mid": MID_SERVICE, "desc": "发送私聊消息"},
    # ── 游戏操作 ──
    "game:cmd":             {"min_mid": MID_SERVICE, "desc": "执行 Minecraft 游戏指令"},
    "game:say":             {"min_mid": MID_APP,     "desc": "向游戏内发送消息"},
    "game:title":           {"min_mid": MID_APP,     "desc": "显示游戏标题栏"},
    # ── 事件系统 ──
    "event:publish":        {"min_mid": MID_APP,     "desc": "发布事件到事件总线"},
    "event:publish:admin":  {"min_mid": MID_DAEMON,  "desc": "向 admin lane 发布管理事件"},
    "event:publish:critical":{"min_mid": MID_KERNEL, "desc": "向 critical lane 发布关键事件"},
    "event:listen":         {"min_mid": MID_APP,     "desc": "订阅事件"},
    # ── 会话管理 ──
    "session:manage":       {"min_mid": MID_SERVICE, "desc": "管理交互式会话（enter/leave）"},
    # ── 模块管理 ──
    "module:freeze":        {"min_mid": MID_DAEMON,  "desc": "冻结/卸载其他模块"},
    "module:delegate":      {"min_mid": MID_DAEMON,  "desc": "跨模块权限委托"},
    # ── 网络访问 ──
    "network:http":         {"min_mid": MID_APP,     "desc": "发起 HTTP 出站请求"},
}


def check_permission(permission_key: str, module_mid: int,
                     registry: Optional[Dict] = None) -> bool:
    """检查模块是否有指定权限。"""
    perms = registry or BUILTIN_PERMISSIONS
    entry = perms.get(permission_key)
    if entry is None:
        # 未知权限键 → 默认 daemon 以上可用
        return module_mid <= MID_DAEMON
    return module_mid <= entry["min_mid"]


def validate_module_permissions(required: list, module_mid: int,
                                module_name: str = "") -> list:
    """校验模块声明的权限是否合理。返回不合规权限列表。"""
    violations = []
    for perm in required:
        if not check_permission(perm, module_mid):
            violations.append(perm)
    return violations


def get_permission_info(permission_key: str) -> Optional[dict]:
    """查询权限信息。"""
    return BUILTIN_PERMISSIONS.get(permission_key)

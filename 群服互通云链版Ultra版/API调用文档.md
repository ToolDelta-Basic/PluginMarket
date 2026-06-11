# 群服互通云链版 Ultra API 调用指南

插件名称：群服互通云链版Ultra版  
插件 ID：群服互通云链版Ultra版  
API 别名：QQLinkerUltraAPI  
当前文档基于插件版本：2.0.0

本文说明其它 ToolDelta 类式插件如何调用本插件暴露的 API。推荐优先使用带 `api_` 前缀的方法和 `add_trigger(...)`；没有 `api_` 前缀的业务方法可能随内部实现调整。

## 1. 获取 API 实例

### 1.1 声明前置依赖

在调用方插件的 `datas.json` 中声明依赖：

```json
{
  "pre-plugins": {
    "群服互通云链版Ultra版": ">=2.0.0"
  }
}
```

### 1.2 在 preload 阶段获取实例

```python
from tooldelta import Plugin, ToolDelta, plugin_entry


class ExamplePlugin(Plugin):
    name = "示例调用方插件"
    author = "your-name"
    version = (0, 0, 1)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.qqlinker = None
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        self.qqlinker = self.GetPluginAPI("QQLinkerUltraAPI", (2, 0, 0))


entry = plugin_entry(ExamplePlugin)
```

> **注意**：不要在 `__init__` 中调用 `GetPluginAPI(...)`。ToolDelta 前置 API 更稳妥的获取阶段是 preload。

## 2. 运行状态 API

### 2.1 api_get_status

```python
api_get_status() -> dict[str, Any]
```

返回 Ultra 的运行状态快照。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `available` | `bool` | 云链 WebSocket 当前是否可用 |
| `ws_initialized` | `bool` | WebSocket 对象是否已初始化 |
| `websocket_target` | `str` | 当前连接目标地址 |
| `manual_launch` | `bool` | 是否处于本地启动器手动连接模式 |
| `manual_launch_port` | `int` | 手动连接模式端口 |
| `reloaded` | `bool` | 当前连接是否处于重载状态 |
| `reconnect_delay` | `Optional[int]` | 下一次自动重连延迟 |
| `session_id` | `int` | 当前 WebSocket 会话编号 |
| `linked_groups` | `list[int]` | 已配置的群号列表 |
| `default_group` | `Optional[int]` | 兼容旧单群调用的默认群号 |

示例：

```python
status = qqlinker.api_get_status()
if not status["available"]:
    self.print_war("Ultra 云链暂不可用")
```

### 2.2 在线玩家查询

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_get_online_players()` | `list[str]` | 返回当前在线玩家名副本 |
| `api_is_player_online(player_name, ignore_case=False)` | `bool` | 判断玩家是否在线，`ignore_case=True` 时忽略大小写 |

### 2.3 MC 指令执行

```python
api_execute_game_cmd(command: str) -> tuple[bool, str]
```

执行一条 MC 指令，并返回稳定的 `(是否成功, 结果文本)`。该接口复用 Ultra 原有指令执行与中文结果整理逻辑；空指令会返回失败。

### 2.4 游戏到群转发规则

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_get_game_to_group_targets(enabled_only=True)` | `list[dict[str, Any]]` | 返回游戏到群转发目标和规则副本 |
| `api_should_forward_game_message(group_id, message)` | `tuple[bool, str] \| None` | 预判某条游戏消息是否会转发到指定群，并返回裁剪后的消息；群未配置时返回 `None` |

`api_get_game_to_group_targets(...)` 返回项包含 `group_id`、`enabled`、`format`、`required_prefixes`、`blocked_prefixes`、`forward_player_events` 和 `config`。

### 2.5 云链重载

```python
api_reload_websocket() -> tuple[bool, str]
```

请求 Ultra 按当前配置重载云链 WebSocket 连接。调用失败时返回 `(False, 错误文本)`。

## 3. 群配置与权限 API

### 3.1 群配置查询

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_get_linked_groups()` | `list[int]` | 返回当前已配置群号，顺序与运行时一致 |
| `api_get_default_group()` | `Optional[int]` | 返回默认群号，通常是第一个配置群 |
| `api_is_group_configured(group_id)` | `bool` | 判断群号是否已配置 |
| `api_get_group_config(group_id)` | `Optional[dict[str, Any]]` | 返回指定群配置副本 |
| `api_get_group_state(group_id)` | `Optional[dict[str, list[int]]]` | 返回指定群管理员状态副本，包含 `owner`、`super_admins`、`admins` |

`api_get_group_config(...)` 和 `api_get_group_state(...)` 返回的是副本，调用方修改返回值不会写回 Ultra 内部状态。

### 3.2 群权限查询

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_get_group_admins(group_id, include_super=True)` | `list[int]` | 返回群管理员；默认包含该群 `权限设置` 中的所有者和超级管理员 |
| `api_get_group_super_admins(group_id)` | `list[int]` | 返回该群 `权限设置` 中的超级管理员，不包含所有者 |
| `api_get_group_owner(group_id)` | `Optional[int]` | 返回该群 `权限设置` 中的所有者 QQ；群未配置或所有者为 `0` 时返回 `None` |
| `api_is_group_admin(group_id, qqid)` | `bool` | 判断 QQ 是否拥有群管理权限 |
| `api_is_group_super_admin(group_id, qqid)` | `bool` | 判断 QQ 是否拥有超级管理员级权限，所有者也返回 `True` |
| `api_is_group_owner(group_id, qqid)` | `bool` | 判断 QQ 是否为该群 `权限设置` 中的所有者 |

### 3.3 群权限写入

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_add_group_admin(group_id, qqid, is_super=False)` | `tuple[bool, str]` | 添加普通管理员或超级管理员；不能把所有者重复添加为管理员 |
| `api_remove_group_admin(group_id, qqid, is_super=False)` | `tuple[bool, str]` | 移除普通管理员或超级管理员；不能移除所有者 |

示例：

```python
ok, msg = qqlinker.api_add_group_admin(
    group_id=987654321,
    qqid=123456789,
    is_super=False,
)

if not ok:
    self.print_war(msg)
```

## 4. 群触发词 API

### 4.1 api_get_group_triggers

```python
api_get_group_triggers(group_id: int | str) -> dict[str, Any] | None
```

返回指定群归一化后的触发词配置。群未配置时返回 `None`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `help` | `list[str]` | 帮助菜单触发词 |
| `admin_menu` | `list[str]` | 管理员菜单触发词 |
| `player_list` | `list[str]` | 在线玩家列表触发词 |
| `inventory_menu` | `list[str]` | 背包查询菜单触发词 |
| `menu_exit` | `list[str]` | 退出整个菜单触发词 |
| `menu_back` | `list[str]` | 返回上级菜单触发词 |
| `command_prefix` | `str` | 群内发送 MC 指令前缀 |
| `orion_ban` | `list[str]` | Orion 封禁触发词 |
| `orion_unban` | `list[str]` | Orion 解封触发词 |
| `checker_menu` | `list[str]` | 白名单与管理员检测菜单触发词 |
| `task_menu` | `list[str]` | 任务系统菜单触发词 |
| `land_menu` | `list[str]` | 领地系统菜单触发词 |
| `guild_menu` | `list[str]` | 公会系统菜单触发词；普通成员需绑定游戏账号，群管理员进入管理菜单 |
| `binding` | `list[str]` | QQ/游戏账号绑定触发词 |

### 4.2 api_get_registered_triggers

```python
api_get_registered_triggers() -> list[dict[str, Any]]
```

返回通过 `add_trigger(...)` 注册进 Ultra 的外部 QQ 触发器元信息。

返回项字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `triggers` | `list[str]` | 触发词列表 |
| `argument_hint` | `Optional[str]` | 参数提示 |
| `usage` | `str` | 用途说明 |
| `op_only` | `bool` | 是否仅群管理员可用 |
| `accept_group` | `bool` | 回调是否接收 `group_id` 参数 |

## 5. 群聊触发器注册

### 5.1 add_trigger

```python
add_trigger(
    triggers: list[str],
    argument_hint: str | None,
    usage: str,
    func,
    args_pd=lambda _: True,
    op_only: bool = False,
)
```

把调用方插件的 QQ 群指令挂入 Ultra 的统一分发入口。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `triggers` | `list[str]` | 触发词列表，按前缀匹配 |
| `argument_hint` | `Optional[str]` | 参数错误时展示的格式提示 |
| `usage` | `str` | 用途说明 |
| `func` | `Callable` | 回调函数 |
| `args_pd` | `Callable[[int], bool]` | 参数个数校验函数 |
| `op_only` | `bool` | 是否仅允许群管理员调用 |

回调签名支持两种形式：

```python
def handler(group_id: int, qqid: int, args: list[str]):
    ...

def legacy_handler(qqid: int, args: list[str]):
    ...
```

推荐使用带 `group_id` 的新签名，便于多群场景区分来源。

### 5.2 注册示例

```python
def on_query_binding(group_id: int, qqid: int, args: list[str]):
    target_qq = int(args[0]) if args else qqid
    players = qqlinker.api_get_bound_players_by_qq(target_qq)
    if not players:
        qqlinker.api_reply_group_member(group_id, qqid, "暂无绑定记录")
        return

    lines = [
        f"- {item['player_name']} ({item['xuid']})"
        for item in players
    ]
    qqlinker.api_send_group_msg(group_id, "绑定记录：\n" + "\n".join(lines))


qqlinker.add_trigger(
    triggers=["查绑定"],
    argument_hint="[QQ号]",
    usage="查询 QQ 绑定的游戏账号",
    func=on_query_binding,
    args_pd=lambda n: n in (0, 1),
    op_only=False,
)
```

## 6. QQ 与游戏账号绑定 API

绑定数据保存在 Ultra 数据目录下的 `QQ绑定数据.json`，结构会被自动归一化。

### 6.1 查询接口

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_get_binding_data()` | `dict[str, dict[str, Any]]` | 返回完整绑定数据副本 |
| `api_get_all_bindings()` | `list[dict[str, Any]]` | 返回扁平化绑定记录列表 |
| `api_get_xuids_by_qq(qqid)` | `list[str]` | 查询 QQ 绑定的所有 XUID |
| `api_get_qqs_by_xuid(xuid)` | `list[int]` | 查询 XUID 绑定的所有 QQ |
| `api_get_player_name_by_xuid(xuid)` | `Optional[str]` | 查询 XUID 最近记录的玩家名 |
| `api_get_bound_players_by_qq(qqid)` | `list[dict[str, str]]` | 查询 QQ 绑定的玩家记录 |
| `api_get_bound_qqs_by_xuid(xuid)` | `list[dict[str, Any]]` | 查询 XUID 绑定的 QQ 记录 |
| `api_get_xuids_by_player_name(player_name, ignore_case=True)` | `list[str]` | 按玩家名查询 XUID |
| `api_get_qqs_by_player_name(player_name, ignore_case=True)` | `list[int]` | 按玩家名查询 QQ |
| `api_is_binding_enabled(group_id=None)` | `bool` | 查询绑定功能是否启用 |
| `api_is_qq_bound(qqid)` | `bool` | 判断 QQ 是否已有绑定 |
| `api_is_xuid_bound(xuid)` | `bool` | 判断 XUID 是否已有绑定 |
| `api_is_qq_bound_to_xuid(qqid, xuid)` | `bool` | 判断指定 QQ/XUID 关系是否存在 |

### 6.2 写入接口

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_bind_qq_to_xuid(qqid, xuid, player_name="", group_id=None)` | `tuple[bool, str]` | 创建或刷新 QQ/XUID 绑定，遵守多绑定配置 |
| `api_unbind_qq_from_xuid(qqid, xuid)` | `tuple[bool, str]` | 删除一条指定 QQ/XUID 绑定 |
| `api_unbind_all_by_qq(qqid)` | `tuple[bool, str]` | 删除某个 QQ 的全部绑定 |
| `api_unbind_all_by_xuid(xuid)` | `tuple[bool, str]` | 删除某个 XUID 的全部 QQ 绑定 |
| `api_update_xuid_player_name(xuid, player_name)` | `tuple[bool, str]` | 更新已绑定 XUID 的最近玩家名 |
| `api_start_binding_request(group_id, qqid)` | `tuple[bool, str]` | 创建验证码绑定流程 |

### 6.3 验证码绑定流程

```python
ok, msg = qqlinker.api_start_binding_request(
    group_id=987654321,
    qqid=123456789,
)
```

流程说明：

1. Ultra 向 QQ 用户私信 6 位数字验证码。
2. 玩家在游戏聊天中发送验证码。
3. Ultra 读取玩家 XUID 并写入绑定数据。

## 7. 消息发送与等待输入 API

### 7.1 稳定发送接口

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_send_group_msg(group_id, message, remove_cq_code=True)` | `tuple[bool, str]` | 向指定群发送消息 |
| `api_reply_group_member(group_id, qqid, message)` | `tuple[bool, str]` | 在群内 @ 指定 QQ 并回复 |
| `api_send_private_msg(qqid, message)` | `tuple[bool, str]` | 向指定 QQ 发送私信 |

示例：

```python
ok, msg = qqlinker.api_send_group_msg(
    group_id=987654321,
    message="服务器当前在线人数：12",
)
```

这些 `api_` 包装会捕获底层发送异常，并返回 `(False, "错误信息")`。

### 7.2 等待群消息

```python
api_wait_group_msg(qqid, timeout=60, group_id=None) -> str | None
```

等待某个 QQ 的下一条群消息。传入 `group_id` 时只接收指定群的下一条消息；不传 `group_id` 时保留旧单群兼容行为。

```python
reply = qqlinker.api_wait_group_msg(
    qqid=123456789,
    timeout=30,
    group_id=987654321,
)
```

### 7.3 兼容发送方法

Ultra 仍保留以下旧方法：

| 方法 | 说明 |
| --- | --- |
| `sendmsg(group, msg, do_remove_cq_code=True)` | 直接发送群消息，可能抛出底层异常 |
| `send_private_msg(qqid, msg)` | 直接发送私信，可能抛出底层异常 |

新插件优先使用 `api_send_group_msg(...)`、`api_reply_group_member(...)` 和 `api_send_private_msg(...)`。

## 8. 群消息广播事件

Ultra 收到云链群消息后，会向 ToolDelta 框架广播内部事件。外部插件可以监听事件并返回真值来阻止 Ultra 继续处理该消息。

| 事件名 | 负载 | 说明 |
| --- | --- | --- |
| `群服互通/数据json` | 云链原始 `dict` | 所有来自云链的原始数据 |
| `群服互通/链接群消息` | `{"群号": int, "QQ号": int, "昵称": str, "消息": str}` | 已确认来自已配置互通群的文本消息 |

普通命令扩展优先使用 `add_trigger(...)`；只有需要截获原始消息或阻止后续转发时，才使用内部广播事件。

## 9. 原始群消息监听 API

如果不想直接依赖 ToolDelta 内部广播，也可以通过 Ultra 注册原始群消息监听器。监听器只会收到云链上报的群消息原始 `dict`；回调返回真值时，Ultra 会停止后续命令分发和群到游戏转发。

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `api_register_message_listener(name, listener)` | `tuple[bool, str]` | 注册一个原始群消息监听器 |
| `api_unregister_message_listener(name)` | `tuple[bool, str]` | 注销指定名称的监听器 |
| `api_get_message_listeners()` | `list[dict[str, Any]]` | 返回已注册监听器元信息 |

示例：

```python
def on_raw_group_message(data: dict):
    group_id = data.get("group_id")
    message = data.get("message")
    return False

ok, msg = qqlinker.api_register_message_listener(
    "example-listener",
    on_raw_group_message,
)
```

## 10. Orion 联动入口

以下方法可复用 Ultra 已封装的 Orion 玩家封禁/解封逻辑，但它们没有 `api_` 前缀，应视为辅助入口：

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `orion_ban_player(target, ban_time_raw, reason)` | `tuple[bool, str]` | 按玩家名或 XUID 解析目标，并通过 Orion 写入 XUID 封禁 |
| `orion_unban_player(target)` | `tuple[bool, str]` | 按玩家名或 XUID 解析目标，并通过 Orion 解除 XUID 封禁 |

## 11. 常见问题

**Q1: 多群环境下不传 `group_id` 会怎样？**

部分旧兼容接口会使用默认群号。新插件应尽量显式传入 `group_id`，避免套用错误群配置。

**Q2: 什么时候用 `api_send_group_msg(...)`，什么时候用 `sendmsg(...)`？**

新插件优先使用 `api_send_group_msg(...)`。它会处理参数校验和异常返回，调用方更容易统一处理失败。

**Q3: 群消息应该用广播事件还是 `add_trigger(...)`？**

普通命令扩展用 `add_trigger(...)`。只有需要处理全部原始消息、阻止 Ultra 继续转发或接入非命令式逻辑时，才使用广播事件。

## 12. 快速参考

### 12.1 常用场景

| 场景 | 推荐接口 |
| --- | --- |
| 获取 Ultra API | `GetPluginAPI("QQLinkerUltraAPI", (1, 1, 10))` |
| 查看运行状态 | `api_get_status()` |
| 查询在线玩家 | `api_get_online_players()` |
| 判断玩家是否在线 | `api_is_player_online(player_name)` |
| 执行 MC 指令 | `api_execute_game_cmd(command)` |
| 查询游戏到群转发目标 | `api_get_game_to_group_targets()` |
| 预判游戏消息转发 | `api_should_forward_game_message(group_id, message)` |
| 重载云链连接 | `api_reload_websocket()` |
| 获取已配置群 | `api_get_linked_groups()` |
| 查询群配置 | `api_get_group_config(group_id)` |
| 查询群管理员 | `api_get_group_admins(group_id)` |
| 增删群管理员 | `api_add_group_admin(...)` / `api_remove_group_admin(...)` |
| 查询群触发词 | `api_get_group_triggers(group_id)` |
| 查询外部触发器 | `api_get_registered_triggers()` |
| 注册 QQ 群命令 | `add_trigger(...)` |
| 查询 QQ 绑定玩家 | `api_get_bound_players_by_qq(qqid)` |
| 发起验证码绑定 | `api_start_binding_request(group_id, qqid)` |
| 发送群消息 | `api_send_group_msg(group_id, message)` |
| @ 群成员回复 | `api_reply_group_member(group_id, qqid, message)` |
| 发送 QQ 私信 | `api_send_private_msg(qqid, message)` |
| 等待 QQ 群回复 | `api_wait_group_msg(qqid, timeout, group_id)` |
| 注册原始群消息监听 | `api_register_message_listener(name, listener)` |

### 12.2 完整 `api_*` 索引

| 分类 | 接口 |
| --- | --- |
| 运行状态 | `api_get_status()` |
| 在线玩家 | `api_get_online_players()` |
| 在线玩家 | `api_is_player_online(player_name, ignore_case=False)` |
| 游戏指令 | `api_execute_game_cmd(command)` |
| 游戏到群 | `api_get_game_to_group_targets(enabled_only=True)` |
| 游戏到群 | `api_should_forward_game_message(group_id, message)` |
| 云链连接 | `api_reload_websocket()` |
| 群配置 | `api_get_linked_groups()` |
| 群配置 | `api_get_default_group()` |
| 群配置 | `api_is_group_configured(group_id)` |
| 群配置 | `api_get_group_config(group_id)` |
| 群配置 | `api_get_group_state(group_id)` |
| 群权限 | `api_get_group_admins(group_id, include_super=True)` |
| 群权限 | `api_get_group_super_admins(group_id)` |
| 群权限 | `api_get_group_owner(group_id)` |
| 群权限 | `api_is_group_admin(group_id, qqid)` |
| 群权限 | `api_is_group_super_admin(group_id, qqid)` |
| 群权限 | `api_is_group_owner(group_id, qqid)` |
| 群权限 | `api_add_group_admin(group_id, qqid, is_super=False)` |
| 群权限 | `api_remove_group_admin(group_id, qqid, is_super=False)` |
| 触发词 | `api_get_group_triggers(group_id)` |
| 触发词 | `api_get_registered_triggers()` |
| 绑定查询 | `api_get_binding_data()` |
| 绑定查询 | `api_get_all_bindings()` |
| 绑定查询 | `api_get_xuids_by_qq(qqid)` |
| 绑定查询 | `api_get_qqs_by_xuid(xuid)` |
| 绑定查询 | `api_get_player_name_by_xuid(xuid)` |
| 绑定查询 | `api_get_bound_players_by_qq(qqid)` |
| 绑定查询 | `api_get_bound_qqs_by_xuid(xuid)` |
| 绑定查询 | `api_get_xuids_by_player_name(player_name, ignore_case=True)` |
| 绑定查询 | `api_get_qqs_by_player_name(player_name, ignore_case=True)` |
| 绑定状态 | `api_is_binding_enabled(group_id=None)` |
| 绑定状态 | `api_is_qq_bound(qqid)` |
| 绑定状态 | `api_is_xuid_bound(xuid)` |
| 绑定状态 | `api_is_qq_bound_to_xuid(qqid, xuid)` |
| 绑定写入 | `api_bind_qq_to_xuid(qqid, xuid, player_name="", group_id=None)` |
| 绑定写入 | `api_unbind_qq_from_xuid(qqid, xuid)` |
| 绑定写入 | `api_unbind_all_by_qq(qqid)` |
| 绑定写入 | `api_unbind_all_by_xuid(xuid)` |
| 绑定写入 | `api_update_xuid_player_name(xuid, player_name)` |
| 绑定写入 | `api_start_binding_request(group_id, qqid)` |
| 消息发送 | `api_send_group_msg(group_id, message, remove_cq_code=True)` |
| 消息发送 | `api_reply_group_member(group_id, qqid, message)` |
| 消息发送 | `api_send_private_msg(qqid, message)` |
| 等待输入 | `api_wait_group_msg(qqid, timeout=60, group_id=None)` |
| 原始群消息监听 | `api_register_message_listener(name, listener)` |
| 原始群消息监听 | `api_unregister_message_listener(name)` |
| 原始群消息监听 | `api_get_message_listeners()` |

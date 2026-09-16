# 『Libra-天秤座』玩家权限管理系统 API 调用文档

## 1. 文档说明

本文档面向其他 ToolDelta 插件，说明如何调用『Libra-天秤座』玩家权限管理系统（以下简称 Libra）提供的 Python API。

Libra 不提供 HTTP 或 IPC 接口。其他插件应通过 ToolDelta 的 `GetPluginAPI()` 获取 Libra 插件实例，再调用实例上的公开方法。

当前插件信息：

| 项目 | 值 |
| --- | --- |
| `plugin-id` | `『Libra-天秤座』玩家权限管理系统` |
| 当前版本 | `0.2.0` |
| API 最低版本 | `0.2.0` |
| 前置插件 | `XUID获取` `0.0.7` |

> **注意**：文档只列出稳定公开 API。以 `_` 开头的方法、`state`、`realtime`、`store` 等内部对象不属于稳定调用接口，不建议其他插件直接依赖。

## 2. 获取 Libra API

应在 `ListenPreload` 阶段获取 API，不要在插件构造函数中调用 `GetPluginAPI()`。

```python
from tooldelta import Plugin, ToolDelta, plugin_entry


class ExamplePlugin(Plugin):
    name = "Libra API 调用示例"
    author = "your-name"
    version = (0, 0, 1)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.libra = None
        self.ListenPreload(self.on_preload)

    def on_preload(self) -> None:
        self.libra = self.GetPluginAPI(
            "『Libra-天秤座』玩家权限管理系统",
            (0, 2, 0),
        )


entry = plugin_entry(ExamplePlugin, "libra-api-example")
```

如果 Libra 未安装、版本过低或加载失败，`GetPluginAPI()` 可能抛出异常。调用方应在 `on_preload` 中处理异常，并在 API 为空时停止注册依赖 Libra 的功能。

## 3. 权限标志格式

所有权限设置 API 使用恰好 8 位、只包含 `0` 和 `1` 的字符串，例如 `11111100`。字符串位置按 Libra 的能力顺序解释：

| 位置 | 位掩码 | 能力 | `1` 表示 |
| ---: | ---: | --- | --- |
| 第 1 位 | `1 << 0` | 建造 | 可以建造 |
| 第 2 位 | `1 << 1` | 挖掘 | 可以挖掘 |
| 第 3 位 | `1 << 2` | 门和开关 | 可以操作门、开关等 |
| 第 4 位 | `1 << 3` | 打开容器 | 可以打开容器 |
| 第 5 位 | `1 << 4` | 攻击玩家 | 可以攻击玩家 |
| 第 6 位 | `1 << 5` | 攻击生物 | 可以攻击生物 |
| 第 7 位 | `1 << 6` | 管理员命令 | 可以使用管理员命令 |
| 第 8 位 | `1 << 7` | 传送 | 可以使用传送能力 |

常用权限类别由完整 8 位字符串判断：

| 权限标志 | 类别 |
| --- | --- |
| `00000000` | 访客 |
| `11111100` | 成员 |
| `11111111` | 管理员 |
| 其他合法 8 位组合 | 自定义 |

“自定义”不等于“管理员”。是否属于管理员还应以服务器 `/permission list` 返回的管理员列表为准。

## 4. 权限转换与校验 API

### 4.1 `parse_flags(value)`

把 8 位权限字符串解析为 `ParsedFlags` 对象。

```python
parsed = self.libra.parse_flags("11111100")
print(parsed.raw)          # "11111100"
print(parsed.mask)         # 63
print(parsed.permissions)  # (True, True, True, True, True, True, False, False)
```

返回对象字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `raw` | `str` | 原始 8 位字符串 |
| `mask` | `int` | 由各能力位组成的整数掩码 |
| `permissions` | `tuple[bool, ...]` | 按能力顺序排列的布尔值 |

输入不是 8 位 `0/1` 字符串时抛出 `ValueError`。

### 4.2 `format_flags(mask)`

把 `0` 到 `255` 的整数掩码转换为 8 位权限字符串。

```python
flags = self.libra.format_flags(63)
# flags == "11111100"
```

输入不是整数或不在 `0..255` 范围内时抛出 `ValueError`。

### 4.3 `describe_flags(flags)`

返回能力名称到布尔值的字典。

```python
details = self.libra.describe_flags("10000000")
# {
#     "build": True,
#     "mine": False,
#     "doors": False,
#     "containers": False,
#     "attack_players": False,
#     "attack_mobs": False,
#     "commands": False,
#     "teleport": False,
# }
```

### 4.4 `classify_permission(flags)`

返回 `访客`、`成员`、`管理员`、`自定义` 或 `未知`。

```python
category = self.libra.classify_permission("11111100")
# category == "成员"
```

## 5. 管理员列表与权限变更

### 5.1 `list_admins(refresh=True)`

读取服务器当前管理员 XUID 列表。

```python
admins = self.libra.list_admins(refresh=True)
# ["8ee8ba9a", "24c8e47a", ...]
```

- `refresh=True`：通过配置的命令通道重新查询服务器。
- `refresh=False`：只读取 Libra 最近一次成功缓存，不发送命令。
- 查询失败时，Libra 保留上次成功缓存；调用方可通过 `get_status()` 检查最近查询状态。

### 5.2 `list_admin_details(refresh=True)`

返回带玩家名和命令模式的管理员列表。

```python
result = self.libra.list_admin_details()
```

成功示例：

```python
{
    "success": True,
    "error": None,
    "admins": [
        {"xuid": "8ee8ba9a", "name": "玩家甲", "permission": "operator"}
    ],
    "command_mode": "magic",
}
```

`name` 由前置插件 `XUID获取` 的在线/离线身份数据解析；无法解析时为 `None`。

### 5.3 `set_permission_flags(xuid, flags=None, actor="api", reason="", management="once")`

设置玩家权限，支持在线和离线玩家。

```python
result = self.libra.set_permission_flags(
    "ab2018cd",
    "11111100",
    actor="白名单插件",
    reason="通过白名单审核",
)
```

参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `xuid` | `str` | 必填 | 8-32 位十六进制 XUID |
| `flags` | `str | None` | `None` | 8 位 `0/1` 权限字符串；省略时使用配置项 `默认权限` |
| `actor` | `str` | `"api"` | 操作者标识，写入操作记录 |
| `reason` | `str` | `""` | 操作原因，写入操作记录 |
| `management` | `str` | `"once"` | `once` 一次设置，`manage` 设置并建立持续管理规则，`auto` 供实时修正内部使用 |

成功返回：

```python
{
    "success": True,
    "action": "set",
    "xuid": "ab2018cd",
    "flags": "11111100",
    "response": { ... },
}
```

失败返回至少包含 `success=False`、`error`、`message` 和 `xuid`。常见错误值包括：

| `error` | 含义 |
| --- | --- |
| `managed_player` | 玩家已启用持续管理，拒绝一次性覆盖 |
| `busy` | 另一个权限变更正在执行 |
| `permission_denied` | 当前命令通道没有执行 `permission` 命令的权限 |
| `command_failed` | 命令发送或服务器执行失败 |

XUID 或权限格式非法时抛出 `ValueError`。当玩家已启用持续管理时，如需修改目标权限，应使用 `management="manage"` 更新规则，或先调用 `pause_managed_rule()`。

### 5.4 `revoke_admin(xuid, actor="api", reason="")`

调用 `/permission del` 撤销玩家的管理员权限，并清除 Libra 中对应的期望权限记录。

```python
result = self.libra.revoke_admin("ab2018cd", actor="安全审计", reason="账号回收")
```

返回结构与 `set_permission_flags()` 类似，成功时 `action` 为 `revoke`。

### 5.5 `audit()`

查询管理员列表并根据配置 `实时管理.管理员XUID` 计算未知管理员。配置列表中的 XUID 都按受保护管理员处理。

```python
result = self.libra.audit()
# {
#   "success": True,
#   "admins": [...],
#   "unknown": [...],
#   "configured": [...],
# }
```

返回中的 `trusted` 字段仍作为兼容别名保留，其内容与 `configured` 相同。

### 5.6 `get_status()`

返回权限服务状态：

```python
{
    "ready": True,
    "cached_admins": 4,
    "managed_players": 2,
    "last_list_time": 1720000000,
    "last_list_status": "成功",
    "last_list_error": None,
    "command_channel": "magic",
}
```

`command_channel` 为 `magic` 时使用 `sendaicmd_with_resp()`，为 `normal` 时使用 `sendcmd_with_resp()`。通道由配置项 `是否使用魔法指令模式运行` 决定。

### 5.7 `preview_sync(refresh=True)`

比较 Libra 保存的期望权限与服务器当前管理员列表，生成待设置、待删除、未知和已配置管理员列表。该方法只生成计划，不执行权限变更。

```python
plan = self.libra.preview_sync()
```

成功时返回：

```python
{
    "to_set": [{"xuid": "ab2018cd", "flags": "11111100"}],
    "to_delete": [],
    "unknown": [],
    "configured": [],
}
```

返回中的 `protected` 字段仍作为兼容别名保留，其内容与 `configured` 相同；现在不存在独立的受保护管理员配置。

刷新管理员列表失败时会返回 `success=False` 和 `error`。

### 5.8 `sync_all(remove_unknown=False, actor="api")`

先生成同步计划，再执行待设置权限；当 `remove_unknown=True` 时，同时撤销不在 `实时管理.管理员XUID` 中的未知管理员。

```python
result = self.libra.sync_all(remove_unknown=False, actor="权限同步插件")
```

返回 `plan` 和 `results`。`results` 中每一项都是权限设置或撤销 API 的返回值。建议默认保持 `remove_unknown=False`，先展示计划并由业务方确认后再执行。

## 6. 快照 API

快照保存 Libra 的期望权限、持续管理玩家和最近发现的管理员。快照还原只更新 Libra 本地状态，不会自动向服务器发送权限命令；需要后续检查或显式设置权限才能使服务器状态变化。

### 6.1 `save_snapshot(name=None)`

创建快照。名称为空时自动使用 `YYYY-MM-DDTHH:MM:SS`。

```python
snapshot = self.libra.save_snapshot("发布前")
```

### 6.2 `list_snapshots_api(page=1, page_size=20, query="")`

分页列出快照。返回的 `索引` 是状态中的真实索引，可直接传给预览、还原或删除 API。

```python
page = self.libra.list_snapshots_api(page=1, page_size=20, query="发布")
for item in page["项目"]:
    print(item["索引"], item["快照"]["名称"])
```

返回字段：`页码`、`每页数量`、`总数`、`项目`。`items` 和 `snapshots` 是兼容性别名。

### 6.3 `preview_snapshot_api(index)`

预览指定快照。

```python
preview = self.libra.preview_snapshot_api(index)
if preview.get("success"):
    snapshot = preview["snapshot"]
```

索引不存在时返回 `{"success": False, "error": "snapshot_not_found"}`。

### 6.4 `restore_snapshot_api(index=-1, actor="api")`

还原快照中的期望权限和持续管理规则。

```python
result = self.libra.restore_snapshot_api(index=3, actor="备份插件")
```

成功返回 `success=True`、`desired` 和 `index`；快照不存在或内容非法时返回 `snapshot_not_found` 或 `snapshot_invalid`。

### 6.5 `delete_snapshot_api(index, actor="api")`

删除指定快照。

```python
result = self.libra.delete_snapshot_api(3, actor="备份插件")
```

## 7. 实时权限管理 API

实时管理基于 ToolDelta 在线 `Player` 对象的 `abilities` 属性读取八项能力，不依赖 NeOmega。它只会持续修正已建立持续管理规则的玩家；未托管玩家不会因为普通在线检查而被修改。实时线程分别按 `在线权限检查间隔(秒)` 检查在线能力、按 `管理员列表检查间隔(秒)` 查询管理员列表并执行未授权管理员策略；`启动后立即检查` 控制这两类检查是否在启动时立即执行。

### 7.1 `get_realtime_status()`

返回实时管理状态，包括是否启用、是否运行、实时在线人数、权限观测数、最近修正数和当前两类检查间隔。

```python
status = self.libra.get_realtime_status()
```

### 7.2 `set_realtime_enabled(enabled)`

启用或停用实时管理，并写回配置。

```python
self.libra.set_realtime_enabled(True)
```

### 7.3 `set_managed_rule(xuid, flags, enabled=True, actor="api")`

先向服务器设置目标权限，命令成功后建立持续管理规则。

```python
result = self.libra.set_managed_rule(
    "ab2018cd",
    "11111100",
    enabled=True,
    actor="白名单插件",
)
```

如果权限命令失败，规则不会写入。返回结果会包含 `持续管理` 和 `目标权限`。

### 7.4 `get_managed_rule(xuid)`

查询单个玩家的持续管理规则。不存在或 XUID 无效时返回 `None`。

```python
rule = self.libra.get_managed_rule("ab2018cd")
# {"玩家XUID": "ab2018cd", "是否启用": True, "目标权限": "11111100"}
```

### 7.5 `set_managed_enabled(xuid, enabled, actor="api")`

只切换规则启用状态，不改变目标权限。玩家没有持续管理规则时返回 `not_managed`。

### 7.6 `pause_managed_rule(xuid, actor="api")`

暂停持续管理规则，保留规则和目标权限，返回 `是否启用=False`。

### 7.7 `remove_managed_rule(xuid, actor="api")`

删除持续管理规则，但不会自动撤销服务器当前权限；已保存的期望权限记录也不会因为删除规则而自动清除。

### 7.8 `list_online_permissions(page=1, page_size=20)`

返回当前在线且已经观测到能力数据的玩家权限，自动清理已下线玩家的在线观测缓存。

每一项通常包含：

```python
{
    "XUID": "ab2018cd",
    "玩家名称": "玩家甲",
    "是否托管": True,
    "实际权限": "11111100",
    "权限标志": "11111100",
    "权限类别": "成员",
    "就绪": True,
    "玩家权限等级": 1,
    "命令权限等级": 1,
}
```

返回字段：`页码`、`每页数量`、`总数`、`项目`。

### 7.9 `get_permission_fix_history(limit=100)`

返回最近的权限修正记录，最多返回 `limit` 条。

### 7.10 `get_player_permissions(xuid)`

读取指定 XUID 最近一次在线能力观测记录。没有观测记录时返回 `None`。

### 7.11 `request_permission_check(xuid=None)`

立即检查在线玩家权限：

- `xuid=None`：检查当前所有在线玩家，返回结果列表。
- 指定 XUID：检查该在线玩家，返回单个结果。
- 玩家不在线：返回 `{"状态": "玩家不在线", "XUID": "..."}`。

## 8. 玩家身份搜索 API

这些方法使用前置插件 `XUID获取` 的运行时映射和插件数据目录中的离线身份数据。

### 8.1 `resolve_player_name(xuid, refresh=True)`

把 XUID 解析为玩家名，无法找到时返回 `None`。

### 8.2 `resolve_player_names(xuids)`

批量解析 XUID，返回 `{xuid: name_or_none}`。

### 8.3 `search_players(query, limit=8)`

按玩家名搜索身份记录，匹配顺序为完全匹配、前缀匹配、包含匹配。

```python
matches = self.libra.search_players("小六", limit=8)
# [{"xuid": "ab2018cd", "name": "小六神"}, ...]
```

## 9. 事件订阅 API

### 9.1 `subscribe_permission_events(callback)`

订阅 Libra 发出的全部实时事件，返回整数令牌。

```python
def on_libra_event(event: dict) -> None:
    if event.get("事件") == "权限修正":
        print(event["XUID"], event["目标权限"])


token = self.libra.subscribe_permission_events(on_libra_event)
```

通用事件载荷至少包含：

| 字段 | 说明 |
| --- | --- |
| `事件` | 事件名称 |
| `时间` | Unix 时间戳 |

当前事件名称包括：`权限修正`、`权限复核`、`未授权管理员`、`持续管理暂停`、`持续管理删除`、`持续管理状态变更`。自动修正成功后会在 `修改后复核延迟(秒)` 之后复核，最长等待 `修改后复核超时时间(秒)`，并通过 `权限复核` 事件报告 `通过` 或 `超时`。

### 9.2 `subscribe_unknown_admin_events(callback)`

只订阅未授权管理员事件。

```python
def on_unknown_admin(event: dict) -> None:
    print(event["玩家名称"], event["XUID"], event["发现时间文本"])


token = self.libra.subscribe_unknown_admin_events(on_unknown_admin)
```

事件载荷示例：

```python
{
    "事件": "未授权管理员",
    "时间": 1720000000,
    "XUID": "ab2018cd",
    "玩家名称": "玩家甲",
    "发现时间": 1720000000,
    "发现时间文本": "2026-09-16T12:34:56+08:00",
    "处理策略": "仅提醒",
    "目标权限": None,
}
```

`处理策略` 由配置项 `实时管理.未授权管理员处理(0:仅提醒,1:设为成员,2:设为访客)` 决定：`0` 只广播提醒，`1` 设为成员，`2` 设为访客。`实时管理.管理员XUID` 中的管理员和已托管玩家不会生成该事件。

### 9.3 `unsubscribe_permission_events(token)`

取消订阅并返回布尔值：令牌存在时为 `True`，不存在时为 `False`。

```python
self.libra.unsubscribe_permission_events(token)
```

## 10. 命令通道与并发注意事项

1. Libra 根据 `是否使用魔法指令模式运行` 选择命令发送方法：
   - `true`：`game_ctrl.sendaicmd_with_resp()`。
   - `false`：`game_ctrl.sendcmd_with_resp()`。
2. 权限变更使用单写入锁。同一时间已有权限变更时，新的变更返回 `error="busy"`，调用方可稍后重试。
3. `list_admins(refresh=False)`、`get_status()` 和权限观测读取属于缓存读取，不会重新查询服务器。
4. 事件回调在 Libra 内部触发。回调应快速返回；耗时任务请由调用方自行放入线程或任务队列。
5. 关闭 ToolDelta 时 Libra 会停止实时管理线程并保存状态。调用方不应直接操作 Libra 的持久化文件。

实时权限变更还遵循以下配置：`权限修改最小间隔(秒)`限制连续写入速度；自动/托管变更失败后按 `失败重试次数` 和 `失败重试间隔(秒)`重试；操作记录和实时修正记录最多保留 `处理记录保留条数` 条。`默认权限`用于调用 `set_permission_flags()` 时省略 `flags` 的情况。

## 11. 推荐的完整调用示例

```python
from tooldelta import Plugin, ToolDelta, plugin_entry


class PermissionConsumer(Plugin):
    name = "权限联动示例"
    author = "your-name"
    version = (0, 0, 1)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.libra = None
        self.event_token = None
        self.ListenPreload(self.on_preload)
        self.ListenFrameExit(self.on_exit)

    def on_preload(self) -> None:
        self.libra = self.GetPluginAPI(
            "『Libra-天秤座』玩家权限管理系统",
            (0, 2, 0),
        )
        self.event_token = self.libra.subscribe_unknown_admin_events(
            self.on_unknown_admin
        )

    def on_unknown_admin(self, event: dict) -> None:
        self.print_war(
            f"发现未授权管理员：{event['玩家名称']} ({event['XUID']})"
        )

    def on_exit(self, *_args) -> None:
        if self.libra is not None and self.event_token is not None:
            self.libra.unsubscribe_permission_events(self.event_token)


entry = plugin_entry(PermissionConsumer, "permission-consumer-example")
```

## 12. 常见问题

**Q1：调用 `set_permission_flags()` 后，实时管理会不会立即覆盖权限？**

如果实时管理已启用且该玩家已启用持续管理，默认 `management="once"` 会返回 `managed_player`，不会覆盖。应使用 `set_managed_rule()` 更新目标规则，或暂停持续管理后再执行一次性设置。

**Q2：快照还原后服务器权限是否立即改变？**

不会。还原只更新 Libra 的期望权限和持续管理状态。启用实时管理时，后续在线检查可能按还原后的目标权限修正；否则需要调用权限设置 API。

**Q3：为什么管理员列表只有 XUID，没有名字？**

名字来自 `XUID获取` 的在线/离线身份数据。数据不存在或前置 API 不可用时，`list_admin_details()` 会将 `name` 返回为 `None`，但 XUID 仍然保留。

**Q4：自定义权限是否等同于管理员？**

不等同。`classify_permission()` 只按八项能力标志分类；服务器管理员身份应以 `list_admins()` 的结果判断。

## 13. 快速索引

| 类别 | API |
| --- | --- |
| 转换校验 | `parse_flags`、`format_flags`、`describe_flags`、`classify_permission` |
| 管理员与权限 | `list_admins`、`list_admin_details`、`set_permission_flags`、`revoke_admin`、`audit`、`get_status` |
| 快照 | `save_snapshot`、`list_snapshots_api`、`preview_snapshot_api`、`restore_snapshot_api`、`delete_snapshot_api` |
| 实时管理 | `get_realtime_status`、`set_realtime_enabled`、`set_managed_rule`、`get_managed_rule`、`set_managed_enabled`、`pause_managed_rule`、`remove_managed_rule`、`list_online_permissions` |
| 在线检查 | `get_permission_fix_history`、`get_player_permissions`、`request_permission_check` |
| 身份搜索 | `resolve_player_name`、`resolve_player_names`、`search_players` |
| 事件 | `subscribe_permission_events`、`subscribe_unknown_admin_events`、`unsubscribe_permission_events` |

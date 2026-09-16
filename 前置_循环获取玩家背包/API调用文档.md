# 前置_循环获取玩家背包 API

插件 ID：`循环获取玩家背包`

插件使用 `sendwscmd()` 的 WebSocket 通道，不会调用 `queryInventory()` 或修改 ToolDelta 源码。每轮会读取当前在线玩家（包含 ToolDelta 机器人），并发发送并等待响应：

```text
codebuilder_actorinfo inventory "玩家名"
```

一轮查询全部完成后，等待配置项“发送命令间隔时长(单位：秒)”指定的时间再开始下一轮。

返回数据按 ToolDelta 原版 `queryInventory()` 的 `QueriedInventory` 结构解析：兼容
`DataSet` 直接返回库存对象，以及部分接入点使用的 `{"inventory": {...}}` 包装格式；同时兼容 UTF-8 BOM、嵌套 JSON 字符串和被转义的 JSON 文本。

## 配置

配置文件由 ToolDelta 自动生成：

```json
{
    "发送命令间隔时长(单位：秒)": 3,
    "单次查询超时时间(秒)": 1
}
```

当接入点不支持 WebSocket 指令时，插件仍会加载，但只输出一次警告并暂停轮询。

## 直接 API

其他插件通过 `GetPluginAPI("循环获取玩家背包", (0, 0, 1))` 获取插件实例。

| 方法 | 说明 |
| --- | --- |
| `get_cached_inventory(player_name)` | 返回指定玩家最近一次成功查询的 `QueriedInventory`，没有缓存时返回 `None`。 |
| `get_cached_inventories()` | 返回 `{玩家名: QueriedInventory}`。返回值是副本，修改不会影响插件缓存。 |
| `get_cached_inventories_dict()` | 返回 `{玩家名: dict}`，结构与原版 `queryInventory()` 解码后的字典一致。 |
| `get_last_failures()` | 返回最近一轮失败玩家及错误时间。 |
| `query_inventory(player_name, timeout=None)` | 立即查询一个当前在线玩家，默认使用配置中的单次超时时间，并更新该玩家缓存。 |
| `queryInventory(player_name, timeout=None)` | `query_inventory` 的兼容别名，返回同样的 `QueriedInventory` 对象。 |
| `force_update()` | 立即并发查询全部在线玩家，广播并返回本轮快照。插件暂停时返回 `None`。 |
| `set_cycle(seconds)` | 运行时修改轮询间隔，仅影响当前运行周期。 |

## 内部广播

### 发布事件：`ggpi:publish_player_inventory`

插件每轮完成后发送一次：

```python
{
    "玩家背包": {"玩家名": QueriedInventory(...)},
    "玩家背包字典": {"玩家名": {...}},
    "失败玩家": {
        "玩家名": {
            "错误": "错误文本",
            "失败原因": "错误文本",
            "时间": "ISO-8601 时间"
        }
    },
    "更新时间": "ISO-8601 时间"
}
```

成功玩家组成当前缓存；本轮失败玩家和已经离线的玩家都会从当前缓存移除。

### 请求立即刷新：`ggpi:force_update`

```python
InternalBroadcast("ggpi:force_update", {})
```

回调返回本轮快照；插件暂停时返回 `None`。

### 修改轮询间隔：`ggpi:set_cycle`

```python
InternalBroadcast("ggpi:set_cycle", {"间隔": 5})
```

也兼容坐标前置风格的键名：`{"cycle": 5}`。

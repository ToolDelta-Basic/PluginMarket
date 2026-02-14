# NekoMaid 中转站 Agent（ToolDelta）

本插件用于让 ToolDelta 作为 **Agent 客户端** 连接 `neko-relay`，从而与 `maid.neko-craft.com`（或本地 NekoMaid 前端）共用同一套前端协议。

## 前置条件

- 已部署并可访问 `neko-relay`（提供 `/ws/agent` 与 `/s/<node_id>`）
- ToolDelta 运行环境可连接到该 `neko-relay`（通常走内网 `ws://.../ws/agent`）

## 配置文件

首次启动会自动生成：`插件配置文件/NekoMaid中转站Agent.json`

常用字段：

- `中转服务地址`：Agent 连接地址（例：`ws://127.0.0.1:7071/ws/agent`）
- `对外访问地址`：浏览器可访问的 base URL（例：`https://relay.example.com`）
- `节点ID` / `节点密钥` / `网页Token`：留空会自动生成/回填
- `状态刷新间隔秒`：向面板上报在线列表等状态的间隔
- `启用玩家上下线事件` / `启用聊天事件`：是否上报事件到面板控制台

## 控制台命令

插件在激活后注册控制台命令：

- `maid` / `neko` / `relay`：打印“对外服务器地址”和“maid 打开链接”


# Lumelta

## 项目概述
Lumelta 是基于 Lupa 框架开发的 ToolDelta 平台扩展插件，专注于为 Lumega 生态的 Lua 插件提供运行时支持。作为连接 ToolDelta 框架与 Lumega 插件生态的桥梁，本项目致力于实现高度兼容的 Lua 插件运行环境。

## 功能实现状态

### ✅ 已实现核心模块
| 模块名称        | 功能描述                           |
|-----------------|----------------------------------|
| `storage`       | 数据存储模块                     |
| `cmds`          | 指令执行模块                     |
| `players`       | 玩家交互模块                      |
| `listen`        | 基于 Mux Poller 的事件监听模块      |
| `system`        | 系统操作模块                      |
| `async_http`    | 异步 HTTP 通信模块                 |
| `flex`          | 跨插件调用模块                     |
| `menu`          | 交互式菜单系统                     |
| `storage_path`  | 存储路径管理模块                   |

### 🚧 开发中模块
- `common`: 基础工具库
- `builder`: 方块构建模块
- `botUq`: 机器人数据模块

### ❌ 待实现模块
- `c_common_exts` C扩展库
- `bot_action` 机器人操作
- `websocket` WebSocket 支持
- `cqhttp` CQHTTP 协议集成
- `share` 数据共享

## 兼容性说明

### 插件支持
- **基础兼容**：可正常运行大部分的 Lumega Lua 插件
- **已知限制**：
  - 机器人相关功能需待 `botUq` 和 `bot_action` 模块完成
- **已知问题**：
  - 日志记录错误（没有记录在 `log` 文件夹）

### Built-In
Lumega 的 Built-In 插件可通过以下方式适配：
1. 写入进 Lumelta 代码中
2. 编写类 ToolDelta 插件放入文件夹 `wrap/builtin_plugins` 中（参考示例：[死亡点记录插件](./wrap/builtin_plugins/返回死亡点/__init__.py))

## 使用说明

### neomega_storage
会直接生成在运行时目录的 `./neomega_storage` 文件夹中

## 贡献指引
欢迎通过以下方式参与项目：
- 编写注释
- 模块开发
- 兼容测试
- 文档完善
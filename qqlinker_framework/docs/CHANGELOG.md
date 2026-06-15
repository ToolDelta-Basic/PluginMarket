# v1.5.0 更新日志

## 安全加固（渗透测试驱动）

### 高危修复
- **规则引擎权限落地**: `CommandRouter` 的 `min_uid` 检查现在读取 `raw_data._rule_uid`，规则引擎托管命令真正以 `uid=200` 执行，不再依赖触发者的真实 uid
- **DemoRunner 并发控制**: 浮动任务改为 `asyncio.create_task` 保存引用，每群并发上限 1，`on_stop` 全部取消，防止消息洪泛攻击

### 中危修复
- **规则文件原子写入**: `_save_rules` 改用 `tempfile.mkstemp` 替代硬编码 `.tmp`
- **规则列表深拷贝**: `_get_rules` 返回 `copy.deepcopy(rules)`，防止调用方意外污染
- **动作链上限**: 规则创建时最多 20 条动作，执行时硬截断 `MAX_ACTIONS_PER_RULE`
- **group_only 下沉**: `DemoRunner.run()` 执行层二次校验群限定（defense in depth）

### 架构加强
- **框架关闭超时**: 每个模块 `on_stop` 有 5 秒超时，超时跳过不阻塞
- **命令残留清理**: `SourceManager.cleanup_orphan_commands()` 每 20 分钟扫描清理未加载模块的过期命令

## 新功能

### 模版引擎 TemplateEngine
- `TemplateModule` 注册为宿主框架服务 (`services.register("template", engine)`)
- 命令: `.模板 列表` / `.模板 检查` / `.模板 切换 <名>` / `.模板 状态`
- 四种内置模板: 保守/默认/激进/调试
- 切换时自动备份当前配置

### 演示模式 DemoModule
- `@demo_scene` 装饰器约定，开发者定义演示脚本
- `.演示 列表` / `.演示 <场景名>` 命令
- 纯文本发送，不进 EventBus，零攻击面

### 服务注册表 ServiceRegistry
- 与模块注册表同款的允则 JSON 控制 (`数据/服务注册表.json`)
- 内核级服务免检（mid ≤ 99），首次启动自动签署
- `ServiceContainer.register()` 中加注册表检查

### 平台解绑
- 新增 `StandaloneAdapter` — QQ 独立模式，所有游戏接口空实现
- 适配器接口隔离完整，无需 Minecraft 即可运行
- 平台迁移文档更新

### Phase 2 分层改进
- 初始化分层现在同时使用 `required_services` 和 `dependencies`
- 确保 `template` 先于 `config_router` 初始化

## 改进
- 规则引擎调试日志降级为 `_log.debug`，仅在调试模式输出
- `_route_command` 路径与 `_get_rules` 统一，消除规则匹配/列表路径不一致 bug
- 规则动作链洪水防护（创建上限 + 执行截断）
- 模块 API 文档全面更新到 v1.5.0

---

# v1.5.1 更新日志

## 架构升维：框架变为纯通信信道

### 核心变革
- **框架定位升维**: 从"包含所有业务逻辑的全能框架"变为"库与库之间的通信信道"
- **信道协议**: 新增 `core/channel.py` — `ServiceBus`, `EventPipe`, `ConfigSource`, `MessageBus`, `CommandRegistry`, `Library` 六大协议定义
- **信道核心**: 新增 `libraries/service_bus.py` — 从零实现的 `ServiceRegistry` + `EventBus`，零旧代码依赖
- **配置信道**: 新增 `libraries/config_source.py` — 从零实现的 `_ConfigStore`（JSON 原子写入 + 点号路径）
- **信道主机**: 新增 `libraries/channel_host.py` — 拓扑排序 + 顺序 mount，不依赖旧 `core/host.py`

### 业务库从零重写
- **消息总线**: `libraries/message_bus.py` — 令牌桶削峰消息队列 + `_CommandRegistry`
- **命令路由**: `libraries/command_router.py` — 命令匹配 + 冷却 + 权限 + 子命令回退
- **适配器桥接**: `libraries/adapter_bridge.py` — 4 种平台事件 → 信道事件（GroupMessage / GameChat / PlayerJoin / PlayerLeave）
- **模块加载**: `libraries/module_loader.py` — `Module` 基类 + 动态发现 + 注册表 + 信道注入

### 统计
- 7 个新库，983 行纯实现
- 21 个类，52 个方法
- **全部零旧代码依赖**（不 import `core/kernel/`, `managers/`, `core/drivers/`）
- 任意库可独立替换

### 约定系统
- **ConventionRegistry**: `注册表/约定注册表.json` — 9 个内置约定（演示模式、规则引擎、模板引擎等），允则控制
- **注册表统一**: 模块/服务/约定注册表全部迁移到 `注册表/` 目录

### 演示模式 v1.3
- 硬编码返回模式：`ctx.user()` 模拟用户消息，`ctx.bot()` 模拟机器人回复
- 三个内置演示场景：命令系统、规则引擎、CMD会话
- 零副作用：不发真实命令

### 测试增强
- `MockAdapter.fire_group_message()` 模拟完整 QQ 消息链路
- 全量语法检查通过（144 个 .py 文件）
- 导入测试 13/13 通过

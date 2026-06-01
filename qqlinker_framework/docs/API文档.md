API 参考文档

版本 1.0.0

本文档描述框架中对外开放的核心服务、管理器、事件以及模块开发所需的全部接口。所有示例均基于 Python 3.10+ 及框架 1.0.0。

---

1. 服务容器 ServiceContainer

位置：core/services.py

框架的 IoC 容器，负责服务实例的注册与获取。所有管理器（如 ConfigManager、MessageManager）均通过它统一暴露。

ServiceContainer.register(name, instance_or_factory)

· name (str)：服务名称。
· instance_or_factory (Any)：实例或可调用工厂函数。若为工厂，则每次调用 get 时只执行一次并缓存结果。

ServiceContainer.get(name) -> Any

· 获取服务实例。如果注册的是工厂，会延迟实例化并缓存单例。
· 若服务未注册，抛出 KeyError。

ServiceContainer.has(name) -> bool

· 检查服务是否已注册。

示例：

```python
services = ServiceContainer()
services.register("config", ConfigManager())
config = services.get("config")
```

---

2. 事件总线 EventBus

位置：core/bus.py

线程安全的发布‑订阅事件系统，支持普通函数和协程处理器，并内置递归深度保护。

EventBus.subscribe(event_type, handler, priority=0)

· event_type (str)：事件类名（如 "GroupMessageEvent"）。
· handler (Callable)：处理函数，接收事件实例（同步或异步）。
· priority (int)：优先级，数值越高越早执行。默认 0。

EventBus.unsubscribe(event_type, handler)

· 取消指定类型的某个处理器的订阅。

await EventBus.publish(event)

· 发布事件，按优先级顺序依次调用所有订阅处理器。
· 若处理器为异步，则 await 执行；同步处理器直接调用。
· 当嵌套发布深度超过 MAX_EVENT_DEPTH（10）时，事件被丢弃并记录错误。

示例：

```python
async def handle_ai(event: AIResponseEvent):
    ...

event_bus.subscribe("AIResponseEvent", handle_ai, priority=5)
await event_bus.publish(AIResponseEvent(user_id=123, group_id=456, reply="Hello"))
```

---

3. 模块基类 Module

位置：core/module.py

所有业务模块必须继承此类。它提供声明式命令注册、事件监听、工具注册以及服务注入。

类属性：

· name (str)：模块唯一名称。
· version (tuple[int, int, int])：版本号。
· dependencies (list[str])：依赖的其他模块 name。
· required_services (list[str])：需要注入的服务名称列表，自动作为实例属性（例如 "message" 对应 self.message）。

Module.__init__(services, event_bus)

· 框架调用，注入服务容器和事件总线。子类不应覆盖。

await Module.on_init()

· 抽象方法，必须实现。在此注册命令、工具、事件监听。

await Module.on_start()

· 可选。模块启动后的额外逻辑（如连接外部服务）。

await Module.on_stop()

· 可选。模块卸载时的清理逻辑（如关闭连接、释放资源）。

Module.register_command(trigger, callback, *, cmd_type="group", description="", op_only=False, argument_hint="")

· trigger (str)：命令触发词（如 ".ping"）。
· callback (Callable)：异步回调，接收 CommandContext 实例。
· cmd_type："group" 或 "console"。
· description：帮助文本。
· op_only：是否仅管理员可用。
· argument_hint：参数提示文本（如 "<问题>"）。

Module.listen(event_type, handler, priority=0)

· event_type (str)：事件类名。
· handler (Callable)：事件处理函数。
· priority (int)：优先级。

Module.register_tool(tool_definition: dict)

· 注册一个通用工具，详见 ToolManager。

---

4. 声明式装饰器

位置：core/decorators.py

@command(trigger, *, cmd_type="group", description="", op_only=False, argument_hint="")

· 标记一个方法为命令处理器。等价于在 on_init 中调用 self.register_command(...)。

@listen(event_type, priority=0)

· 标记一个方法为事件监听器。

示例：

```python
class MyModule(Module):
    @command(".test")
    async def cmd_test(self, ctx):
        await ctx.reply("test")

    @listen("GroupMessageEvent")
    async def on_msg(self, event):
        ...
```

---

5. 命令上下文 CommandContext

位置：core/context.py

封装一次命令请求的所有信息，并提供便捷回复方法。

属性：

· user_id (int)：发送者 QQ 号。
· group_id (int)：群号。
· nickname (str)：昵称。
· message (str)：原始完整消息。
· args (List[str])：按空格分割的参数列表。
· adapter (IFrameworkAdapter)：平台适配器实例。

await CommandContext.reply(text: str)

· 回复消息，优先通过消息管理器（享有限流），否则直接通过适配器发送。

---

6. 配置管理器 ConfigManager

位置：managers/config_mgr.py

服务名："config"

基于 JSON 文件，支持点号分隔的键路径访问，默认值自动合并，修改后自动持久化。

ConfigManager.register_section(section, defaults)

· 注册一个配置节并设置默认值。若配置文件中尚无此节，则立即写入。
· section (str)：顶层键名。
· defaults (dict)：默认值字典。

ConfigManager.get(key, default=None)

· key：点号分隔的路径，如 "消息转发.游戏到群.是否启用"。
· default：未找到时的返回值。

ConfigManager.set(key, value)

· 设置值，自动创建中间字典。

ConfigManager.get_data_dir() -> str

· 返回数据目录路径。

---

7. 消息管理器 MessageManager

位置：managers/message_mgr.py

服务名："message"

基于令牌桶的削峰填谷消息队列，避免触发平台频率限制。

优先级枚举：

```python
class SendPriority(IntEnum):
    HIGH = 0
    NORMAL = 1
    LOW = 2
```

await MessageManager.send_group(group_id, message, priority=SendPriority.NORMAL)

· 将群消息推入队列异步发送。

await MessageManager.send_private(user_id, message, priority=SendPriority.NORMAL)

· 私聊消息队列。

await MessageManager.start() / stop()

· 框架自动管理，模块无需调用。

---

8. 工具管理器 ToolManager

位置：managers/tool_mgr.py

服务名："tool"

通用工具注册中心，支持分类、权限、配置注入，并生成 OpenAI function‑calling schema。

ToolManager.register_tool(tool_def: dict) -> bool

· 注册一个工具。tool_def 必须包含：
  · "name"：唯一名称。
  · "description"：描述。
  · "parameters"：OpenAI JSON Schema 的 properties 字典。
  · "callback"：执行回调，签名可为 (params, context) 或 (params, context, tool_config)。
  · 可选："timeout", "enabled", "risk_level", "admin_only", "category", "required_config_keys"（提供者名称列表）。

ToolManager.get_tools_schema(only_enabled=True) -> list[dict]

· 返回所有已注册工具的 OpenAI function‑calling 兼容数组。

await ToolManager.execute(name, arguments, context=None) -> str

· 异步执行指定工具，返回结果字符串。自动注入工具所需的 API 提供者配置。

ToolManager.add_provider(name, address, token=None) -> bool

· 动态添加 API 提供者，写入 tool_config.json，重复名称返回 False。

---

9. 包管理器 PackageManager

位置：managers/package_mgr.py

服务名："package"

运行时依赖检查与安装，支持多源镜像与失败回滚。

PackageManager.register_requirements(reqs: dict[str, str])

· 注册 {包名: 导入名} 映射。

PackageManager.check_missing() -> dict

· 返回缺失的依赖。

PackageManager.install_packages(packages, upgrade=False, mirror_sources=None) -> bool

· 使用 pip 安装列表中的包，失败时自动回滚。

---

10. 平台适配器 IFrameworkAdapter

位置：adapters/base.py

抽象基类，定义所有需要实现的平台操作。当前实现为 ToolDeltaAdapter。

核心方法（均需实现）：

· send_game_command(cmd: str)
· send_game_message(target: str, text: str)
· get_online_players() -> List[str]
· send_group_msg(group_id: int, message: str) -> bool
· send_private_msg(user_id: int, message: str) -> bool
· listen_game_chat(handler)
· listen_player_join(handler)
· listen_player_leave(handler)
· listen_group_message(handler)
· register_console_command(triggers, hint, usage, func)
· get_plugin_api(name: str) -> Any
· is_user_admin(user_id: int, config_mgr) -> bool

---

11. 事件类

位置：core/events.py

所有事件均为 @dataclass，继承 BaseEvent。

事件类 重要字段
GroupMessageEvent user_id, group_id, nickname, message, raw_data, handled
GameChatEvent player_name, message
PlayerJoinEvent player_name
PlayerLeaveEvent player_name
AIResponseEvent user_id, group_id, reply, media, should_forward_to_game
SystemStartEvent / SystemStopEvent 框架生命周期
from tooldelta import cfg

CONFIG_DEFAULT = {
    "白名单": [
        "player1",
        "player2",
        "MagiCow"
    ],
    "完全权限白名单": [
        "player1"
    ],
    "一级权限白名单": [
        "player1",
        "player2"
    ],
    "危险命令列表": [
        "op ",
        "deop ",
        "stop"
    ],
    "Info": {
        "无权限提示": "§c§l您没有权限使用此功能",
    },
    "UI文本": {
        "AI助手": {
            "输入为空": "§c§l✗ Input is empty",
            "消息不能为空": "§c✗ Message cannot be empty",
            "输入提示": "§e§lEnter your request: ",
            "参数格式错误": "§c✗ Invalid argument format: {error}",
            "输入错误": "§c✗ Invalid input: {error}",
            
            "处理中框": "§d╔═══════════════════════╗",
            "处理中标题": "§d║ §6§lProcessing Request §d║",
            "处理中框底": "§d╚═══════════════════════╝",
            "分隔线": "§8━━━━━━━━━━━━━━━━━━━━━━━",
            "工具说明": "§7§oAI can call game tools to complete your request...",
            
            "思考中": "§d┃ §fAI Thinking... §7(Call: {current}/{max})",
            
            "工具调用框顶": "§b┌─ §6[Tool Call #{count}] §b─┐",
            "工具名称": "§b│ §fTool: §e{tool}",
            "工具参数": "§b│ §fArgs: §7{args}",
            "工具结果成功": "§b│ §fResult: §a✓ {message}",
            "工具结果失败": "§b│ §fResult: §c✗ {error}",
            "工具调用框底": "§b└─────────────────┘",
            
            "错误框": "§c╔═══════════════════════╗",
            "错误标题": "§c║ §4§lError Occurred §c║",
            "错误框底": "§c╚═══════════════════════╝",
            
            "响应框": "§d╔═══════════════════════╗",
            "响应标题": "§d║ §b§lAI Agent Response §d║",
            "响应框底": "§d╚═══════════════════════╝",
            
            "统计标题": "§7§l Statistics",
            "工具调用次数": "§7• §fTools Called: §e{count}",
            "Token使用": "§7• §fTokens Used: §e{tokens}",
            "费用": "§7• §fCost: §e¥{cost}"
            # 注意 Cost仅为预期消耗费用 实际产生费用以模型提供方的每百万输入/输出token为主
        },
        
        "清除对话": {
            "成功框": "§a╔═══════════════════════╗",
            "成功标题": "§a║ §2§lSuccess §a║",
            "成功框底": "§a╚═══════════════════════╝",
            "成功消息": "§a✓ Chat history cleared",
            
            "失败框": "§c╔═══════════════════════╗",
            "失败标题": "§c║ §4§lFailed §c║",
            "失败框底": "§c╚═══════════════════════╝",
            "失败消息": "§c✗ Failed to clear chat history"
        },
        
        "取消AI": {
            "成功框": "§a╔═══════════════════════╗",
            "成功标题": "§a║ §2§l请求已取消 §a║",
            "成功框底": "§a╚═══════════════════════╝",
            "成功消息": "§a✓ 您的AI请求已被标记为取消",
            "提示": "§7AI将在当前操作完成后停止",
            
            "无请求框": "§c╔═══════════════════════╗",
            "无请求标题": "§c║ §4§l无活动请求 §c║",
            "无请求框底": "§c╚═══════════════════════╝",
            "无请求消息": "§c✗ 您当前没有正在进行的AI请求"
        }
    },
    "AI配置": {
        "API提供商": "siliconflow",
        "APIkey": "Api key",
        "工具系统提示词": """你是Minecraft基岩版AI助手，帮助玩家执行游戏操作。

1. 操作玩家相关操作前必须先调用get_online_players获取在线列表
2. 支持模糊匹配玩家名（中英文、大小写不敏感）
3. 找不到玩家时列出在线玩家供选择
【ID格式】
- 物品/方块：minecraft:item_name 或 item_name
- 坐标：x y z（如：100 64 200）
【工作流程】
涉及玩家操作 → get_online_players → 匹配名称 → 执行工具 → 格式化回复
【回复格式】
使用Minecraft颜色代码直接格式化文本：
- §a = 绿色（成功）
- §c = 红色（错误）
- §6 = 金色（警告）
- §b = 蓝色（数据信息）
- §e = 黄色（高亮）
- §f = 白色（普通）
示例：
- 传送成功：§a✓ §f已将玩家§e Steve §f传送到§b (100, 64, 200)
- 给予物品：§a✓ §f已给予§e Steve §f物品§b minecraft:diamond ×10
- 查询背包：§e Steve §f的背包：§b 钻石×10 铁锭×64 §f等共15种物品
保持语言简洁 逻辑清晰
""",
        "模型名称": "deepseek-chat",
        "硅基流动模型名称": "deepseek-ai/DeepSeek-V3.2",
        "最大历史长度": 3,
        "最大工具调用次数": 24,
        "API请求超时秒数": 90
    },
}

CONFIG_STD = {
    "白名单": cfg.JsonList((int, str)),
    "完全权限白名单": cfg.JsonList((int, str)),
    "一级权限白名单": cfg.JsonList((int, str)),
    "危险命令列表": cfg.JsonList(str),
    "Info": dict,
    "UI文本": dict,
    "AI配置": dict,
}

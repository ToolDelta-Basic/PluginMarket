from typing import TYPE_CHECKING
from tooldelta import Player
from tooldelta.internal.launch_cli import FrameNeOmgAccessPoint
if TYPE_CHECKING:
    from . import MCAgent


class Core:
    """Core functionality handler for MCAgent plugin.

    Manages main plugin operations including AI assistant interactions,
    conversation management, and menu integrations.
    """

    def __init__(self, plugin: "MCAgent"):
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl
        self.players = plugin.players
        self.neomega = self.get_neomega()

    def get_neomega(self):
        if isinstance(self.plugin.frame.launcher, FrameNeOmgAccessPoint):
            return self.plugin.frame.launcher.omega
        else:
            raise ValueError("此启动框架无法使用 NeOmega API")

    def ClearChat(self, player: Player, args: tuple):
        from .permission import PermissionLevel
        player_permission = self.plugin.permission_manager.get_player_permission_level(player)

        if player_permission.value < PermissionLevel.CREATIVE.value:
            player.show(self.plugin.Info['无权限提示'])
            return True

        self.clear_chat_history(player, "tools")
        return True

    def CancelAI(self, player: Player, args: tuple):
        """取消当前正在进行的AI请求"""
        from .permission import PermissionLevel
        player_permission = self.plugin.permission_manager.get_player_permission_level(player)

        if player_permission.value < PermissionLevel.CREATIVE.value:
            player.show(self.plugin.Info['无权限提示'])
            return True

        # 尝试取消请求
        if self.plugin.agent.cancel_request(player.name):
            player.show("§a╔═══════════════════════╗")
            player.show("§a║ §2§l请求已取消 §a║")
            player.show("§a╚═══════════════════════╝")
            player.show("§a✓ 您的AI请求已被标记为取消")
            player.show("§7AI将在当前操作完成后停止")
        else:
            player.show("§c╔═══════════════════════╗")
            player.show("§c║ §4§l无活动请求 §c║")
            player.show("§c╚═══════════════════════╝")
            player.show("§c✗ 您当前没有正在进行的AI请求")

        return True

    def clear_chat_history(self, player: Player, conversation_type: str = "tools"):
        ui = self.plugin.ui_texts['清除对话']

        success = self.plugin.agent.clear_conversation_history(player.name, conversation_type)
        if success:
            player.show(ui['成功框'])
            player.show(ui['成功标题'])
            player.show(ui['成功框底'])
            player.show(ui['成功消息'])
        else:
            player.show(ui['失败框'])
            player.show(ui['失败标题'])
            player.show(ui['失败框底'])
            player.show(ui['失败消息'])


    def AIAssistant(self, player: Player, args: tuple):
        ui = self.plugin.ui_texts['AI助手']

        from .permission import PermissionLevel
        player_permission = self.plugin.permission_manager.get_player_permission_level(player)

        if player_permission.value < PermissionLevel.CREATIVE.value:
            player.show(self.plugin.Info['无权限提示'])
            return True

        if args:
            try:
                if isinstance(args[0], list):
                    message = ' '.join(args[0])
                else:
                    message = ' '.join(args)
            except Exception as e:
                player.show(ui['参数格式错误'].format(error=str(e)))
                return True
        else:
            try:
                player.show("§7§l提示: 输入消息时请勿使用其他菜单命令")
                player.show("§7如需退出，请输入 §e退出 §7或 §ecancel")
                message = player.input(ui['输入提示'], 120)
            except TimeoutError:
                player.show("§c输入超时，已自动退出")
                return True
            except Exception as e:
                player.show(ui['输入错误'].format(error=str(e)))
                return True

        # 检查是否是退出命令
        if message and message.lower() in ['退出', 'exit', 'quit', 'cancel', 'q']:
            player.show("§a已取消操作")
            return True

        if not message:
            player.show(ui['消息不能为空'])
            return True

        self.chat_with_tools(player, message)
        return True

    def chat_with_tools(self, player: Player, message: str):
        config = self.plugin.agent_config

        api_provider = config.get('API提供商', 'deepseek').lower()

        if api_provider == 'siliconflow':
            model = config.get('硅基流动模型名称', 'deepseek/deepseek-chat')
        else:
            model = config.get('模型名称', 'deepseek-chat')

        default_system_prompt = """你是Minecraft基岩版AI助手，帮助玩家执行游戏操作。
】
1. 操作玩家前必须先调用get_online_players获取在线列表
2. 支持模糊匹配玩家名（中英文、大小写不敏感）
3. 找不到玩家时列出在线玩家供选择
4. 操作后简洁告知结果

【ID格式】
- 物品/方块：minecraft:item_name 或 item_name
- 坐标：x y z（如：100 64 200）

【工作流程】
涉及玩家操作 → get_online_players → 匹配名称 → 执行工具 → 格式化回复

【交互式菜单工具使用规则 】
使用interact_with_menu工具与菜单系统交互，支持会话管理：

1. 开始新会话：
   interact_with_menu(player_name, trigger_word, action="start")
   # 创建新会话并获取菜单选项

2. 读取返回信息：
   - new_messages: 本次新增的消息
   - menu_options: 提取的选项列表
   - input_prompts: 输入提示
   - has_more_interaction: 是否需要继续
   - session_active: 会话是否活跃

3. 继续会话（提供输入）：
   interact_with_menu(player_name, trigger_word, user_input="4")
   # action默认为"continue"，在同一会话中输入

4. 循环交互：
   重复步骤2-3直到has_more_interaction为false

5. 会话自动结束：
   菜单完成后会话自动清理，无需手动结束

示例流程（提升职业等级）：
玩家："帮我把职业升到40级"
AI: interact_with_menu("Steve", "职业", action="start")
返回: ["1. 创建职业", "2. 职业晋升", "3. 重置职业", "4. 提升等级", ...]
AI: interact_with_menu("Steve", "职业", user_input="4")  # 选择提升等级
返回: [输入提示] 请输入想要提升的等级数量:
AI: interact_with_menu("Steve", "职业", user_input="39")  # 输入39级
返回: [输入提示] 确定要进行升级吗？
AI: interact_with_menu("Steve", "职业", user_input="确认")  # 确认
完成！

保持友好、简洁、专业"""

        self.plugin.agent.chat_with_tools(
            player=player,
            message=message,
            system_prompt=config.get('工具系统提示词', default_system_prompt),
            api_key=config['APIkey'],
            model=model,
            max_history_length=config['最大历史长度'],
            conversation_type="tools",
            max_tool_calls=config.get('最大工具调用次数', 10),
            api_provider=api_provider
        )

import json
import queue
import threading
import time
from typing import TYPE_CHECKING, Dict, List, Any, Optional, Callable
from tooldelta import Player, game_utils, fmts
from .tool_schemas import get_all_tool_schemas
from .permission import PermissionManager
from .command_block_tool import CommandBlockTool
if TYPE_CHECKING:
    from . import MCAgent

class MenuSession:
    def __init__(self, player: Player, trigger_word: str):
        self.player = player
        self.trigger_word = trigger_word
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.is_active = True
        self.captured_messages = []
        self.original_show = player.show
        self.original_input = player.input
        
    def mock_show(self, message):
        """捕获显示的消息"""
        self.captured_messages.append(str(message))
        self.original_show(message)
        self.output_queue.put(("message", str(message)))
        
    def mock_input(self, prompt="", timeout=None):
        """从队列获取输入"""
        self.captured_messages.append(f"[输入提示] {prompt}")
        self.output_queue.put(("input_request", prompt))
        
        # 等待AI提供输入
        try:
            user_input = self.input_queue.get(timeout=timeout or 300)
            return user_input
        except queue.Empty:
            raise TimeoutError("等待AI输入超时")
    
    def provide_input(self, user_input: str):
        """AI提供输入"""
        self.input_queue.put(user_input)
    
    def start(self):
        """启动会话 替换player的方法"""
        self.player.show = self.mock_show
        self.player.input = self.mock_input
    
    def stop(self):
        """停止会话 恢复player的方法"""
        self.player.show = self.original_show
        self.player.input = self.original_input
        self.is_active = False


class MinecraftAITool:
    def __init__(self, plugin: "MCAgent"):
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl
        self.players = plugin.players
        self.permission_manager = PermissionManager(plugin)
        self.tool_logger = plugin.tool_logger
        self.command_block_tool = CommandBlockTool(plugin)
        self.tools: Dict[str, Callable] = {}
        self._register_tools()
        self._current_caller: Optional[Player] = None
        self.menu_sessions: Dict[str, MenuSession] = {}  # 存储活动的菜单会话
    
    def _register_tools(self):
        self.tools = {
            "execute_command": self.execute_command,
            "teleport_player": self.teleport_player,
            "give_item": self.give_item,
            "get_player_info": self.get_player_info,
            "get_online_players": self.get_online_players,
            "get_player_position": self.get_player_position,
            "get_player_inventory": self.get_player_inventory,
            "get_player_tags": self.get_player_tags,
            "get_player_score": self.get_player_score,
            "set_block": self.set_block,
            "fill_blocks": self.fill_blocks,
            "send_message": self.send_message,
            "broadcast_message": self.broadcast_message,
            "get_game_rule": self.get_game_rule,
            "place_command_block": self.place_command_block,
            "get_chatbar_menu_triggers": self.get_chatbar_menu_triggers,
            "interact_with_menu": self.interact_with_menu,
        }
    
    def get_tools_schema(self, player: Optional[Player] = None) -> List[Dict[str, Any]]:
        all_schemas = get_all_tool_schemas()
        
        if player is None:
            return all_schemas
        
        available_tools = self.permission_manager.get_available_tools_for_player(player)
        
        filtered_schemas = [
            schema for schema in all_schemas
            if schema.get("function", {}).get("name") in available_tools
        ]
        
        return filtered_schemas
    
    def execute_tool(self, tool_name: str, parameters: Dict[str, Any], player: Optional[Player] = None) -> Dict[str, Any]:
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"未知的工具: {tool_name}",
                "available_tools": list(self.tools.keys())
            }
        
        if player is not None:
            has_permission, error_msg = self.permission_manager.check_tool_permission(player, tool_name)
            if not has_permission:
                return {
                    "success": False,
                    "error": error_msg,
                    "tool_name": tool_name,
                    "permission_denied": True
                }
        
        try:
            if tool_name == "execute_command" and player is not None:
                command = parameters.get("command", "")
                is_safe, error_msg = self.permission_manager.check_command_safety(player, command)
                if not is_safe:
                    return {
                        "success": False,
                        "error": error_msg,
                        "tool_name": tool_name,
                        "command_blocked": True
                    }
            
            self._current_caller = player
            result = self.tools[tool_name](**parameters)
            self.tool_logger.log_tool_call(tool_name, player, parameters, result)
            
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"工具执行失败: {str(e)}",
                "tool_name": tool_name,
                "parameters": parameters
            }
        finally:
            self._current_caller = None
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        try:
            if not command.startswith("/"):
                command = "/" + command
            
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
            
            if result.SuccessCount > 0:
                return {
                    "success": True,
                    "message": "命令执行成功",
                    "output": result.OutputMessages[0].Message if result.OutputMessages else "",
                    "success_count": result.SuccessCount
                }
            else:
                return {
                    "success": False,
                    "error": result.OutputMessages[0].Message if result.OutputMessages else "命令执行失败",
                    "command": command
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"命令执行异常: {str(e)}",
                "command": command
            }
    
    def teleport_player(self, player_name: str, x: float, y: float, z: float) -> Dict[str, Any]:
        try:
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            command = f"/tp {player_name} {x} {y} {z}"
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
            
            if result.SuccessCount > 0:
                return {
                    "success": True,
                    "message": f"已将玩家 {player_name} 传送到 ({x}, {y}, {z})",
                    "player": player_name,
                    "position": {"x": x, "y": y, "z": z}
                }
            else:
                return {
                    "success": False,
                    "error": "传送失败",
                    "details": result.OutputMessages[0].Message if result.OutputMessages else ""
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"传送异常: {str(e)}"
            }
    
    def give_item(self, player_name: str, item_id: str, amount: int = 1) -> Dict[str, Any]:
        try:
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            if ":" not in item_id:
                item_id = f"minecraft:{item_id}"
            
            command = f"/give {player_name} {item_id} {amount}"
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
            
            if result.SuccessCount > 0:
                return {
                    "success": True,
                    "message": f"已给予玩家 {player_name} {amount}个 {item_id}",
                    "player": player_name,
                    "item": item_id,
                    "amount": amount
                }
            else:
                return {
                    "success": False,
                    "error": "给予物品失败",
                    "details": result.OutputMessages[0].Message if result.OutputMessages else ""
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"给予物品异常: {str(e)}"
            }
    
    def get_player_info(self, player_name: str) -> Dict[str, Any]:
        try:
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            # 获取玩家对象
            player = self.plugin.frame.players_maintainer.getPlayerByName(player_name)
            if player is None:
                return {
                    "success": False,
                    "error": f"无法获取玩家 {player_name} 的信息"
                }
            
            try:
                pos_data = game_utils.getPos(player_name, timeout=5)
                position = pos_data["position"]
                dimension = pos_data["dimension"]
            except Exception:
                position = None
                dimension = None
            
            return {
                "success": True,
                "player": {
                    "name": player.name,
                    "uuid": player.uuid,
                    "xuid": player.xuid,
                    "online": player.online,
                    "is_op": player.is_op(),
                    "position": position,
                    "dimension": dimension
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取玩家信息异常: {str(e)}"
            }
    
    def get_online_players(self) -> Dict[str, Any]:
        try:
            players = game_utils.get_all_player()
            return {
                "success": True,
                "players": players,
                "count": len(players)
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取在线玩家列表异常: {str(e)}"
            }
    
    def get_player_position(self, player_name: str) -> Dict[str, Any]:
        try:
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            pos_data = game_utils.getPos(player_name, timeout=5)
            position = pos_data["position"]
            dimension = pos_data["dimension"]
            
            return {
                "success": True,
                "player": player_name,
                "position": {
                    "x": position["x"],
                    "y": position["y"],
                    "z": position["z"]
                },
                "dimension": dimension
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取玩家位置异常: {str(e)}"
            }
    
    def get_player_inventory(self, player_name: str) -> Dict[str, Any]:
        try:
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            # 获取玩家对象
            player = self.plugin.frame.players_maintainer.getPlayerByName(player_name)
            if player is None:
                return {
                    "success": False,
                    "error": f"无法获取玩家 {player_name} 的信息"
                }
            
            inventory = player.queryInventory()
            items_list = []
            item_summary = {}
            
            for i in range(36):
                slot = inventory.slots[i] if i < len(inventory.slots) else None
                if slot is not None:
                    item_id = getattr(slot, 'id', 'unknown')
                    stack_size = getattr(slot, 'stackSize', 0)
                    
                    if stack_size > 0:
                        item_info = {
                            "slot": i,
                            "item_id": item_id,
                            "count": stack_size
                        }
                        items_list.append(item_info)
                        
                        if item_id in item_summary:
                            item_summary[item_id] += stack_size
                        else:
                            item_summary[item_id] = stack_size
            
            return {
                "success": True,
                "player": player_name,
                "inventory": {
                    "items": items_list,
                    "summary": item_summary,
                    "total_slots": len(items_list),
                    "empty_slots": 36 - len(items_list)
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取玩家背包异常: {str(e)}"
            }
    
    def get_player_tags(self, player_name: str) -> Dict[str, Any]:
        try:
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            command = f"/tag \"{player_name}\" list"
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
            
            if result.SuccessCount > 0 and result.OutputMessages:
                message = result.OutputMessages[0].Message
                fmts.print_inf(f"[get_player_tags] 原始消息: {message}")
                
                tags = []
                message_lower = message.lower()
                
                if "has no tags" in message_lower or "no tags" in message_lower:
                    return {
                        "success": True,
                        "player": player_name,
                        "tags": [],
                        "count": 0,
                        "raw_message": message
                    }
                
                if hasattr(result.OutputMessages[0], 'Parameters') and result.OutputMessages[0].Parameters:
                    params = result.OutputMessages[0].Parameters
                    fmts.print_inf(f"[get_player_tags] Parameters: {params}")
                    
                    if len(params) > 1:
                        potential_tags = params[1:]
                        tags = [str(tag).strip() for tag in potential_tags if tag and str(tag).strip()]
                
                if not tags:
                    if ":" in message:
                        tags_part = message.split(":", 1)[1].strip()
                        if "," in tags_part:
                            tags = [tag.strip() for tag in tags_part.split(",") if tag.strip()]
                        elif " " in tags_part:
                            tags = [tag.strip() for tag in tags_part.split() if tag.strip()]
                        else:
                            if tags_part:
                                tags = [tags_part]
                    
                    # 尝试查找方括号内的内容 [tag1, tag2]
                    elif "[" in message and "]" in message:
                        import re
                        match = re.search(r'\[(.*?)\]', message)
                        if match:
                            tags_str = match.group(1)
                            tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
                
                fmts.print_inf(f"[get_player_tags] 解析结果: {tags}")
                
                return {
                    "success": True,
                    "player": player_name,
                    "tags": tags,
                    "count": len(tags),
                    "raw_message": message
                }
            else:
                error_msg = result.OutputMessages[0].Message if result.OutputMessages else "未知错误"
                return {
                    "success": False,
                    "error": "获取玩家标签失败",
                    "details": error_msg,
                    "success_count": result.SuccessCount
                }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": f"获取玩家标签异常: {str(e)}",
                "traceback": traceback.format_exc()
            }
    
    def get_player_score(self, player_name: str, objective: str) -> Dict[str, Any]:
        """
        获取玩家在指定计分板上的分数
        
        Args:
            player_name (str): 玩家名称
            objective (str): 计分板名称
            
        Returns:
            Dict[str, Any]: 玩家分数信息
        """
        try:
            # 检查玩家是否在线
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            # 执行scoreboard命令查询分数
            command = f"/scoreboard players test {player_name} {objective} * *"
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
            
            if result.SuccessCount > 0 and result.OutputMessages:
                message = result.OutputMessages[0].Message
                parameters = result.OutputMessages[0].Parameters if hasattr(result.OutputMessages[0], 'Parameters') else []
                
                # 尝试从参数中提取分数
                score = None
                if parameters and len(parameters) > 0:
                    try:
                        score = int(parameters[0])
                    except (ValueError, IndexError):
                        # 如果参数解析失败，尝试从消息中提取
                        import re
                        match = re.search(r'(\d+)', message)
                        if match:
                            score = int(match.group(1))
                
                if score is not None:
                    return {
                        "success": True,
                        "player": player_name,
                        "objective": objective,
                        "score": score
                    }
                else:
                    return {
                        "success": False,
                        "error": "无法解析分数值",
                        "details": message
                    }
            else:
                # 如果test命令失败，尝试使用list命令
                command = f"/scoreboard players list {player_name}"
                result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
                
                if result.SuccessCount > 0 and result.OutputMessages:
                    message = result.OutputMessages[0].Message
                    # 尝试从消息中提取指定计分板的分数
                    import re
                    pattern = rf"{objective}:\s*(\d+)"
                    match = re.search(pattern, message)
                    if match:
                        score = int(match.group(1))
                        return {
                            "success": True,
                            "player": player_name,
                            "objective": objective,
                            "score": score
                        }
                
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 在计分板 {objective} 上没有分数或计分板不存在",
                    "details": result.OutputMessages[0].Message if result.OutputMessages else ""
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取玩家分数异常: {str(e)}"
            }

    def set_block(self, x: int, y: int, z: int, block_id: str) -> Dict[str, Any]:
        """
        设置方块
        
        Args:
            x (int): X坐标
            y (int): Y坐标
            z (int): Z坐标
            block_id (str): 方块ID
            
        Returns:
            Dict[str, Any]: 设置结果
        """
        try:
            if ":" not in block_id:
                block_id = f"minecraft:{block_id}"
            
            command = f"/setblock {x} {y} {z} {block_id}"
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
            
            if result.SuccessCount > 0:
                return {
                    "success": True,
                    "message": f"已在 ({x}, {y}, {z}) 设置方块 {block_id}",
                    "position": {"x": x, "y": y, "z": z},
                    "block": block_id
                }
            else:
                return {
                    "success": False,
                    "error": "设置方块失败",
                    "details": result.OutputMessages[0].Message if result.OutputMessages else ""
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"设置方块异常: {str(e)}"
            }
    
    def fill_blocks(self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int, block_id: str) -> Dict[str, Any]:
        """
        填充方块区域
        
        Args:
            x1, y1, z1 (int): 起始坐标
            x2, y2, z2 (int): 结束坐标
            block_id (str): 方块ID
            
        Returns:
            Dict[str, Any]: 填充结果
        """
        try:
            # 确保方块ID格式正确
            if ":" not in block_id:
                block_id = f"minecraft:{block_id}"
            
            # 执行fill命令
            command = f"/fill {x1} {y1} {z1} {x2} {y2} {z2} {block_id}"
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=10)
            
            if result.SuccessCount > 0:
                return {
                    "success": True,
                    "message": f"已填充区域 ({x1},{y1},{z1}) 到 ({x2},{y2},{z2}) 为 {block_id}",
                    "start": {"x": x1, "y": y1, "z": z1},
                    "end": {"x": x2, "y": y2, "z": z2},
                    "block": block_id
                }
            else:
                return {
                    "success": False,
                    "error": "填充方块失败",
                    "details": result.OutputMessages[0].Message if result.OutputMessages else ""
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"填充方块异常: {str(e)}"
            }
    
    def send_message(self, player_name: str, message: str) -> Dict[str, Any]:
        """
        向玩家发送消息
        
        Args:
            player_name (str): 玩家名称
            message (str): 消息内容
            
        Returns:
            Dict[str, Any]: 发送结果
        """
        try:
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            self.game_ctrl.say_to(player_name, message)
            
            return {
                "success": True,
                "message": f"已向玩家 {player_name} 发送消息",
                "player": player_name,
                "content": message
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"发送消息异常: {str(e)}"
            }
    
    def broadcast_message(self, message: str) -> Dict[str, Any]:
        """
        向所有玩家广播消息
        
        Args:
            message (str): 消息内容
            
        Returns:
            Dict[str, Any]: 广播结果
        """
        try:
            command = f"/say {message}"
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
            
            if result.SuccessCount > 0:
                return {
                    "success": True,
                    "message": "消息已广播",
                    "content": message,
                    "recipients": len(self.game_ctrl.allplayers)
                }
            else:
                return {
                    "success": False,
                    "error": "广播消息失败",
                    "details": result.OutputMessages[0].Message if result.OutputMessages else ""
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"广播消息异常: {str(e)}"
            }
    
    def get_game_rule(self, rule_name: str) -> Dict[str, Any]:
        """
        获取游戏规则
        
        Args:
            rule_name (str): 规则名称
            
        Returns:
            Dict[str, Any]: 规则值
        """
        try:
            # 执行gamerule查询命令
            command = f"/gamerule {rule_name}"
            result = self.game_ctrl.sendwscmd_with_resp(command, timeout=5)
            
            if result.SuccessCount > 0 and result.OutputMessages:
                # 解析返回的规则值
                message = result.OutputMessages[0].Message
                parameters = result.OutputMessages[0].Parameters if hasattr(result.OutputMessages[0], 'Parameters') else []
                
                return {
                    "success": True,
                    "rule": rule_name,
                    "value": parameters[0] if parameters else message
                }
            else:
                return {
                    "success": False,
                    "error": "获取游戏规则失败",
                    "details": result.OutputMessages[0].Message if result.OutputMessages else ""
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取游戏规则异常: {str(e)}"
            }

    def get_chatbar_menu_triggers(self) -> Dict[str, Any]:
        """
        获取前置_聊天栏菜单中注册的所有触发词
        
        Returns:
            Dict[str, Any]: 所有触发词信息
        """
        try:
            chatbar_api = self.plugin.chatbar
            if chatbar_api is None:
                return {
                    "success": False,
                    "error": "聊天栏菜单API未加载"
                }
            
            triggers_info = []
            for trigger in chatbar_api.chatbar_triggers:
                # 只处理StandardChatbarTriggers类型
                if hasattr(trigger, 'triggers') and hasattr(trigger, 'usage'):
                    trigger_data = {
                        "triggers": trigger.triggers,
                        "usage": trigger.usage,
                        "op_only": trigger.op_only if hasattr(trigger, 'op_only') else False,
                    }
                    
                    # 获取参数提示信息
                    if hasattr(trigger, 'argument_hints'):
                        if trigger.argument_hints == ...:
                            trigger_data["argument_hints"] = "任意参数"
                        else:
                            args_info = []
                            for hint_name, hint_type, default_val in trigger.argument_hints:
                                arg_info = {
                                    "name": hint_name,
                                    "type": hint_type.__name__ if hasattr(hint_type, '__name__') else str(hint_type),
                                    "default": default_val
                                }
                                args_info.append(arg_info)
                            trigger_data["argument_hints"] = args_info
                    
                    triggers_info.append(trigger_data)
            
            return {
                "success": True,
                "triggers": triggers_info,
                "count": len(triggers_info)
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": f"获取聊天栏菜单触发词异常: {str(e)}",
                "traceback": traceback.format_exc()
            }
    
    def interact_with_menu(self, player_name: str, trigger_word: str, user_input: str = None, action: str = "continue") -> Dict[str, Any]:
        """
        交互式菜单工具 - AI可以触发菜单、读取返回信息、并自动输入选择
        
        支持会话管理，AI可以在同一个菜单会话中连续输入多次
        
        Args:
            player_name (str): 玩家名称
            trigger_word (str): 触发词
            user_input (str): AI提供的输入（如选项编号、参数等）
            action (str): 操作类型
                - "start": 开始新会话
                - "continue": 继续当前会话（默认）
                - "end": 结束会话
            
        Returns:
            Dict[str, Any]: 包含菜单返回的信息和状态
        """
        try:
            session_key = f"{player_name}_{trigger_word}"
            
            # 检查玩家是否在线
            if player_name not in self.game_ctrl.allplayers:
                return {
                    "success": False,
                    "error": f"玩家 {player_name} 不在线"
                }
            
            # 获取玩家对象
            player = self.plugin.frame.players_maintainer.getPlayerByName(player_name)
            if player is None:
                return {
                    "success": False,
                    "error": f"无法获取玩家 {player_name} 的信息"
                }
            
            # 处理结束会话
            if action == "end":
                if session_key in self.menu_sessions:
                    session = self.menu_sessions[session_key]
                    session.stop()
                    del self.menu_sessions[session_key]
                    return {
                        "success": True,
                        "message": "会话已结束",
                        "session_ended": True
                    }
                else:
                    return {
                        "success": False,
                        "error": "没有活动的会话"
                    }
            
            # 获取或创建会话
            if action == "start" or session_key not in self.menu_sessions:
                # 清理旧会话
                if session_key in self.menu_sessions:
                    old_session = self.menu_sessions[session_key]
                    old_session.stop()
                
                # 获取聊天栏菜单API
                chatbar_api = self.plugin.chatbar
                if chatbar_api is None:
                    return {
                        "success": False,
                        "error": "聊天栏菜单API未加载"
                    }
                
                # 查找匹配的触发词
                matched_trigger = None
                for trigger in chatbar_api.chatbar_triggers:
                    if hasattr(trigger, 'triggers'):
                        if trigger_word in trigger.triggers:
                            matched_trigger = trigger
                            break
                
                if matched_trigger is None:
                    return {
                        "success": False,
                        "error": f"未找到触发词: {trigger_word}",
                        "available_triggers": [
                            t.triggers[0] for t in chatbar_api.chatbar_triggers 
                            if hasattr(t, 'triggers') and t.triggers
                        ]
                    }
                
                # 检查权限
                if hasattr(matched_trigger, 'op_only') and matched_trigger.op_only:
                    if not player.is_op():
                        return {
                            "success": False,
                            "error": f"触发词 {trigger_word} 需要OP权限",
                            "permission_denied": True
                        }
                
                # 创建新会话
                session = MenuSession(player, trigger_word)
                self.menu_sessions[session_key] = session
                session.start()
                
                # 在新线程中执行菜单
                def run_menu():
                    try:
                        if hasattr(matched_trigger, 'execute_with_no_args'):
                            matched_trigger.execute_with_no_args(player, trigger_word)
                        elif hasattr(matched_trigger, 'func'):
                            matched_trigger.func(player.name, [])
                    except Exception as e:
                        session.output_queue.put(("error", str(e)))
                    finally:
                        session.output_queue.put(("completed", None))
                
                menu_thread = threading.Thread(target=run_menu, daemon=True)
                menu_thread.start()
                
                # 等待第一个输出
                time.sleep(0.5)
            
            # 获取当前会话
            if session_key not in self.menu_sessions:
                return {
                    "success": False,
                    "error": "会话不存在，请使用 action='start' 开始新会话"
                }
            
            session = self.menu_sessions[session_key]
            
            # 如果提供了输入，发送给会话
            if user_input is not None:
                session.provide_input(user_input)
                time.sleep(0.3)  # 等待处理
            
            # 收集输出
            messages = []
            input_requests = []
            has_input_request = False
            
            while not session.output_queue.empty():
                try:
                    msg_type, content = session.output_queue.get_nowait()
                    if msg_type == "message":
                        messages.append(content)
                    elif msg_type == "input_request":
                        input_requests.append(content)
                        has_input_request = True
                    elif msg_type == "completed":
                        session.stop()
                        if session_key in self.menu_sessions:
                            del self.menu_sessions[session_key]
                    elif msg_type == "error":
                        return {
                            "success": False,
                            "error": f"菜单执行错误: {content}"
                        }
                except queue.Empty:
                    break
            
            # 解析菜单选项
            menu_options = []
            for msg in messages:
                if any(f"{i}." in msg or f"{i}、" in msg for i in range(1, 20)):
                    menu_options.append(msg)
            
            return {
                "success": True,
                "trigger": trigger_word,
                "user_input_provided": user_input,
                "captured_messages": session.captured_messages[-20:],  # 最近20条消息
                "new_messages": messages,
                "menu_options": menu_options,
                "input_prompts": input_requests,
                "has_more_interaction": has_input_request,
                "session_active": session_key in self.menu_sessions,
                "note": "使用action='start'开始新会话，action='continue'继续会话，action='end'结束会话"
            }
            
        except Exception as e:
            import traceback
            # 清理会话
            session_key = f"{player_name}_{trigger_word}"
            if session_key in self.menu_sessions:
                try:
                    self.menu_sessions[session_key].stop()
                    del self.menu_sessions[session_key]
                except:
                    pass
            
            return {
                "success": False,
                "error": f"交互式菜单异常: {str(e)}",
                "traceback": traceback.format_exc()
            }

    def place_command_block(
        self,
        x: int,
        y: int,
        z: int,
        command: str,
        mode: int = 0,
        facing: int = 0,
        need_redstone: bool = False,
        tick_delay: int = 0,
        conditional: bool = False,
        name: str = "",
        in_dim: str = "overworld"
    ) -> Dict[str, Any]:
        """
        放置命令方块并配置命令
        
        Args:
            x (int): X坐标
            y (int): Y坐标
            z (int): Z坐标
            command (str): 命令方块中的命令
            mode (int): 命令方块模式 (0: 脉冲, 1: 循环, 2: 连锁)
            facing (int): 朝向 (0-5: 下/上/北/南/西/东)
            need_redstone (bool): 是否需要红石激活
            tick_delay (int): 刻度延迟
            conditional (bool): 是否为条件模式
            name (str): 命令方块名称
            in_dim (str): 维度 (overworld/nether/the_end)
            
        Returns:
            Dict[str, Any]: 放置结果
        """
        try:
            # 安全检查：非完全权限玩家不能创建循环命令方块或保持激活的命令方块
            if self._current_caller is not None:
                from .permission import PermissionLevel
                player_permission = self.permission_manager.get_player_permission_level(self._current_caller)
                
                # 如果不是完全权限玩家
                if player_permission != PermissionLevel.FULL:
                    # 强制设置为需要红石激活
                    original_need_redstone = need_redstone
                    need_redstone = True
                    
                    # 禁止循环模式
                    if mode == 1:
                        return {
                            "success": False,
                            "error": "§c§l安全限制: 非完全权限玩家不能创建循环命令方块。请使用脉冲模式(mode=0)或连锁模式(mode=2)。",
                            "security_blocked": True
                        }
                    
                    # 如果原本请求的是保持激活状态，返回提示信息
                    result = self.command_block_tool.place_command_block(
                        x=x, y=y, z=z,
                        command=command,
                        mode=mode,
                        facing=facing,
                        need_redstone=need_redstone,
                        tick_delay=tick_delay,
                        conditional=conditional,
                        name=name,
                        should_track_output=True,
                        execute_on_first_tick=False,  # 非完全权限玩家的命令方块不在第一刻执行
                        in_dim=in_dim
                    )
                    
                    # 如果成功放置，添加安全提示
                    if result.get("success"):
                        mode_names = {0: "脉冲", 1: "循环", 2: "连锁"}
                        mode_name = mode_names.get(mode, "未知")
                        
                        result["message"] = f"§e§l[安全模式] §f已在 ({x}, {y}, {z}) 放置{mode_name}命令方块\n§6§l注意: §f命令方块已设置为需要红石激活，请检查命令后手动激活"
                        result["security_mode"] = True
                        result["need_manual_activation"] = True
                        
                        if not original_need_redstone:
                            result["message"] += "\n§7(原请求为保持激活状态，已被安全系统修改为需要红石激活)"
                    
                    return result
            
            # 完全权限玩家或系统调用，正常执行
            return self.command_block_tool.place_command_block(
                x=x, y=y, z=z,
                command=command,
                mode=mode,
                facing=facing,
                need_redstone=need_redstone,
                tick_delay=tick_delay,
                conditional=conditional,
                name=name,
                should_track_output=True,
                execute_on_first_tick=True,
                in_dim=in_dim
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"放置命令方块异常: {str(e)}"
            }

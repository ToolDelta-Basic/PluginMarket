from typing import List, Dict, Any

def get_all_tool_schemas() -> List[Dict[str, Any]]:
    """Get all tool schema definitions for AI model"""
    return [
        {
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "执行Minecraft命令",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的Minecraft命令（不需要前缀/）"
                        }
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "teleport_player",
                "description": "传送玩家到指定坐标",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {"type": "string", "description": "玩家名称"},
                        "x": {"type": "number", "description": "X坐标"},
                        "y": {"type": "number", "description": "Y坐标"},
                        "z": {"type": "number", "description": "Z坐标"}
                    },
                    "required": ["player_name", "x", "y", "z"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "give_item",
                "description": "给予玩家物品",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {"type": "string", "description": "玩家名称"},
                        "item_id": {"type": "string", "description": "物品ID，如minecraft:diamond"},
                        "amount": {"type": "integer", "description": "物品数量", "default": 1}
                    },
                    "required": ["player_name", "item_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_player_info",
                "description": "获取玩家详细信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {"type": "string", "description": "玩家名称"}
                    },
                    "required": ["player_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_online_players",
                "description": "获取当前在线玩家列表",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_player_position",
                "description": "获取玩家当前位置坐标",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {"type": "string", "description": "玩家名称"}
                    },
                    "required": ["player_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_player_inventory",
                "description": "获取玩家背包物品列表，包括物品ID、数量、槽位等信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {"type": "string", "description": "玩家名称"}
                    },
                    "required": ["player_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_player_tags",
                "description": "获取玩家的所有标签(tag)列表。标签是用于标记玩家的自定义文本，返回玩家当前拥有的所有标签。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {"type": "string", "description": "玩家名称"}
                    },
                    "required": ["player_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_player_score",
                "description": "获取玩家在指定计分板上的分数",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {"type": "string", "description": "玩家名称"},
                        "objective": {"type": "string", "description": "计分板名称"}
                    },
                    "required": ["player_name", "objective"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "set_block",
                "description": "在指定坐标设置方块",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "X坐标"},
                        "y": {"type": "integer", "description": "Y坐标"},
                        "z": {"type": "integer", "description": "Z坐标"},
                        "block_id": {"type": "string", "description": "方块ID，如minecraft:stone"}
                    },
                    "required": ["x", "y", "z", "block_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "fill_blocks",
                "description": "填充方块区域",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x1": {"type": "integer", "description": "起始X坐标"},
                        "y1": {"type": "integer", "description": "起始Y坐标"},
                        "z1": {"type": "integer", "description": "起始Z坐标"},
                        "x2": {"type": "integer", "description": "结束X坐标"},
                        "y2": {"type": "integer", "description": "结束Y坐标"},
                        "z2": {"type": "integer", "description": "结束Z坐标"},
                        "block_id": {"type": "string", "description": "方块ID"}
                    },
                    "required": ["x1", "y1", "z1", "x2", "y2", "z2", "block_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_message",
                "description": "向指定玩家发送消息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {"type": "string", "description": "玩家名称"},
                        "message": {"type": "string", "description": "消息内容"}
                    },
                    "required": ["player_name", "message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "broadcast_message",
                "description": "向所有玩家广播消息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "消息内容"}
                    },
                    "required": ["message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_game_rule",
                "description": "查询游戏规则",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rule_name": {"type": "string", "description": "规则名称"}
                    },
                    "required": ["rule_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "place_command_block",
                "description": "在指定坐标放置命令方块并配置命令。命令方块可以自动执行Minecraft命令。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "X坐标"},
                        "y": {"type": "integer", "description": "Y坐标"},
                        "z": {"type": "integer", "description": "Z坐标"},
                        "command": {"type": "string", "description": "命令方块中要执行的命令（不需要前缀/）"},
                        "mode": {
                            "type": "integer",
                            "description": "命令方块模式：0=脉冲（需要激活一次执行一次），1=循环（持续执行），2=连锁（前一个命令方块执行后触发）",
                            "enum": [0, 1, 2],
                            "default": 0
                        },
                        "facing": {
                            "type": "integer",
                            "description": "命令方块朝向：0=下，1=上，2=北，3=南，4=西，5=东",
                            "enum": [0, 1, 2, 3, 4, 5],
                            "default": 0
                        },
                        "need_redstone": {
                            "type": "boolean",
                            "description": "是否需要红石信号激活（true=需要红石，false=保持激活）",
                            "default": False
                        },
                        "tick_delay": {
                            "type": "integer",
                            "description": "执行延迟（游戏刻，20刻=1秒）",
                            "default": 0
                        },
                        "conditional": {
                            "type": "boolean",
                            "description": "是否为条件模式（仅当前一个命令方块成功执行时才执行）",
                            "default": False
                        },
                        "name": {
                            "type": "string",
                            "description": "命令方块的名称（可选）",
                            "default": ""
                        },
                        "in_dim": {
                            "type": "string",
                            "description": "放置的维度",
                            "enum": ["overworld", "nether", "the_end"],
                            "default": "overworld"
                        }
                    },
                    "required": ["x", "y", "z", "command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_chatbar_menu_triggers",
                "description": "获取聊天栏菜单中注册的所有触发词列表，包括触发词名称、功能说明、参数提示等信息。可以用来查看服务器中有哪些可用的菜单命令。",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "interact_with_menu",
                "description": "交互式菜单工具 - 支持会话管理，AI可以在同一个菜单会话中连续输入多次。工作流程：1. action='start'开始新会话并获取菜单；2. 读取返回的menu_options；3. 提供user_input继续交互；4. 重复步骤2-3直到完成；5. action='end'结束会话（可选）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {
                            "type": "string",
                            "description": "玩家名称"
                        },
                        "trigger_word": {
                            "type": "string",
                            "description": "要触发的触发词（从get_chatbar_menu_triggers获取）"
                        },
                        "user_input": {
                            "type": "string",
                            "description": "AI提供的输入（如选项编号'1'、'2'，或其他参数）。首次调用时不提供，后续调用时提供。",
                            "default": None
                        },
                        "action": {
                            "type": "string",
                            "enum": ["start", "continue", "end"],
                            "description": "操作类型：'start'=开始新会话，'continue'=继续当前会话（默认），'end'=结束会话",
                            "default": "continue"
                        }
                    },
                    "required": ["player_name", "trigger_word"]
                }
            }
        }
    ]

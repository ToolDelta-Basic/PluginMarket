import json
import time
from typing import TYPE_CHECKING, Optional, Dict, Any
import requests
from tooldelta import Player, fmts, utils
from .utils import Utils
from .mctools import MinecraftAITool
from .permission import PermissionLevel
if TYPE_CHECKING:
    from . import MCAgent


class AIAgent:
    """AI Agent for handling chat requests and tool calling with Minecraft integration.
    
    This class manages conversations, API requests, and tool execution for AI-powered
    Minecraft assistance.
    """
    API_PROVIDERS = {
        "deepseek": {
            "base_url": "https://api.deepseek.com",
            "chat_endpoint": "/v1/chat/completions",
            "format": "openai"
        },
        "siliconflow": {
            "base_url": "https://api.siliconflow.cn",
            "chat_endpoint": "/v1/chat/completions",
            "format": "openai"
        }
    }

    def __init__(self, plugin: "MCAgent"):
        self.plugin = plugin
        self.conversations = {}
        self.active_requests = set()
        self.cancel_requests = set()  # 存储需要取消的请求
        self.mc_tools = MinecraftAITool(plugin)

    def get_api_config(self, provider: str = "deepseek") -> Dict[str, str]:
        """Get API configuration for specified provider"""
        provider = provider.lower()
        if provider not in self.API_PROVIDERS:
            fmts.print_wrn(f"未知的API提供商: {provider}，使用默认的deepseek")
            provider = "deepseek"
        return self.API_PROVIDERS[provider]

    @staticmethod
    def extract_content_from_response(
        response_data: Dict[str, Any]
    ) -> Optional[str]:
        """Extract content from API response"""
        try:
            if (
                isinstance(response_data, dict)
                and "choices" in response_data
                and len(response_data["choices"]) > 0
                and "message" in response_data["choices"][0]
                and "content" in response_data["choices"][0]["message"]
            ):
                return response_data["choices"][0]["message"]["content"]
            return None
        except (TypeError, KeyError, IndexError) as e:
            fmts.print_err(f"从API响应中提取内容时出错: {e}")
            return None

    def extract_content_from_siliconflow_response(
        self, response_data: Dict[str, Any]
    ) -> Optional[str]:
        """Extract content from SiliconFlow API response"""
        try:
            if isinstance(response_data, dict) and "content" in response_data:
                content = response_data["content"]
                if isinstance(content, list) and len(content) > 0:
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            return block.get("text")
                elif isinstance(content, str):
                    return content

            return self.extract_content_from_response(response_data)
        except (TypeError, KeyError, IndexError) as e:
            fmts.print_err(f"从硅基流动API响应中提取内容时出错: {e}")
            return None

    @staticmethod
    def calculate_cost(
        total_tokens: int, cost_per_million: float = 8.0
    ) -> float:
        """Calculate API usage cost based on token count"""
        return (total_tokens / 1_000_000) * cost_per_million

    def load_conversation_history(
        self, player_name: str, conversation_type: str = "default"
    ) -> list:
        """Load conversation history from disk"""
        file_path = Utils.make_data_file(
            self.plugin, f"agent_conversations_{conversation_type}.json"
        )
        history_data = Utils.disk_read(file_path)

        if player_name in history_data:
            return history_data[player_name]
        return []

    @staticmethod
    def clean_orphaned_tool_messages(messages: list) -> list:
        """Clean orphaned tool messages that don't have corresponding tool_calls"""
        cleaned_messages = []

        for msg in messages:
            # 如果是tool消息，检查前面是否有对应的assistant tool_calls
            if msg.get("role") == "tool":
                tool_call_id = msg.get("tool_call_id")
                has_valid_tool_call = False

                # 向前查找最近的assistant消息
                for j in range(len(cleaned_messages) - 1, -1, -1):
                    if cleaned_messages[j].get("role") == "assistant":
                        # 检查是否有匹配的tool_call
                        for tc in cleaned_messages[j].get("tool_calls", []):
                            if tc.get("id") == tool_call_id:
                                has_valid_tool_call = True
                                break
                        break

                # 只保留有效的tool消息
                if has_valid_tool_call:
                    cleaned_messages.append(msg)
                # else: skip orphaned tool messages
            else:
                cleaned_messages.append(msg)

        return cleaned_messages

    def save_conversation_history(
        self,
        player_name: str,
        messages: list,
        conversation_type: str = "default",
        max_history_length: int = 15
    ) -> None:
        """Save conversation history to disk"""
        cleaned_messages = self.clean_orphaned_tool_messages(messages)
        limited_messages = self._limit_conversation_history(
            cleaned_messages, max_history_length, player_name
        )

        file_path = Utils.make_data_file(
            self.plugin, f"agent_conversations_{conversation_type}.json"
        )
        history_data = Utils.disk_read(file_path)
        history_data[player_name] = limited_messages
        Utils.disk_write(file_path, history_data)

    @staticmethod
    def _limit_conversation_history(
        messages: list,
        max_history_length: int,
        player_name: str = "未知玩家"
    ) -> list:
        """Limit conversation history to specified length"""
        if not messages:
            return messages

        system_msg = (
            messages[0] if messages and messages[0].get("role") == "system"
            else None
        )
        non_system_messages = messages[1:] if system_msg else messages

        user_message_count = sum(
            1 for msg in non_system_messages if msg.get("role") == "user"
        )

        if user_message_count <= max_history_length:
            return messages

        users_to_remove = user_message_count - max_history_length
        user_count = 0
        cutoff_index = 0

        for i, msg in enumerate(non_system_messages):
            if msg.get("role") == "user":
                user_count += 1
                if user_count > users_to_remove:
                    cutoff_index = i
                    break

        recent_messages = non_system_messages[cutoff_index:]

        if system_msg:
            limited_messages = [system_msg] + recent_messages
        else:
            limited_messages = recent_messages

        return limited_messages

    @staticmethod
    def get_conversation_key(
        player_name: str, conversation_type: str = "default"
    ) -> str:
        """Generate conversation key for player"""
        return f"{player_name}_{conversation_type}"

    def send_request(
        self,
        player_name: str,
        message: str,
        system_prompt: str,
        api_key: str,
        model: str = "deepseek-chat",
        max_history_length: int = 15,
        stream: bool = False,
        conversation_type: str = "default",
        api_provider: str = "deepseek"
    ) -> Any:
        """
        Send request to AI API
        
        Args:
            player_name (str): 玩家名称
            message (str): 用户消息
            system_prompt (str): 系统提示词
            api_key (str): API密钥
            model (str): 模型名称
            max_history_length (int): 最大历史记录长度
            stream (bool): 是否使用流式输出
            conversation_type (str): 对话类型
            api_provider (str): API提供商 (deepseek/siliconflow)
            
        Returns:
            dict/requests.Response/str: API响应结果或错误信息
        """
        if not api_key:
            return "错误：未提供 API 密钥"
        
        # 获取API配置
        api_config = self.get_api_config(api_provider)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # 获取或初始化对话历史
        conversation_key = self.get_conversation_key(player_name, conversation_type)
        if conversation_key not in self.conversations:
            # 尝试从文件加载
            self.conversations[conversation_key] = self.load_conversation_history(player_name, conversation_type)
        
        messages = self.conversations[conversation_key]
        
        # 确保系统提示词在第一条
        if not messages or messages[0]["role"] != "system":
            messages.insert(0, {
                "role": "system",
                "content": system_prompt
            })
        
        # 添加用户消息
        messages.append({
            "role": "user",
            "content": f"{player_name}: {message}"
        })
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        try:
            url = f"{api_config['base_url']}{api_config['chat_endpoint']}"
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                stream=stream
            )
            
            if response.status_code != 200:
                return f"请求失败，状态码：{response.status_code}，响应内容：{response.text}"
            
            # 如果是流式输出，直接返回响应对象
            if stream:
                return response
            
            # 非流式输出，解析响应
            result = response.json()
            assistant_response = self.extract_content_from_response(result)
            
            if assistant_response is None:
                return "错误：无法从API响应中提取内容"
            
            # 添加AI回复到对话历史
            messages.append({
                "role": "assistant",
                "content": assistant_response
            })
            
            # 限制对话历史轮数
            # 计算对话轮数：每个user消息算一轮
            system_msg = messages[0] if messages and messages[0]["role"] == "system" else None
            non_system_messages = messages[1:] if system_msg else messages
            
            # 统计user消息数量（轮数）
            user_message_count = sum(1 for msg in non_system_messages if msg.get("role") == "user")
            
            # 如果超过max_history_length轮，保留最近的轮次
            if user_message_count > max_history_length:
                # 找到第(max_history_length+1)轮的user消息位置
                user_count = 0
                cutoff_index = len(non_system_messages)
                
                for i in range(len(non_system_messages) - 1, -1, -1):
                    if non_system_messages[i].get("role") == "user":
                        user_count += 1
                        if user_count > max_history_length:
                            cutoff_index = i + 1
                            break
                
                # 截取最近的消息
                recent_messages = non_system_messages[cutoff_index:]
                
                # 重新组装消息列表（保留系统提示词）
                if system_msg:
                    messages = [system_msg] + recent_messages
                else:
                    messages = recent_messages
                
                self.conversations[conversation_key] = messages
            
            # 保存对话历史到文件
            self.save_conversation_history(player_name, messages, conversation_type, max_history_length)
            
            return result
            
        except requests.exceptions.RequestException as e:
            return f"网络请求异常：{str(e)}"
        except UnicodeError as e:
            return f"编码异常：{str(e)}"
        except Exception as e:
            return f"未知错误：{str(e)}"
    
    def handle_stream_response(
        self,
        player: Player,
        response: requests.Response,
        player_name: str,
        conversation_type: str = "default",
        display_interval: int = 100,
        max_history_length: int = 15
    ) -> str:
        """
        Handle streaming response from AI API
        
        Args:
            player (Player): 玩家对象
            response (requests.Response): 流式响应对象
            player_name (str): 玩家名称
            conversation_type (str): 对话类型
            display_interval (int): 显示更新间隔（毫秒）
            max_history_length (int): 最大历史长度
            
        Returns:
            str: 完整的响应内容
        """
        full_response = ""
        last_update_time = time.time()
        
        try:
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data = decoded_line[6:]  # 移除 "data: " 前缀
                        
                        if data == "[DONE]":
                            break
                        
                        try:
                            chunk_data = json.loads(data)
                            if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                delta = chunk_data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                
                                if content:
                                    full_response += content
                                    
                                    # 控制更新频率
                                    current_time = time.time()
                                    if (current_time - last_update_time) * 1000 >= display_interval:
                                        # 使用ActionBar显示流式输出
                                        player.setActionbar(f"§a<AI Agent>: §f{full_response}")
                                        last_update_time = current_time
                        except json.JSONDecodeError:
                            pass
            
            # 最后一次更新
            if full_response:
                player.setActionbar(f"§a<AI Agent>: §f{full_response}")
            
            # 保存完整响应到对话历史
            conversation_key = self.get_conversation_key(player_name, conversation_type)
            if conversation_key in self.conversations:
                messages = self.conversations[conversation_key]
                messages.append({
                    "role": "assistant",
                    "content": full_response
                })
                self.save_conversation_history(player_name, messages, conversation_type, max_history_length)
            
            return full_response
            
        except Exception as e:
            fmts.print_err(f"流式传输过程中发生错误: {str(e)}")
            return full_response
    
    def clear_conversation_history(self, player_name: str, conversation_type: str = "default") -> bool:
        """Clear conversation history for player"""
        try:
            conversation_key = self.get_conversation_key(player_name, conversation_type)
            
            if conversation_key in self.conversations:
                del self.conversations[conversation_key]
            
            file_path = Utils.make_data_file(self.plugin, f"agent_conversations_{conversation_type}.json")
            history_data = Utils.disk_read(file_path)
            
            if player_name in history_data:
                del history_data[player_name]
                Utils.disk_write(file_path, history_data)
            
            return True
        except Exception as e:
            fmts.print_err(f"清除对话历史时出错: {str(e)}")
            return False
    
    def get_conversation_history(self, player_name: str, conversation_type: str = "default") -> list:
        """Get conversation history for player"""
        conversation_key = self.get_conversation_key(player_name, conversation_type)
        
        if conversation_key in self.conversations:
            return self.conversations[conversation_key]
        
        return self.load_conversation_history(player_name, conversation_type)
    
    @utils.thread_func("AI_Agent_Chat")
    def chat(
        self,
        player: Player,
        message: str,
        system_prompt: str = "你是一个友好的AI助手",
        api_key: str = "",
        model: str = "deepseek-chat",
        max_history_length: int = 15,
        stream: bool = False,
        conversation_type: str = "default",
        api_provider: str = "deepseek"
    ) -> bool:
        """
        Handle player chat request (thread-safe)
        
        Args:
            player (Player): 玩家对象
            message (str): 用户消息
            system_prompt (str): 系统提示词
            api_key (str): API密钥
            model (str): 模型名称
            max_history_length (int): 最大历史记录长度
            stream (bool): 是否使用流式输出
            conversation_type (str): 对话类型
            api_provider (str): API提供商 (deepseek/siliconflow)
            
        Returns:
            bool: 执行结果
        """
        ui = self.plugin.ui_texts['基础对话']
        
        if not message:
            player.show(ui['输入为空'])
            return False
        
        player.show(ui['处理中框'])
        player.show(ui['处理中标题'])
        player.show(ui['处理中框底'])
        player.show(f"§f{message}")
        
        # 发送请求
        result = self.send_request(
            player.name,
            message,
            system_prompt,
            api_key,
            model,
            max_history_length,
            stream,
            conversation_type,
            api_provider
        )
        
        # 处理响应
        if isinstance(result, str):
            # 错误消息
            player.show(ui['错误框'])
            player.show(ui['错误标题'])
            player.show(ui['错误框底'])
            player.show(f"§c{result}")
            return False
        elif isinstance(result, requests.Response):
            # 流式响应
            full_response = self.handle_stream_response(player, result, player.name, conversation_type, 100, max_history_length)
            player.show(ui['响应框'])
            player.show(ui['响应标题'])
            player.show(ui['响应框底'])
            player.show(f"§f{full_response}")
            fmts.print_inf(f"Player {player.name} request: {message}, response: {full_response}")
            return True
        elif isinstance(result, dict):
            # 非流式响应
            content = self.extract_content_from_response(result)
            
            if content is None:
                player.show(ui['提取内容失败'])
                return False
            
            # 显示回复和token消耗
            player.show(ui['响应框'])
            player.show(ui['响应标题'])
            player.show(ui['响应框底'])
            player.show(f"§f{content}")
            
            if 'usage' in result and 'total_tokens' in result['usage']:
                total_tokens = result['usage']['total_tokens']
                cost = self.calculate_cost(total_tokens)
                player.show(ui['统计分隔线'])
                player.show(ui['统计信息'].format(tokens=total_tokens, cost=f"{cost:.6f}"))
                player.show(ui['统计分隔线'])
                fmts.print_inf(f"Player {player.name} request: {message}, response: {content}, tokens: {total_tokens}")
            else:
                fmts.print_inf(f"Player {player.name} request: {message}, response: {content}")
            
            return True
        else:
            player.show(ui['响应格式无效'])
            return False

    
    def cancel_request(self, player_name: str) -> bool:
        """
        Cancel player's AI request
        
        Args:
            player_name (str): 玩家名称
            
        Returns:
            bool: 是否成功标记为取消
        """
        if player_name in self.active_requests:
            self.cancel_requests.add(player_name)
            return True
        return False
    
    def send_request_with_tools(
        self,
        player: Player,
        message: str,
        system_prompt: str,
        api_key: str,
        model: str = "deepseek-chat",
        max_history_length: int = 15,
        conversation_type: str = "default",
        max_tool_calls: int = 10,
        api_provider: str = "deepseek",
        timeout: int = 90
    ) -> Dict[str, Any]:
        """
        Send request with tool calling support to AI API
        
        Args:
            player (Player): 玩家对象
            message (str): 用户消息
            system_prompt (str): 系统提示词
            api_key (str): API密钥
            model (str): 模型名称
            max_history_length (int): 最大历史记录长度
            conversation_type (str): 对话类型
            max_tool_calls (int): 最大工具调用次数
            api_provider (str): API提供商 (deepseek/siliconflow)
            timeout (int): API请求超时时间（秒）
            
        Returns:
            Dict[str, Any]: 包含响应和执行信息的字典
        """
        if not api_key:
            return {"success": False, "error": "错误：未提供 API 密钥"}
        
        # 检查是否被取消
        if player.name in self.cancel_requests:
            self.cancel_requests.remove(player.name)
            return {"success": False, "error": "请求已被用户取消", "cancelled": True}
        
        # 获取API配置
        api_config = self.get_api_config(api_provider)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # 获取或初始化对话历史
        conversation_key = self.get_conversation_key(player.name, conversation_type)
        if conversation_key not in self.conversations:
            self.conversations[conversation_key] = self.load_conversation_history(player.name, conversation_type)
        
        messages = self.conversations[conversation_key]
        
        # 确保系统提示词在第一条
        if not messages or messages[0]["role"] != "system":
            messages.insert(0, {
                "role": "system",
                "content": system_prompt
            })
        
        # 添加用户消息
        messages.append({
            "role": "user",
            "content": f"{player.name}: {message}"
        })
        
        # 获取工具定义（根据玩家权限过滤）
        tools = self.mc_tools.get_tools_schema(player)
        
        tool_call_count = 0
        total_tokens = 0
        tool_execution_logs = []
        
        try:
            # 循环处理工具调用
            while tool_call_count < max_tool_calls:
                # 检查是否被取消
                if player.name in self.cancel_requests:
                    self.cancel_requests.remove(player.name)
                    return {
                        "success": False,
                        "error": "请求已被用户取消",
                        "cancelled": True,
                        "total_tokens": total_tokens,
                        "tool_calls_count": tool_call_count,
                        "tool_execution_logs": tool_execution_logs
                    }
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto"
                }
                
                ui = self.plugin.ui_texts['AI助手']
                player.show(ui['思考中'].format(current=tool_call_count + 1, max=max_tool_calls))
                player.show("§7§o提示: 输入 §e取消 §7可以中止AI处理")
                
                url = f"{api_config['base_url']}{api_config['chat_endpoint']}"
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout  # 使用配置的超时时间
                )
                
                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"请求失败，状态码：{response.status_code}，响应内容：{response.text}"
                    }
                
                result = response.json()
                
                # 累计token消耗
                if 'usage' in result and 'total_tokens' in result['usage']:
                    total_tokens += result['usage']['total_tokens']
                
                # 获取AI响应
                if 'choices' not in result or len(result['choices']) == 0:
                    return {"success": False, "error": "API响应格式错误"}
                
                choice = result['choices'][0]
                assistant_message = choice['message']
                
                # 添加助手消息到历史
                messages.append(assistant_message)
                
                # 检查是否有工具调用
                if assistant_message.get('tool_calls'):
                    tool_call_count += 1
                    
                    # 处理每个工具调用
                    for tool_call in assistant_message['tool_calls']:
                        tool_name = tool_call['function']['name']
                        tool_args = json.loads(tool_call['function']['arguments'])
                        tool_id = tool_call['id']
                        
                        # 检查玩家权限等级
                        player_permission = self.plugin.permission_manager.get_player_permission_level(player)
                        is_full_permission = (player_permission == PermissionLevel.FULL)
                        
                        # 记录工具调用 - 使用配置的UI文本
                        log_msg = ui['工具调用框顶'].format(count=tool_call_count)
                        player.show(log_msg)
                        tool_execution_logs.append(log_msg)
                        
                        tool_info = ui['工具名称'].format(tool=tool_name)
                        player.show(tool_info)
                        tool_execution_logs.append(tool_info)
                        
                        # 显示参数信息（仅完全权限用户）
                        args_info = ui['工具参数'].format(args=json.dumps(tool_args, ensure_ascii=False))
                        if is_full_permission:
                            player.show(args_info)
                        tool_execution_logs.append(args_info)
                        
                        # 执行工具
                        tool_result = self.mc_tools.execute_tool(tool_name, tool_args, player)
                        
                        # 显示结果信息
                        if tool_result.get('success'):
                            result_msg = ui['工具结果成功'].format(message=tool_result.get('message', 'Success'))
                        else:
                            result_msg = ui['工具结果失败'].format(error=tool_result.get('error', 'Unknown error'))
                        
                        player.show(result_msg)
                        tool_execution_logs.append(result_msg)
                        
                        footer = ui['工具调用框底']
                        player.show(footer)
                        tool_execution_logs.append(footer)
                        
                        # 添加工具结果到消息历史
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": json.dumps(tool_result, ensure_ascii=False)
                        })
                    
                    # 继续循环，让AI处理工具结果
                    continue
                
                # 没有工具调用，获取最终回复
                final_content = assistant_message.get('content', '')
                
                if not final_content:
                    return {"success": False, "error": "AI未返回有效内容"}
                
                # 检测并处理格式化指令
                formatted_content = self._process_format_instruction(final_content, player)
                
                # 限制对话历史（使用max_history_length参数）
                # 直接使用_limit_conversation_history方法来统一处理
                messages = self._limit_conversation_history(messages, max_history_length, player.name)
                self.conversations[conversation_key] = messages
                
                # 保存对话历史
                self.save_conversation_history(player.name, messages, conversation_type, max_history_length)
                
                return {
                    "success": True,
                    "content": formatted_content,  # 返回处理后的内容
                    "total_tokens": total_tokens,
                    "tool_calls_count": tool_call_count,
                    "tool_execution_logs": tool_execution_logs
                }
            
            # 达到最大调用次数
            return {
                "success": False,
                "error": f"已达到最大工具调用次数限制 ({max_tool_calls})",
                "total_tokens": total_tokens,
                "tool_calls_count": tool_call_count,
                "tool_execution_logs": tool_execution_logs
            }
            
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"网络请求异常：{str(e)}"}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON解析错误：{str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"未知错误：{str(e)}"}
    
    def _process_format_instruction(self, content: str, player: Player) -> str:
        """AI now directly uses Minecraft color codes, no additional processing needed.
        
        Args:
            content: The content string from AI
            player: The player object (unused but kept for interface compatibility)
            
        Returns:
            The unmodified content string
        """
        return content
    
    @utils.thread_func("AI_Agent_Chat_With_Tools")
    def chat_with_tools(
        self,
        player: Player,
        message: str,
        system_prompt: str = """你是Minecraft基岩版AI助手，帮助玩家执行游戏操作。

【核心规则】
1. 操作玩家前必须先调用get_online_players获取在线列表
2. 支持模糊匹配玩家名（中英文、大小写不敏感）
3. 找不到玩家时列出在线玩家供选择

【ID格式】
- 物品/方块：minecraft:item_name 或 item_name
- 坐标：x y z（如：100 64 200）

【回复格式】
使用Minecraft颜色代码直接格式化文本：
- §a = 绿色（成功）
- §c = 红色（错误）
- §6 = 金色（警告）
- §b = 蓝色（信息）
- §e = 黄色（高亮）
- §f = 白色（普通）

示例：
- 传送成功：§a✓ §f已将玩家§e Steve §f传送到§b (100, 64, 200)
- 给予物品：§a✓ §f已给予§e Steve §f物品§b minecraft:diamond ×10
- 查询背包：§e Steve §f的背包：§b 钻石×10 铁锭×64 §f等共15种物品

保持简洁""",
        api_key: str = "",
        model: str = "deepseek-chat",
        max_history_length: int = 15,
        conversation_type: str = "default",
        max_tool_calls: int = 10,
        api_provider: str = "deepseek"
    ) -> bool:
        """
        Handle player chat request with tool calling support (thread-safe)
        
        Args:
            player (Player): 玩家对象
            message (str): 用户消息
            system_prompt (str): 系统提示词
            api_key (str): API密钥
            model (str): 模型名称
            max_history_length (int): 最大历史记录长度
            conversation_type (str): 对话类型
            max_tool_calls (int): 最大工具调用次数
            api_provider (str): API提供商 (deepseek/siliconflow)
            
        Returns:
            bool: 执行结果
        """
        ui = self.plugin.ui_texts['AI助手']
        
        if not message:
            player.show(ui['输入为空'])
            return False
        
        # 检查是否有正在进行的请求
        if player.name in self.active_requests:
            player.show("§c╔═══════════════════════╗")
            player.show("§c║ §4§l请求被拒绝 §c║")
            player.show("§c╚═══════════════════════╝")
            player.show("§c您有一个AI请求正在处理中")
            player.show("§7请等待当前请求完成后再试")
            return False
        
        # 添加请求锁定
        self.active_requests.add(player.name)
        
        try:
            player.show(ui['处理中框'])
            player.show(ui['处理中标题'])
            player.show(ui['处理中框底'])
            player.show(f"§f{message}")
            player.show(ui['分隔线'])
            player.show(ui['工具说明'])
            player.show(ui['分隔线'])
            
            # 发送请求
            result = self.send_request_with_tools(
                player,
                message,
                system_prompt,
                api_key,
                model,
                max_history_length,
                conversation_type,
                max_tool_calls,
                api_provider,
                self.plugin.agent_config.get('API请求超时秒数', 90)  # 从配置读取超时时间
            )
            
            # 处理响应 并检查取消
            if not result.get('success'):
                if result.get('cancelled'):
                    player.show("§6╔═══════════════════════╗")
                    player.show("§6║ §e§l操作已取消 §6║")
                    player.show("§6╚═══════════════════════╝")
                    player.show("§e✓ AI请求已成功取消")
                    return False
                
                player.show(ui['错误框'])
                player.show(ui['错误标题'])
                player.show(ui['错误框底'])
                player.show(f"§c{result.get('error', 'Unknown error')}")
                
                return False
            
            content = result.get('content', '')
            
            if content:
                player.show(ui['响应框'])
                player.show(ui['响应标题'])
                player.show(ui['响应框底'])
                player.show(content)
            
            total_tokens = result.get('total_tokens', 0)
            tool_calls_count = result.get('tool_calls_count', 0)
            cost = self.calculate_cost(total_tokens)
            
            player.show("")
            player.show(ui['统计标题'])
            player.show(ui['工具调用次数'].format(count=tool_calls_count))
            player.show(ui['Token使用'].format(tokens=total_tokens))
            player.show(ui['费用'].format(cost=f"{cost:.6f}"))
            
            fmts.print_inf(
                f"玩家 {player.name} 请求: {message}, "
                f"工具调用: {tool_calls_count}次, "
                f"Token: {total_tokens}, "
                f"回复: {content}"
            )
            
            return True
        
        finally:
            # 无论成功还是失败，都要释放请求锁定
            if player.name in self.active_requests:
                self.active_requests.remove(player.name)

import requests
import random
from tooldelta import Player, fmts, utils

class DeepSeek:
    def __init__(self, plugin):
        self.plugin = plugin
        self.conversations_O = {}
        self.conversations = {}
        self.packet_count = 0
        
    def calculate_output_cost(self, total_output_tokens):
        cost_per_million = 8  # 计算价格 这里需要根据对应不同模型实际token价格进行修改
        return (total_output_tokens / 1_000_000) * cost_per_million

    def format_text_with_newlines(self, text: str, chars_per_line: int) -> str:
        if not text:
            return text
            
        # 每chars_per_line个字符添加一个换行符
        formatted_text = ""
        for i in range(0, len(text), chars_per_line):
            if i > 0:
                formatted_text += "\n"
            formatted_text += text[i:i + chars_per_line]
            
        return formatted_text
    
    
    @utils.thread_func("RandomRemark")
    def RandomRemark(self, packet: dict):
        # 过滤选择玩家发送的信息
        if packet.get('TextType') != 1 or not packet.get('SourceName'):
            return
        self.packet_count += 1
        trigger_frequency = self.plugin.RandomRemark['检测频率']

        if self.packet_count >= trigger_frequency:
            self.packet_count = 0  # 重置计数器
            remark_probability = self.plugin.RandomRemark['插话概率']
            
            if random.random() < remark_probability:
                p = packet
                print(p['Message'])
                result = self.reDeepSeek( p['Message'], p['SourceName'])
                reply = result['choices'][0]['message']['content']
                command = '/tellraw @a {{"rawtext":[{{"text":"<§d小猫娘§f>:§e@{}§a {}"}}]}}'.format(p['SourceName'],reply)
                self.plugin.game_ctrl.sendwocmd(command)
    def reDeepOSeek(self, Message: str, playername: str):
        base_url = "https://api.deepseek.com"
        api_key = self.plugin.SetDeepOSeek['APIkey']
        if not api_key:
            return "错误：插件管理者未提供 DeepSeek API 密钥。"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        if playername not in self.conversations_O:
            self.conversations_O[playername] = []
        messages = self.conversations_O[playername]
       
        if not messages or messages[0]["role"] != "system":
            messages.insert(0, {
                "role": "system",
                "content": self.plugin.SetDeepOSeek['DeepSeek提示词']
            })
        messages.append({
            "role": "user",
            "content": f"{playername}: {Message}",
            "name": playername
        })
        payload = {
            "model": self.plugin.SetDeepOSeek['DeepSeekModel'],  
            "messages": messages,
            "stream": False
        }
        try:
            response = requests.post(
                f"{base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            )
            if response.status_code != 200:
                return f"请求失败，状态码：{response.status_code}，响应内容：{response.text}"
            result = response.json()
            assistant_response = result['choices'][0]['message']['content']
            messages.append({
                "role": "assistant",
                "content": assistant_response
            })
            if len(messages) > self.plugin.SetDeepOSeek['max_history_length'] * 2:
                self.conversations_O[playername] = messages[-self.plugin.SetDeepOSeek['max_history_length'] * 2:]
            return result
        except requests.exceptions.RequestException as e:
            return f"网络请求异常：{str(e)}"
        except UnicodeError as e:
            return f"编码异常：{str(e)}"
            
    def reDeepSeek(self, Message: str, playername: str):
        base_url = "https://api.deepseek.com"
        api_key = self.plugin.SetDeepSeek['APIkey']
        if not api_key:
            return "错误：插件管理者未提供 DeepSeek API 密钥。"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        if playername not in self.conversations:
            self.conversations[playername] = []
        messages = self.conversations[playername]
       
        if not messages or messages[0]["role"] != "system":
            messages.insert(0, {
                "role": "system",
                "content": self.plugin.SetDeepSeek['DeepSeek提示词']
            })
        messages.append({
            "role": "user",
            "content": f"{playername}: {Message}",
            "name": playername
        })
        payload = {
            "model": self.plugin.SetDeepSeek['DeepSeekModel'],  
            "messages": messages,
            "stream": self.plugin.SetDeepSeek.get('stream', False)
        }
        
        # 如果启用流式输出
        if self.plugin.SetDeepSeek.get('stream', False):
            try:
                response = requests.post(
                    f"{base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    stream=True
                )
                if response.status_code != 200:
                    return f"请求失败，状态码：{response.status_code}，响应内容：{response.text}"
                
                # 返回流式响应对象
                return response
            except requests.exceptions.RequestException as e:
                return f"网络请求异常：{str(e)}"
            except UnicodeError as e:
                return f"编码异常：{str(e)}"
        else:
            # 非流式输出
            try:
                response = requests.post(
                    f"{base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                if response.status_code != 200:
                    return f"请求失败，状态码：{response.status_code}，响应内容：{response.text}"
                result = response.json()
                assistant_response = result['choices'][0]['message']['content']
                messages.append({
                    "role": "assistant",
                    "content": assistant_response
                })
                if len(messages) > self.plugin.SetDeepSeek['max_history_length'] * 2:
                    self.conversations[playername] = messages[-self.plugin.SetDeepSeek['max_history_length'] * 2:]
                return result
            except requests.exceptions.RequestException as e:
                return f"网络请求异常：{str(e)}"
            except UnicodeError as e:
                return f"编码异常：{str(e)}"
                
    @utils.thread_func("DeepOSeek")
    def DeepOSeek(self, player: Player, args: tuple):
        playername = player.name
        if playername not in self.plugin.GMlist:
            player.show(self.plugin.Info['若不是协管'])
            return True
            
        # 获取用户输入内容
        if args:  
            try:
                param = ' '.join(args) if isinstance(args, (list, tuple)) else str(args)
            except ValueError:
                player.show("§c§l参数格式错误")
                return True
        else: 
            try:
                param = player.input("§a§l请输入要问的指令: ")
            except Exception as e:
                player.show(f"§c§l输入无效{str(e)}")
                return True
                
        player.show(f"§a§l内容: {param}，正在转发")
        DS_result = self.reDeepOSeek(param, player.name)
        for keyword in self.plugin.NO_CMDsend:
            if keyword in DS_result['choices'][0]['message']['content']:
                player.show(f"§c§l命令包含禁止关键词:§e§l {keyword}§c§l，无法执行。")
                return True
        player.show(f"§f§l原始指令内容为:§u{DS_result['choices'][0]['message']['content']} §f本次消耗Token: {DS_result['usage']['total_tokens']} §a共花费{self.calculate_output_cost(DS_result['usage']['total_tokens'])}元")
        self.plugin.game_ctrl.sendwocmd(f"/{DS_result['choices'][0]['message']['content']}")
        fmts.print(f"§f§l玩家:§e§l {player.name}§f§l 请求了§e§l {param}")
        fmts.print(f"§f§l实际执行结果为§e§l {DS_result['choices'][0]['message']['content']} §f本次消耗Token: {DS_result['usage']['total_tokens']} §a共花费{self.calculate_output_cost(DS_result['usage']['total_tokens'])}元")
        return True
        
    @utils.thread_func("DeepSeek")
    def DeepSeek(self, player: Player, args: tuple):
        # 获取用户输入内容
        if args:  
            try:
                param = ' '.join(args) if isinstance(args, (list, tuple)) else str(args)
            except ValueError:
                player.show("§c§l参数格式错误")
                return True
        else: 
            try:
                param = player.input("§a§l请输入内容: ")
            except Exception as e:
                player.show(f"§c§l输入无效: {str(e)}")
                return True
                
        player.show(f"§a§l内容: {param}，正在转发")
        DS_result = self.reDeepSeek(param, player.name)
        
        # 检查是否为错误消息
        if isinstance(DS_result, str):
            if DS_result.startswith("错误：") or "请求失败" in DS_result or "网络请求异常" in DS_result or "编码异常" in DS_result:
                player.show(f"§c§l{DS_result}")
                return True
        
        # 检查是否为流式响应对象
        if hasattr(DS_result, 'iter_lines'):
            full_response = ""
            player.show("§a§l正在流式接收响应...")
            
            # 处理流式响应
            try:
                for line in DS_result.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("data: "):
                            data = decoded_line[6:]  # 移除 "data: " 前缀
                            if data != "[DONE]":
                                try:
                                    import json
                                    chunk_data = json.loads(data)
                                    if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                        delta = chunk_data['choices'][0].get('delta', {})
                                        content = delta.get('content', '')
                                        if content:
                                            full_response += content 
                                            formatted_text = self.format_text_with_newlines(full_response, 20)
                                            command = '/titleraw @a[name="{}"] actionbar {{"rawtext":[{{"text":"<DeepSeek>:{}"}}]}}'.format(player.name, formatted_text)
                                            self.plugin.game_ctrl.sendwocmd(command)
                                except json.JSONDecodeError:
                                    pass
                            # 处理包含usage信息的最终数据块
                            elif data == "[DONE]":
                                command = '/titleraw @a[name="{}"] actionbar {{"rawtext":[{{"text":"<DeepSeek>:{}"}}]}}'.format(player.name, formatted_text)
                                self.plugin.game_ctrl.sendwocmd(command)
                
                # 显示完整响应
                player.show(f"§f§l原始内容为:§e{full_response}")
                fmts.print(f"§f§l玩家:§e§l {player.name}§f§l 请求了§e§l {param}")
                fmts.print(f"§f§l实际执行结果为§e§l {full_response}")
            except Exception as e:
                player.show(f"§c§l流式传输过程中发生错误: {str(e)}")
        else:
            # 非流式输出处理
            if isinstance(DS_result, dict) and 'choices' in DS_result:
                player.show(f"§f§l原始内容为:§e{DS_result['choices'][0]['message']['content']} §f本次消耗Token: {DS_result['usage']['total_tokens']} §a共花费{self.calculate_output_cost(DS_result['usage']['total_tokens'])}元")
                fmts.print(f"§f§l玩家:§e§l {player.name}§f§l 请求了§e§l {param}")
                fmts.print(f"§f§l实际执行结果为§e§l {DS_result['choices'][0]['message']['content']} §f本次消耗Token: {DS_result['usage']['total_tokens']} §a共花费{self.calculate_output_cost(DS_result['usage']['total_tokens'])}元")
            else:
                player.show(f"§c§l响应格式错误: {DS_result}")
        return True
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from tooldelta import Plugin, Player, cfg, utils, Chat, plugin_entry
import time
import threading
import re

try:
    from pypinyin import lazy_pinyin, Style
    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False


class PinyinConverter:
    """中文拼音转换器:使用pypinyin库"""
    
    @classmethod
    def to_pinyin(cls, text: str) -> str:
        """将中文转换为拼音"""
        if not text or not PYPINYIN_AVAILABLE:
            return text.lower()
            
        result = []
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 中文字符
                pinyin_list = lazy_pinyin(char, style=Style.NORMAL)
                if pinyin_list:
                    result.append(pinyin_list[0])
                else:
                    result.append(char)
            else:
                result.append(char.lower())
        
        return ''.join(result)
    
    @classmethod
    def get_pinyin_initials(cls, text: str) -> str:
        """获取拼音首字母"""
        if not text or not PYPINYIN_AVAILABLE:
            return ''.join(c for c in text.lower() if c.isalpha())
            
        result = []
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 中文字符
                pinyin_list = lazy_pinyin(char, style=Style.FIRST_LETTER)
                if pinyin_list:
                    result.append(pinyin_list[0])
                else:
                    result.append(char)
            elif char.isalpha():
                result.append(char.lower())
        
        return ''.join(result)


class TpaRequest:
    """传送请求类"""
    def __init__(self, sender: Player, target: str, request_type="to", timeout=60):
        self.sender = sender
        self.target = target
        self.request_type = request_type  # "to" 表示传送到目标，"here" 表示拉取目标到自己
        self.timestamp = time.time()
        self.timeout = timeout
        
    def is_expired(self):
        return time.time() - self.timestamp > self.timeout


class WuxiePlayerTeleport(Plugin):
    name = "无邪玩家互传"
    author = "无邪"
    version = (1, 0, 0)
    description = "功能完善的玩家互传系统，支持传送请求、权限管理和智能拼音搜索功能"

    def __init__(self, frame):
        super().__init__(frame)
        
        # 默认配置
        self.default_config = {
            "传送超时时间": 60,  # 秒
            "冷却时间": 5,  # 秒
            "最大传送距离": 0,  # 方块，0表示无限制
            "是否允许跨维度传送": False,
            "触发命令": ["tpa", "tp", "传送"],
            "权限设置": {
                "所有玩家都可使用": True,
                "OP专用功能": ["强制传送", "无冷却传送"]
            },
            "消息配置": {
                "菜单标题": "§7一一一一一§f传送菜单§7一一一一一",
                "传送成功": "§7 [§aTPA§7] §f传送成功",
                "传送失败": "§7 [§cTPA§7] §f传送失败",
                "请求已发送": "§7 [§6TPA§7] §f已向 §e{target}§f 发送传送请求",
                "请求被接受": "§7 [§aTPA§7] §f{sender} §7接受了你的传送请求",
                "请求被拒绝": "§7 [§cTPA§7] §f{sender} §7拒绝了你的传送请求",
                "请求超时": "§7 [§cTPA§7] §7传送请求已超时",
                "冷却中": "§7 [§cTPA§7] §7传送功能冷却中 , 请等待§f {time} §7秒",
                "无在线玩家": "§7 [§cTPA§7] §7当前没有其他在线玩家",
                "玩家不存在": "§7 [§cTPA§7] §7玩家§f {player} §7不在线",
                "距离过远": "§7 [§cTPA§7] §7传送距离过远 , 无法完成传送"
            }
        }
        
        # 加载配置
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, {}, self.default_config, self.version
        )
        
        # 存储传送请求和冷却信息
        self.tpa_requests: list[TpaRequest] = []
        self.player_cooldowns = {}  # 玩家冷却时间记录
        self.player_preferences = {}  # 玩家偏好设置
        
        # 注册事件监听器
        self.ListenActive(self.on_active)
        self.ListenPlayerLeave(self.on_player_leave)
        
        # 获取聊天栏菜单API
        self.chatbar_menu = None
        
    def on_active(self):
        """插件激活时的初始化"""
        # 检查并自动安装pypinyin库
        if not PYPINYIN_AVAILABLE:
            self.print("§e检测到pypinyin库未安装，正在尝试自动安装...")
            if self._auto_install_pypinyin():
                self.print("§a拼音搜索功能已启用")
            else:
                self.print("§c自动安装失败，拼音搜索功能将被禁用")
                self.print("§e手动安装命令: pip install pypinyin")
        else:
            self.print("§a拼音搜索功能已启用")
            
        try:
            self.chatbar_menu = self.GetPluginAPI("聊天栏菜单")
            if self.chatbar_menu:
                # 注册命令（支持多个别名但只显示一个菜单项）
                self.chatbar_menu.add_new_trigger(
                    self.config["触发命令"],
                    [("操作", str, "help")],
                    "玩家互传系统",
                    self.handle_tpa_command
                )
                self.print("§a成功注册聊天栏菜单命令")
            else:
                self.print("§c未找到聊天栏菜单插件，某些功能可能不可用")
        except Exception as e:
            self.print(f"§c无法获取聊天栏菜单API: {e}")
            self.print("§e插件将以兼容模式运行")
        
        # 启动后台清理线程
        utils.createThread(self.cleanup_expired_requests, (), "TPA请求清理")
    
    def _auto_install_pypinyin(self) -> bool:
        """自动安装pypinyin库"""
        try:
            pip_support = self.GetPluginAPI("pip")
            if pip_support is None:
                self.print("§c未找到pip模块支持插件，无法自动安装")
                return False
                
            self.print("§e正在安装pypinyin库...")
            # 使用require方法，这是推荐的方式
            pip_support.require("pypinyin")
            
            # 尝试重新导入
            global PYPINYIN_AVAILABLE, lazy_pinyin, Style
            try:
                from pypinyin import lazy_pinyin, Style
                PYPINYIN_AVAILABLE = True
                self.print("§a pypinyin库安装成功！")
                return True
            except ImportError:
                return False
                
        except Exception as e:
            self.print(f"§c自动安装过程中出现错误: {e}")
            return False
    
    def on_player_leave(self, player: Player):
        """玩家离开时清理相关请求"""
        player_name = player.name
        
        # 清理发送的请求
        for req in self.tpa_requests[:]:
            if req.sender.name == player_name:
                self.tpa_requests.remove(req)
                self.game_ctrl.say_to(req.target, f"§7 [§fTPA§7] §f{player_name} §7已下线 , 传送请求自动取消")
            elif req.target == player_name:
                self.tpa_requests.remove(req)
                req.sender.show(f"§7 [§fTPA§7] §f{player_name} §7已下线 , 传送请求自动取消")
        
        # 清理冷却记录
        if player_name in self.player_cooldowns:
            del self.player_cooldowns[player_name]
    
    @utils.thread_func("TPA命令处理")
    def handle_tpa_command(self, player: Player, args: tuple):
        """处理TPA命令"""
        if not args or len(args) == 0:
            self.show_help_menu(player)
            return
            
        action = args[0].lower()
        
        if action == "help" or action == "帮助":
            self.show_help_menu(player)
        elif action == "to" or action == "去":
            if len(args) > 1:
                self.handle_fuzzy_player_selection(player, args[1], "to")
            else:
                self.show_player_selection(player, "to")
        elif action == "here" or action == "来":
            if len(args) > 1:
                self.handle_fuzzy_player_selection(player, args[1], "here")
            else:
                self.show_player_selection(player, "here")
        elif action == "accept" or action == "同意" or action == "acc":
            self.accept_request(player)
        elif action == "deny" or action == "拒绝" or action == "dec":
            self.deny_request(player)
        elif action == "cancel" or action == "取消":
            self.cancel_request(player)
        elif action == "list" or action == "列表":
            self.list_requests(player)
        elif action == "toggle" or action == "设置":
            self.toggle_preference(player)
        elif action == "info" or action == "信息":
            self.show_plugin_info(player)
        else:
            # 直接指定玩家名，使用模糊搜索
            self.handle_fuzzy_player_selection(player, action, "to")
    
    def show_help_menu(self, player: Player):
        """显示帮助菜单"""
        player.show(self.config["消息配置"]["菜单标题"])
        player.show("§7 [§fTPA§7] §f可用命令:")
        player.show("§7   §a.tpa to <玩家名> §7- 请求传送到指定玩家")
        player.show("§7   §a.tpa here <玩家名> §7- 请求玩家传送到你这里")
        player.show("§7   §a.tpa accept §7- 接受传送请求")
        player.show("§7   §a.tpa deny §7- 拒绝传送请求")
        player.show("§7   §a.tpa cancel §7- 取消你发送的请求")
        player.show("§7   §a.tpa list §7- 查看待处理的请求")
        player.show("§7   §a.tpa toggle §7- 切换是否接受传送请求")
        player.show("§7   §a.tpa info §7- 查看插件信息")
        player.show("§7   §a.tpa <玩家名> §7- 快捷请求传送到玩家")
        player.show("§7   §aTips §7: §7输入 §fq §f可退出输入交互")
        player.show("§7 [§6TPA§7] §7支持模糊搜索玩家名:")
        player.show("§7   §e英文: §f.tpa ab §7→ §fAbc123")
        if PYPINYIN_AVAILABLE:
            player.show("§7   §e拼音: §f.tpa zhang §7-> §f张三")
            player.show("§7   §e首字母: §f.tpa zs §7-> §f张三")
        else:
            player.show("§7   §c拼音搜索需要安装pypinyin库")
    
    def show_player_selection(self, player: Player, mode: str):
        """显示玩家选择菜单"""
        online_players = self.get_online_players()
        if player.name in online_players:
            online_players.remove(player.name)
            
        if not online_players:
            player.show(self.config["消息配置"]["无在线玩家"])
            return
            
        player.show(self.config["消息配置"]["菜单标题"])
        if mode == "to":
            player.show("§7 [§fTPA§7] §f选择要传送到的玩家:")
        else:
            player.show("§7 [§fTPA§7] §f选择要拉取到你这里的玩家:")
            
        for i, target in enumerate(online_players, 1):
            player.show(f"§7   §a{i}. §f{target}")
        player.show("§7 [§fTPA§7] §7输入序号选择玩家 , 输入§f q §7退出")
        
        while True:
            response = player.input("请选择：", timeout=30)
            if response is None:
                player.show("§7 [§cTPA§7] §7选择超时")
                return
            if response.lower() == "q":
                player.show("§7 [§fTPA§7] §7已退出选择")
                return
                
            try:
                index = int(response) - 1
                if 0 <= index < len(online_players):
                    target = online_players[index]
                    if mode == "to":
                        self.request_teleport_to(player, target)
                    else:
                        self.request_teleport_here(player, target)
                    return
                else:
                    player.show("§7 [§cTPA§7] §7序号无效 , 请重新输入")
            except ValueError:
                player.show("§7 [§cTPA§7] §7请输入有效的序号")
    
    def fuzzy_search_player(self, query: str) -> list[str]:
        """模糊搜索玩家名（支持拼音）"""
        if not query:
            return []
            
        query = query.lower()
        online_players = self.get_online_players()
        
        # 调试信息
        self.print(f"§7[调试] 搜索词: {query}, 在线玩家: {online_players}")
        self.print(f"§7[调试] pypinyin可用: {PYPINYIN_AVAILABLE}")
        
        # 完全匹配 (最高优先级)
        exact_matches = [p for p in online_players if p.lower() == query]
        if exact_matches:
            return exact_matches
            
        # 开头匹配 (高优先级)
        start_matches = []
        # 包含匹配 (中优先级)
        contains_matches = []
        # 拼音匹配 (中优先级)
        pinyin_matches = []
        # 拼音首字母匹配 (中优先级)
        pinyin_initial_matches = []
        # 按字符相似度匹配 (低优先级)
        similar_matches = []
        
        for player in online_players:
            player_lower = player.lower()
            
            # 跳过完全匹配的玩家
            if player_lower == query:
                continue
                
            # 生成拼音相关信息
            player_pinyin = PinyinConverter.to_pinyin(player)
            player_initials = PinyinConverter.get_pinyin_initials(player)
            
            # 调试信息
            self.print(f"§7[调试] 玩家 {player}: 拼音={player_pinyin}, 首字母={player_initials}")
            
            # 开头匹配
            if (player_lower.startswith(query) or 
                player_pinyin.startswith(query) or 
                player_initials.startswith(query)):
                start_matches.append(player)
                continue
            
            # 包含匹配
            if (query in player_lower or 
                query in player_pinyin or 
                query in player_initials):
                # 拼音匹配优先级更高
                if query in player_pinyin or query in player_initials:
                    pinyin_matches.append(player)
                else:
                    contains_matches.append(player)
                continue
            
            # 拼音首字母匹配（模糊）
            if self._fuzzy_pinyin_match(query, player_pinyin, player_initials):
                pinyin_initial_matches.append(player)
                continue
                
            # 字符相似度匹配
            match_count = 0
            for char in query:
                if char in player_lower or char in player_pinyin:
                    match_count += 1
            if match_count >= len(query) // 2 and match_count > 1:
                similar_matches.append(player)
        
        # 按优先级返回结果
        all_matches = (start_matches + pinyin_matches + contains_matches + 
                      pinyin_initial_matches + similar_matches)
        return all_matches[:10]  # 最多返回10个结果
    
    def _fuzzy_pinyin_match(self, query: str, player_pinyin: str, player_initials: str) -> bool:
        """检查拼音模糊匹配"""
        # 检查是否为连续的拼音首字母
        if len(query) >= 2:
            # 检查连续首字母匹配
            for i in range(len(player_initials) - len(query) + 1):
                if player_initials[i:i+len(query)] == query:
                    return True
            
            # 检查非连续首字母匹配（至少匹配80%）
            matched = 0
            j = 0
            for char in query:
                while j < len(player_initials):
                    if player_initials[j] == char:
                        matched += 1
                        j += 1
                        break
                    j += 1
            if matched >= len(query) * 0.8:
                return True
        
        return False
    
    def handle_fuzzy_player_selection(self, player: Player, query: str, mode: str):
        """处理模糊搜索的玩家选择"""
        matches = self.fuzzy_search_player(query)
        
        # 排除自己
        if player.name in matches:
            matches.remove(player.name)
            
        if not matches:
            player.show(self.config["消息配置"]["玩家不存在"].format(player=query))
            return
            
        if len(matches) == 1:
            # 只有一个匹配结果，直接执行
            target = matches[0]
            if mode == "to":
                self.request_teleport_to(player, target)
            else:
                self.request_teleport_here(player, target)
            return
            
        # 多个匹配结果，让玩家选择
        player.show(self.config["消息配置"]["菜单标题"])
        player.show(f"§7 [§fTPA§7] §f找到多个匹配 §e{query}§f 的玩家:")
        
        for i, target in enumerate(matches, 1):
            player.show(f"§7   §a{i}. §f{target}")
        player.show("§7 [§fTPA§7] §7输入序号选择玩家 , 输入§f q §7退出")
        
        while True:
            response = player.input("请选择：", timeout=30)
            if response is None:
                player.show("§7 [§cTPA§7] §7选择超时")
                return
            if response.lower() == "q":
                player.show("§7 [§fTPA§7] §7已退出选择")
                return
                
            try:
                index = int(response) - 1
                if 0 <= index < len(matches):
                    target = matches[index]
                    if mode == "to":
                        self.request_teleport_to(player, target)
                    else:
                        self.request_teleport_here(player, target)
                    return
                else:
                    player.show("§7 [§cTPA§7] §7序号无效 , 请重新输入")
            except ValueError:
                player.show("§7 [§cTPA§7] §7请输入有效的序号")
    
    def request_teleport_to(self, player: Player, target_name: str):
        """请求传送到目标玩家"""
        if not self.check_cooldown(player):
            return
            
        if not self.is_player_online(target_name):
            player.show(self.config["消息配置"]["玩家不存在"].format(player=target_name))
            return
            
        if self.has_pending_request(player):
            player.show("§7 [§cTPA§7] §7你已有待处理的传送请求")
            return
            
        if not self.can_receive_requests(target_name):
            player.show(f"§7 [§cTPA§7] §f{target_name} §7已关闭传送请求接收")
            return
            
        # 创建请求
        request = TpaRequest(player, target_name, "to", self.config["传送超时时间"])
        self.tpa_requests.append(request)
        
        # 设置冷却
        self.set_cooldown(player)
        
        # 发送消息
        player.show(self.config["消息配置"]["请求已发送"].format(target=target_name))
        self.game_ctrl.say_to(
            target_name,
            f"§7 [§6TPA§7] §f{player.name} §7请求传送到你这里\n"
            f"§7 [§fTPA§7] §a.tpa accept §7同意 , §c.tpa deny §7拒绝"
        )
    
    def request_teleport_here(self, player: Player, target_name: str):
        """请求目标玩家传送到自己这里"""
        if not self.check_cooldown(player):
            return
            
        if not self.is_player_online(target_name):
            player.show(self.config["消息配置"]["玩家不存在"].format(player=target_name))
            return
            
        if self.has_pending_request(player):
            player.show("§7 [§cTPA§7] §7你已有待处理的传送请求")
            return
            
        if not self.can_receive_requests(target_name):
            player.show(f"§7 [§cTPA§7] §f{target_name} §7已关闭传送请求接收")
            return
            
        # 创建请求
        request = TpaRequest(player, target_name, "here", self.config["传送超时时间"])
        self.tpa_requests.append(request)
        
        # 设置冷却
        self.set_cooldown(player)
        
        # 发送消息
        player.show(self.config["消息配置"]["请求已发送"].format(target=target_name))
        self.game_ctrl.say_to(
            target_name,
            f"§7 [§6TPA§7] §f{player.name} §7请求你传送到他那里\n"
            f"§7 [§fTPA§7] §a.tpa accept §7同意 , §c.tpa deny §7拒绝"
        )
    
    def accept_request(self, player: Player):
        """接受传送请求"""
        request = self.get_request_for_target(player.name)
        if not request:
            player.show("§7 [§cTPA§7] §7你没有待处理的传送请求")
            return
            
        # 执行传送
        success = self.execute_teleport(request)
        if success:
            player.show(self.config["消息配置"]["传送成功"])
            request.sender.show(self.config["消息配置"]["请求被接受"].format(sender=player.name))
        else:
            player.show(self.config["消息配置"]["传送失败"])
            request.sender.show("§7 [§cTPA§7] §f传送失败")
            
        # 移除请求
        self.tpa_requests.remove(request)
    
    def deny_request(self, player: Player):
        """拒绝传送请求"""
        request = self.get_request_for_target(player.name)
        if not request:
            player.show("§7 [§cTPA§7] §7你没有待处理的传送请求")
            return
            
        player.show(f"§7 [§cTPA§7] §7已拒绝§f {request.sender.name} §7的传送请求")
        request.sender.show(self.config["消息配置"]["请求被拒绝"].format(sender=player.name))
        
        # 移除请求
        self.tpa_requests.remove(request)
    
    def cancel_request(self, player: Player):
        """取消自己发送的请求"""
        request = self.get_request_from_sender(player)
        if not request:
            player.show("§7 [§cTPA§7] §7你没有待处理的传送请求")
            return
            
        player.show(f"§7 [§fTPA§7] §7已取消向§f {request.target} §7发送的传送请求")
        self.game_ctrl.say_to(request.target, f"§7 [§fTPA§7] §f{player.name} §7取消了传送请求")
        
        # 移除请求
        self.tpa_requests.remove(request)
    
    def list_requests(self, player: Player):
        """列出待处理的请求"""
        player_name = player.name
        
        # 发送的请求
        sent_requests = [req for req in self.tpa_requests if req.sender.name == player_name]
        # 收到的请求
        received_requests = [req for req in self.tpa_requests if req.target == player_name]
        
        if not sent_requests and not received_requests:
            player.show("§7 [§fTPA§7] §7你没有待处理的传送请求")
            return
            
        player.show("§7一一一一一§f传送请求列表§7一一一一一")
        
        if sent_requests:
            player.show("§7 [§aTPA§7] §f发送的请求:")
            for req in sent_requests:
                remaining = req.timeout - (time.time() - req.timestamp)
                type_str = "传送到" if req.request_type == "to" else "拉取"
                player.show(f"§7   §f{type_str}§e {req.target} §7(剩余§f {int(remaining)} §7秒)")
                
        if received_requests:
            player.show("§7 [§6TPA§7] §f收到的请求:")
            for req in received_requests:
                remaining = req.timeout - (time.time() - req.timestamp)
                type_str = "传送到你这里" if req.request_type == "to" else "传送到他那里"
                player.show(f"§7   §e{req.sender.name} §f请求{type_str} §7(剩余§f {int(remaining)} §7秒)")
    
    def toggle_preference(self, player: Player):
        """切换传送请求接收设置"""
        player_name = player.name
        current = self.player_preferences.get(player_name, True)
        self.player_preferences[player_name] = not current
        
        if current:
            player.show("§7 [§cTPA§7] §7已关闭传送请求接收")
        else:
            player.show("§7 [§aTPA§7] §f已开启传送请求接收")
    
    def show_plugin_info(self, player: Player):
        """显示插件信息"""
        player.show("§7一一一一一§f插件信息§7一一一一一")
        player.show(f"§7 插件名: §f{self.name}")
        player.show(f"§7 版本: §f{'.'.join(map(str, self.version))}")
        player.show(f"§7 作者: §f{self.author}")
        player.show(f"§7 描述: §f{self.description}")
        
        # 功能状态
        player.show("§7 功能状态:")
        player.show(f"§7   聊天栏菜单: {'§a已连接' if self.chatbar_menu else '§c未连接'}")
        player.show(f"§7   拼音搜索: {'§a已启用' if PYPINYIN_AVAILABLE else '§c未启用'}")
        
        # 统计信息
        active_requests = len(self.tpa_requests)
        player.show(f"§7 当前活跃请求: §f{active_requests}")
        
        if player.is_op():
            cooldown_players = len(self.player_cooldowns)
            player.show(f"§7 冷却中玩家: §f{cooldown_players}")
            disabled_players = len([p for p, enabled in self.player_preferences.items() if not enabled])
            player.show(f"§7 关闭接收玩家: §f{disabled_players}")
    
    def execute_teleport(self, request: TpaRequest) -> bool:
        """执行传送"""
        try:
            if request.request_type == "to":
                # 传送发起者到目标
                result = self.game_ctrl.sendwscmd_with_resp(
                    f"tp {request.sender.name} {request.target}", 5
                )
            else:
                # 传送目标到发起者
                result = self.game_ctrl.sendwscmd_with_resp(
                    f"tp {request.target} {request.sender.name}", 5
                )
            return result.SuccessCount > 0
        except Exception as e:
            self.print(f"传送执行失败: {e}")
            return False
    
    def check_cooldown(self, player: Player) -> bool:
        """检查玩家冷却时间"""
        if player.is_op():
            return True  # OP无冷却
            
        player_name = player.name
        if player_name in self.player_cooldowns:
            remaining = self.player_cooldowns[player_name] - time.time()
            if remaining > 0:
                player.show(self.config["消息配置"]["冷却中"].format(time=int(remaining)))
                return False
        return True
    
    def set_cooldown(self, player: Player):
        """设置玩家冷却时间"""
        if not player.is_op():
            self.player_cooldowns[player.name] = time.time() + self.config["冷却时间"]
    
    def get_online_players(self) -> list[str]:
        """获取在线玩家列表"""
        try:
            return list(self.game_ctrl.allplayers)
        except:
            return []
    
    def is_player_online(self, player_name: str) -> bool:
        """检查玩家是否在线"""
        return player_name in self.get_online_players()
    
    def has_pending_request(self, player: Player) -> bool:
        """检查玩家是否有待处理的请求"""
        return any(req.sender.name == player.name for req in self.tpa_requests)
    
    def can_receive_requests(self, player_name: str) -> bool:
        """检查玩家是否接受传送请求"""
        return self.player_preferences.get(player_name, True)
    
    def get_request_for_target(self, target_name: str) -> TpaRequest | None:
        """获取目标玩家的传送请求"""
        for req in self.tpa_requests:
            if req.target == target_name:
                return req
        return None
    
    def get_request_from_sender(self, sender: Player) -> TpaRequest | None:
        """获取发送者的传送请求"""
        for req in self.tpa_requests:
            if req.sender.name == sender.name:
                return req
        return None
    
    def cleanup_expired_requests(self):
        """清理过期的传送请求"""
        while True:
            try:
                current_time = time.time()
                
                # 清理过期请求
                for request in self.tpa_requests[:]:
                    if request.is_expired():
                        request.sender.show(self.config["消息配置"]["请求超时"])
                        self.game_ctrl.say_to(request.target, f"§7 [§cTPA§7] §7来自§f {request.sender.name} §7的传送请求已超时")
                        self.tpa_requests.remove(request)
                
                # 清理过期冷却
                for player_name in list(self.player_cooldowns.keys()):
                    if self.player_cooldowns[player_name] <= current_time:
                        del self.player_cooldowns[player_name]
                        
                time.sleep(5)  # 每5秒检查一次
            except Exception as e:
                self.print(f"清理线程错误: {e}")
                time.sleep(10)


# 插件入口点
entry = plugin_entry(WuxiePlayerTeleport) 

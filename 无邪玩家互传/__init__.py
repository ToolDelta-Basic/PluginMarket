# pyright: reportMissingImports=false, reportMissingModuleSource=false
from tooldelta import Plugin, Player, cfg, utils, plugin_entry
import time
import threading




class PinyinConverter:
    """中文拼音转换器:使用pypinyin库"""
    
    def __init__(self, pypinyin_available=False, lazy_pinyin=None, style=None):
        self.pypinyin_available = pypinyin_available
        self.lazy_pinyin = lazy_pinyin
        self.style = style
    
    def to_pinyin(self, text: str) -> str:
        """将中文转换为拼音"""
        if not text or not self.pypinyin_available or self.lazy_pinyin is None:
            return text.lower()
            
        result = []
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 中文字符
                pinyin_list = self.lazy_pinyin(char, style=self.style.NORMAL)
                if pinyin_list:
                    result.append(pinyin_list[0])
                else:
                    result.append(char)
            else:
                result.append(char.lower())
        
        return ''.join(result)
    
    def get_pinyin_initials(self, text: str) -> str:
        """获取拼音首字母"""
        if not text or not self.pypinyin_available or self.lazy_pinyin is None:
            return ''.join(c for c in text.lower() if c.isalpha())
            
        result = []
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 中文字符
                pinyin_list = self.lazy_pinyin(char, style=self.style.FIRST_LETTER)
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
    
    # 类常量 - 消除魔法数字
    MAX_SEARCH_RESULTS = 10  # 模糊搜索最多返回结果数
    MIN_SIMILARITY_RATIO = 0.5  # 最小相似度比例
    PINYIN_MATCH_THRESHOLD = 0.8  # 拼音匹配阈值

    def __init__(self, frame):
        super().__init__(frame)
        
        # 初始化pypinyin相关变量
        self.pypinyin_available = False
        self.lazy_pinyin = None
        self.style = None
        self.pinyin_converter = None
        
        # 配置模板 - 符合官方规范
        config_template = {
            "传送超时时间": cfg.PInt,
            "冷却时间": cfg.PInt,
            "最大传送距离": cfg.NNInt,
            "是否允许跨维度传送": bool,
            "触发命令": cfg.JsonList(str),
            "权限设置": {
                "所有玩家都可使用": bool,
                "OP专用功能": cfg.JsonList(str)
            },
            "消息配置": cfg.AnyKeyValue(str)
        }
        
        default_config = {
            "传送超时时间": 60,
            "冷却时间": 5,
            "最大传送距离": 0,
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
        
        # 加载配置 - 使用类型检查
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, config_template, default_config, self.version
        )
        
        # 存储传送请求和冷却信息
        self.tpa_requests: list[TpaRequest] = []
        self.player_cooldowns = {}
        self.player_preferences = {}
        
        # 线程锁 - 防止竞态条件
        self._requests_lock = threading.Lock()
        self._cooldowns_lock = threading.Lock()
        self._preferences_lock = threading.Lock()
        
        # 注册生命周期钩子 - 符合官方规范
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_active)
        self.ListenPlayerLeave(self.on_player_leave)
        
        # API 引用
        self.chatbar_menu = None
        
    def on_def(self):
        """加载前置 API - 必须在 ListenPreload 中"""
        try:
            self.chatbar_menu = self.GetPluginAPI("聊天栏菜单")
        except Exception as e:
            self.game_ctrl.say_to("@a", f"§c无法获取聊天栏菜单API: {e}")
        
        # 在 ListenPreload 中安装 pypinyin
        self._install_pypinyin()
    
    def _install_pypinyin(self):
        """安装并导入pypinyin库 - 在 ListenPreload 中调用"""
        try:
            from pypinyin import lazy_pinyin, Style
            self.pypinyin_available = True
            self.lazy_pinyin = lazy_pinyin
            self.style = Style
        except ImportError:
            # 安装 pypinyin - 使用字典格式(官方推荐)
            try:
                pip_support = self.GetPluginAPI("pip")
                if pip_support:
                    pip_support.require({"pypinyin": "pypinyin"})
                    # 重新导入
                    from pypinyin import lazy_pinyin, Style
                    self.pypinyin_available = True
                    self.lazy_pinyin = lazy_pinyin
                    self.style = Style
            except Exception:
                self.pypinyin_available = False
                self.lazy_pinyin = None
                self.style = None

    def on_active(self):
        """插件激活时的初始化"""
        # 初始化拼音转换器
        self.pinyin_converter = PinyinConverter(
            self.pypinyin_available, 
            self.lazy_pinyin, 
            self.style
        )
        
        # 注册命令
        if self.chatbar_menu:
            self.chatbar_menu.add_new_trigger(
                self.config["触发命令"],
                [("操作", str, "help")],
                "玩家互传系统",
                self.handle_tpa_command
            )
        
        status = "§a拼音搜索已启用" if self.pypinyin_available else "§e拼音搜索未启用"
        self.game_ctrl.say_to("@a", f"§a无邪玩家互传系统已加载 {status}")
        
        # 启动后台清理线程
        utils.createThread(self.cleanup_expired_requests, usage="TPA请求清理")
    
    
    def on_player_leave(self, player: Player):
        """玩家离开时清理相关请求"""
        player_name = player.name
        
        # 使用锁保护 - 清理发送的请求
        with self._requests_lock:
            requests_to_remove = []
            for req in self.tpa_requests:
                if req.sender.name == player_name:
                    requests_to_remove.append(req)
                    self.game_ctrl.say_to(req.target, f"§7 [§fTPA§7] §f{player_name} §7已下线 , 传送请求自动取消")
                elif req.target == player_name:
                    requests_to_remove.append(req)
                    req.sender.show(f"§7 [§fTPA§7] §f{player_name} §7已下线 , 传送请求自动取消")
            
            # 移除找到的请求
            for req in requests_to_remove:
                if req in self.tpa_requests:
                    self.tpa_requests.remove(req)
        
        # 使用锁保护 - 清理冷却记录
        with self._cooldowns_lock:
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
        if self.pypinyin_available:
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
        
        # 完全匹配
        exact_matches = [p for p in online_players if p.lower() == query]
        if exact_matches:
            return exact_matches
        
        # 按优先级分类匹配
        matches = self._classify_player_matches(query, online_players)
        return self._merge_and_limit_matches(matches)
    
    def _classify_player_matches(self, query: str, players: list[str]) -> dict:
        """将玩家按匹配优先级分类"""
        matches = {
            "start": [],
            "pinyin": [],
            "contains": [],
            "pinyin_initial": [],
            "similar": []
        }
        
        for player in players:
            if player.lower() == query:
                continue
            
            match_type = self._get_player_match_type(query, player)
            if match_type:
                matches[match_type].append(player)
        
        return matches
    
    def _get_player_match_type(self, query: str, player: str) -> str | None:
        """获取玩家匹配类型"""
        player_lower = player.lower()
        player_pinyin = self.pinyin_converter.to_pinyin(player)
        player_initials = self.pinyin_converter.get_pinyin_initials(player)
        
        # 开头匹配
        if (player_lower.startswith(query) or 
            player_pinyin.startswith(query) or 
            player_initials.startswith(query)):
            return "start"
        
        # 包含匹配
        if query in player_lower or query in player_pinyin or query in player_initials:
            if query in player_pinyin or query in player_initials:
                return "pinyin"
            return "contains"
        
        # 拼音首字母模糊匹配
        if self._fuzzy_pinyin_match(query, player_pinyin, player_initials):
            return "pinyin_initial"
        
        # 字符相似度匹配
        if self._check_similarity(query, player_lower, player_pinyin):
            return "similar"
        
        return None
    
    def _check_similarity(self, query: str, player_lower: str, player_pinyin: str) -> bool:
        """检查字符相似度"""
        match_count = sum(1 for char in query if char in player_lower or char in player_pinyin)
        return match_count >= len(query) * self.MIN_SIMILARITY_RATIO and match_count > 1
    
    def _merge_and_limit_matches(self, matches: dict) -> list[str]:
        """合并并限制匹配结果"""
        all_matches = (
            matches["start"] + 
            matches["pinyin"] + 
            matches["contains"] + 
            matches["pinyin_initial"] + 
            matches["similar"]
        )
        return all_matches[:self.MAX_SEARCH_RESULTS]
    
    def _fuzzy_pinyin_match(self, query: str, player_pinyin: str, player_initials: str) -> bool:
        """检查拼音模糊匹配"""
        if len(query) < 2:
            return False
        
        # 检查连续首字母匹配
        for i in range(len(player_initials) - len(query) + 1):
            if player_initials[i:i+len(query)] == query:
                return True
        
        # 检查非连续首字母匹配
        matched = 0
        j = 0
        for char in query:
            while j < len(player_initials):
                if player_initials[j] == char:
                    matched += 1
                    j += 1
                    break
                j += 1
        
        return matched >= len(query) * self.PINYIN_MATCH_THRESHOLD
    
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
            
        # 创建请求 - 使用锁保护
        request = TpaRequest(player, target_name, "to", self.config["传送超时时间"])
        with self._requests_lock:
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
            
        # 创建请求 - 使用锁保护
        request = TpaRequest(player, target_name, "here", self.config["传送超时时间"])
        with self._requests_lock:
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
            
        # 移除请求 - 使用锁保护
        with self._requests_lock:
            if request in self.tpa_requests:
                self.tpa_requests.remove(request)
    
    def deny_request(self, player: Player):
        """拒绝传送请求"""
        request = self.get_request_for_target(player.name)
        if not request:
            player.show("§7 [§cTPA§7] §7你没有待处理的传送请求")
            return
            
        player.show(f"§7 [§cTPA§7] §7已拒绝§f {request.sender.name} §7的传送请求")
        request.sender.show(self.config["消息配置"]["请求被拒绝"].format(sender=player.name))
        
        # 移除请求 - 使用锁保护
        with self._requests_lock:
            if request in self.tpa_requests:
                self.tpa_requests.remove(request)
    
    def cancel_request(self, player: Player):
        """取消自己发送的请求"""
        request = self.get_request_from_sender(player)
        if not request:
            player.show("§7 [§cTPA§7] §7你没有待处理的传送请求")
            return
            
        player.show(f"§7 [§fTPA§7] §7已取消向§f {request.target} §7发送的传送请求")
        self.game_ctrl.say_to(request.target, f"§7 [§fTPA§7] §f{player.name} §7取消了传送请求")
        
        # 移除请求 - 使用锁保护
        with self._requests_lock:
            if request in self.tpa_requests:
                self.tpa_requests.remove(request)
    
    def list_requests(self, player: Player):
        """列出待处理的请求"""
        player_name = player.name
        
        # 使用锁保护 - 读取请求列表
        with self._requests_lock:
            sent_requests = [req for req in self.tpa_requests if req.sender.name == player_name]
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
        
        # 使用锁保护 - 修改偏好设置
        with self._preferences_lock:
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
        player.show(f"§7   拼音搜索: {'§a已启用' if self.pypinyin_available else '§c未启用'}")
        
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
        
        # 使用锁保护 - 读取冷却时间
        with self._cooldowns_lock:
            if player_name in self.player_cooldowns:
                remaining = self.player_cooldowns[player_name] - time.time()
                if remaining > 0:
                    player.show(self.config["消息配置"]["冷却中"].format(time=int(remaining)))
                    return False
        return True
    
    def set_cooldown(self, player: Player):
        """设置玩家冷却时间"""
        if not player.is_op():
            # 使用锁保护 - 设置冷却时间
            with self._cooldowns_lock:
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
        with self._requests_lock:
            return any(req.sender.name == player.name for req in self.tpa_requests)
    
    def can_receive_requests(self, player_name: str) -> bool:
        """检查玩家是否接受传送请求"""
        with self._preferences_lock:
            return self.player_preferences.get(player_name, True)
    
    def get_request_for_target(self, target_name: str) -> TpaRequest | None:
        """获取目标玩家的传送请求"""
        with self._requests_lock:
            for req in self.tpa_requests:
                if req.target == target_name:
                    return req
        return None
    
    def get_request_from_sender(self, sender: Player) -> TpaRequest | None:
        """获取发送者的传送请求"""
        with self._requests_lock:
            for req in self.tpa_requests:
                if req.sender.name == sender.name:
                    return req
        return None
    
    def cleanup_expired_requests(self):
        """清理过期的传送请求"""
        while True:
            try:
                current_time = time.time()
                
                # 使用锁保护 - 清理过期请求
                with self._requests_lock:
                    expired_requests = []
                    for request in self.tpa_requests:
                        if request.is_expired():
                            expired_requests.append(request)
                    
                    # 处理过期请求
                    for request in expired_requests:
                        if request in self.tpa_requests:
                            request.sender.show(self.config["消息配置"]["请求超时"])
                            self.game_ctrl.say_to(request.target, f"§7 [§cTPA§7] §7来自§f {request.sender.name} §7的传送请求已超时")
                            self.tpa_requests.remove(request)
                
                # 使用锁保护 - 清理过期冷却
                with self._cooldowns_lock:
                    expired_cooldowns = [name for name, expire_time in self.player_cooldowns.items() if expire_time <= current_time]
                    for player_name in expired_cooldowns:
                        del self.player_cooldowns[player_name]
                        
                time.sleep(5)  # 每5秒检查一次
            except Exception as e:
                self.game_ctrl.say_to("@a", f"§c清理线程错误: {e}")
                time.sleep(10)


# 插件入口点
entry = plugin_entry(WuxiePlayerTeleport)
import json
import os
import time
import re
from typing import Dict, Any, List, Set, Optional

from tooldelta import Plugin, plugin_entry, utils, fmts, cfg
from tooldelta.utils import mc_translator


class PlayerScoreRecorder(Plugin):
    """
    玩家计分板数值记录插件
    
    功能：
    - 通过配置文件自定义要记录的计分板项
    - 仅在玩家在线时更新该玩家的数据
    - 离线玩家保持最后一次在线时的数据
    - 每 60 秒更新一次在线玩家数据
    - 支持聊天栏菜单查询
    """

    author = "54875644"
    version = (0, 0, 2)  # 修改版本号
    name = "记录玩家积分版数值"

    def __init__(self, frame):
        super().__init__(frame)

        # 初始化配置
        self.config = None
        self.TARGET_OBJECTIVES: List[str] = []
        self.debug_mode = False
        
        # 保存文件路径
        try:
            self.save_path = self.format_data_path("player_scores.json")
        except Exception:
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
            os.makedirs(base, exist_ok=True)
            self.save_path = os.path.join(base, "player_scores.json")

        # 加载配置
        self._load_config()
        
        # 加载已有数据（历史玩家）
        self.player_scores: Dict[str, Any] = self._load_data()

        # 控制状态
        self._running = False
        self._thread = None
        self._last_update_time = 0

        # 注册生命周期回调
        self.ListenActive(self.on_active)
        self.ListenPreload(self.on_preload)
        self.ListenPlayerJoin(self.on_player_join)

        # 注册控制台查询命令
        self.frame.add_console_cmd_trigger(
            ["积分查询"], "[玩家名]", "查询玩家计分板数值", self._console_query
        )

    # ---------------- 配置文件管理 ----------------
    def _load_config(self):
        """加载插件配置文件"""
        try:
            # 定义配置结构
            config_schema = {
                "目标计分板": cfg.JsonList(str),
                "更新间隔": cfg.PInt,
                "启用调试模式": bool,
                "启用聊天栏菜单": bool,
                "自动保存间隔": cfg.PInt,
            }
            
            # 默认配置 - 修改为["1", "2", "3", "4"]
            default_config = {
                "目标计分板": ["1", "2", "3", "4"],
                "更新间隔": 60,
                "启用调试模式": False,
                "启用聊天栏菜单": True,
                "自动保存间隔": 300,
            }
            
            # 使用cfg模块加载配置
            self.config, config_version = cfg.get_plugin_config_and_version(
                self.name,
                config_schema,
                default_config,
                (1, 0, 0)
            )
            
            # 应用配置
            self.TARGET_OBJECTIVES = self.config["目标计分板"]
            self.debug_mode = self.config["启用调试模式"]
            
            # 输出配置信息
            fmts.print_suc(f"[{self.name}] 配置加载成功")
            fmts.print_inf(f"[{self.name}] 目标计分板: {', '.join(self.TARGET_OBJECTIVES)}")
            fmts.print_inf(f"[{self.name}] 更新间隔: {self.config['更新间隔']}秒")
            
            if len(self.TARGET_OBJECTIVES) == 0:
                fmts.print_err(f"[{self.name}] 警告: 目标计分板列表为空，插件可能无法正常工作")
                
        except Exception as e:
            fmts.print_err(f"[{self.name}] 加载配置失败: {e}")
            fmts.print_inf(f"[{self.name}] 使用默认配置")
            
            # 使用默认配置
            self.config = {
                "目标计分板": ["1", "2", "3", "4"],
                "更新间隔": 60,
                "启用调试模式": False,
                "启用聊天栏菜单": True,
                "自动保存间隔": 300,
            }
            self.TARGET_OBJECTIVES = self.config["目标计分板"]
            self.debug_mode = False

    def _debug_print(self, message: str):
        """调试输出，仅在调试模式启用时输出"""
        if self.debug_mode:
            fmts.print_inf(f"[{self.name}-DEBUG] {message}")

    # ---------------- 数据文件 I/O ----------------
    def _load_data(self) -> Dict[str, Any]:
        """加载玩家数据文件"""
        if not os.path.exists(self.save_path):
            parent = os.path.dirname(self.save_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            try:
                with open(self.save_path, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=4)
            except Exception as e:
                fmts.print_err(f"[{self.name}] 创建数据文件失败: {e}")
            return {}

        try:
            with open(self.save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    player_count = len(data)
                    fmts.print_inf(f"[{self.name}] 已加载 {player_count} 条历史记录")
                    self._debug_print(f"加载的数据文件路径: {self.save_path}")
                    return data
        except json.JSONDecodeError as e:
            fmts.print_err(f"[{self.name}] 数据文件格式错误: {e}")
            # 备份损坏的文件
            backup_path = f"{self.save_path}.backup.{int(time.time())}"
            try:
                import shutil
                shutil.copy2(self.save_path, backup_path)
                fmts.print_inf(f"[{self.name}] 已备份损坏的文件到: {backup_path}")
            except Exception:
                pass
        except Exception as e:
            fmts.print_err(f"[{self.name}] 读取数据文件失败: {e}")
            
        return {}

    def _save_data(self) -> None:
        """保存玩家数据到文件"""
        try:
            with open(self.save_path, "w", encoding="utf-8") as f:
                json.dump(self.player_scores, f, ensure_ascii=False, indent=4)
            self._debug_print(f"数据已保存，玩家数量: {len(self.player_scores)}")
        except Exception as e:
            fmts.print_err(f"[{self.name}] 保存数据失败: {e}")

    # ---------------- 聊天栏菜单集成 ----------------
    def on_preload(self):
        """预加载阶段：注册聊天栏菜单"""
        if not self.config.get("启用聊天栏菜单", True):
            fmts.print_inf(f"[{self.name}] 聊天栏菜单已禁用")
            return
            
        try:
            # 获取聊天栏菜单插件API
            chatbar = self.GetPluginAPI("聊天栏菜单")
            if chatbar:
                # 添加积分查询菜单项
                chatbar.add_new_trigger(
                    ["积分查询", "score"],
                    [("玩家名", str, "")],
                    "查询玩家计分板数值",
                    self._chatbar_query,
                    op_only=False
                )
                fmts.print_suc(f"[{self.name}] 聊天栏菜单注册成功")
            else:
                fmts.print_err(f"[{self.name}] 未找到聊天栏菜单插件API，聊天栏功能不可用")
        except Exception as e:
            fmts.print_err(f"[{self.name}] 聊天栏菜单注册失败: {e}")

    def _chatbar_query(self, player, args):
        """聊天栏菜单回调函数"""
        try:
            player_name = getattr(player, "name", str(player))
            
            # 解析参数
            if args and len(args) > 0 and args[0]:
                target_name = args[0]
            else:
                target_name = player_name
            
            # 查询数据
            if target_name not in self.player_scores:
                message = f"§c未找到玩家 {target_name} 的记录"
                self.game_ctrl.say_to(player_name, message)
                return True
            
            # 获取玩家数据
            pdata = self.player_scores[target_name]
            
            # 构建回复消息
            messages = [f"§e=== 玩家 {target_name} 的计分板 ==="]
            
            # 只显示配置中指定的计分板项
            for objective in self.TARGET_OBJECTIVES:
                if objective in pdata:
                    value = pdata[objective]
                    messages.append(f"§6{objective}: §f{value}")
            
            # 添加最后更新时间
            last_update = pdata.get('last_update', 0)
            if last_update > 0:
                time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_update))
                messages.append(f"§6最后更新: §f{time_str}")
            
            # 发送给玩家
            for msg in messages:
                self.game_ctrl.say_to(player_name, msg)
                
            self._debug_print(f"玩家 {player_name} 查询了 {target_name} 的计分板数据")
            return True
            
        except Exception as e:
            fmts.print_err(f"[{self.name}] 聊天栏查询出错: {e}")
            try:
                self.game_ctrl.say_to(player_name, "§c查询失败，请稍后再试")
            except Exception:
                pass
            return True

    # ---------------- 插件生命周期 ----------------
    def on_active(self):
        """插件激活"""
        fmts.print_suc(f"[{self.name}] 插件已激活")
        fmts.print_inf(f"[{self.name}] 监控的计分板: {', '.join(self.TARGET_OBJECTIVES)}")
        
        # 启动守护线程
        if not self._running:
            self._running = True
            self._thread = utils.createThread(self._loop, usage=f"{self.name}/更新线程")
            fmts.print_inf(f"[{self.name}] 更新线程已启动，间隔: {self.config['更新间隔']}秒")

    def on_disable(self):
        """插件停用"""
        self._running = False
        fmts.print_inf(f"[{self.name}] 停止中...")
        
        # 等待线程结束
        try:
            if self._thread and hasattr(self._thread, "is_alive") and self._thread.is_alive():
                self._thread.join(timeout=2)
        except Exception:
            pass
            
        # 保存数据
        try:
            self._save_data()
        except Exception:
            pass
            
        fmts.print_inf(f"[{self.name}] 已停止并保存数据")

    def on_player_join(self, player):
        """玩家加入事件"""
        try:
            name = getattr(player, "name", None) or str(player)
            
            # 确保玩家在数据中存在
            if name not in self.player_scores:
                # 创建新玩家记录
                entry = {
                    "player_name": name, 
                    "last_update": 0,
                    "last_seen": int(time.time())
                }
                
                # 为所有目标计分板项初始化
                for obj in self.TARGET_OBJECTIVES:
                    entry[obj] = 0
                    
                self.player_scores[name] = entry
                self._save_data()
                fmts.print_inf(f"[{self.name}] 新玩家加入并初始化记录: {name}")
            else:
                # 更新最后在线时间
                self.player_scores[name]["last_seen"] = int(time.time())
                
        except Exception as e:
            self._debug_print(f"on_player_join 异常: {e}")

    # ---------------- 主循环 ----------------
    def _loop(self):
        """后台循环：定期更新在线玩家的数据"""
        update_interval = self.config.get("更新间隔", 60)
        save_interval = self.config.get("自动保存间隔", 300)
        last_save_time = time.time()
        
        while self._running:
            try:
                current_time = time.time()
                
                # 检查是否到达更新间隔
                if current_time - self._last_update_time >= update_interval:
                    self._update_online_players_once()
                    self._last_update_time = current_time
                    
                    # 检查是否需要自动保存
                    if current_time - last_save_time >= save_interval:
                        self._save_data()
                        last_save_time = current_time
                        self._debug_print(f"自动保存完成，玩家数量: {len(self.player_scores)}")
                
            except Exception as e:
                fmts.print_err(f"[{self.name}] 主循环出错: {e}")

            # 分段等待以便更快停机
            for _ in range(10):
                if not self._running:
                    break
                time.sleep(1)

    # ---------------- 计分板数据获取 ----------------
    def _get_all_scores(self) -> Dict[str, Dict[str, int]]:
        """获取所有在线玩家的计分板数据"""
        all_scores = {}
        
        try:
            # 发送命令获取计分板数据
            result = self.game_ctrl.sendwscmd("/scoreboard players list @a", waitForResp=True, timeout=10)
            
            if result is None:
                self._debug_print("sendwscmd返回None，命令执行失败")
                return {}
            
            # 提取结果文本
            result_text = ""
            
            if hasattr(result, 'as_dict'):
                try:
                    result_dict = result.as_dict
                    if 'OutputMessages' in result_dict:
                        for msg in result_dict['OutputMessages']:
                            if 'Message' in msg:
                                translation_key = msg['Message']
                                parameters = msg.get('Parameters', [])
                                
                                # 使用 mc_translator 翻译
                                try:
                                    translated = mc_translator.translate(
                                        translation_key, 
                                        parameters, 
                                        translate_args=True
                                    )
                                    result_text += translated + "\n"
                                except Exception as e:
                                    self._debug_print(f"翻译失败: {e}")
                                    result_text += translation_key + "\n"
                except Exception as e:
                    self._debug_print(f"处理字典结果失败: {e}")
            
            # 如果获取到了文本，解析它
            if result_text:
                self._debug_print(f"获取到计分板数据，文本长度: {len(result_text)}")
                all_scores = self._parse_scoreboard_text(result_text)
            else:
                self._debug_print("无法获取命令返回的文本结果")
                
        except Exception as e:
            fmts.print_err(f"[{self.name}] 获取计分板数据失败: {e}")
        
        return all_scores

    def _parse_scoreboard_text(self, text: str) -> Dict[str, Dict[str, int]]:
        """解析计分板命令返回的文本"""
        scores = {}
        current_player = None
        
        # 分割行
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检查是否是玩家行
            if "正在为" in line and "显示" in line and "个追踪目标：" in line:
                # 提取玩家名
                match = re.search(r'正在为\s+([^\s]+)\s+显示\s+\d+\s+个追踪目标：', line)
                if match:
                    current_player = match.group(1)
                    scores[current_player] = {}
            
            # 检查是否是计分板项行
            elif current_player and line.startswith("- "):
                line = line[2:].strip()
                
                if ": " in line and " (" in line:
                    parts = line.split(": ", 1)
                    if len(parts) == 2:
                        objective = parts[0].strip()
                        score_part = parts[1]
                        
                        # 提取分数
                        score_match = re.search(r'^(\d+)\s+\(', score_part)
                        if score_match:
                            try:
                                score = int(score_match.group(1))
                                scores[current_player][objective] = score
                            except ValueError:
                                pass
        
        return scores

    # ---------------- 更新逻辑 ----------------
    def _update_online_players_once(self) -> None:
        """更新在线玩家的计分板数据"""
        try:
            # 获取所有玩家的计分板数据
            all_scores = self._get_all_scores()
            
            if not all_scores:
                self._debug_print("未获取到计分板数据，跳过本次更新")
                return
            
            # 获取在线玩家列表
            online_players = []
            try:
                online_players = self.game_ctrl.players.getAllPlayers() or []
            except Exception:
                try:
                    online_names = getattr(self.game_ctrl, "allplayers", []) or []
                    online_players = online_names
                except Exception:
                    online_players = []

            online_names = [getattr(p, "name", str(p)) for p in online_players]
            
            # 只记录在线玩家数量，不逐个打印
            self._debug_print(f"在线玩家: {len(online_names)}人")

            # 更新在线玩家的数据
            updated_count = 0
            updated_players = []
            
            for name in online_names:
                # 确保存在条目
                if name not in self.player_scores:
                    self.player_scores[name] = {"player_name": name, "last_update": 0}
                    for obj in self.TARGET_OBJECTIVES:
                        self.player_scores[name][obj] = 0

                # 检查是否有任何更新
                has_update = False
                updated_fields = []
                
                # 从获取的数据中提取该玩家的计分板数据
                player_scores = all_scores.get(name, {})
                
                # 更新我们关注的计分板项
                for obj in self.TARGET_OBJECTIVES:
                    # 处理计分板项名称映射
                    target_obj = obj
                    if obj == "在线时间":
                        # 尝试不同的名称
                        if "在线时间" in player_scores:
                            target_obj = "在线时间"
                        elif "游玩时长" in player_scores:
                            target_obj = "游玩时长"
                    
                    if target_obj in player_scores:
                        new_score = player_scores[target_obj]
                        old_score = self.player_scores[name].get(obj, 0)
                        
                        if new_score != old_score:
                            self.player_scores[name][obj] = new_score
                            has_update = True
                            updated_fields.append(obj)
                
                # 如果有更新，更新时间戳
                if has_update:
                    self.player_scores[name]["last_update"] = int(time.time())
                    updated_count += 1
                    updated_players.append((name, updated_fields))

            # 保存数据
            if updated_count > 0:
                self._save_data()
                # 只显示有更新的玩家数量，不显示详细信息
                fmts.print_inf(f"[{self.name}] 更新了 {updated_count} 个玩家的数据")
                
                # 只有在调试模式才显示详细信息
                if self.debug_mode and updated_players:
                    for player_name, fields in updated_players:
                        fmts.print_inf(f"  {player_name}: {', '.join(fields)}")
            else:
                self._debug_print("检查了所有在线玩家，数据无变化")
                
        except Exception as e:
            fmts.print_err(f"[{self.name}] 更新玩家数据失败: {e}")

    # ---------------- 控制台查询 ----------------
    def _console_query(self, args):
        """控制台查询命令"""
        try:
            if not args:
                fmts.print_inf("用法: 积分查询 <玩家名>")
                fmts.print_inf("可用计分板: " + ", ".join(self.TARGET_OBJECTIVES))
                return
                
            pname = args[0]
            if pname not in self.player_scores:
                fmts.print_inf(f"未找到玩家 {pname} 的记录")
                return
                
            pdata = self.player_scores[pname]
            fmts.print_inf(f"=== 玩家 {pname} 的计分板 ===")
            
            # 只显示配置中指定的计分板项
            for obj in self.TARGET_OBJECTIVES:
                if obj in pdata:
                    fmts.print_inf(f"  {obj}: {pdata[obj]}")
                    
            last_update = pdata.get('last_update', 0)
            if last_update > 0:
                time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_update))
                fmts.print_inf(f"  最后更新: {time_str}")
                
        except Exception as e:
            fmts.print_err(f"[{self.name}] 控制台查询出错: {e}")

    # ---------------- 插件卸载 ----------------
    def __del__(self):
        try:
            self._running = False
            if self._thread and hasattr(self._thread, "is_alive") and self._thread.is_alive():
                try:
                    self._thread.join(timeout=1)
                except Exception:
                    pass
            self._save_data()
        except Exception:
            pass


# 插件入口
entry = plugin_entry(PlayerScoreRecorder)
from tooldelta import Plugin, plugin_entry, Player, game_utils, utils, cfg
import json
import time
import os
from typing import Dict, Any, Optional


class SoulOutOfBody(Plugin):
    name = "灵魂出窍"
    author = "镜流"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        
        # 默认配置
        CONFIG_DEFAULT = {
            "灵魂出窍维持时间": 30,
            "冷却时间": 10,
            "提示信息": {
                "灵魂出窍成功": "§5⚡ §d灵魂出窍 §5⚡ §7| §e灵魂已脱离身体",
                "灵魂返回成功": "§a✨ §2灵魂返回 §a✨ §7| §e灵魂已回归身体",
                "已经在出窍状态": "§c你已经在灵魂出窍状态 §7| §e请先使用 §6灵魂返回",
                "未在出窍状态": "§c你不在灵魂出窍状态 §7| §e请先使用 §6灵魂出窍",
                "出窍时间结束": "§6⚠ §e灵魂强制返回 §6⚠ §7| §c超过维持时间",
                "冷却提示": "§c冷却中 §7| §e还需等待 §6{time}秒",
                "获取模式失败": "§c无法获取你的游戏模式",
                "获取位置失败": "§c获取位置信息失败",
                "切换模式失败": "§c切换旁观模式失败"
            }
        }
        
        # 配置模板
        CONFIG_STD = {
            "灵魂出窍维持时间": cfg.PInt,
            "冷却时间": cfg.PInt,
            "提示信息": cfg.AnyKeyValue(str)
        }
        
        # 读取配置
        config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        
        self.max_time = config["灵魂出窍维持时间"]
        self.cooldown_time = config["冷却时间"]
        self.messages = config["提示信息"]
        
        # 数据存储
        self.soul_data_file = os.path.join(self.data_path, "soul_data.json")
        self.cooldown_data_file = os.path.join(self.data_path, "cooldown_data.json")
        
        # 初始化数据
        self.soul_data = {}
        self.cooldown_data = {}
        self.load_data()
        
        # 监听事件
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenPlayerJoin(self.on_player_join)
        
        # 超时检测线程
        self.timeout_check_thread = None

    def on_preload(self):
        """预加载阶段，获取前置插件API"""
        try:
            self.chatbar = self.GetPluginAPI("聊天栏菜单")
            self.plugin_enabled = True
        except Exception:
            self.print_err("未找到前置插件-聊天栏菜单 插件已禁用")
            self.plugin_enabled = False
            raise

    def on_active(self):
        """激活阶段，注册聊天栏命令"""
        if not self.plugin_enabled:
            return
            
        # 注册灵魂出窍命令
        self.chatbar.add_new_trigger(
            ["灵魂出窍", "soulout", "so"],
            [],
            "§6灵魂出窍 §7- §e将灵魂脱离身体进入旁观模式",
            self.cmd_soul_out,
            False
        )
        
        # 注册灵魂返回命令
        self.chatbar.add_new_trigger(
            ["灵魂返回", "soulback", "sh"],
            [],
            "§6灵魂返回 §7- §e将灵魂返回身体",
            self.cmd_soul_return,
            False
        )
        
        # 启动超时检查线程
        self.start_timeout_check()

    def start_timeout_check(self):
        """启动超时检查线程"""
        @utils.thread_func("灵魂出窍超时检查")
        def check_timeouts():
            while True:
                time.sleep(1)
                self.check_soul_timeouts()
        
        check_timeouts()

    def load_data(self):
        """加载数据文件"""
        try:
            if os.path.exists(self.soul_data_file):
                with open(self.soul_data_file, 'r', encoding='utf-8') as f:
                    self.soul_data = json.load(f)
            else:
                self.soul_data = {}
        except Exception as e:
            self.print_err(f"加载灵魂数据失败 {e}")
            self.soul_data = {}
            
        try:
            if os.path.exists(self.cooldown_data_file):
                with open(self.cooldown_data_file, 'r', encoding='utf-8') as f:
                    self.cooldown_data = json.load(f)
            else:
                self.cooldown_data = {}
        except Exception as e:
            self.print_err(f"加载冷却数据失败 {e}")
            self.cooldown_data = {}

    def save_data(self):
        """保存数据到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.soul_data_file), exist_ok=True)
            
            # 保存灵魂数据
            with open(self.soul_data_file, 'w', encoding='utf-8') as f:
                json.dump(self.soul_data, f, ensure_ascii=False, indent=2)
            
            # 保存冷却数据
            with open(self.cooldown_data_file, 'w', encoding='utf-8') as f:
                json.dump(self.cooldown_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.print_err(f"保存数据失败 {e}")

    def get_player_gamemode(self, player_name: str) -> Optional[int]:
        """获取玩家游戏模式"""
        for mode in range(4):  # 0:生存 1:创造 2:冒险 3:旁观
            try:
                result = game_utils.getTarget(f'@a[name="{player_name}",m={mode}]', timeout=2)
                if player_name in result:
                    return mode
            except Exception:
                continue
        return None

    def get_player_info(self, player_name: str) -> Optional[Dict[str, Any]]:
        """获取玩家信息（坐标和维度）"""
        try:
            pos_info = game_utils.getPos(player_name)
            dimension = pos_info["dimension"]
            position = pos_info["position"]
            x, y, z = position["x"], position["y"], position["z"]
            
            return {
                "dimension": dimension,
                "x": x,
                "y": y,
                "z": z
            }
        except Exception as e:
            self.print_err(f"获取玩家 {player_name} 信息失败 {e}")
            return None

    def check_cooldown(self, player_name: str) -> bool:
        """检查冷却时间"""
        current_time = time.time()
        if player_name in self.cooldown_data:
            cooldown_end = self.cooldown_data[player_name]
            if current_time < cooldown_end:
                return False
        return True

    def cmd_soul_out(self, player: Player, _):
        """灵魂出窍命令"""
        player_name = player.name
        
        # 检查冷却
        if not self.check_cooldown(player_name):
            remaining = int(self.cooldown_data[player_name] - time.time())
            msg = self.messages["冷却提示"].format(time=remaining)
            player.show(msg)
            return
        
        # 检查是否已经在灵魂状态
        if player_name in self.soul_data:
            player.show(self.messages["已经在出窍状态"])
            return
        
        # 获取当前位置和游戏模式
        player_info = self.get_player_info(player_name)
        if not player_info:
            player.show(self.messages["获取位置失败"])
            return
        
        # 获取游戏模式
        gamemode = self.get_player_gamemode(player_name)
        if gamemode is None:
            player.show(self.messages["获取模式失败"])
            return
        
        # 保存灵魂数据
        self.soul_data[player_name] = {
            "gamemode": gamemode,
            "dimension": player_info["dimension"],
            "position": [player_info["x"], player_info["y"], player_info["z"]],
            "timestamp": time.time(),
            "xuid": player.xuid
        }
        
        # 切换到旁观模式
        try:
            self.game_ctrl.sendwocmd(f'/gamemode spectator "{player_name}"')
        except Exception:
            player.show(self.messages["切换模式失败"])
            return
        
        # 施加黑暗效果和播放音效
        try:
            self.game_ctrl.sendwocmd(f'/effect "{player_name}" darkness 5 255 true')
            self.game_ctrl.sendwocmd(f'/execute as "{player_name}" at @s run playsound mob.evocation_illager.prepare_summon @s ~ ~ ~ 10 0.9 10')
        except Exception:
            pass
        
        # 发送提示信息
        player.show(self.messages["灵魂出窍成功"])
        player.show(f"§7你将在 §6{self.max_time}秒 §7后自动返回 §7| §c超过时间灵魂会消散")
        
        self.save_data()

    def cmd_soul_return(self, player: Player, _):
        """灵魂返回命令"""
        player_name = player.name
        
        # 检查是否在灵魂状态
        if player_name not in self.soul_data:
            player.show(self.messages["未在出窍状态"])
            return
        
        # 执行灵魂返回
        self.perform_soul_back(player_name, is_auto=False)

    def perform_soul_back(self, player_name: str, is_auto: bool = False):
        """执行灵魂返回逻辑"""
        if player_name not in self.soul_data:
            return
        
        soul_info = self.soul_data[player_name]
        
        try:
            # 恢复游戏模式
            gamemode_map = {0: "survival", 1: "creative", 2: "adventure", 3: "spectator"}
            original_gamemode = soul_info["gamemode"]
            if original_gamemode in gamemode_map:
                self.game_ctrl.sendwocmd(f'/gamemode {gamemode_map[original_gamemode]} "{player_name}"')
            
            # 传送回原位置
            pos = soul_info["position"]
            dim = soul_info["dimension"]
            
            # 根据维度选择传送命令
            if dim == 0:  # 主世界
                self.game_ctrl.sendwocmd(f'/tp "{player_name}" {pos[0]} {pos[1]} {pos[2]}')
            elif dim == 1:  # 下界
                self.game_ctrl.sendwocmd(f'/execute in minecraft:the_nether run tp "{player_name}" {pos[0]} {pos[1]} {pos[2]}')
            elif dim == 2:  # 末地
                self.game_ctrl.sendwocmd(f'/execute in minecraft:the_end run tp "{player_name}" {pos[0]} {pos[1]} {pos[2]}')
            
            # 播放返回音效和粒子
            self.game_ctrl.sendwocmd(f'/execute as "{player_name}" at @s run playsound item.trident.riptide_3 @s ~ ~ ~ 999 1 999')
            self.game_ctrl.sendwocmd(f'/execute as "{player_name}" at @s run particle minecraft:egg_destroy_emitter ~ ~ ~')
            
            # 发送提示信息
            if not is_auto:
                player_obj = self.game_ctrl.players.getPlayerByName(player_name)
                if player_obj:
                    player_obj.show(self.messages["灵魂返回成功"])
            else:
                player_obj = self.game_ctrl.players.getPlayerByName(player_name)
                if player_obj:
                    player_obj.show(self.messages["出窍时间结束"])
            
            # 设置冷却时间
            self.cooldown_data[player_name] = time.time() + self.cooldown_time
            
            # 清理数据
            del self.soul_data[player_name]
            self.save_data()
            
            self.print_inf(f"玩家 {player_name} 灵魂返回")
            
        except Exception as e:
            self.print_err(f"灵魂返回失败 {player_name} {e}")
            # 清理数据即使失败
            if player_name in self.soul_data:
                del self.soul_data[player_name]
            self.save_data()

    def check_soul_timeouts(self):
        """检查超时的灵魂出窍状态"""
        current_time = time.time()
        players_to_return = []
        
        for player_name, soul_info in list(self.soul_data.items()):
            start_time = soul_info["timestamp"]
            
            # 检查是否超时
            if current_time - start_time > self.max_time:
                players_to_return.append(player_name)
        
        # 执行超时返回
        for player_name in players_to_return:
            self.perform_soul_back(player_name, is_auto=True)
        
        # 清理过期的冷却数据
        for player_name, cooldown_end in list(self.cooldown_data.items()):
            if current_time > cooldown_end:
                del self.cooldown_data[player_name]
        
        if players_to_return:
            self.save_data()

    def on_player_leave(self, player: Player):
        """玩家离开时触发"""
        player_name = player.name
        
        # 如果玩家在灵魂状态离开，记录其XUID
        if player_name in self.soul_data:
            self.soul_data[player_name]["xuid"] = player.xuid
            self.save_data()
            self.print_inf(f"玩家 {player_name} 在灵魂出窍状态下退出")

    def on_player_join(self, player: Player):
        """玩家加入时触发"""
        player_name = player.name
        
        # 检查是否有该玩家的灵魂出窍数据（按名称）
        if player_name in self.soul_data:
            # 延迟执行灵魂返回
            def delayed_return():
                time.sleep(1)
                self.perform_soul_back(player_name, is_auto=True)
                player_obj = self.game_ctrl.players.getPlayerByName(player_name)
                if player_obj:
                    player_obj.show("§6⚠ §e检测到异常退出 §6⚠ §7| §c灵魂已强制返回")
            
            utils.createThread(delayed_return, usage="延迟灵魂返回")
            self.print_inf(f"检测到玩家 {player_name} 上次在灵魂出窍状态退出 正在恢复")
            return
        
        # 按XUID查找（防止改名）
        xuid = player.xuid
        for stored_name, soul_info in list(self.soul_data.items()):
            if soul_info.get("xuid") == xuid:
                # 更新玩家名并恢复
                self.soul_data[player_name] = soul_info
                del self.soul_data[stored_name]
                
                # 延迟执行灵魂返回
                def delayed_return():
                    time.sleep(1)
                    self.perform_soul_back(player_name, is_auto=True)
                    player_obj = self.game_ctrl.players.getPlayerByName(player_name)
                    if player_obj:
                        player_obj.show("§6⚠ §e检测到改名玩家 §6⚠ §7| §c灵魂已强制返回")
                
                utils.createThread(delayed_return, usage="延迟灵魂返回(改名)")
                self.save_data()
                self.print_inf(f"检测到改名玩家 {player_name}(原 {stored_name}) 上次在灵魂出窍状态退出 正在恢复")
                break

    def on_frame_exit(self, evt):
        """框架退出时保存数据"""
        self.save_data()


# 插件入口
entry = plugin_entry(SoulOutOfBody)
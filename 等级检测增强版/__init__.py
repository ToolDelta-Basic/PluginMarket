import json
import time
from typing import Optional

from tooldelta import Plugin, plugin_entry, fmts, cfg, utils
from tooldelta.constants import PacketIDS

# 尝试导入websocket库
try:
    import websocket
except ImportError:
    try:
        # 尝试从本地websocket文件夹导入
        from .websocket import websocket_client as websocket
    except ImportError:
        fmts.print_err("未找到websocket库！")
        fmts.print_err("请运行: pip install websocket-client")
        fmts.print_err("或者从群服互通云链版插件复制websocket文件夹")
        websocket = None


class LevelCheckEnhanced(Plugin):
    """等级检测增强版插件 - 支持QQ群聊白名单绕过"""

    name = "等级检测增强版"
    author = "Q3CC"
    version = (1, 0, 1)
    description = "基于等级检测的增强版本，支持QQ群聊白名单绕过等级限制"

    def __init__(self, frame):
        super().__init__(frame)

        # 默认配置
        CONFIG_DEFAULT = {
            "配置版本": "1.0.1",
            "配置项": {
                "等级检测设置": {
                    "是否启用": True,
                    "最低限制等级": 6,
                    "踢出理由": "等级过低，无法加入服务器",
                    "延迟踢出时间": 3
                },
                "QQ白名单设置": {
                    "是否启用": True,
                    "云链地址": "ws://127.0.0.1:3001",
                    "校验码": None,
                    "链接的群聊": 832240220,
                    "管理员QQ": [114514]
                },
                "消息设置": {
                    "白名单绑定成功": "✅ 成功绑定玩家 [玩家名]，现在可以绕过等级限制进入服务器",
                    "白名单绕过提示": "玩家 [玩家名] (等级 [等级]) 通过QQ白名单进入服务器",
                    "等级不足提示": "玩家 [玩家名] 等级 [等级] 低于最低等级 [最低等级]，已踢出"
                }
            }
        }

        # 配置验证规则
        CONFIG_STD = {
            "配置版本": str,
            "配置项": {
                "等级检测设置": {
                    "是否启用": bool,
                    "最低限制等级": cfg.NNInt,
                    "踢出理由": str,
                    "延迟踢出时间": cfg.NNInt
                },
                "QQ白名单设置": {
                    "是否启用": bool,
                    "云链地址": str,
                    "校验码": (str, type(None)),
                    "链接的群聊": cfg.PInt,
                    "管理员QQ": cfg.JsonList(cfg.PInt)
                },
                "消息设置": {
                    "白名单绑定成功": str,
                    "白名单绕过提示": str,
                    "等级不足提示": str
                }
            }
        }

        # 加载配置
        self.config, config_version = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        
        # 配置版本升级处理
        self._handle_config_upgrade(config_version)

        # 提取配置项
        config_items = self.config["配置项"]
        level_cfg = config_items["等级检测设置"]
        qq_cfg = config_items["QQ白名单设置"]

        self.level_enabled = level_cfg["是否启用"]
        self.min_level = level_cfg["最低限制等级"]
        self.kick_reason = level_cfg["踢出理由"]
        self.kick_delay = level_cfg["延迟踢出时间"]

        self.qq_enabled = qq_cfg["是否启用"]
        self.ws_url = qq_cfg["云链地址"]
        self.auth_token = qq_cfg["校验码"]
        self.linked_group = qq_cfg["链接的群聊"]
        self.admin_qq_list = qq_cfg["管理员QQ"]

        # 运行时变量
        self.ws: Optional[websocket.WebSocketApp] = None
        self.whitelist_data = {}  # 格式: {player_name: qq_number}
        self.banned_qq_list = []  # 禁用QQ列表
        self.reloaded = False

        # 检查websocket库是否可用
        if websocket is None:
            fmts.print_err(f"[{self.name}] WebSocket库未安装，QQ白名单功能将被禁用")
            self.qq_enabled = False
            # 尝试使用pip模块自动安装
            self._try_auto_install_websocket()

        # 初始化白名单数据存储
        self.init_whitelist_storage()

        # 注册事件监听
        self.ListenPacket(PacketIDS.PlayerList, self.on_playerlist)

        # 如果启用QQ功能且websocket库可用，连接WebSocket
        if self.qq_enabled and websocket is not None:
            self.connect_websocket()

    def _handle_config_upgrade(self, current_version: tuple[int, int, int]):
        """处理配置文件版本升级"""
        config_changed = False
        
        # 检查是否是旧版本配置文件（无配置版本字段或版本过低）
        if "配置版本" not in self.config:
            # 这是最旧版本，直接转换为新格式
            fmts.print_inf(f"[{self.name}] 检测到旧版配置文件，正在升级...")
            self._upgrade_from_old_format()
            config_changed = True
        else:
            config_version = self.config["配置版本"]
            
            # 版本升级链
            if config_version == "1.0.0":
                fmts.print_inf(f"[{self.name}] 配置文件从v1.0.0升级到v1.0.1")
                self._upgrade_to_v1_0_1()
                config_changed = True
            # 可以在这里添加更多版本升级
            
        # 如果配置有变化，保存升级后的配置
        if config_changed:
            cfg.upgrade_plugin_config(
                self.name,
                self.config,
                self.version
            )
            fmts.print_suc(f"[{self.name}] 配置文件升级完成")
    
    def _upgrade_from_old_format(self):
        """从旧版本格式升级到新版本格式"""
        # 检查是否是平级结构的旧配置
        if "等级检测设置" in self.config:
            # 转换为新的嵌套结构
            old_config = dict(self.config)
            self.config = {
                "配置版本": "1.0.1",
                "配置项": old_config
            }
        else:
            # 如果是完全空的配置，使用默认值
            self.config = {
                "配置版本": "1.0.1",
                "配置项": {
                    "等级检测设置": {
                        "是否启用": True,
                        "最低限制等级": 6,
                        "踢出理由": "等级过低，无法加入服务器",
                        "延迟踢出时间": 3
                    },
                    "QQ白名单设置": {
                        "是否启用": True,
                        "云链地址": "ws://127.0.0.1:3001",
                        "校验码": None,
                        "链接的群聊": 832240220,
                        "管理员QQ": [114514]
                    },
                    "消息设置": {
                        "白名单绑定成功": "✅ 成功绑定玩家 [玩家名]，现在可以绕过等级限制进入服务器",
                        "白名单绕过提示": "玩家 [玩家名] (等级 [等级]) 通过QQ白名单进入服务器",
                        "等级不足提示": "玩家 [玩家名] 等级 [等级] 低于最低等级 [最低等级]，已踢出"
                    }
                }
            }
    
    def _upgrade_to_v1_0_1(self):
        """从v1.0.0升级到v1.0.1"""
        # 更新配置版本号
        self.config["配置版本"] = "1.0.1"
        
        # 可以在这里添加v1.0.1版本的特定升级逻辑
        # 例如：添加新的配置项、修改默认值等
        
        # 示例：确保消息设置存在所有必需的字段
        if "配置项" in self.config and "消息设置" in self.config["配置项"]:
            msg_settings = self.config["配置项"]["消息设置"]
            # 如果缺少某些消息模板，添加默认值
            if "白名单绑定成功" not in msg_settings:
                msg_settings["白名单绑定成功"] = "✅ 成功绑定玩家 [玩家名]，现在可以绕过等级限制进入服务器"
            if "白名单绕过提示" not in msg_settings:
                msg_settings["白名单绕过提示"] = "玩家 [玩家名] (等级 [等级]) 通过QQ白名单进入服务器"
            if "等级不足提示" not in msg_settings:
                msg_settings["等级不足提示"] = "玩家 [玩家名] 等级 [等级] 低于最低等级 [最低等级]，已踢出"

    def _try_auto_install_websocket(self):
        """尝试自动安装websocket库"""
        try:
            # 尝试获取pip模块支持插件
            pip_api = self.GetPluginAPI("pip", (0, 0, 1), False)
            if pip_api:
                fmts.print_inf(f"[{self.name}] 正在自动安装websocket-client库...")
                try:
                    pip_api.require({"websocket-client": "websocket"})
                    msg = (f"[{self.name}] websocket库安装成功，"
                          f"请重启ToolDelta以启用QQ功能")
                    fmts.print_suc(msg)
                except Exception as e:
                    fmts.print_err(f"[{self.name}] 自动安装websocket库失败: {e}")
            else:
                fmts.print_inf(f"[{self.name}] 未找到pip模块支持插件，跳过自动安装")
        except Exception as e:
            fmts.print_err(f"[{self.name}] 尝试自动安装websocket库时发生错误: {e}")

    def init_whitelist_storage(self):
        """初始化白名单数据存储"""
        # 确保数据文件夹存在
        self.make_data_path()

        # 白名单数据文件路径
        whitelist_file = self.format_data_path("whitelist.json")
        banned_qq_file = self.format_data_path("banned_qq.json")

        try:
            # 加载白名单数据
            self.whitelist_data = utils.tempjson.load_and_read(
                whitelist_file,
                need_file_exists=False,
                default={}
            )

            # 加载禁用QQ列表
            self.banned_qq_list = utils.tempjson.load_and_read(
                banned_qq_file,
                need_file_exists=False,
                default=[]
            )

            msg = (f"[{self.name}] 白名单数据加载完成: "
                  f"{len(self.whitelist_data)}个玩家, "
                  f"{len(self.banned_qq_list)}个禁用QQ")
            fmts.print_inf(msg)

        except Exception as e:
            fmts.print_err(f"加载白名单数据失败: {e}")
            self.whitelist_data = {}
            self.banned_qq_list = []

    def save_whitelist(self):
        """保存白名单数据"""
        try:
            # 分别保存白名单和禁用QQ列表到不同文件
            whitelist_file = self.format_data_path("whitelist.json")
            banned_qq_file = self.format_data_path("banned_qq.json")

            # 保存白名单数据
            utils.tempjson.load_and_write(whitelist_file, self.whitelist_data)

            # 保存禁用QQ列表
            utils.tempjson.load_and_write(banned_qq_file, self.banned_qq_list)

            fmts.print_suc(f"[{self.name}] 白名单数据已保存")
        except Exception as e:
            fmts.print_err(f"保存白名单数据失败: {e}")

    def is_in_whitelist(self, player_name: str) -> bool:
        """检查玩家是否在白名单中"""
        return player_name in self.whitelist_data

    def get_qq_bound_player(self, qq_number: int) -> Optional[str]:
        """获取QQ绑定的玩家名"""
        for player_name, bound_qq in self.whitelist_data.items():
            if bound_qq == qq_number:
                return player_name
        return None

    def is_qq_banned(self, qq_number: int) -> bool:
        """检查QQ是否被禁用"""
        return qq_number in self.banned_qq_list

    def bind_player_to_qq(self, player_name: str, 
                         qq_number: int) -> tuple[bool, str]:
        """绑定玩家到QQ号"""
        # 检查QQ是否被禁用
        if self.is_qq_banned(qq_number):
            return False, "❌ 您的QQ已被禁止绑定白名单"

        # 检查QQ是否已绑定其他账号
        bound_player = self.get_qq_bound_player(qq_number)
        if bound_player and bound_player != player_name:
            msg = (f"❌ 您的QQ已绑定玩家 {bound_player}，"
                  f"请使用 #白名单 解绑 后重新绑定")
            return False, msg

        # 检查玩家是否已被其他QQ绑定
        if (player_name in self.whitelist_data and 
            self.whitelist_data[player_name] != qq_number):
            return False, f"❌ 玩家 {player_name} 已被其他QQ绑定"

        # 执行绑定
        self.whitelist_data[player_name] = qq_number
        self.save_whitelist()
        return True, utils.simple_fmt(
            {"[玩家名]": player_name},
            self.config["配置项"]["消息设置"]["白名单绑定成功"]
        )

    def unbind_qq(self, qq_number: int) -> tuple[bool, str]:
        """解绑QQ的玩家"""
        bound_player = self.get_qq_bound_player(qq_number)
        if not bound_player:
            return False, "❌ 您没有绑定任何玩家"

        del self.whitelist_data[bound_player]
        self.save_whitelist()
        return True, f"✅ 已解绑玩家 {bound_player}"

    def admin_ban_qq(self, qq_number: int) -> tuple[bool, str]:
        """管理员禁用QQ"""
        if qq_number in self.banned_qq_list:
            return False, f"❌ QQ {qq_number} 已经在禁用列表中"

        # 如果该QQ有绑定的玩家，先解绑
        bound_player = self.get_qq_bound_player(qq_number)
        if bound_player:
            del self.whitelist_data[bound_player]

        self.banned_qq_list.append(qq_number)
        self.save_whitelist()
        return True, f"✅ 已禁用QQ {qq_number}" + (f"，并解绑了玩家 {bound_player}" if bound_player else "")

    def admin_remove_from_whitelist(self, player_name: str) -> tuple[bool, str]:
        """管理员移除白名单玩家"""
        if player_name not in self.whitelist_data:
            return False, f"❌ 玩家 {player_name} 不在白名单中"

        bound_qq = self.whitelist_data[player_name]
        del self.whitelist_data[player_name]
        self.save_whitelist()
        return True, f"✅ 已将玩家 {player_name} (QQ: {bound_qq}) 从白名单移除"

    @utils.thread_func("WebSocket连接线程")
    def connect_websocket(self):
        """连接到WebSocket"""
        if websocket is None:
            fmts.print_err(f"[{self.name}] WebSocket库未安装，无法连接")
            return

        try:
            header = None
            if self.auth_token:
                header = {"Authorization": f"Bearer {self.auth_token}"}

            self.ws = websocket.WebSocketApp(
                self.ws_url,
                header=header,
                on_message=self.on_ws_message,
                on_error=self.on_ws_error,
                on_close=self.on_ws_close,
                on_open=self.on_ws_open
            )
            self.ws.run_forever()
        except Exception as e:
            fmts.print_err(f"WebSocket连接失败: {e}")

    def on_ws_open(self, ws):
        """WebSocket连接成功"""
        fmts.print_suc("成功连接到QQ机器人WebSocket")

    def on_ws_message(self, ws, message):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)
            if data.get("post_type") == "message" and data["message_type"] == "group":
                if data["group_id"] == self.linked_group:
                    self.handle_qq_message(data)
        except Exception as e:
            fmts.print_err(f"处理QQ消息失败: {e}")

    def on_ws_error(self, ws, error):
        """WebSocket错误处理"""
        if not isinstance(error, Exception):
            fmts.print_inf(f"WebSocket连接关闭: {error}")
            self.reloaded = True
            return

        fmts.print_err(f"WebSocket发生错误: {error}, 15秒后尝试重连")
        time.sleep(15)

    def on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭"""
        if self.reloaded:
            return

        fmts.print_err("WebSocket连接被关闭, 10秒后尝试重连")
        time.sleep(10)
        self.connect_websocket()

    def handle_qq_message(self, data):
        """处理QQ群消息"""
        user_id = data["sender"]["user_id"]
        nickname = data["sender"]["card"] or data["sender"]["nickname"]
        message = data["message"]

        # 处理消息格式（支持NapCat格式）
        if isinstance(message, list):
            msg_data = message[0]
            if msg_data["type"] == "text":
                message = msg_data["data"]["text"]
            else:
                return
        elif not isinstance(message, str):
            return

        message = message.strip()

        # 检查是否是白名单管理指令（必须以#开头）
        if message.startswith("#白名单"):
            self.handle_whitelist_command(user_id, nickname, message)

    def handle_whitelist_command(self, user_id: int, nickname: str, command: str):
        """处理白名单管理指令"""
        # 移除#号前缀
        command = command[1:]  # 移除开头的#号
        parts = command.split()

        # 如果只输入 "#白名单"，显示帮助
        if len(parts) == 1:
            self.send_qq_help(user_id)
            return

        if len(parts) < 2:
            self.send_qq_help(user_id)
            return

        action = parts[1]

        # 用户自行绑定指令
        if action == "添加" and len(parts) >= 3:
            player_name = parts[2]
            success, message = self.bind_player_to_qq(player_name, user_id)
            self.send_qq_message(f"[CQ:at,qq={user_id}] {message}")

        elif action == "解绑":
            success, message = self.unbind_qq(user_id)
            self.send_qq_message(f"[CQ:at,qq={user_id}] {message}")

        elif action == "查询":
            bound_player = self.get_qq_bound_player(user_id)
            if bound_player:
                self.send_qq_message(f"[CQ:at,qq={user_id}] 您当前绑定的玩家: {bound_player}")
            else:
                self.send_qq_message(f"[CQ:at,qq={user_id}] 您没有绑定任何玩家")

        # 管理员专用指令
        elif user_id in self.admin_qq_list:
            if action == "ban" and len(parts) >= 3:
                try:
                    target_qq = int(parts[2])
                    success, message = self.admin_ban_qq(target_qq)
                    self.send_qq_message(message)
                except ValueError:
                    self.send_qq_message("❌ 请输入有效的QQ号")

            elif action == "移除" and len(parts) >= 3:
                player_name = parts[2]
                success, message = self.admin_remove_from_whitelist(player_name)
                self.send_qq_message(message)

            elif action == "列表":
                if not self.whitelist_data:
                    self.send_qq_message("📋 白名单为空")
                else:
                    msg_lines = ["📋 当前白名单:"]
                    for i, (player, qq) in enumerate(self.whitelist_data.items(), 1):
                        msg_lines.append(f"{i}. {player} (QQ: {qq})")
                    if self.banned_qq_list:
                        msg_lines.append("\n🚫 禁用QQ列表:")
                        msg_lines.extend([f"- {qq}" for qq in self.banned_qq_list])
                    self.send_qq_message("\n".join(msg_lines))
            else:
                self.send_qq_admin_help(user_id)
        else:
            self.send_qq_message(f"[CQ:at,qq={user_id}] 您没有管理员权限")

    def send_qq_help(self, user_id: int):
        """发送QQ帮助信息"""
        help_msg = f"""[CQ:at,qq={user_id}] 白名单管理指令:
#白名单 添加 [玩家名] - 绑定玩家到您的QQ
#白名单 解绑 - 解绑您绑定的玩家
#白名单 查询 - 查看您绑定的玩家

注意: 每个QQ只能绑定一个玩家账号"""
        self.send_qq_message(help_msg)

    def send_qq_admin_help(self, user_id: int):
        """发送管理员帮助信息"""
        help_msg = f"""[CQ:at,qq={user_id}] 管理员专用指令:
#白名单 ban [QQ号] - 禁止指定QQ绑定白名单
#白名单 移除 [玩家名] - 强制移除白名单玩家
#白名单 列表 - 查看完整白名单和禁用列表"""
        self.send_qq_message(help_msg)

    def send_qq_message(self, message: str):
        """发送消息到QQ群"""
        if not self.ws:
            return

        try:
            json_data = json.dumps({
                "action": "send_group_msg",
                "params": {
                    "group_id": self.linked_group,
                    "message": message
                }
            })
            self.ws.send(json_data)
        except Exception as e:
            fmts.print_err(f"发送QQ消息失败: {e}")

    def on_playerlist(self, packet):
        """处理PlayerList数据包"""
        if not self.level_enabled:
            return

        try:
            # 检查数据包格式
            if not packet.get("GrowthLevels"):
                fmts.print_err("GrowthLevels 不存在")
                return

            level_data = packet["GrowthLevels"][0]
            if not level_data:
                fmts.print_err("level_data 不存在")
                return

            # 遍历所有玩家条目
            if "Entries" in packet and isinstance(packet["Entries"], list):
                for entry in packet["Entries"]:
                    self.process_player_entry(entry, level_data)

        except Exception as e:
            fmts.print_err(f"处理PlayerList数据包失败: {e}")

    def process_player_entry(self, entry: dict, level: int):
        """处理单个玩家条目"""
        try:
            # 获取玩家信息
            player_name = self.get_player_name(entry)
            player_xuid = self.get_player_xuid(entry)

            if not player_name or not player_xuid:
                return

            # 检查是否在白名单中（优先级高于等级检查）
            if self.is_in_whitelist(player_name):
                msg = utils.simple_fmt(
                    {
                        "[玩家名]": player_name,
                        "[等级]": str(level)
                    },
                    self.config["配置项"]["消息设置"]["白名单绕过提示"]
                )
                fmts.print_inf(msg)

                # 发送QQ通知
                if self.qq_enabled and self.ws:
                    self.send_qq_message(f"🎯 {msg}")
                return

            # 检查等级
            if level < self.min_level:
                self.kick_player_for_low_level(player_name, player_xuid, level)

        except Exception as e:
            fmts.print_err(f"处理玩家条目失败: {e}")

    def get_player_name(self, entry: dict) -> Optional[str]:
        """获取玩家名"""
        if "Username" in entry:
            return entry["Username"]
        fmts.print_err("没有 Username 数据")
        return None

    def get_player_xuid(self, entry: dict) -> Optional[str]:
        """获取玩家XUID"""
        if "XUID" in entry:
            return entry["XUID"]
        fmts.print_err("没有 XUID 数据")
        return None

    @utils.thread_func("踢出玩家线程")
    def kick_player_for_low_level(self, player_name: str, xuid: str, level: int):
        """踢出等级过低的玩家"""
        msg = utils.simple_fmt(
            {
                "[玩家名]": player_name,
                "[等级]": str(level),
                "[最低等级]": str(self.min_level)
            },
            self.config["配置项"]["消息设置"]["等级不足提示"]
        )
        fmts.print_war(msg)

        # 发送QQ通知
        if self.qq_enabled and self.ws:
            self.send_qq_message(f"⛔ {msg}")

        # 延迟后踢出玩家
        time.sleep(self.kick_delay)
        self.game_ctrl.sendwocmd(f"kick {xuid} {self.kick_reason}")


# 注册插件
entry = plugin_entry(LevelCheckEnhanced)

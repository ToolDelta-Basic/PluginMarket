import asyncio
import json
import threading
import time

from tooldelta import Config, Plugin, plugin_entry, game_utils
from tooldelta.constants import PacketIDS


class CrossServerChat(Plugin):
    """服服互通聊天插件 (高频心跳防丢版)。"""

    name = "服服互通聊天"
    author = "哈茶块"
    version = (2, 2, 0)

    CONFIG_TEMPLATE = {
        "中转服务器地址": "ws://core.aurorabot.top",
        "当前服务器名称": "你的服务器名称",
        "频道名称": "全球大厅"
    }

    def __init__(self, frame):
        """初始化插件，处理热重载。"""
        super().__init__(frame)

        # 防止重载插件时旧的后台线程继续存活导致消息重复发送
        if hasattr(self.frame, "_cross_server_chat_instance"):
            old_inst = getattr(self.frame, "_cross_server_chat_instance", None)
            if old_inst:
                try:
                    old_inst.stop()
                except Exception:
                    pass
        self.frame._cross_server_chat_instance = self

        self.is_running = True

        self.cfg, _ = Config.get_plugin_config_and_version(
            self.name,
            Config.auto_to_std(self.CONFIG_TEMPLATE),
            self.CONFIG_TEMPLATE,
            self.version
        )
        self.ws_conn = None
        self.msg_queue = asyncio.Queue()
        self.loop = None

        self.ListenPreload(self.on_def)
        self.ListenPacket(PacketIDS.Text, self.on_chat)

    def stop(self):
        """停止后台服务，供重载时安全清理旧线程。"""
        self.is_running = False
        if self.ws_conn and self.loop:
            try:
                # 线程安全的关闭 WebSocket 连接
                asyncio.run_coroutine_threadsafe(self.ws_conn.close(), self.loop)
            except Exception:
                pass

    def get_online_players(self):
        """核心修复：万能在线玩家获取方法，兼容所有 ToolDelta 版本和接入核心"""
        players = []
        
        # 1. 尝试使用游戏目标选择器 (最稳定)
        try:
            res = game_utils.getTarget("@a")
            if isinstance(res, list):
                players = res
        except Exception:
            pass
            
        if players: return players
        
        # 2. 尝试从 players 对象管理器中提取
        try:
            if hasattr(self.game_ctrl, "players"):
                p_list = self.game_ctrl.players.getAllPlayers()
                players = [p.name if hasattr(p, 'name') else str(p) for p in p_list]
        except Exception:
            pass
            
        if players: return players
        
        # 3. 兜底方案：旧版直接属性
        try:
            if hasattr(self.game_ctrl, "all_players") and isinstance(self.game_ctrl.all_players, list):
                players = self.game_ctrl.all_players
        except Exception:
            pass
            
        return players

    def on_def(self):
        """插件加载时启动后台 WebSocket 线程。"""
        try:
            self.GetPluginAPI("pip").require("websockets")
        except Exception as e:
            self.print_err(f"无法调用内置 pip 模块检查依赖，请确保已安装 [pip模块支持] 插件: {e}")
            return

        self.print_inf(f"准备连接到频道: [{self.cfg['频道名称']}]")
        threading.Thread(target=self.run_ws_client, daemon=True).start()

    def run_ws_client(self):
        """在新线程中初始化异步事件循环。"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.ws_main())

    async def ws_main(self):
        """维持与中转服务器的持久连接。"""
        import websockets

        uri = self.cfg["中转服务器地址"]
        channel = self.cfg["频道名称"]

        while self.is_running:
            try:
                self.print_inf(f"正在尝试连接中转服务器: {uri} ...")
                async with websockets.connect(uri) as ws:
                    self.ws_conn = ws
                    self.print_suc("✅ 成功连接到中转服务器！互通服务已上线。")

                    # 1. 握手阶段
                    auth_data = {
                        "type": "auth",
                        "channel": channel,
                        "server_name": self.cfg["当前服务器名称"]
                    }
                    await ws.send(json.dumps(auth_data))

                    # 2. 并发任务：收、发、以及【高频状态上报】
                    recv_task = asyncio.create_task(self.ws_recv(ws))
                    send_task = asyncio.create_task(self.ws_send(ws))
                    report_task = asyncio.create_task(self.status_report_loop(ws))

                    # 3. 等待任务
                    _, pending = await asyncio.wait(
                        [recv_task, send_task, report_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    # 清理未完成的任务
                    for task in pending:
                        task.cancel()

            except Exception as e:
                if self.is_running:
                    self.print_err(f"❌ 与中转服务器连接断开或无法连接: {e}")
            finally:
                self.ws_conn = None

            if not self.is_running:
                break

            # 5秒后自动重连
            if self.is_running:
                self.print_war("5秒后尝试重新连接...")
                for _ in range(5):
                    if not self.is_running:
                        break
                    await asyncio.sleep(1)

    async def status_report_loop(self, ws):
        """核心修复：3秒高频上报本服务器的真实玩家名单给后端缓存"""
        while self.is_running:
            try:
                local_players = self.get_online_players()
                payload = {
                    "type": "status",
                    "players": local_players
                }
                await ws.send(json.dumps(payload))
            except Exception:
                pass
            # 缩短为 3 秒一次！解决玩家刚进服搜不到人的“真空期”问题
            await asyncio.sleep(3)

    async def ws_recv(self, ws):
        """接收中转服务器发来的跨服消息。"""
        async for msg in ws:
            if not self.is_running:
                break
            try:
                data = json.loads(msg)
                msg_type = data.get("type")
                server_name = data.get("server", "未知服务器")
                sender = data.get("player", "未知玩家")
                content = data.get("msg", "")

                # 1. 普通全服聊天或公告
                if msg_type == "chat":
                    fmt_msg = f"§7[§b{server_name}§7] §e{sender} §f> §r{content}"
                    self.game_ctrl.say_to("@a", fmt_msg)

                # 2. 跨服机制事件 (系统提示/名单返回等)
                elif msg_type == "event":
                    sub_type = data.get("sub_type")
                    
                    # 后端把拼接好的全服名单发给我们了，直接展示给请求的玩家
                    if sub_type == "reply_list":
                        target = data.get("target")
                        reply_content = data.get("content")
                        self.game_ctrl.say_to(target, reply_content)
                        
                    # 后端告诉我们发送私聊失败了 (查无此人)
                    elif sub_type == "private_msg_error":
                        target = data.get("target")
                        error_msg = data.get("msg")
                        self.game_ctrl.say_to(target, error_msg)

                # 3. 收到了别人发来的私聊包裹
                elif msg_type == "private_msg":
                    target = data.get("target")
                    local_players = self.get_online_players()
                    # 检查是不是发给自己服务器里的人的，如果是，就拦截下来显示
                    if target in local_players:
                        fmt_msg = f"§d[私聊] §7[§b{server_name}§7] §e{sender} §f-> §e你§f: §r{content}"
                        self.game_ctrl.say_to(target, fmt_msg)

            except Exception as e:
                self.print_err(f"处理跨服消息时出错: {e}")

    async def ws_send(self, ws):
        """将队列里的本地消息发送给中转服务器。"""
        while self.is_running:
            try:
                msg = await asyncio.wait_for(self.msg_queue.get(), timeout=1.0)
                await ws.send(msg)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    def on_chat(self, pkt):
        """监听本地玩家聊天。"""
        player = pkt.get("SourceName", "")
        msg = pkt.get("Message", "").strip()
        text_type = pkt.get("TextType", 0)

        if not player or not msg:
            return False

        if text_type != 1:
            return False

        if player == self.game_ctrl.bot_name:
            return False

        # ===============================================
        # 跨服私聊 ( .msg 或 .w ) 修复了包含空格名字的匹配问题
        # ===============================================
        if msg.startswith(".msg ") or msg.startswith(".w "):
            cmd_str = msg.split(" ", 1)[1].strip()
            target_player = ""
            content = ""
            
            # 支持用双引号包裹带空格的玩家名 (如: .msg "Player A" 你好)
            if cmd_str.startswith('"'):
                end_idx = cmd_str.find('"', 1)
                if end_idx != -1:
                    target_player = cmd_str[1:end_idx]
                    content = cmd_str[end_idx+1:].strip()
                else:
                    parts = cmd_str.split(" ", 1)
                    target_player = parts[0]
                    content = parts[1] if len(parts) > 1 else ""
            else:
                parts = cmd_str.split(" ", 1)
                if len(parts) < 2:
                    self.game_ctrl.say_to(player, "§c格式错误！用法: .msg <玩家名> <内容> (如果名字带空格请用双引号包裹)")
                    return True
                target_player = parts[0]
                content = parts[1]

            local_players = self.get_online_players()

            # 优先尝试本服内私聊
            if target_player in local_players:
                self.game_ctrl.say_to(target_player, f"§d[私聊] §7[§b{self.cfg['当前服务器名称']}§7] §e{player} §f-> §e你§f: §r{content}")
                self.game_ctrl.say_to(player, f"§d[私聊] §f你 -> §e{target_player}§f: §r{content}")
                return True

            # 本服找不到，直接甩给后端让它去找
            if self.is_running and self.loop and self.ws_conn:
                data = {
                    "type": "private_msg",
                    "server": self.cfg["当前服务器名称"],
                    "player": player,
                    "target": target_player,
                    "msg": content
                }
                asyncio.run_coroutine_threadsafe(
                    self.msg_queue.put(json.dumps(data)),
                    self.loop
                )
                self.game_ctrl.say_to(player, f"§d[私聊] §f你 -> §e{target_player}§f: §r{content}")
            else:
                self.game_ctrl.say_to(player, "§c互通服务未连接，无法发送跨服私聊。")
            return True

        # ===============================================
        # 全网在线状态查询 ( .list 或 .在线 )
        # ===============================================
        if msg in [".list", ".在线"]:
            if self.is_running and self.loop and self.ws_conn:
                # 告诉后端：把全网名单拼好直接发回来给我
                data = {
                    "type": "event",
                    "sub_type": "request_list",
                    "requester": player
                }
                asyncio.run_coroutine_threadsafe(
                    self.msg_queue.put(json.dumps(data)),
                    self.loop
                )
            else:
                # 断网时只显示本地
                local_players = self.get_online_players()
                self.game_ctrl.say_to(player, f"§e==== 🌐 本服在线: {len(local_players)} 人 ====\n§7[§b{self.cfg['当前服务器名称']}§7] §f{', '.join(local_players)}\n§c(跨服网络未连接)")
            return True

        # 过滤其他插件可能会用到的指令前缀
        if msg.startswith("/") or msg.startswith("."):
            return False

        # 正常全服聊天
        if self.is_running and self.loop and self.ws_conn:
            data = {
                "type": "chat",
                "server": self.cfg["当前服务器名称"],
                "player": player,
                "msg": msg
            }
            asyncio.run_coroutine_threadsafe(
                self.msg_queue.put(json.dumps(data)),
                self.loop
            )

        return False


entry = plugin_entry(CrossServerChat)

import asyncio
import json
import threading

from tooldelta import Config, Plugin, plugin_entry, game_utils
from tooldelta.constants import PacketIDS


class CrossServerChat(Plugin):
    """服服互通聊天插件 (频道鉴权版)。"""

    name = "服服互通聊天"
    author = "哈茶块"
    version = (2, 3, 2)

    # 扩展配置，增加鉴权信息
    CONFIG_TEMPLATE = {
        "中转服务器地址": "ws://core.aurorabot.top",
        "当前服务器名称": "你的服务器名称",
        # 默认进入官方公开频道。如需建立私人网络请改为自定义名称
        "频道名称": "全球大厅",
        "频道类型(公开/私密)": "公开",
        "频道密钥(仅私密需填)": ""
    }

    def __init__(self, frame):
        """初始化插件，处理热重载。"""
        super().__init__(frame)

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
                asyncio.run_coroutine_threadsafe(self.ws_conn.close(), self.loop)
            except Exception:
                pass

    def get_online_players(self):
        """获取所有在线玩家列表，兼容多核心版本。"""
        players = []
        try:
            res = game_utils.getTarget("@a")
            if isinstance(res, list):
                players = res
        except Exception:
            pass

        if players:
            return players

        try:
            if hasattr(self.game_ctrl, "players"):
                p_list = self.game_ctrl.players.getAllPlayers()
                players = [
                    p.name if hasattr(p, 'name') else str(p) for p in p_list
                ]
        except Exception:
            pass

        if players:
            return players

        try:
            has_all = hasattr(self.game_ctrl, "all_players")
            if has_all and isinstance(self.game_ctrl.all_players, list):
                players = self.game_ctrl.all_players
        except Exception:
            pass

        return players

    def on_def(self):
        """插件预加载时检查依赖并启动线程。"""
        try:
            self.GetPluginAPI("pip").require("websockets")
        except Exception as e:
            err_msg = f"无法调用内置 pip 模块检查依赖: {e}"
            self.print_err(err_msg)
            return

        c_type = self.cfg.get("频道类型(公开/私密)", "公开")
        lock_icon = "🔒" if c_type == "私密" else "🌐"
        self.print_inf(f"准备连接到频道: {lock_icon} [{self.cfg['频道名称']}]")
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

                    # 1. 鉴权握手
                    auth_data = {
                        "type": "auth",
                        "channel": channel,
                        "server_name": self.cfg["当前服务器名称"],
                        "channel_type": self.cfg.get("频道类型(公开/私密)", "公开"),
                        "channel_key": self.cfg.get("频道密钥(仅私密需填)", "")
                    }
                    await ws.send(json.dumps(auth_data))

                    # 2. 等待服务端反馈 (5秒超时)
                    auth_resp_str = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    auth_resp = json.loads(auth_resp_str)

                    if auth_resp.get("type") == "auth_fail":
                        self.print_err(f"❌ 互通连接被拒绝: {auth_resp.get('msg')}")
                        self.print_war("请修改配置后使用 reload 重载插件。")
                        self.is_running = False  # 彻底阻断，防止刷屏重连
                        return

                    self.ws_conn = ws
                    self.print_suc("✅ 鉴权通过，互通服务已上线！")

                    # 3. 正常建立并发任务
                    recv_task = asyncio.create_task(self.ws_recv(ws))
                    send_task = asyncio.create_task(self.ws_send(ws))
                    report_task = asyncio.create_task(self.status_report_loop(ws))

                    _, pending = await asyncio.wait(
                        [recv_task, send_task, report_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for task in pending:
                        task.cancel()

            except Exception as e:
                if self.is_running:
                    self.print_err(f"❌ 与中转服务器连接断开或无法连接: {e}")
            finally:
                self.ws_conn = None

            if not self.is_running:
                break

            if self.is_running:
                self.print_war("5秒后尝试重新连接...")
                for _ in range(5):
                    if not self.is_running:
                        break
                    await asyncio.sleep(1)

    async def status_report_loop(self, ws):
        """定时高频上报本服务器的真实玩家名单给后端缓存。"""
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

                if msg_type == "chat":
                    fmt_msg = f"§7[§b{server_name}§7] §e{sender} §f> §r{content}"
                    self.game_ctrl.say_to("@a", fmt_msg)

                elif msg_type == "event":
                    sub_type = data.get("sub_type")
                    if sub_type == "reply_list":
                        target = data.get("target")
                        reply_content = data.get("content")
                        self.game_ctrl.say_to(target, reply_content)

                    elif sub_type == "private_msg_error":
                        target = data.get("target")
                        error_msg = data.get("msg")
                        self.game_ctrl.say_to(target, error_msg)

                elif msg_type == "private_msg":
                    target = data.get("target")
                    local_players = self.get_online_players()
                    if target in local_players:
                        fmt_msg = (
                            f"§d[私聊] §7[§b{server_name}§7] §e{sender} "
                            f"§f-> §e你§f: §r{content}"
                        )
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

    def on_chat(self, pkt):  # skipcq: PY-R1000
        """监听本地玩家聊天并处理指令分发。"""
        player = pkt.get("SourceName", "")
        msg = pkt.get("Message", "").strip()
        text_type = pkt.get("TextType", 0)

        if not player or not msg:
            return False
        if text_type != 1:
            return False
        if player == self.game_ctrl.bot_name:
            return False

        if msg.startswith(".msg ") or msg.startswith(".w "):
            cmd_str = msg.split(" ", 1)[1].strip()
            target_player = ""
            content = ""

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
                    self.game_ctrl.say_to(
                        player,
                        "§c格式错误！用法: .msg <玩家名> <内容> (名字带空格请用双引号)"
                    )
                    return True
                target_player = parts[0]
                content = parts[1]

            local_players = self.get_online_players()

            if target_player in local_players:
                self.game_ctrl.say_to(
                    target_player,
                    f"§d[私聊] §7[§b{self.cfg['当前服务器名称']}§7] "
                    f"§e{player} §f-> §e你§f: §r{content}"
                )
                self.game_ctrl.say_to(
                    player,
                    f"§d[私聊] §f你 -> §e{target_player}§f: §r{content}"
                )
                return True

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
                self.game_ctrl.say_to(
                    player,
                    f"§d[私聊] §f你 -> §e{target_player}§f: §r{content}"
                )
            else:
                self.game_ctrl.say_to(player, "§c互通服务未连接，无法发送跨服私聊。")
            return True

        if msg in [".list", ".在线"]:
            if self.is_running and self.loop and self.ws_conn:
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
                local_players = self.get_online_players()
                local_str = ", ".join(local_players)
                msg_str = (
                    f"§e==== 🌐 本服在线: {len(local_players)} 人 ====\n"
                    f"§7[§b{self.cfg['当前服务器名称']}§7] §f{local_str}\n"
                    "§c(跨服网络未连接)"
                )
                self.game_ctrl.say_to(player, msg_str)
            return True

        if msg.startswith("/") or msg.startswith("."):
            return False

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

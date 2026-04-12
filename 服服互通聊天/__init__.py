import asyncio
import json
import threading

from tooldelta import Config, Plugin, plugin_entry
from tooldelta.constants import PacketIDS


class CrossServerChat(Plugin):
    """服服互通聊天插件。"""

    name = "服服互通聊天"
    author = "哈茶块"
    version = (1, 0, 3)

    CONFIG_TEMPLATE = {
        "中转服务器地址": "ws://core.aurorabot.top",
        "当前服务器名称": "你的服务器名称",
        "频道名称": "全球大厅"
    }

    def __init__(self, frame):
        """初始化插件，处理热重载。"""
        super().__init__(frame)

        #  防止重载插件时旧的后台线程继续存活导致消息重复发送
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
                # 线程安全的关闭 WebSocket 连接，触发异常结束任务
                asyncio.run_coroutine_threadsafe(self.ws_conn.close(), self.loop)
            except Exception:
                pass

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
        # 此时 websockets 必定已经被官方 pip 模块处理好了，可以直接局部导入
        import websockets

        uri = self.cfg["中转服务器地址"]
        channel = self.cfg["频道名称"]

        while self.is_running:
            try:
                self.print_inf(f"正在尝试连接中转服务器: {uri} ...")
                async with websockets.connect(uri) as ws:
                    self.ws_conn = ws
                    self.print_suc("成功连接到中转服务器！互通服务已上线。")

                    # 1. 握手阶段：告诉服务器我属于哪个频道
                    await ws.send(json.dumps({"type": "auth", "channel": channel}))

                    # 2. 并发任务：一个负责收，一个负责发
                    recv_task = asyncio.create_task(self.ws_recv(ws))
                    send_task = asyncio.create_task(self.ws_send(ws))

                    # 3. 等待任意一个任务出错（例如连接断开）
                    _, pending = await asyncio.wait(
                        [recv_task, send_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    # 清理未完成的任务
                    for task in pending:
                        task.cancel()

            except Exception as e:
                # 只有在非关闭状态下才打印断开提示
                if self.is_running:
                    self.print_err(f" 与中转服务器连接断开或无法连接: {e}")
            finally:
                self.ws_conn = None

            if not self.is_running:
                break

            # 5秒后自动重连 (分片Sleep以保证重载时能快速中断退出)
            if self.is_running:
                self.print_war("5秒后尝试重新连接...")
                for _ in range(5):
                    if not self.is_running:
                        break
                    await asyncio.sleep(1)

    async def ws_recv(self, ws):
        """接收中转服务器发来的跨服消息。"""
        async for msg in ws:
            if not self.is_running:
                break
            try:
                data = json.loads(msg)
                if data.get("type") == "chat":
                    server_name = data.get("server")
                    player = data.get("player")
                    content = data.get("msg")

                    # 格式化输出到本地游戏内
                    fmt_msg = f"§7[§b{server_name}§7] §e{player} §f> §r{content}"
                    self.game_ctrl.say_to("@a", fmt_msg)
            except Exception as e:
                self.print_err(f"处理跨服消息时出错: {e}")

    async def ws_send(self, ws):
        """将队列里的本地消息发送给中转服务器。"""
        while self.is_running:
            try:
                # 使用 wait_for 限制等待时间，确保能实时检测到 self.is_running 的变化
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

        # 1. 过滤空消息或无来源消息
        if not player or not msg:
            return False

        # 2. 严格检测文本类型，仅放行真正的玩家聊天 (TextType == 1)
        if text_type != 1:
            return False

        # 3. 过滤指令前缀 (以 / 或 . 开头的内容不转发)
        if msg.startswith("/") or msg.startswith("."):
            return False

        # 4. 过滤机器人(Bot)自己发出的消息
        if player == self.game_ctrl.bot_name:
            return False

        # 如果 WebSocket 已连接且插件处于运行状态，将合法玩家聊天压入发送队列
        if self.is_running and self.loop and self.ws_conn:
            data = {
                "type": "chat",
                "server": self.cfg["当前服务器名称"],
                "player": player,
                "msg": msg
            }
            # 安全地将消息从 ToolDelta 主线程跨线程推入 asyncio 队列
            asyncio.run_coroutine_threadsafe(
                self.msg_queue.put(json.dumps(data)),
                self.loop
            )

        return False


entry = plugin_entry(CrossServerChat)

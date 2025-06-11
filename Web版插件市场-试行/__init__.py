from tooldelta import Plugin, fmts, plugin_entry
import os
import zipfile
import json
import requests
import websockets
import asyncio
import random
import string
import datetime
import time
import threading
from typing import Dict, Any, Callable

class ClientConfig:
    def __init__(self, server_url: str = "api.tooldelta.xyz"):
        self.server_url = server_url
        self.user_id: str = None
        self.device_fingerprint: str = None
        self.websocket_url = f"ws://{self.server_url}/api/socket"

    def generate_user_id(self) -> str:
        return "".join(random.choices(string.ascii_uppercase, k=6))

    def generate_device_fingerprint(self) -> str:
        return "".join(random.choices(string.ascii_letters + string.digits, k=32))

class HTTPClient:
    def __init__(self, config: ClientConfig):
        self.config = config
        self.session = requests.Session()
        
    def _get_full_url(self, endpoint: str) -> str:
        return f"http://{self.config.server_url}/{endpoint.lstrip('/')}"

    def _add_headers(self, headers: Dict[str, str] = None) -> Dict[str, str]:
        default_headers = {
            "Content-Type": "application/json",
            "X-Custom-ID": self.config.user_id
        }
        if headers:
            default_headers.update(headers)
        return default_headers

    def _make_request(self, method: str, endpoint: str, data: Dict[str, Any] = None, params: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            response = self.session.request(
                method=method,
                url=self._get_full_url(endpoint),
                json=data,
                params=params,
                headers=self._add_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            fmts.print_err(f"请求失败: {str(e)}")
            raise

    def get_plugins(self) -> Dict[str, Any]:
        return self._make_request("GET", "api/plugins")

    def get_packages(self) -> Dict[str, Any]:
        return self._make_request("GET", "api/packages")

    def download_plugin(self, plugin_id: str) -> Dict[str, Any]:
        data = {"user_id": self.config.user_id}
        return self._make_request("POST", f"api/plugin/download/{plugin_id}", data=data)

    def rate_plugin(self, plugin_id: str, rating: int) -> Dict[str, Any]:
        data = {"user_id": self.config.user_id, "rating": rating}
        return self._make_request("POST", f"api/plugin/rate/{plugin_id}", data=data)

class WebSocketClient:
    def __init__(self, config: ClientConfig, message_callback: Callable | None = None):
        self.config = config
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.message_callback = message_callback
        self.current_file = None
        self.is_connected = False
        self.heartbeat_interval = 15
        self.last_activity = time.time()
        self.keepalive_timeout = 90
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.ws_lock = asyncio.Lock()
        self.loop = asyncio.new_event_loop()
        self.stop_flag = threading.Event()
        self.last_heartbeat_ack = 0
        self._print_progress()

    async def ws_send(self, message):
        async with self.ws_lock:
            await self.ws.send(message)

    async def ws_recv(self):
        async with self.ws_lock:
            return await self.ws.recv()

    async def save_received_file(self):
        if not self.current_file:
            return
        
        file_id = self.current_file["id"]
        file_data = self.current_file["data"]
        
        # 确保下载目录存在
        download_dir = os.path.join("插件文件", "ToolDelta类式插件", file_id)
        os.makedirs(download_dir, exist_ok=True)
        
        # 保存ZIP文件
        zip_path = os.path.join(download_dir, f"{file_id}.zip")
        try:
            with open(zip_path, "wb") as f:
                f.write(file_data)
            
            # 解压文件
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(download_dir)
            
            # 删除临时ZIP文件
            os.remove(zip_path)
            
            fmts.print_suc(f"插件 {file_id} 已成功安装到: {download_dir}")
            fmts.print_inf(f"文件大小: {len(file_data)} bytes")
            
        except Exception as e:
            fmts.print_err(f"文件处理失败: {str(e)}")
            fmts.print_err(f"错误文件路径: {zip_path}")

    def _print_progress(self):
        if self.current_file:
            received = self.current_file.get("received", 0)
            total = self.current_file.get("size", 0)
            if total > 0:
                percentage = min(int((received / total) * 100), 100)
                # 创建更直观的进度条
                bar_length = 50
                filled_length = int(bar_length * percentage // 100)
                bar = '■' * filled_length + '□' * (bar_length - filled_length)
                # 使用 \r 实现行内刷新
                print(f"\r[{bar}] {percentage}%", end='', flush=True)
                
                # 下载完成时换行
                if percentage == 100:
                    print()

    async def _listen_messages(self):
        try:
            while not self.stop_flag.is_set() and self.is_connected:
                try:
                    if self.ws is None:
                        break
                    
                    # 使用异步接收避免阻塞
                    message = await asyncio.wait_for(self.ws_recv(), timeout=self.keepalive_timeout)
                    self.last_activity = time.time()
                    
                    # 处理文本消息
                    if isinstance(message, str):
                        try:
                            msg = json.loads(message)
                            # 处理服务端发来的心跳包
                            if msg.get("type") == "heartbeat":
                                # 回复心跳确认
                                ack_msg = json.dumps({
                                    "type": "heartbeat_ack",
                                    "timestamp": datetime.datetime.now().isoformat()
                                })
                                await self.ws_send(ack_msg)
                                # fmts.print_inf(f"收到服务端心跳并回复确认")
                                continue
                                
                            # 处理心跳确认（服务端对客户端心跳的回复）
                            elif msg.get("type") == "heartbeat_ack":
                                self.last_heartbeat_ack = time.time()
                                # fmts.print_inf("收到心跳确认")
                                continue
                                
                            # 文件传输处理（保持原逻辑）
                            elif msg.get("type") == "file_start":
                                file_id = msg["file_id"]
                                total_size = msg["size"]
                                self.current_file = {
                                    "id": file_id,
                                    "received": 0,
                                    "data": b"",
                                    "size": total_size
                                }
                                print(f"开始下载: {file_id} ({total_size} bytes)")
                                self._print_progress()
                                
                                
                            elif msg.get("type") == "file_end":
                                if self.current_file:
                                    self._print_progress()  # 确保显示100%
                                    await self.save_received_file()
                                    self.current_file = None  # 重置当前文件
                                
                        except json.JSONDecodeError:
                            pass
                    
                    # 处理二进制数据（文件内容）
                    elif isinstance(message, bytes) and self.current_file:
                        self.current_file["received"] += len(message)
                        self.current_file["data"] += message
                        self._print_progress()
                        
                except asyncio.TimeoutError:
                    continue
        except websockets.ConnectionClosed as e:
            fmts.print_war(f"连接已断开: {e}")
        except Exception as e:
            fmts.print_err(f"监听消息错误: {str(e)}")
        finally:
            self.is_connected = False
            if self.message_callback:
                self.message_callback("disconnected")

    async def _register_client(self):
        if self.config.user_id is None:
            self.config.user_id = self.config.generate_user_id()
            fmts.print_inf(f"生成新的客户端ID: {self.config.user_id}")
        
        register_message = {
            "type": "register",
            "user_id": self.config.user_id
        }
        await self.ws_send(json.dumps(register_message))
        
        response = await self.ws_recv()
        # fmts.print_inf(f"注册响应: {response}")
        self.last_activity = time.time()

    async def _monitor_connection(self):
        while not self.stop_flag.is_set() and self.is_connected:
            try:
                # 发送心跳包
                await self.ws_send(json.dumps({
                    "type": "heartbeat",
                    "timestamp": datetime.datetime.now().isoformat()
                }))
                send_time = time.time()
                
                # 等待确认（不再直接接收消息）
                while time.time() - send_time < 10:  # 10秒超时
                    if self.last_heartbeat_ack > send_time:
                        # fmts.print_inf("心跳确认正常")
                        break
                    await asyncio.sleep(0.5)
                else:
                    fmts.print_war("未收到心跳确认")
                    await self._safe_reconnect()
                    return
                    
            except Exception as e:
                if "NoneType" in str(e):  # 忽略NoneType错误
                    fmts.print_war(f"连接已关闭: {str(e)}")
                else:
                    fmts.print_err(f"心跳监控错误: {str(e)}")
                await self._safe_reconnect()
                return
            await asyncio.sleep(self.heartbeat_interval)

    async def _safe_reconnect(self):
        if self.is_connected:
            await self.close()
        await self.connect()

    async def connect(self) -> None:
        self.stop_flag.clear()  # 重置停止标志
        self.reconnect_attempts = 0
        while not self.stop_flag.is_set() and self.reconnect_attempts < self.max_reconnect_attempts:
            if self.reconnect_attempts > 0:
                self.config.user_id = self.config.generate_user_id()
                fmts.print_inf(f"重连时生成新的用户ID: {self.config.user_id}")
                
            try:
                # fmts.print_inf(f"尝试连接到 {self.config.websocket_url}...")
                async with websockets.connect(
                    self.config.websocket_url,
                    ping_interval=None,
                    close_timeout=1,
                    open_timeout=10
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.last_activity = time.time()
                    fmts.print_inf("成功连接到 PluginMarket-Web 服务端")

                    if self.message_callback:
                        self.message_callback("connected")
                    
                    await self._register_client()
                    
                    # 启动心跳监控任务
                    asyncio.create_task(self._monitor_connection())
                    
                    await self._listen_messages()
                    
            except (asyncio.TimeoutError, websockets.ConnectionClosed, websockets.InvalidURI) as e:
                self.reconnect_attempts += 1
                fmts.print_war(f"连接失败 ({self.reconnect_attempts}/{self.max_reconnect_attempts}): {str(e)}")
                await asyncio.sleep(min(2 ** self.reconnect_attempts, 30))
            except Exception as e:
                if "NoneType" in str(e):  # 忽略NoneType错误
                    fmts.print_war(f"连接已关闭: {str(e)}")
                else:
                    fmts.print_err(f"连接异常: {str(e)}")
                self.reconnect_attempts += 1
                await asyncio.sleep(5)
        
        if not self.stop_flag.is_set():
            fmts.print_err("达到最大重连次数，放弃连接")


    async def send_message(self, message: Dict[str, Any]) -> None:
        if self.ws and self.is_connected:
            await self.ws_send(json.dumps(message))
            self.last_activity = time.time()
            if self.message_callback:
                self.message_callback("sent", message)
        else:
            fmts.print_err("WebSocket未连接")

    async def close(self) -> None:
        self.stop_flag.set()  # 设置停止标志
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.is_connected = False
        fmts.print_inf("WebSocket连接已关闭")

    def run_in_thread(self):
        def start_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.connect())

        self.thread = threading.Thread(target=start_loop, daemon=True)
        self.thread.start()
        # fmts.print_inf("WebSocket客户端已在后台线程启动")

    def stop(self):
        self.stop_event.set()
        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.close(), self.loop)
            self.loop.call_soon_threadsafe(self.loop.stop)
        fmts.print_inf("WebSocket客户端已停止")

class Client:
    def __init__(self, server_url: str = "api.tooldelta.xyz", message_callback: Callable = None):
        self.config = ClientConfig(server_url)
        self.http_client = HTTPClient(self.config)
        self.ws_client = WebSocketClient(self.config, message_callback)
        
    def generate_ids(self) -> None:
        if not self.config.user_id:
            self.config.user_id = self.config.generate_user_id()
            fmts.print_succ(f"PluginMarketWeb 身份ID -> {self.config.user_id}")
        
        if not self.config.device_fingerprint:
            self.config.device_fingerprint = self.config.generate_device_fingerprint()
            # fmts.print_inf(f"生成设备指纹: {self.config.device_fingerprint}")

    def connect_in_thread(self) -> None:
        self.generate_ids()
        self.ws_client.run_in_thread()

    def stop(self) -> None:
        self.ws_client.stop()

async def message_callback(event_type: str, *args):
    if event_type == "connected":
        fmts.print_inf("连接成功")
    elif event_type == "disconnected":
        fmts.print_war("连接已断开")
    elif event_type == "message":
        fmts.print_inf(f"接收到消息: {args[0]}")

class PluginMarketWeb(Plugin):
    name = "PluginMarketWeb"
    author = "ToolDelta"
    version = (0, 1, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenFrameExit(self.on_disable)
        self.ListenActive(self.on_active)

    def on_active(self):
        fmts.print_load("PluginMarketWeb 官方网站地址: http://web.tooldelta.xyz")
        self.client = Client(message_callback=message_callback)
        self.client.connect_in_thread()

    def on_disable(self):
        self.client.stop()

entry = plugin_entry(PluginMarketWeb, "pluginmarket_web")
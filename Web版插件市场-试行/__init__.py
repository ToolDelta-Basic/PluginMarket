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
        """生成6位大写字母的客户端ID"""
        return "".join(random.choices(string.ascii_uppercase, k=6))

    def generate_device_fingerprint(self) -> str:
        """生成设备指纹"""
        return "".join(random.choices(string.ascii_letters + string.digits, k=32))

class HTTPClient:
    def __init__(self, config: ClientConfig):
        self.config = config
        self.session = requests.Session()
        
    def _get_full_url(self, endpoint: str) -> str:
        """获取完整的API URL"""
        return f"http://{self.config.server_url}/{endpoint.lstrip('/')}"

    def _add_headers(self, headers: Dict[str, str] = None) -> Dict[str, str]:
        """添加默认headers"""
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
        """获取所有插件信息"""
        return self._make_request("GET", "api/plugins")

    def get_packages(self) -> Dict[str, Any]:
        """获取所有整合包信息"""
        return self._make_request("GET", "api/packages")

    def download_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """记录插件下载"""
        data = {"user_id": self.config.user_id}
        return self._make_request("POST", f"api/plugin/download/{plugin_id}", data=data)

    def rate_plugin(self, plugin_id: str, rating: int) -> Dict[str, Any]:
        """为插件评分"""
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
        self.stop_event = threading.Event()

    async def ws_send(self, message):
        async with self.ws_lock:
            await self.ws.send(message)

    async def ws_recv(self):
        async with self.ws_lock:
            return await self.ws.recv()

    async def save_received_file(self):
        if not self.current_file:
            return
        download_dir = os.path.join("插件文件", "ToolDelta类式插件", self.current_file["id"])
        os.makedirs(download_dir, exist_ok=True)
        file_path = os.path.join(download_dir, f"{self.current_file['id']}.zip")
        with open(file_path, "wb") as f:
            f.write(self.current_file["data"])
        try:
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                zip_ref.extractall(download_dir)
            os.remove(file_path)
            fmts.print_inf(f"文件 {self.current_file['id']} 已保存到 {download_dir}")
        except Exception as e:
            fmts.print_err(f"解压文件失败: {str(e)}")

    async def _monitor_connection(self):
        while self.is_connected and not self.stop_event.is_set():
            try:
                async with self.ws_lock:
                    if self.ws:
                        await self.ws.send(json.dumps({
                            "type": "heartbeat",
                            "timestamp": datetime.datetime.now().isoformat()
                        }))
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                fmts.print_err(f"心跳监控错误: {str(e)}")
                await self._safe_reconnect()
                return

    async def _safe_reconnect(self):
        if self.is_connected:
            await self.close()
        await self.connect()

    async def connect(self) -> None:
        self.reconnect_attempts = 0
        while self.reconnect_attempts < self.max_reconnect_attempts and not self.stop_event.is_set():
            if self.reconnect_attempts > 0:
                self.config.user_id = self.config.generate_user_id()
                fmts.print_inf(f"重连时生成新的用户ID: {self.config.user_id}")
                
            try:
                fmts.print_inf(f"尝试连接到 {self.config.websocket_url}...")
                async with websockets.connect(
                    self.config.websocket_url,
                    ping_interval=None,
                    close_timeout=1,
                    open_timeout=10
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.last_activity = time.time()
                    fmts.print_inf("WebSocket连接成功")

                    if self.message_callback:
                        self.message_callback("connected")
                    
                    await self._register_client()
                    
                    asyncio.create_task(self._monitor_connection())
                    
                    await self._listen_messages()
                    
            except (asyncio.TimeoutError, websockets.ConnectionClosed, websockets.InvalidURI) as e:
                self.reconnect_attempts += 1
                fmts.print_war(f"连接失败 ({self.reconnect_attempts}/{self.max_reconnect_attempts}): {str(e)}")
                await asyncio.sleep(min(2 ** self.reconnect_attempts, 30))
            except Exception as e:
                fmts.print_err(f"连接异常: {str(e)}")
                self.reconnect_attempts += 1
                await asyncio.sleep(5)
        
        if not self.stop_event.is_set():
            fmts.print_err("达到最大重连次数，放弃连接")

    async def _register_client(self) -> None:
        if self.config.user_id is None:
            self.config.user_id = self.config.generate_user_id()
            fmts.print_inf(f"生成新的客户端ID: {self.config.user_id}")
        
        register_message = {
            "type": "register",
            "user_id": self.config.user_id
        }
        await self.ws_send(json.dumps(register_message))
        
        response = await self.ws_recv()
        fmts.print_inf(f"注册响应: {response}")
        self.last_activity = time.time()

    async def _listen_messages(self):
        try:
            while self.is_connected and not self.stop_event.is_set():
                try:
                    message = await asyncio.wait_for(self.ws_recv(), timeout=self.keepalive_timeout)
                    self.last_activity = time.time()
                    
                    if isinstance(message, str):
                        msg = json.loads(message)
                        if msg.get("type") == "file_start":
                            file_id = msg["file_id"]
                            total_size = msg["size"]
                            self.current_file = {"id": file_id, "received": 0, "data": b"", "size": total_size}
                            fmts.print_inf(f"开始接收文件 {file_id}, 总大小: {total_size} bytes")
                        elif msg.get("type") == "file_end":
                            if self.current_file:
                                await self.save_received_file()
                                fmts.print_inf(f"完成接收文件 {self.current_file['id']}")
                                self.current_file = None
                        elif msg.get("type") == "heartbeat_ack":
                            fmts.print_inf("收到心跳确认")
                        else:
                            fmts.print_inf(f"接收消息: {message}")
                            if self.message_callback:
                                self.message_callback("message", message)
                    elif isinstance(message, bytes):
                        if self.current_file:
                            self.current_file["received"] += len(message)
                            self.current_file["data"] += message
                            progress = (self.current_file["received"] / self.current_file["size"]) * 100
                            fmts.print_inf(f"接收进度: {progress:.1f}%")
                            if self.message_callback:
                                self.message_callback("progress", progress)
                
                except asyncio.TimeoutError:
                    continue
                
        except websockets.ConnectionClosed as e:
            fmts.print_inf(f"连接已关闭: {e}")
        except Exception as e:
            fmts.print_err(f"监听消息错误: {str(e)}")
        finally:
            self.is_connected = False
            if self.message_callback:
                self.message_callback("disconnected")

    async def send_message(self, message: Dict[str, Any]) -> None:
        if self.ws and self.is_connected:
            await self.ws_send(json.dumps(message))
            self.last_activity = time.time()
            fmts.print_inf(f"发送消息: {message}")
            if self.message_callback:
                self.message_callback("sent", message)
        else:
            fmts.print_err("WebSocket未连接")

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.is_connected = False
        fmts.print_inf("WebSocket连接已关闭")

    def run_in_thread(self):
        """在新线程中运行事件循环"""
        def start_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.connect())

        self.thread = threading.Thread(target=start_loop, daemon=True)
        self.thread.start()
        fmts.print_inf("WebSocket客户端已在后台线程启动")

    def stop(self):
        """停止客户端并清理资源"""
        self.stop_event.set()
        if self.loop.is_running():
            # 安排关闭任务
            asyncio.run_coroutine_threadsafe(self.close(), self.loop)
            # 停止事件循环
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
            fmts.print_inf(f"生成客户端ID: {self.config.user_id}")
        
        if not self.config.device_fingerprint:
            self.config.device_fingerprint = self.config.generate_device_fingerprint()
            fmts.print_inf(f"生成设备指纹: {self.config.device_fingerprint}")

    def connect_in_thread(self) -> None:
        """在独立线程中启动连接"""
        self.generate_ids()
        self.ws_client.run_in_thread()

    def stop(self) -> None:
        """停止客户端"""
        self.ws_client.stop()

async def message_callback(event_type: str, *args):
    """示例回调函数"""
    if event_type == "connected":
        print("连接成功")
    elif event_type == "disconnected":
        print("连接已断开")
    elif event_type == "message":
        print(f"接收到消息: {args[0]}")
    elif event_type == "progress":
        print(f"下载进度: {args[0]}%")

class PluginMarketWeb(Plugin):
    name = "PluginMarketWeb"
    author = "ToolDelta"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.client = Client(message_callback=message_callback)
        # 在独立线程中启动客户端
        self.client.connect_in_thread()

    def on_disable(self):
        """插件卸载时停止客户端"""
        self.client.stop()
        fmts.print_inf(f"[{self.name}] 插件市场客户端已关闭")

entry = plugin_entry(PluginMarketWeb, "pluginmarket_web")
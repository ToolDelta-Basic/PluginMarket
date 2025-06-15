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
from typing import Dict, Any, Callable, Optional

class ClientConfig:
    def __init__(self, server_url: str = "api.tooldelta.xyz"):
        self.server_url = server_url
        self.user_id: str = None
        self.device_fingerprint: str = None
        self.websocket_url = f"ws://{self.server_url}/api/socket"

    def generate_user_id(self) -> str:
        """生成符合服务端要求的6位大写字母ID"""
        return "".join(random.choices(string.ascii_uppercase, k=6))

    def generate_device_fingerprint(self) -> str:
        """生成32位设备指纹（与服务端兼容）"""
        return "".join(random.choices(string.ascii_letters + string.digits, k=32))

class HTTPClient:
    def __init__(self, config: ClientConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ToolDeltaPluginMarketClient/1.0",
            "Accept": "application/json"
        })
        
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
                timeout=15
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    fmts.print_err(f"请求失败 ({e.response.status_code}): {error_data.get('message', '未知错误')}")
                except:
                    fmts.print_err(f"请求失败 ({e.response.status_code}): {e.response.text[:100]}")
            else:
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
        self.heartbeat_interval = 25
        self.last_activity = time.time()
        self.keepalive_timeout = 60
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 15
        self.ws_lock = asyncio.Lock()
        self.loop = asyncio.new_event_loop()
        self.stop_flag = threading.Event()
        self.last_heartbeat_ack = 0
        self.last_progress_update = 0
        self.progress_interval = 0.5
        self.connection_lock = threading.Lock()
        self.last_exception = None

    async def ws_send(self, message):
        async with self.ws_lock:
            if self.ws is None or not self.is_connected:
                return
            try:
                await self.ws.send(message)
            except (websockets.ConnectionClosed, websockets.InvalidState) as e:
                self.is_connected = False
                self.last_exception = e
            except Exception as e:
                fmts.print_err(f"发送消息失败: {str(e)}")
                self.last_exception = e

    async def ws_recv(self):
        async with self.ws_lock:
            if self.ws is None or not self.is_connected:
                return None
            try:
                return await self.ws.recv()
            except (websockets.ConnectionClosed, websockets.InvalidState) as e:
                self.is_connected = False
                self.last_exception = e
                return None
            except Exception as e:
                fmts.print_err(f"接收消息失败: {str(e)}")
                self.last_exception = e
                return None

    async def save_received_file(self):
        if not self.current_file:
            return
        
        file_id = self.current_file["id"]
        file_data = self.current_file["data"]
        
        download_dir = os.path.join("插件文件", "ToolDelta类式插件", file_id)
        os.makedirs(download_dir, exist_ok=True)
        
        zip_path = os.path.join(download_dir, f"{file_id}.zip")
        try:
            with open(zip_path, "wb") as f:
                f.write(file_data)
            
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(download_dir)
            
            os.remove(zip_path)
            
            fmts.print_suc(f"插件 {file_id} 已成功安装到: {download_dir}")
            fmts.print_inf(f"文件大小: {len(file_data)} bytes")
            
            if self.is_connected:
                await self.ws_send(json.dumps({
                    "type": "download_complete",
                    "file_id": file_id,
                    "status": "success"
                }))
                
        except Exception as e:
            fmts.print_err(f"文件处理失败: {str(e)}")
            if self.is_connected:
                await self.ws_send(json.dumps({
                    "type": "download_complete",
                    "file_id": file_id,
                    "status": "failed",
                    "error": str(e)
                }))
        finally:
            self.current_file = None

    def _print_progress(self, force: bool = False):
        if not self.current_file:
            return
            
        current_time = time.time()
        if not force and current_time - self.last_progress_update < self.progress_interval:
            return
            
        self.last_progress_update = current_time
        
        received = self.current_file.get("received", 0)
        total = self.current_file.get("size", 0)
        if total > 0:
            percentage = min(int((received / total) * 100), 100)
            bar_length = 30
            filled_length = int(bar_length * percentage // 100)
            bar = '■' * filled_length + '□' * (bar_length - filled_length)
            speed = self.current_file.get("speed", 0) / 1024
            print(f"\r[{bar}] {percentage}% | {speed:.1f} KB/s", end='', flush=True)
            
            if percentage == 100:
                print()

    async def _listen_messages(self):
        try:
            while not self.stop_flag.is_set() and self.is_connected:
                try:
                    if self.ws is None or not self.is_connected:
                        break
                    
                    message = await asyncio.wait_for(self.ws_recv(), timeout=self.keepalive_timeout)
                    
                    # 检查消息是否为None
                    if message is None:
                        # 如果消息为None，可能是连接已关闭
                        if not self.is_connected:
                            break
                        continue
                        
                    self.last_activity = time.time()
                    
                    # 处理文本消息
                    if isinstance(message, str):
                        try:
                            # 确保消息不是空字符串
                            if not message.strip():
                                continue
                                
                            # 记录原始消息用于调试
                            # fmts.print_inf(f"收到消息: {message[:200]}")
                            
                            msg = json.loads(message)
                            if msg.get("type") == "heartbeat":
                                ack_msg = json.dumps({
                                    "type": "heartbeat_ack",
                                    "timestamp": datetime.datetime.now().isoformat()
                                })
                                await self.ws_send(ack_msg)
                                continue
                                
                            elif msg.get("type") == "heartbeat_ack":
                                self.last_heartbeat_ack = time.time()
                                continue
                                
                            elif msg.get("type") == "file_start":
                                file_id = msg["file_id"]
                                total_size = msg["size"]
                                self.current_file = {
                                    "id": file_id,
                                    "received": 0,
                                    "data": b"",
                                    "size": total_size,
                                    "start_time": time.time(),
                                    "last_update": time.time(),
                                    "speed": 0
                                }
                                print(f"开始下载: {file_id} ({total_size} bytes)")
                                self._print_progress(force=True)
                                
                            elif msg.get("type") == "file_end":
                                if self.current_file:
                                    self.current_file["received"] = self.current_file["size"]
                                    self._print_progress(force=True)
                                    await self.save_received_file()
                                
                            elif msg.get("type") == "error":
                                fmts.print_err(f"服务端错误: {msg.get('message', '未知错误')}")
                                
                            elif msg.get("type") == "notification":
                                fmts.print_inf(f"服务端通知: {msg.get('message', '')}")
                                
                            elif msg.get("type") == "register_response":
                                if msg.get("status") == "success":
                                    fmts.print_suc(f"服务端注册成功: {msg.get('message', '')}")
                                else:
                                    fmts.print_err(f"服务端注册失败: {msg.get('message', '未知错误')}")
                                
                        except json.JSONDecodeError as e:
                            fmts.print_war(f"JSON解析失败: {str(e)}")
                            fmts.print_war(f"原始消息: {message[:200]}")
                            if self.message_callback:
                                self.message_callback("message", message)
                    
                    # 处理二进制数据（文件内容）
                    elif isinstance(message, bytes) and self.current_file:
                        current_time = time.time()
                        data_size = len(message)
                        self.current_file["received"] += data_size
                        
                        time_diff = current_time - self.current_file["last_update"]
                        if time_diff > 0.1:
                            self.current_file["speed"] = data_size / time_diff
                            self.current_file["last_update"] = current_time
                        
                        self.current_file["data"] += message
                        self._print_progress()
                        
                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed as e:
                    fmts.print_war(f"连接已关闭: {e.code} - {e.reason}")
                    self.is_connected = False
                    break
                except Exception as e:
                    fmts.print_err(f"监听消息时发生错误: {str(e)}")
                    self.is_connected = False
                    break
                    
        except Exception as e:
            fmts.print_err(f"监听消息循环错误: {str(e)}")
            self.is_connected = False
        finally:
            self.is_connected = False
            if self.message_callback:
                self.message_callback("disconnected")

    async def _register_client(self):
        if self.config.user_id is None:
            self.config.user_id = self.config.generate_user_id()
            fmts.print_inf(f"生成新的客户端ID: {self.config.user_id}")
        
        # 创建完整的注册消息
        register_message = {
            "type": "register",
            "user_id": self.config.user_id,
            "device_fingerprint": self.config.device_fingerprint
        }
        
        fmts.print_inf(f"发送注册信息: 用户ID={self.config.user_id}, 设备指纹={self.config.device_fingerprint[:6]}...")
        await self.ws_send(json.dumps(register_message))
        
        try:
            # 等待注册响应
            response = await asyncio.wait_for(self.ws_recv(), timeout=8)
            if response:
                try:
                    # 确保响应不是空字符串
                    if response.strip():
                        msg = json.loads(response)
                        if msg.get("type") == "register_response":
                            if msg.get("status") == "success":
                                fmts.print_suc(f"注册成功: {msg.get('message', '')}")
                            else:
                                fmts.print_err(f"注册失败: {msg.get('message', '未知错误')}")
                                # 注册失败时断开连接
                                self.is_connected = False
                                return False
                        elif msg.get("type") == "welcome":
                            fmts.print_suc(f"服务端欢迎: {msg.get('message', '连接成功')}")
                        else:
                            fmts.print_war(f"收到未知响应类型: {msg.get('type', '未知')}")
                except json.JSONDecodeError as e:
                    fmts.print_war(f"注册响应JSON解析失败: {str(e)}")
                    fmts.print_war(f"原始响应: {response[:200]}")
        except asyncio.TimeoutError:
            fmts.print_war("注册响应超时，但连接保持")
        except Exception as e:
            fmts.print_err(f"注册过程中发生错误: {str(e)}")
            
        self.last_activity = time.time()
        return True

    async def _monitor_connection(self):
        while not self.stop_flag.is_set() and self.is_connected:
            try:
                # 发送心跳包
                await self.ws_send(json.dumps({
                    "type": "heartbeat",
                    "timestamp": datetime.datetime.now().isoformat()
                }))
                send_time = time.time()
                
                # 等待确认
                while time.time() - send_time < 10 and self.is_connected:
                    if self.last_heartbeat_ack > send_time:
                        break
                    await asyncio.sleep(0.5)
                else:
                    if self.is_connected:
                        fmts.print_war("未收到心跳确认，重新连接...")
                        await self._safe_reconnect()
                    return
                    
            except Exception as e:
                if self.is_connected:
                    fmts.print_err(f"心跳监控错误: {str(e)}")
                    await self._safe_reconnect()
                return
                
            # 随机化心跳间隔
            wait_time = self.heartbeat_interval + random.uniform(-3, 3)
            await asyncio.sleep(wait_time)

    async def _safe_reconnect(self):
        if self.is_connected:
            await self.close()
        await self.connect()

    async def connect(self) -> None:
        # 确保只有一个连接线程在运行
        with self.connection_lock:
            if self.is_connected:
                fmts.print_war("连接已在进行中，跳过重复连接")
                return
                
            self.stop_flag.clear()
            self.reconnect_attempts = 0
            self.is_connected = True
            
            while not self.stop_flag.is_set() and self.reconnect_attempts < self.max_reconnect_attempts:
                try:
                    # 使用最简化的连接方式
                    fmts.print_inf(f"尝试连接到: {self.config.websocket_url}")
                    self.ws = await websockets.connect(
                        self.config.websocket_url,
                        ping_interval=None,
                        close_timeout=3,
                        open_timeout=15
                    )
                    
                    self.last_activity = time.time()
                    fmts.print_suc(f"成功连接到服务端: {self.config.server_url}")

                    if self.message_callback:
                        self.message_callback("connected")
                    
                    # 执行注册并检查是否成功
                    registration_success = await self._register_client()
                    if not registration_success:
                        fmts.print_err("注册失败，终止连接")
                        self.is_connected = False
                        break
                    
                    # 启动心跳监控任务
                    asyncio.create_task(self._monitor_connection())
                    
                    # 开始监听消息
                    await self._listen_messages()
                    
                    # 如果正常断开，不再重连
                    if self.stop_flag.is_set():
                        return
                        
                    # 如果连接断开，尝试重新连接
                    if not self.is_connected:
                        fmts.print_war("连接已断开，尝试重新连接...")
                        await asyncio.sleep(1)
                        
                except (asyncio.TimeoutError, websockets.ConnectionClosed) as e:
                    self.reconnect_attempts += 1
                    wait_time = min(2 ** self.reconnect_attempts, 60)
                    fmts.print_war(f"连接断开 ({self.reconnect_attempts}/{self.max_reconnect_attempts}), {wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
                except Exception as e:
                    self.reconnect_attempts += 1
                    fmts.print_err(f"连接异常: {str(e)}")
                    await asyncio.sleep(5)
            
            if not self.stop_flag.is_set():
                fmts.print_err("达到最大重连次数，放弃连接")
            self.is_connected = False

    async def send_message(self, message: Dict[str, Any]) -> None:
        if self.ws and self.is_connected:
            try:
                await self.ws_send(json.dumps(message))
                self.last_activity = time.time()
                if self.message_callback:
                    self.message_callback("sent", message)
            except Exception as e:
                fmts.print_err(f"消息发送失败: {str(e)}")
        else:
            fmts.print_war("WebSocket未连接，无法发送消息")

    async def close(self) -> None:
        self.stop_flag.set()
        if self.ws:
            try:
                # 安全关闭连接
                await self.ws.close()
            except AttributeError:
                # 处理 'ClientConnection' object has no attribute 'close'
                pass
            except Exception as e:
                fmts.print_war(f"关闭连接时出错: {str(e)}")
            finally:
                self.ws = None
        self.is_connected = False
        fmts.print_inf("WebSocket连接已关闭")

    def run_in_thread(self):
        def start_loop():
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self.connect())
            except Exception as e:
                fmts.print_err(f"WebSocket线程错误: {str(e)}")
            finally:
                # 清理资源
                try:
                    tasks = asyncio.all_tasks(loop=self.loop)
                    for task in tasks:
                        task.cancel()
                    self.loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                except:
                    pass
                try:
                    self.loop.close()
                except:
                    pass

        self.thread = threading.Thread(target=start_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()
        # 安全关闭循环
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.close(), self.loop)
        else:
            # 如果循环未运行，直接关闭
            asyncio.run_coroutine_threadsafe(self.close(), asyncio.new_event_loop())
        fmts.print_inf("WebSocket客户端已停止")

class Client:
    def __init__(self, server_url: str = "api.tooldelta.xyz", message_callback: Callable = None):
        self.config = ClientConfig(server_url)
        self.http_client = HTTPClient(self.config)
        self.ws_client = WebSocketClient(self.config, message_callback)
        
    def generate_ids(self) -> None:
        if not self.config.user_id:
            self.config.user_id = self.config.generate_user_id()
            fmts.print_suc(f"用户ID: {self.config.user_id}")
        
        if not self.config.device_fingerprint:
            self.config.device_fingerprint = self.config.generate_device_fingerprint()

    def connect_in_thread(self) -> None:
        self.generate_ids()
        self.ws_client.run_in_thread()

    def stop(self) -> None:
        self.ws_client.stop()

def message_callback(event_type: str, *args):
    try:
        if event_type == "connected":
            fmts.print_suc("已连接到服务端")
        elif event_type == "disconnected":
            fmts.print_war("与服务端的连接已断开")
        elif event_type == "message":
            # 确保消息不是None
            if args and args[0] is not None:
                # 截断长消息
                msg = str(args[0])
                if len(msg) > 200:
                    msg = msg[:200] + "..."
                fmts.print_inf(f"服务端消息: {msg}")
        elif event_type == "sent":
            if args and args[0] is not None:
                # 截断长消息
                msg = str(args[0])
                if len(msg) > 200:
                    msg = msg[:200] + "..."
                fmts.print_inf(f"已发送消息: {msg}")
    except Exception as e:
        fmts.print_err(f"消息回调处理错误: {str(e)}")

class PluginMarketWeb(Plugin):
    name = "PluginMarketWeb"
    author = "ToolDelta"
    version = (0, 1, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.client = None
        self.ListenFrameExit(self.on_disable)
        self.ListenActive(self.on_active)

    def on_active(self):
        try:
            self.client = Client(message_callback=message_callback)
            self.client.connect_in_thread()
            fmts.print_inf("插件市场客户端已启动")
        except Exception as e:
            fmts.print_err(f"客户端启动失败: {str(e)}")

    def on_disable(self):
        if self.client:
            self.client.stop()
            fmts.print_inf("插件市场客户端已停止")

entry = plugin_entry(PluginMarketWeb, "pluginmarket_web")
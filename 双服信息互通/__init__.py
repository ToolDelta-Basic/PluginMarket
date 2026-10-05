# -*- coding: utf-8 -*-
from tooldelta import Plugin, plugin_entry, fmts, cfg, Chat
import requests
import threading
import time


class CrossServerSync(Plugin):
    name = "双服信息互通"
    author = "你困了吗 uvu"
    version = (1, 1, 0)  

    def __init__(self, frame):
        super().__init__(frame)
        
        # 配置加载
        CFG_DEFAULT = {
            "当前服务器名称": "服务器A",
            "目标服务器名称": "服务器B",
            "API地址": "http://你的域名或ip/api.php", 
            "通信密钥": "key123456",      
            "轮询间隔(秒)": 2,
            "受信任管理员": ["你困了吗uvu"]
        }
        CFG_STD = cfg.auto_to_std(CFG_DEFAULT)
        self.config, _ = cfg.get_plugin_config_and_version(self.name, CFG_STD, CFG_DEFAULT, self.version)
        
        self.CURRENT_SERVER = self.config["当前服务器名称"]
        self.TARGET_SERVER = self.config["目标服务器名称"]
        self.API_URL = self.config["API地址"]
        self.SECRET_KEY = self.config["通信密钥"]
        self.POLL_INTERVAL = self.config["轮询间隔(秒)"]
        self.TRUSTED_ADMINS = self.config["受信任管理员"]
        
        self.ListenChat(self.on_chat)
        self.ListenActive(self.on_inject)
        
        threading.Thread(target=self.poll_loop, daemon=True).start()

    def on_chat(self, chat: Chat):
        player_name = chat.player.name
        msg = chat.msg.strip()
        
        if not msg:
            return

        # 跨服查询人数命令
        if msg == ".list":
            # 发送系统查询请求给对服
            self.send_to_api("message", "[SYS_QUERY_PLAYERS]", player_name)
            self.game_ctrl.say_to(player_name, f"§a[跨服] 正在查询 §e{self.TARGET_SERVER} §a的在线情况...")
            return  

        # 拦截跨服命令
        if msg.startswith(".cmd "):
            if player_name in self.TRUSTED_ADMINS:
                cmd_content = msg[5:].strip()
                if cmd_content:
                    self.send_to_api("command", cmd_content, player_name)
                    self.game_ctrl.say_to(player_name, f"§a[跨服] 已向 {self.TARGET_SERVER} 发送命令: §f{cmd_content}")
                return 
            else:
                self.game_ctrl.say_to(player_name, "§c[跨服] 您没有权限发送跨服命令！")
                return

        # 普通聊天消息自动发给目标服
        self.send_to_api("message", msg, player_name)

    def poll_loop(self):
        time.sleep(3) 
        fmts.print_inf(f"[{self.name}] 跨服消息轮询已启动 (间隔 {self.POLL_INTERVAL} 秒)")
        
        while True:
            time.sleep(self.POLL_INTERVAL)
            try:
                data = {
                    "action": "receive",
                    "secret_key": self.SECRET_KEY,
                    "server_name": self.CURRENT_SERVER
                }
                resp = requests.post(self.API_URL, data=data, timeout=3)
                if resp.status_code == 200:
                    res = resp.json()
                    if res.get("success") and res.get("data"):
                        for item in res["data"]:
                            self.handle_received(item)
            except Exception:
                pass 

    def handle_received(self, item):
        #处理从API拉到的每一条数据
        from_server = item["from_server"]
        sender_name = item["sender_name"]
        msg_type = item["type"]
        content = item["content"]
        
        if msg_type == "message":
            # 处理别的服发来的查询请求
            if content == "[SYS_QUERY_PLAYERS]":
                self._handle_query_players(from_server)
                return
            
            # 处理别的服返回的查询结果
            if content.startswith("[SYS_QUERY_RESULT]"):
                real_content = content.replace("[SYS_QUERY_RESULT]", "", 1)
                # 转义双引号防止 JSON 报错
                safe_content = real_content.replace('"', '\\"').replace('\n', ' ')
                cmd = f'tellraw @a {{"rawtext":[{{"text":"{safe_content}"}}]}}'
                self.game_ctrl.sendwocmd(cmd)
                return

            # 使用 tellraw 广播到公屏
            safe_content = content.replace('"', '\\"').replace('\n', ' ')
            safe_sender = sender_name.replace('"', '\\"')
            
            tellraw_text = f"§b丨[{from_server}]§e{safe_sender}§f:{safe_content}"
            cmd = f'tellraw @a {{"rawtext":[{{"text":"{tellraw_text}"}}]}}'
            self.game_ctrl.sendwocmd(cmd)
            
        elif msg_type == "command":
            if sender_name in self.TRUSTED_ADMINS:
                fmts.print_inf(f"[{self.name}] 执行来自 {from_server} ({sender_name}) 的跨服命令: {content}")
                self.game_ctrl.sendwocmd(content)
            else:
                fmts.print_war(f"[{self.name}] 拒绝执行非法跨服命令: {content} (发送者: {sender_name})")

    # ================= 新增：处理人数查询逻辑 =================
    def _handle_query_players(self, from_server):
        """获取本服玩家列表并返回给请求方"""
        try:
            players = self.game_ctrl.players.getAllPlayers()
            count = len(players)
            
            # 提取玩家名字
            if players:
                # 如有需要过滤掉机器人名字
                names = ", ".join([p.name for p in players if p.name != self.game_ctrl.bot_name])
                if not names:
                    names = "无真人在线"
            else:
                names = "无"
                
            result_text = f"§e[{self.CURRENT_SERVER}] §a当前在线人数:§b{count}§e|§a玩家列表:§f{names}"
            
            # 将结果作为消息发回给请求方服务器
            self.send_to_api("message", f"[SYS_QUERY_RESULT]{result_text}", "System")
            fmts.print_inf(f"[{self.name}] 响应了来自 {from_server} 的在线人数查询")
        except Exception as e:
            fmts.print_err(f"[{self.name}] 获取玩家列表失败: {e}")
          
    def send_to_api(self, msg_type, content, sender):
        """异步发送数据到 PHP API"""
        def _send():
            try:
                data = {
                    "action": "send",
                    "secret_key": self.SECRET_KEY,
                    "from_server": self.CURRENT_SERVER,
                    "to_server": self.TARGET_SERVER,
                    "type": msg_type,
                    "content": content,
                    "sender_name": sender
                }
                requests.post(self.API_URL, data=data, timeout=3)
            except Exception as e:
                fmts.print_err(f"[{self.name}] 发送API失败: {e}")
        
        threading.Thread(target=_send, daemon=True).start()


entry = plugin_entry(CrossServerSync)

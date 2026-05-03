import asyncio
import json
import logging
import websockets

# 配置日志输出格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 存储所有连接的客户端详细信息
# 结构：{ websocket: {"channel": "大厅", "server_name": "生存一区", "players": ["Steve", "Alex"]} }
clients = {}


async def handle_client(websocket, _path):
    """处理每个客户端连接及数据路由"""
    try:
        # 握手认证
        auth_msg = await websocket.recv()
        auth_data = json.loads(auth_msg)

        if auth_data.get("type") != "auth":
            logging.warning("非法的连接请求，已拒绝")
            return

        channel = auth_data.get("channel", "default")
        server_name = auth_data.get("server_name", "未知子服")

        clients[websocket] = {
            "channel": channel,
            "server_name": server_name,
            "players": [] # 重点：在此缓存该服务器定时上报的在线玩家名单
        }

        logging.info("🔗 新子服接入: [%s] (%s) | 当前总节点: %d", server_name, channel, len(clients))

        # 智能数据路由
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")
            my_info = clients[websocket]

            # 1. 普通聊天直接全频道广播
            if msg_type == "chat":
                targets = [
                    ws for ws, info in list(clients.items())
                    if info["channel"] == my_info["channel"] and ws != websocket
                ]
                for target_ws in targets:
                    try:
                        await target_ws.send(message)
                    except Exception:
                        pass
                        
            # 2. 接收子服定时上报的状态，并更新缓存
            elif msg_type == "status":
                clients[websocket]["players"] = data.get("players", [])

            # 3. 处理事件（比如前端请求全网名单）
            elif msg_type == "event":
                sub_type = data.get("sub_type")

                # 前端要求后端下发整理好的全网名单
                if sub_type == "request_list":
                    requester = data.get("requester")
                    
                    # 后端瞬间聚合内存中的数据
                    total_players = 0
                    servers_data = {}
                    
                    for ws, info in clients.items():
                        if info["channel"] == my_info["channel"]:
                            p_list = info["players"]
                            servers_data[info["server_name"]] = p_list
                            total_players += len(p_list)
                            
                    # 直接在后端完成排版
                    lines = [f"§e==== 🌐 全网同频道在线: {total_players} 人 ===="]
                    for srv, p_list in servers_data.items():
                        p_str = ", ".join(p_list) if p_list else "§8无人在线"
                        lines.append(f"§7[§b{srv}§7] §a({len(p_list)}人) §f{p_str}")
                        
                    # 把拼接好的文本发回给那个发请求的子服
                    reply_msg = {
                        "type": "event",
                        "sub_type": "reply_list",
                        "target": requester,
                        "content": "\n".join(lines)
                    }
                    try:
                        await websocket.send(json.dumps(reply_msg))
                    except Exception:
                        pass

            # 4. 跨服私聊直接由后端依据缓存进行路由分发
            elif msg_type == "private_msg":
                target = data.get("target")
                sender = data.get("player")
                
                routed = False
                for ws, info in clients.items():
                    # 遍历缓存，如果人在那个服的名单里，就发过去
                    if info["channel"] == my_info["channel"] and target in info["players"]:
                        try:
                            await ws.send(message)
                            routed = True
                            logging.info(f"✉️ 跨服私聊路由: {sender} -> {target} (已投递至 {info['server_name']})")
                        except Exception:
                            pass
                        break
                        
                # 如果翻遍了所有缓存都没这个人，给发送者回个错误提示
                if not routed:
                    error_msg = {
                        "type": "event",
                        "sub_type": "private_msg_error",
                        "target": sender,
                        "msg": f"§c跨服私聊失败: 全网未找到玩家 {target} (可能不在线或拼写有误)。"
                    }
                    try:
                        await websocket.send(json.dumps(error_msg))
                    except Exception:
                        pass

    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logging.error("客户端连接异常: %s", e)
    finally:
        if websocket in clients:
            info = clients[websocket]
            del clients[websocket]
            logging.info("❌ 子服断开: [%s] (%s) | 剩余节点: %d", info["server_name"], info["channel"], len(clients))


async def main():
    """启动 WebSocket 服务器。"""
    host = "0.0.0.0"  # skipcq: BAN-B104
    port = 8765
    logging.info("🚀 互通中转核心已启动 -> ws://%s:%d", host, port)
    logging.info("💡 当前处于【定时上报，后端缓存集中路由】的数据流模式")

    async with websockets.serve(handle_client, host, port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

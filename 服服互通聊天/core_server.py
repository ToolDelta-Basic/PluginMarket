import asyncio
import json
import logging
import websockets

# 配置日志输出格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 存储所有连接的客户端，结构：{websocket_object: "频道名称"}
clients = {}


async def handle_client(websocket, _path):
    """处理每个客户端连接。"""
    try:
        # 第一步：等待客户端发送握手认证消息，获取频道信息
        auth_msg = await websocket.recv()
        auth_data = json.loads(auth_msg)

        if auth_data.get("type") != "auth":
            logging.warning("客户端未发送认证消息，连接断开")
            return

        channel = auth_data.get("channel", "default")
        clients[websocket] = channel
        logging.info(
            "新服务器接入: %s | 绑定频道: [%s] | 当前总连接数: %d",
            websocket.remote_address,
            channel,
            len(clients)
        )

        # 第二步：循环接收消息并分发
        async for message in websocket:
            data = json.loads(message)
            if data.get("type") == "chat":
                # 获取该消息的频道
                msg_channel = clients[websocket]
                server_name = data.get("server")
                player = data.get("player")
                chat_msg = data.get("msg")

                logging.info(
                    "频道 [%s] 收到来自 [%s] %s 的消息: %s",
                    msg_channel,
                    server_name,
                    player,
                    chat_msg
                )

                # 寻找同一频道内的其他所有服务器 (排除发送者自己)
                targets = [
                    ws for ws, ch in clients.items()
                    if ch == msg_channel and ws != websocket
                ]

                # 异步广播消息给目标
                for target_ws in targets:
                    try:
                        await target_ws.send(message)
                    except Exception as e:
                        logging.warning("向节点发送消息失败: %s", e)

    except websockets.exceptions.ConnectionClosed:
        pass  # 正常断开连接
    except Exception as e:
        logging.error("处理客户端连接时发生异常: %s", e)
    finally:
        # 客户端断开连接，清理信息
        if websocket in clients:
            channel = clients[websocket]
            del clients[websocket]
            logging.info(
                "服务器断开连接: %s | 解除频道: [%s] | 剩余连接数: %d",
                websocket.remote_address,
                channel,
                len(clients)
            )


async def main():
    """启动 WebSocket 服务器。"""
    host = "0.0.0.0"  # deepsource ignore: BAN-B104
    port = 8765  # 你可以在这里修改中转服务器开放的端口
    logging.info("🚀 服服互通中转服务器正在启动，监听 ws://%s:%d", host, port)

    # 启动 WebSocket 服务
    async with websockets.serve(handle_client, host, port):
        await asyncio.Future()  # 永久挂起，保持运行


if __name__ == "__main__":
    asyncio.run(main())

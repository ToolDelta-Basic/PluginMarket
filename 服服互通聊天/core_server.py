import asyncio
import json
import logging
import os
import websockets
from aiohttp import web

# 配置日志输出格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 存储所有连接的客户端详细信息
# 结构: { websocket: {"channel": "大厅", "server_name": "一区", "players": []} }
clients = {}

META_FILE = "channels_meta.json"


def load_channels_meta():
    """从本地加载频道鉴权数据防抢注。"""
    if os.path.exists(META_FILE):
        with open(META_FILE, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    return {}


# 存储频道元数据 (类型、密钥)
channels_meta = load_channels_meta()

# 强制锁定官方默认频道，任何人无法抢注更改
channels_meta["全球大厅"] = {"type": "public", "key": ""}


def save_meta():
    """将频道鉴权数据永久保存到本地防抢注。"""
    with open(META_FILE, "w", encoding="utf-8") as file_obj:
        json.dump(channels_meta, file_obj, ensure_ascii=False, indent=4)


# ==================== 🌐 Web UI 模板 ====================
WEB_UI_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>服服互通 - 全网实时监控大屏</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <style>
        [v-cloak] { display: none; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
    </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-800
             selection:bg-blue-200 font-sans">
    <div id="app" v-cloak class="max-w-7xl mx-auto p-4 sm:p-8">

        <!-- 头部 -->
        <header class="flex flex-col sm:flex-row justify-between
                       items-center mb-8 gap-4">
            <div>
                <h1 class="text-3xl font-extrabold text-slate-900
                           tracking-tight flex items-center">
                    <span class="text-blue-600 mr-2">✦</span>
                    跨服互通枢纽
                    <span class="ml-3 px-3 py-1 bg-blue-100 text-blue-700
                                 text-sm rounded-full animate-pulse border
                                 border-blue-200">Active</span>
                </h1>
                <p class="text-slate-500 mt-2 ml-1 text-sm font-medium">
                    Global Network & Authorization Gateway
                </p>
            </div>
            <div class="text-sm font-mono bg-white px-4 py-2 rounded-lg
                        shadow-sm border border-slate-100 text-slate-500">
                Data refreshed {{ lastUpdate }}
            </div>
        </header>

        <!-- 数据总览卡片 -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="bg-white rounded-2xl shadow-sm border border-slate-100
                        p-6 relative overflow-hidden group hover:shadow-md
                        transition-all">
                <div class="absolute -right-4 -top-4 w-24 h-24 bg-blue-50
                            rounded-full group-hover:scale-150 transition-transform
                            duration-500 ease-out z-0"></div>
                <div class="relative z-10">
                    <div class="text-slate-500 text-sm font-semibold mb-1
                                uppercase tracking-wider">活跃频道数</div>
                    <div class="text-4xl font-black text-slate-800">
                        {{ Object.keys(channels).length }}
                    </div>
                </div>
            </div>
            <div class="bg-white rounded-2xl shadow-sm border border-slate-100
                        p-6 relative overflow-hidden group hover:shadow-md
                        transition-all">
                <div class="absolute -right-4 -top-4 w-24 h-24 bg-emerald-50
                            rounded-full group-hover:scale-150 transition-transform
                            duration-500 ease-out z-0"></div>
                <div class="relative z-10">
                    <div class="text-slate-500 text-sm font-semibold mb-1
                                uppercase tracking-wider">在线子服数</div>
                    <div class="text-4xl font-black text-slate-800">
                        {{ totalServers }}
                    </div>
                </div>
            </div>
            <div class="bg-white rounded-2xl shadow-sm border border-slate-100
                        p-6 relative overflow-hidden group hover:shadow-md
                        transition-all">
                <div class="absolute -right-4 -top-4 w-24 h-24 bg-purple-50
                            rounded-full group-hover:scale-150 transition-transform
                            duration-500 ease-out z-0"></div>
                <div class="relative z-10">
                    <div class="text-slate-500 text-sm font-semibold mb-1
                                uppercase tracking-wider">全网在线玩家</div>
                    <div class="text-4xl font-black text-slate-800">
                        {{ totalPlayers }}
                    </div>
                </div>
            </div>
        </div>

        <!-- 个人私密频道排行榜 -->
        <div v-if="topPrivateByServers.length > 0"
             class="mb-10 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-white rounded-2xl shadow-sm border
                        border-slate-200 overflow-hidden">
                <div class="bg-gradient-to-r from-amber-500 to-orange-400
                            px-6 py-4">
                    <h3 class="text-lg font-bold text-white flex items-center
                               shadow-sm">
                        <svg class="w-5 h-5 mr-2" fill="none"
                             stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round"
                                  stroke-width="2"
                                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2
                                     2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2
                                     2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2
                                     0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                        </svg>
                        私密频道 · 子服规模榜
                    </h3>
                </div>
                <ul class="divide-y divide-slate-100">
                    <li v-for="(ch, idx) in topPrivateByServers" :key="ch.name"
                        class="px-6 py-4 flex justify-between items-center
                               hover:bg-slate-50">
                        <div class="flex items-center">
                            <span class="w-6 h-6 rounded-full flex items-center
                                         justify-center text-xs font-bold mr-3"
                                  :class="idx === 0 ? 'bg-yellow-100 text-yellow-700' :
                                          (idx === 1 ? 'bg-slate-200 text-slate-700' :
                                          (idx === 2 ? 'bg-orange-100 text-orange-800' :
                                          'text-slate-400'))">
                                {{ idx + 1 }}
                            </span>
                            <span class="font-medium text-slate-700">
                                {{ ch.name }}
                            </span>
                        </div>
                        <span class="font-bold text-amber-600">
                            {{ ch.serverCount }}
                            <span class="text-xs font-normal text-slate-400">
                                个服务器
                            </span>
                        </span>
                    </li>
                </ul>
            </div>

            <div class="bg-white rounded-2xl shadow-sm border border-slate-200
                        overflow-hidden">
                <div class="bg-gradient-to-r from-indigo-500 to-purple-500
                            px-6 py-4">
                    <h3 class="text-lg font-bold text-white flex items-center
                               shadow-sm">
                        <svg class="w-5 h-5 mr-2" fill="none"
                             stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round"
                                  stroke-width="2"
                                  d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0
                                     0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4
                                     4 0 11-8 0 4 4 0 018 0z"></path>
                        </svg>
                        私密频道 · 在线人数榜
                    </h3>
                </div>
                <ul class="divide-y divide-slate-100">
                    <li v-for="(ch, idx) in topPrivateByPlayers" :key="ch.name"
                        class="px-6 py-4 flex justify-between items-center
                               hover:bg-slate-50">
                        <div class="flex items-center">
                            <span class="w-6 h-6 rounded-full flex items-center
                                         justify-center text-xs font-bold mr-3"
                                  :class="idx === 0 ? 'bg-yellow-100 text-yellow-700' :
                                          (idx === 1 ? 'bg-slate-200 text-slate-700' :
                                          (idx === 2 ? 'bg-orange-100 text-orange-800' :
                                          'text-slate-400'))">
                                {{ idx + 1 }}
                            </span>
                            <span class="font-medium text-slate-700">
                                {{ ch.name }}
                            </span>
                        </div>
                        <span class="font-bold text-indigo-600">
                            {{ ch.playerCount }}
                            <span class="text-xs font-normal text-slate-400">
                                名玩家
                            </span>
                        </span>
                    </li>
                </ul>
            </div>
        </div>

        <!-- 频道及服务器拓扑 -->
        <div v-for="(channelData, channelName) in channels" :key="channelName"
             class="mb-10">
            <div class="flex items-center mb-5">
                <h2 class="text-2xl font-bold text-slate-800 flex items-center">
                    <span class="bg-slate-800 text-white w-8 h-8 rounded-lg flex
                                 items-center justify-center mr-3 text-sm">#</span>
                    {{ channelName }}
                    <span v-if="channelData.meta.type === 'private'"
                          class="ml-3 px-2 py-0.5 bg-amber-100 text-amber-700
                                 text-xs rounded border border-amber-200 flex
                                 items-center font-normal">
                        <svg class="w-3 h-3 mr-1" fill="currentColor"
                             viewBox="0 0 20 20">
                            <path fill-rule="evenodd" clip-rule="evenodd"
                                  d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0
                                     01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7
                                     V7a3 3 0 016 0z"></path>
                        </svg>
                        私密
                    </span>
                    <span v-else
                          class="ml-3 px-2 py-0.5 bg-emerald-100 text-emerald-700
                                 text-xs rounded border border-emerald-200 flex
                                 items-center font-normal">
                        <svg class="w-3 h-3 mr-1" fill="currentColor"
                             viewBox="0 0 20 20">
                            <path d="M10 12a2 2 0 100-4 2 2 0 000 4z"></path>
                            <path fill-rule="evenodd" clip-rule="evenodd"
                                  d="M.458 10C1.732 5.943 5.522 3 10 3s8.268
                                     2.943 9.542 7c-1.274 4.057-5.064 7-9.542
                                     7S1.732 14.057.458 10zM14 10a4 4 0
                                     11-8 0 4 4 0 018 0z"></path>
                        </svg>
                        公开
                    </span>
                </h2>
                <div class="ml-4 h-px bg-slate-200 flex-grow"></div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div v-for="server in channelData.servers"
                     :key="server.server_name"
                     class="bg-white rounded-2xl shadow-sm border
                            border-slate-100 overflow-hidden hover:border-blue-200
                            transition-colors">
                    <div class="bg-slate-50/50 px-6 py-4 border-b border-slate-100
                                flex justify-between items-center">
                        <div class="font-bold text-lg text-slate-800 flex
                                    items-center">
                            <span class="w-2.5 h-2.5 rounded-full mr-3
                                         shadow-[0_0_8px_rgba(34,197,94,0.6)]"
                                  :class="server.player_count > 0 ?
                                          'bg-green-500' : 'bg-slate-300'">
                            </span>
                            {{ server.server_name }}
                        </div>
                        <span class="text-xs text-slate-400 font-mono bg-slate-100
                                     px-2 py-1 rounded">
                            {{ server.ip }}
                        </span>
                    </div>
                    <div class="p-6">
                        <div class="flex justify-between items-end mb-4">
                            <div class="text-sm text-slate-500 font-medium">
                                在线玩家
                            </div>
                            <div class="text-2xl font-bold"
                                 :class="server.player_count > 0 ?
                                         'text-blue-600' : 'text-slate-400'">
                                {{ server.player_count }}
                                <span class="text-sm font-medium text-slate-400">
                                    人
                                </span>
                            </div>
                        </div>

                        <div class="flex flex-wrap gap-2 max-h-32 overflow-y-auto
                                    pr-2">
                            <span v-if="server.player_count === 0"
                                  class="text-slate-400 text-sm italic py-1">
                                💤 当前服务器无人在线
                            </span>
                            <span v-for="player in server.players" :key="player"
                                  class="bg-blue-50 text-blue-700 text-sm
                                         font-medium px-3 py-1.5 rounded-md border
                                         border-blue-100 flex items-center">
                                <svg class="w-3.5 h-3.5 mr-1.5 opacity-70"
                                     fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" clip-rule="evenodd"
                                          d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7
                                             9a7 7 0 1114 0H3z"></path>
                                </svg>
                                {{ player }}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div v-if="Object.keys(channels).length === 0"
             class="text-center text-slate-400 mt-20 p-10 border-2 border-dashed
                    border-slate-200 rounded-2xl">
            <svg class="mx-auto h-12 w-12 text-slate-300 mb-4" fill="none"
                 viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round"
                      stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <h3 class="text-lg font-medium text-slate-900 mb-1">网络空闲</h3>
            <p>目前没有连接到中转枢纽的子服务器。</p>
        </div>

        <footer class="mt-16 pt-8 border-t border-slate-200 text-center text-sm
                       text-slate-400 pb-8">
            Driven by ToolDelta Cross-Server Hub & Vue.js
        </footer>
    </div>

    <script>
        const { createApp, ref, computed, onMounted } = Vue

        createApp({
            setup() {
                const channels = ref({})
                const lastUpdate = ref('00:00:00')

                const totalServers = computed(() => {
                    let count = 0
                    for (const key in channels.value) {
                        count += channels.value[key].servers.length
                    }
                    return count
                })

                const totalPlayers = computed(() => {
                    let count = 0
                    for (const key in channels.value) {
                        channels.value[key].servers.forEach(s => {
                            count += s.player_count
                        })
                    }
                    return count
                })

                const topPrivateByServers = computed(() => {
                    const privates = Object.entries(channels.value)
                        .filter(([_, data]) => data.meta.type === 'private')
                        .map(([name, data]) => ({
                            name,
                            serverCount: data.servers.length
                        }));
                    return privates.sort(
                        (a, b) => b.serverCount - a.serverCount
                    ).slice(0, 5);
                });

                const topPrivateByPlayers = computed(() => {
                    const privates = Object.entries(channels.value)
                        .filter(([_, data]) => data.meta.type === 'private')
                        .map(([name, data]) => ({
                            name,
                            playerCount: data.servers.reduce(
                                (sum, s) => sum + s.player_count, 0
                            )
                        }));
                    return privates.sort(
                        (a, b) => b.playerCount - a.playerCount
                    ).slice(0, 5);
                });

                const fetchData = async () => {
                    try {
                        const res = await fetch('/api/status')
                        const data = await res.json()
                        channels.value = data

                        const now = new Date()
                        const timeStr = now.toLocaleTimeString(
                            'en-US', { hour12: false }
                        )
                        const msStr = now.getMilliseconds().toString()
                                         .padStart(3, '0').slice(0,1)
                        lastUpdate.value = `${timeStr}.${msStr}`
                    } catch (e) {
                        console.error("Fetch API error:", e)
                    }
                }

                onMounted(() => {
                    fetchData()
                    setInterval(fetchData, 1500)
                })

                return {
                    channels, totalServers, totalPlayers,
                    topPrivateByServers, topPrivateByPlayers, lastUpdate
                }
            }
        }).mount('#app')
    </script>
</body>
</html>
"""


async def web_index(_request):
    """处理 WebUI 首页请求。"""
    return web.Response(text=WEB_UI_HTML, content_type="text/html", charset="utf-8")


async def web_status_api(_request):
    """处理 WebUI 数据获取 API。"""
    data = {}
    for ws, info in clients.items():
        chan = info["channel"]
        srv = info["server_name"]
        players = info["players"]

        ip_addr = "未知 IP"
        if ws.remote_address:
            ip_addr = f"{ws.remote_address[0]}:{ws.remote_address[1]}"

        if chan not in data:
            meta = channels_meta.get(chan, {"type": "public"})
            data[chan] = {
                "meta": {"type": meta["type"]},
                "servers": []
            }

        data[chan]["servers"].append({
            "server_name": srv,
            "player_count": len(players),
            "players": players,
            "ip": ip_addr
        })

    return web.json_response(data)


async def start_web_server(host, port):
    """启动独立运行在同一事件循环内的 Web 服务。"""
    app = web.Application()
    app.router.add_get("/", web_index)
    app.router.add_get("/api/status", web_status_api)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logging.info("🌐 WebUI 管理大屏已就绪，请在浏览器访问 http://%s:%d", host, port)


async def handle_client(websocket, _path):  # skipcq: PY-R1000
    """处理每个客户端连接及数据路由。"""
    try:
        auth_msg = await websocket.recv()
        auth_data = json.loads(auth_msg)

        if auth_data.get("type") != "auth":
            logging.warning("非法的连接请求，已拒绝")
            return

        channel = auth_data.get("channel", "default")
        server_name = auth_data.get("server_name", "未知子服")
        c_type = "private" if auth_data.get("channel_type") == "私密" else "public"
        c_key = auth_data.get("channel_key", "")

        # ================= 权限校验模块 =================
        if channel in channels_meta:
            meta = channels_meta[channel]
            if meta["type"] == "private" and meta["key"] != c_key:
                reject_msg = {"type": "auth_fail", "msg": "该频道为私密频道，密钥错误！"}
                await websocket.send(json.dumps(reject_msg))
                logging.warning(
                    "拒绝接入: %s 尝试连接私密频道 [%s] 密码错误 (%s)",
                    server_name, channel, websocket.remote_address
                )
                return
        else:
            # 若是第一个连接的，则永久注册该频道并保存元数据
            channels_meta[channel] = {"type": c_type, "key": c_key}
            save_meta()
            logging.info("⭐ 新频道永久注册: [%s] (类型: %s)", channel, c_type)

        # 告诉前端验证成功
        await websocket.send(json.dumps({"type": "auth_success"}))

        clients[websocket] = {
            "channel": channel,
            "server_name": server_name,
            "players": []
        }

        logging.info(
            "🔗 新子服接入: [%s] (%s) | 当前总节点: %d",
            server_name, channel, len(clients)
        )

        # 智能数据路由
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")
            my_info = clients[websocket]

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

            elif msg_type == "status":
                clients[websocket]["players"] = data.get("players", [])

            elif msg_type == "event":
                sub_type = data.get("sub_type")

                if sub_type == "request_list":
                    requester = data.get("requester")
                    total_players = 0
                    servers_data = {}

                    for ws, info in clients.items():
                        if info["channel"] == my_info["channel"]:
                            p_list = info["players"]
                            servers_data[info["server_name"]] = p_list
                            total_players += len(p_list)

                    lines = [f"§e==== 🌐 全网同频道在线: {total_players} 人 ===="]
                    for srv, p_list in servers_data.items():
                        p_str = ", ".join(p_list) if p_list else "§8无人在线"
                        lines.append(f"§7[§b{srv}§7] §a({len(p_list)}人) §f{p_str}")

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

            elif msg_type == "private_msg":
                target = data.get("target")
                sender = data.get("player")

                routed = False
                for ws, info in clients.items():
                    is_same_channel = info["channel"] == my_info["channel"]
                    if is_same_channel and target in info["players"]:
                        try:
                            await ws.send(message)
                            routed = True
                            logging.info(
                                "✉️ 跨服私聊路由: %s -> %s (投递至 %s)",
                                sender, target, info["server_name"]
                            )
                        except Exception:
                            pass
                        break

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
        # 断开清理逻辑
        if websocket in clients:
            info = clients[websocket]
            chan = info["channel"]
            del clients[websocket]
            logging.info(
                "❌ 子服断开: [%s] (%s) | 剩余节点: %d",
                info["server_name"], chan, len(clients)
            )


async def main():
    """启动 WebSocket 服务器与 Web 监控页面。"""
    host = "0.0.0.0"  # skipcq: BAN-B104
    ws_port = 8765
    web_port = 8766

    logging.info("🚀 互通中转核心鉴权网关已启动")

    await start_web_server(host, web_port)

    logging.info("🕹️  跨服 WS 网关正在监听 ws://%s:%d", host, ws_port)
    async with websockets.serve(handle_client, host, ws_port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

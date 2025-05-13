import zlib
import asyncio
from tooldelta import fmts, utils
from websockets.legacy.client import WebSocketClientProtocol as WS
from websockets.legacy.client import Connect as WSconnect
from websockets.exceptions import ConnectionClosed
from tooldelta.utils.tooldelta_thread import ThreadExit
from asyncio.exceptions import CancelledError


async def forward_between(ws1: WS, ws2: WS):
    async def forward(src: WS, dst: WS, zip = False, unzip = False):
        try:
            while True:
                if zip:
                    msg = await src.recv()
                    msg = zlib.compress(msg.encode("utf-8"), level = 3) # type: ignore
                    await dst.send(msg)
                elif unzip:
                    msg = await src.recv()
                    msg = zlib.decompress(msg).decode("utf-8") # type: ignore
                    await dst.send(msg)
                else:
                    msg = await src.recv()
                    await dst.send(msg)
        except ConnectionClosed as exc:
            # fmts.print_inf(f"forward data failed: Disconnected.")
            return
        except Exception as exc:
            fmts.print_err(f"forward data failed: {exc}")
            asyncio.create_task(src.close())
        finally:
            if src in conn_list:
                conn_list.remove(src)

    asyncio.create_task(
        forward(ws1, ws2, zip = True)
    )
    asyncio.create_task(
        forward(ws2, ws1, unzip = True)
    )


conn_list: list[WS] = []
async def handle_control(ws: WS, UUID, HOST):
    while True:
        msg: str = await ws.recv()  # type: ignore
        if msg.startswith("CHANNEL:"):
            channel_id = msg.split(":", 1)[1]
            fmts.print_inf(f"New session {channel_id} connected.")
            local_ws = WSconnect("ws://localhost:7912/ws")
            channel_ws = WSconnect(f"wss://{HOST}/ws-channel/{UUID}/{channel_id}")
            try:
                local_ws = await local_ws
                conn_list.append(local_ws)
                channel_ws = await channel_ws
                conn_list.append(channel_ws)
            except Exception as exc:
                fmts.print_err(f"Session {channel_id} conn failed: {exc}")
                if isinstance(local_ws, WS):
                    conn_list.remove(local_ws)
                    asyncio.create_task(local_ws.close())
                if isinstance(channel_ws, WS):
                    conn_list.remove(channel_ws)
                    asyncio.create_task(channel_ws.close())
                continue
            asyncio.create_task(forward_between(local_ws, channel_ws))
        elif msg.startswith("HEARTBEAT:"):
            continue
        else:
            asyncio.create_task(ws.close())
            raise Exception(f"Unknown message {msg}")


async def main(UUID, HOST):
    while True:
        try:
            fmts.print_inf(f"Registering {UUID} to {HOST}...", flush = True)
            async with WSconnect(f"wss://{HOST}/register/{UUID}") as ws:
                fmts.print_suc("Registered.")
                await handle_control(ws, UUID, HOST)
        except (ThreadExit, CancelledError):
            return
        except Exception as exc:
            fmts.print_err(f"Forwarder error: {exc}")
            await asyncio.sleep(5)


@utils.thread_func("WebSocket Forwarder")
def launch(UUID, HOST):
    asyncio.run(main(UUID, HOST))


def exit():
    for ws in conn_list:
        try:
            asyncio.create_task(ws.close())
        except:
            pass
    conn_list.clear()

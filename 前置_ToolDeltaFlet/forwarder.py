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
async def handle_control(ws: WS, UUID, HOST, PORT):
    while True:
        msg: str = await ws.recv()  # type: ignore
        if msg.startswith("CHANNEL:"):
            channel_id = msg.split(":", 1)[1]
            fmts.print_inf(f"New session {channel_id} connected.")
            local_ws = None
            channel_ws = None
            try:
                local_ws = await WSconnect(f"ws://localhost:{PORT}/ws")
                conn_list.append(local_ws)
            except Exception as exc:
                fmts.print_err(f"Session {channel_id} conn failed: {exc}")
                raise ThreadExit
            try:
                channel_ws = await WSconnect(f"wss://{HOST}/ws-channel/{UUID}/{channel_id}")
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
            counter = int(msg.split(":", 1)[1])
            if counter == 1:
                fmts.print_suc("Register succeeded.")
            continue
        else:
            asyncio.create_task(ws.close())
            raise Exception(f"Unknown message {msg}")


async def main(UUID, HOST, PORT):
    while True:
        try:
            fmts.print_inf(f"Register {UUID} to {HOST}...", flush = True)
            async with WSconnect(f"wss://{HOST}/register/{UUID}") as ws:
                await handle_control(ws, UUID, HOST, PORT)
        except (ThreadExit, CancelledError):
            return
        except ConnectionClosed as exc:
            fmts.print_err(f"{exc.reason if exc.reason else 'Forwarder error: disconnected'} (code {exc.code})\nRetry in 2s")
            await asyncio.sleep(2)
        except Exception as exc:
            fmts.print_err(f"Forwarder error: {exc}\nRetry in 2s")
            await asyncio.sleep(2)


@utils.thread_func("WebSocket Forwarder")
def launch(UUID, HOST, PORT):
    asyncio.run(main(UUID, HOST, PORT))


def exit():
    for ws in conn_list:
        try:
            asyncio.create_task(ws.close())
        except:
            pass
    conn_list.clear()

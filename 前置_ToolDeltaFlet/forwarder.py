import zlib
import asyncio
from tooldelta import fmts, utils
from websockets.legacy.client import WebSocketClientProtocol as WebSocket
from websockets.legacy.client import Connect
from websockets.exceptions import ConnectionClosed
from tooldelta.utils.tooldelta_thread import ThreadExit
from asyncio.exceptions import CancelledError


async def forward_between(local_endpoint: WebSocket, server_session_conn: Connect):
    try:
        server_session = await server_session_conn
        conn_list.append(server_session)
        del server_session_conn
    except Exception as exc:
        fmts.print_err(f"Session conn failed: {exc}")
        conn_list.remove(local_endpoint)
        asyncio.create_task(local_endpoint.close())
        return

    async def forward(src: WebSocket, dst: WebSocket, zip = False, unzip = False):
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
            await src.close()
            await dst.close()
        except Exception as exc:
            fmts.print_err(f"forward data failed: {exc}")
            await src.close()
            await dst.close()
        finally:
            if src in conn_list:
                conn_list.remove(src)
            if dst in conn_list:
                conn_list.remove(dst)

    await asyncio.gather(
        forward(local_endpoint, server_session, zip = True),
        forward(server_session, local_endpoint, unzip = True)
    )


conn_list: list[WebSocket] = []
async def process_register(server_register: WebSocket, UUID, HOST, PORT):
    while True:
        message: str = await server_register.recv()  # type: ignore

        if message.startswith("CHANNEL:"):
            session_id = message.split(":", 1)[1]
            fmts.print_inf(f"New session {session_id} connected.")
            local_endpoint = None
            try:
                local_endpoint = await Connect(f"ws://localhost:{PORT}/ws")
                conn_list.append(local_endpoint)
            except Exception as exc:
                fmts.print_err(f"Session {session_id} conn failed: {exc}")
                raise ThreadExit
            server_session = Connect(f"wss://{HOST}/ws-channel/{UUID}/{session_id}")
            asyncio.create_task(forward_between(local_endpoint, server_session))

        elif message.startswith("HEARTBEAT:"):
            counter = int(message.split(":", 1)[1])
            if counter == 1:
                fmts.print_suc("Register succeeded.")
            continue

        else:
            asyncio.create_task(server_register.close())
            raise Exception(f"Unknown message {message}")


async def main(UUID, HOST, PORT):
    while True:
        try:
            fmts.print_inf(f"Register {UUID} to {HOST}...", flush = True)
            async with Connect(f"wss://{HOST}/register/{UUID}") as server_register:
                await process_register(server_register, UUID, HOST, PORT)
        except (ThreadExit, CancelledError):
            exit()
            return
        except ConnectionClosed as exc:
            fmts.print_err(f"{exc.reason if exc.reason else 'Forwarder error: disconnected'} (code {exc.code})\nRetry in 3s")
            await asyncio.sleep(3)
        except Exception as exc:
            fmts.print_err(f"Forwarder error: {exc}\nRetry in 3s")
            await asyncio.sleep(3)


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

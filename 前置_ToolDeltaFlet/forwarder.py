import time
import zlib
import asyncio
import threading
from types import CoroutineType
from asyncio.exceptions import CancelledError
from websockets.legacy.client import WebSocketClientProtocol as WebSocket
from websockets.legacy.client import Connect
from websockets.exceptions import ConnectionClosed
from tooldelta.utils.tooldelta_thread import ThreadExit
from tooldelta import fmts, utils


bg_task_list: set[asyncio.Task] = set()
def create_task(coro: CoroutineType) -> asyncio.Task:
    task = asyncio.create_task(coro)
    bg_task_list.add(task)
    task.add_done_callback(bg_task_list.discard)
    return task


async def forward_between(
    local_endpoint: WebSocket, server_session_conn: Connect
) -> None:
    try:
        server_session = await server_session_conn
        conn_list.append(server_session)
        del server_session_conn
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        fmts.print_err(f"Session conn failed: {exc}")
        conn_list.remove(local_endpoint)
        create_task(local_endpoint.close())
        return

    async def forward(
        src: WebSocket, dst: WebSocket,
        zip_data: bool = False, unzip_data: bool = False
    ) -> None:
        try:
            while True:
                if zip_data:
                    msg = await src.recv()
                    msg = zlib.compress(msg.encode("utf-8"), level = 3) # type:ignore  # noqa:PGH003
                    await dst.send(msg)
                elif unzip_data:
                    msg = await src.recv()
                    msg = zlib.decompress(msg).decode("utf-8")  # type: ignore  # noqa: PGH003
                    await dst.send(msg)
                else:
                    msg = await src.recv()
                    await dst.send(msg)
        except ConnectionClosed:
            await src.close()
            await dst.close()
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            fmts.print_err(f"forward data failed: {exc}")
            await src.close()
            await dst.close()
        finally:
            if src in conn_list:
                conn_list.remove(src)
            if dst in conn_list:
                conn_list.remove(dst)

    await asyncio.gather(
        forward(local_endpoint, server_session, zip_data = True),
        forward(server_session, local_endpoint, unzip_data = True)
    )


conn_list: list[WebSocket] = []
exit_event = threading.Event()
async def process_register(
    server_register: WebSocket, UUID: str,
    HOST: str, PORT: int, evt: threading.Event
) -> None:
    while True:
        message: str = await server_register.recv()  # type: ignore  # noqa: PGH003

        if evt.is_set():
            raise ThreadExit

        if message.startswith("CHANNEL:"):
            session_id = message.split(":", 1)[1]
            fmts.print_inf(f"New session {session_id} connected.")
            local_endpoint = None
            try:
                local_endpoint = await Connect(f"ws://localhost:{PORT}/ws")
                conn_list.append(local_endpoint)
            except Exception as exc:
                fmts.print_err(f"Session {session_id} conn failed: {exc}")
                raise ThreadExit from exc
            server_session = Connect(f"wss://{HOST}/ws-channel/{UUID}/{session_id}")
            create_task(forward_between(local_endpoint, server_session))

        elif message.startswith("HEARTBEAT:"):
            counter = int(message.split(":", 1)[1])
            if counter == 1:
                fmts.print_suc("Register succeeded.")
            continue

        else:
            create_task(server_register.close())
            raise ValueError(f"Unknown message {message}")


async def main(UUID: str, HOST: str, PORT: int, evt: threading.Event) -> None:
    while True:
        try:
            fmts.print_inf(f"Register {UUID} to {HOST}...", flush = True)
            async with Connect(f"wss://{HOST}/register/{UUID}") as server_register:
                await process_register(server_register, UUID, HOST, PORT, evt)
        except (ThreadExit, CancelledError):
            for conn in conn_list:
                create_task(conn.close())
            conn_list.clear()
            break
        except ConnectionClosed as exc:
            fmts.print_err(
                f"{exc.reason if exc.reason else 'Forwarder error: disconnected'} "
                F"(code {exc.code})\nRetry in 3s"
            )
            await asyncio.sleep(3)
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            fmts.print_err(f"Forwarder error: {exc}\nRetry in 3s")
            await asyncio.sleep(3)


@utils.thread_func("WebSocket Forwarder")
def launch(UUID: str, HOST: str, PORT: int) -> None:
    try:
        asyncio.run(main(UUID, HOST, PORT, exit_event))
    except RuntimeError as exc:
        fmts.print_err(f"Forwarder error: {exc}")


def close() -> None:
    exit_event.set()
    fmts.print_with_info("断开全部 WebSocket 连接...", info = "§f  WS  §f")
    while bg_task_list:
        time.sleep(0.2)
    fmts.print_with_info("全部 WebSocket 连接断开.", info = "§f  WS  §f")

"""Authenticated loopback transport shared by MCP and human CLI clients."""

import hmac
import json
import os
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class LoopbackServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, dispatch):
        self.dispatch = dispatch
        self.secret = secrets.token_urlsafe(32)
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", 0), Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            request.settimeout(10)
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def publish(self, path: Path):
        connection = {"url": f"http://127.0.0.1:{self.server_port}/rpc", "token": self.secret}
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temp = Path(handle.name)
            try:
                json.dump(connection, handle)
                handle.flush()
            except BaseException:
                handle.close()
                temp.unlink(missing_ok=True)
                raise
        try:
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def unpublish(self, path: Path):
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("token") == self.secret:
                path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


class Handler(BaseHTTPRequestHandler):
    server: LoopbackServer

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path != "/rpc":
            self.reply(404, error="未知路径")
            return
        authorization = self.headers.get("Authorization", "")
        if self.headers.get("Origin") or not hmac.compare_digest(
            authorization.encode(), ("Bearer " + self.server.secret).encode()
        ):
            self.reply(403, error="认证失败")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 128 * 1024:
                self.reply(413, error="请求体长度无效")
                return
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("请求体应为 JSON 对象")
            result = self.server.dispatch(data)
            self.reply(200, result=result)
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
            self.reply(200, error=str(exc), code=-32602)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            self.close_connection = True
        except Exception as exc:
            self.reply(200, error=f"工具执行失败：{type(exc).__name__}: {exc}", code=-32603)

    def reply(self, status, result=None, error=None, code=None):
        data = {"result": result} if error is None else {
            "error": {"code": code or status, "message": error}}
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

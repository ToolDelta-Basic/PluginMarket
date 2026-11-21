import inspect
import threading
from functools import partial
from pathlib import Path
from uuid import uuid4

from tooldelta import Plugin, cfg, plugin_entry
from tooldelta.utils.fmts.logger import rich_handler

from .catalog import TOOLS, Documents, validate
from .code_runner import execute_code
from .game_api import GameAPI
from .records import Capture, Stream, history
from .transport import LoopbackServer


class GameBridge(Plugin):
    name = "ToolDelta-MCP"
    author = "ToolDelta"
    version = (0, 1, 0)
    description = "让本机 MCP 客户端读取游戏事件、执行指令和游戏自动化代码。"

    def __init__(self, frame):
        super().__init__(frame)
        config, _ = self.get_config_and_version(
            {"控制台允许的触发词": cfg.JsonList(str), "开发文档目录": str,
             "禁用工具": cfg.JsonList(str), "开放指令通道": cfg.JsonList(str)},
            {"控制台允许的触发词": ["?", "help", "list", "reload"],
             "禁用工具": [], "开放指令通道": ["ws", "player", "ai", "wo", "console"],
             "开发文档目录": "../ToolDelta-Wiki/docs/plugin-dev"},
        )
        self.console_allow = config["控制台允许的触发词"]
        self.channels = set(config["开放指令通道"])
        self.tools = [t for t in TOOLS if t["name"] not in config["禁用工具"]]
        self.enabled = {t["name"] for t in self.tools}
        self.docs = Documents(Path(config["开发文档目录"]))
        self.server = None
        self.closed = False
        self.game_ready = False
        self.api = GameAPI(self)
        self._new_session()
        self.capture = Capture(self.logs)
        self.api.register_events(self.emit)
        self.functions = {
            "status": self.status, "players_list": self.api.players_list,
            "game_command": self.game_command, "console_list": self.api.console_list,
            "bot_chat": self.api.bot_chat, "logs_read": self.logs_read,
            "events_read": self.events_read, "events_wait": self.events_wait,
            "docs_get": self.docs.get, "docs_search": self.docs.search,
            "execute_code": self.run_code,
        }
        self.ListenPreload(self.start)
        self.ListenActive(self.active)
        self.ListenFrameExit(self.close)

    def _new_session(self):
        self.session = uuid4().hex
        self.logs = Stream(self.session, 2048)
        self.events = Stream(self.session, 2048)

    def start(self):
        if self.server is not None:
            return
        rich_handler.addFilter(self.capture)
        try:
            server = LoopbackServer(self.dispatch)
            try:
                server.publish(self.data_path / "connection.json")
                threading.Thread(target=server.serve_forever, daemon=True,
                                 name="ToolDelta MCP loopback").start()
            except BaseException:
                server.unpublish(self.data_path / "connection.json")
                server.server_close()
                raise
            self.server = server
        except BaseException:
            rich_handler.removeFilter(self.capture)
            raise
        self.emit("bridge.started", {})
        self.print_suc("本机游戏桥已就绪，等待游戏连接")

    def active(self):
        if self.game_ready:
            self.logs.close()
            self.events.close()
            self._new_session()
            self.capture.stream = self.logs
        self.game_ready = True
        self.emit("game.connected", {})

    def close(self, event):
        self.closed = True
        self.game_ready = False
        self.emit("bridge.closed", {"reason": str(event.reason)})
        self.events.close()
        self.logs.close()
        rich_handler.removeFilter(self.capture)
        if self.server:
            self.server.unpublish(self.data_path / "connection.json")
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def emit(self, kind, data):
        self.events.append({"kind": kind, "data": data})

    def status(self):
        game = self.api.status()
        game["bot_chat"]["enabled"] = "bot_chat" in self.enabled
        for name, channel in game["command_channels"].items():
            channel["enabled"] = "game_command" in self.enabled and name in self.channels
        return {**game, "session": self.session, "tools": sorted(self.enabled),
                "log_cursor": self.logs.cursor, "event_cursor": self.events.cursor,
                "wiki_pages": sum(k.startswith("wiki/") for k in self.docs.pages)}

    def game_command(self, command, channel="ws", wait=True, timeout=5, include_raw=False):
        if channel not in self.channels:
            raise ValueError("该指令通道已在插件配置中禁用")
        session, cursor = self.session, self.logs.cursor
        result = self.api.game_command(command, channel, wait, timeout, include_raw)
        if channel == "console":
            result["observe_logs"] = {"after": cursor, "session": session}
        return result

    def logs_read(self, after=None, limit=50, session="", contains="", date="",
                  level="", timeout=0):
        if date:
            if timeout:
                raise ValueError("历史日志不支持等待，请对实时流使用 timeout")
            return history(Path("日志文件"), date, after, limit, level, contains, session)
        return self.logs.read(after, limit, session, timeout, level=level, contains=contains)

    def events_read(self, after=None, limit=50, session="", kind="", contains=""):
        return self.events.read(after, limit, session, kind=kind, contains=contains)

    def events_wait(self, after=None, limit=50, session="", kind="", contains="", timeout=10):
        return self.events.read(after, limit, session, timeout, kind, contains=contains, future=True)

    def run_code(self, code):
        # Script calls share validation and session checks with single MCP tool calls.
        script_session = self.session
        api = {
            name: partial(self.call_script_tool, script_session, name)
            for name in self.enabled if name != "execute_code"
        }
        return execute_code(code, api)

    def call_script_tool(self, script_session, name, /, *args, **kwargs):
        if script_session != self.session:
            raise ValueError("游戏会话已更换，代码执行已结束")
        bound = inspect.signature(self.functions[name]).bind(*args, **kwargs)
        return self.call(name, bound.arguments)

    def call(self, name, args):
        if self.closed:
            raise ValueError("桥会话已结束，请重连")
        if name not in self.enabled:
            raise ValueError("未知或已禁用的工具 " + name)
        validate(name, args)
        return self.functions[name](**args)

    def dispatch(self, request):
        method = request.get("method")
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "tools/call":
            params = request.get("params")
            if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                raise ValueError("tools/call 需要工具名称")
            return self.call(params["name"], params.get("arguments", {}))
        raise ValueError("未知桥请求")


entry = plugin_entry(GameBridge)

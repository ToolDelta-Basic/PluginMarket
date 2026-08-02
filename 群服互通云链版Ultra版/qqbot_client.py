"""QQ 官方机器人 HTTP 与网关客户端。"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class QQBotHTTPError(RuntimeError):
    """保留 QQ 官方接口 HTTP 状态码和响应正文。"""

    def __init__(self, status_code, detail):
        self.status_code = int(status_code)
        self.detail = str(detail)
        super().__init__(f"HTTP {self.status_code}: {self.detail}")


class QQBotConnectionError(RuntimeError):
    """携带稳定官机错误码的连接阶段异常。"""

    def __init__(self, error_code, message, details=None):
        self.error_code = str(error_code)
        self.message = str(message)
        self.details = [str(item) for item in (details or [])]
        super().__init__(f"[{self.error_code}] {self.message}")


class QQBotClient:
    """负责 QQ 官方机器人的鉴权、消息发送和网关事件接收。"""

    TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"  # nosec B105
    API_BASE = "https://api.sgroup.qq.com"

    def __init__(
        self,
        app_id,
        client_secret,
        openid_map=None,
        group_ids=None,
        log_cb=None,
        websocket_module=None,
        error_cb=None,
    ):
        self._app_id = app_id
        self._client_secret = client_secret
        self._openid_map = openid_map or {}
        self._group_ids = [int(group_id) for group_id in (group_ids or [])]
        self._log = log_cb or (lambda _msg: None)
        self._error_cb = error_cb
        self._websocket_module = websocket_module
        self._token = None
        self._token_expire = 0.0
        self._lock = threading.Lock()
        self._ws = None
        self._ws_active = False
        self._ws_available = False
        self._ws_session_id = 0
        self._ws_heartbeat_done = None
        self.on_group_message = None
        self.on_openid_discovered = None

    def _report_error(self, error_code, message, details=None):
        "通过错误回调或日志输出带稳定错误码的官机异常。"
        details = [str(item) for item in (details or [])]
        if self._error_cb is not None:
            try:
                self._error_cb(str(error_code), str(message), details)
                return
            except Exception as callback_error:
                self._log(f"官机错误回调异常: {callback_error}")
        summary = " | ".join(
            [f"错误码: {error_code}", str(message), *details])
        self._log(summary)

    @property
    def api_base(self):
        '''返回 QQ 官方机器人开放平台 API 根地址。'''
        return self.API_BASE

    @staticmethod
    def _validate_https_url(url):
        '''Validate and return an HTTPS-only QQ Bot API URL.'''
        url = str(url).strip()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValueError("QQ 官方机器人 HTTP 请求仅允许使用 HTTPS URL")
        return url

    def _http_post(self, url, body, headers=None):
        '''向官机接口发送 JSON POST 请求并解析 JSON 响应。'''
        url = self._validate_https_url(url)
        headers = dict(headers or {})
        headers.setdefault("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(  # nosec B310
                    request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise QQBotHTTPError(error.code, detail) from error

    def _http_get(self, url, headers=None):
        '''向官机接口发送 GET 请求并解析 JSON 响应。'''
        url = self._validate_https_url(url)
        request = urllib.request.Request(
            url, headers=dict(headers or {}), method="GET")
        try:
            with urllib.request.urlopen(  # nosec B310
                    request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise QQBotHTTPError(error.code, detail) from error

    def _get_token(self):
        '''获取并缓存 QQ 官方机器人 AccessToken。'''
        with self._lock:
            if self._token and time.time() < self._token_expire - 60:
                return self._token
            try:
                response = self._http_post(
                    self.TOKEN_URL,
                    {"appId": self._app_id, "clientSecret": self._client_secret},
                )
            except QQBotHTTPError as error:
                raise QQBotConnectionError(
                    "QQBOT-1101",
                    "获取官机 AccessToken 的 HTTP 请求失败",
                    [
                        f"HTTP 状态码: {error.status_code}",
                        f"响应内容: {error.detail}",
                    ],
                ) from error
            except Exception as error:
                raise QQBotConnectionError(
                    "QQBOT-1103",
                    "获取官机 AccessToken 时发生网络异常",
                    [
                        f"异常类型: {type(error).__name__}",
                        f"异常信息: {error}",
                    ],
                ) from error
            if "access_token" not in response:
                details = []
                if response.get("code") is not None:
                    details.append(f"平台错误码: {response.get('code')}")
                platform_message = response.get("message") or response.get("msg")
                if platform_message:
                    details.append(f"平台提示: {platform_message}")
                details.append(f"原始响应: {response}")
                raise QQBotConnectionError(
                    "QQBOT-1102",
                    "官机 AccessToken 响应缺少 access_token",
                    details,
                )
            self._token = response["access_token"]
            self._token_expire = time.time() + int(
                response.get("expires_in", 7200))
            return self._token

    def _auth_headers(self):
        '''构造包含当前 AccessToken 的官机 API 请求头。'''
        return {
            "Authorization": f"QQBot {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _get_group_openid(self, group_id):
        '''获取群号对应的官方群 OpenID，未绑定时保留原值。'''
        return self._openid_map.get(str(group_id), str(group_id))

    def replace_openid_map(self, openid_map):
        '''使用群号到官方群 OpenID 的最新映射替换当前缓存。'''
        self._openid_map = dict(openid_map)

    def send_group_msg(self, group_id, message):
        '''向指定群聊发送一条 QQ 官方机器人文本消息。'''
        openid = self._get_group_openid(group_id)
        url = f"{self.api_base}/v2/groups/{openid}/messages"
        try:
            return self._http_post(
                url,
                {"content": message, "msg_type": 0},
                self._auth_headers(),
            )
        except RuntimeError as error:
            raise RuntimeError(
                f"openid={openid}(群{group_id}) | {error}") from error

    def send_private_msg(self, user_openid, message):
        '''向指定用户 OpenID 发送一条官机私聊文本消息。'''
        url = f"{self.api_base}/v2/users/{user_openid}/messages"
        return self._http_post(
            url,
            {"content": message, "msg_type": 0},
            self._auth_headers(),
        )

    def _fetch_gateway_url(self):
        '''获取官机网关地址，并把平台错误转换为状态码输出。'''
        try:
            response = self._http_get(
                f"{self.api_base}/gateway/bot", self._auth_headers())
            url = response.get("url", "")
            if not url:
                details = []
                if response.get("code") is not None:
                    details.append(f"平台错误码: {response.get('code')}")
                details.extend([
                    f"原始响应: {response}",
                    "30 秒后尝试重连",
                ])
                self._report_error(
                    "QQBOT-1202",
                    "官机网关响应缺少 url",
                    details,
                )
            return url
        except QQBotConnectionError as error:
            self._report_error(
                error.error_code,
                error.message,
                [*error.details, "30 秒后尝试重连"],
            )
            return ""
        except QQBotHTTPError as error:
            self._report_error(
                "QQBOT-1201",
                "获取官机网关地址的 HTTP 请求失败",
                [
                    f"HTTP 状态码: {error.status_code}",
                    f"响应内容: {error.detail}",
                    "30 秒后尝试重连",
                ],
            )
            return ""
        except Exception as error:
            self._report_error(
                "QQBOT-1203",
                "获取官机网关地址时发生异常",
                [
                    f"异常类型: {type(error).__name__}",
                    f"异常信息: {error}",
                    "30 秒后尝试重连",
                ],
            )
            return ""

    def start_receiver(self):
        '''启动官机 WebSocket 消息接收线程。'''
        if self._ws_active:
            return
        self._ws_active = True
        self._ws_available = False
        self._ws_session_id = 0
        threading.Thread(
            target=self._ws_loop,
            name="QQBotRX",
            daemon=True,
        ).start()
        self._log("官机消息接收器已启动")

    def stop_receiver(self):
        '''停止官机消息接收器并关闭当前 WebSocket。'''
        self._ws_active = False
        self._stop_heartbeat()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception as error:
                self._report_error(
                    "QQBOT-1304",
                    "关闭官机 WebSocket 连接失败",
                    [
                        f"异常类型: {type(error).__name__}",
                        f"异常信息: {error}",
                    ],
                )

    def _ws_loop(self):
        '''维持官机网关连接，并在断开后按间隔重试。'''
        ws_module = self._websocket_module
        if ws_module is None:
            self._report_error(
                "QQBOT-1001",
                "websocket-client 依赖尚未加载，官机网关无法启动",
                ["依赖模块: websocket-client"],
            )
            self._ws_active = False
            return

        while self._ws_active:
            try:
                gateway = self._fetch_gateway_url()
                if not gateway:
                    if self._wait_before_retry(30):
                        break
                    continue
                session_id = self._ws_session_id + 1
                self._ws_session_id = session_id
                ws_app = ws_module.WebSocketApp(
                    gateway,
                    None,
                    on_message=lambda ws, msg, sid=session_id: self._on_message(
                        ws, msg, sid),
                    on_error=lambda _ws, error, sid=session_id: self._log_error(
                        error, sid),
                    on_close=lambda ws, code, reason, sid=session_id: self._on_close(
                        ws, code, reason, sid),
                )
                ws_app.on_open = lambda ws, sid=session_id: self._on_open(
                    ws, sid)
                self._ws = ws_app
                ws_app.run_forever()
            except Exception as error:
                self._report_error(
                    "QQBOT-1301",
                    "官机网关连接循环异常",
                    [
                        f"异常类型: {type(error).__name__}",
                        f"异常信息: {error}",
                        "10 秒后尝试重连",
                    ],
                )
            if self._wait_before_retry(10):
                break

    def _wait_before_retry(self, seconds):
        '''等待重试间隔，并在接收器停止时提前结束等待。'''
        for _ in range(max(1, int(seconds * 2))):
            if not self._ws_active:
                return True
            time.sleep(0.5)
        return not self._ws_active

    def _log_error(self, error, session_id):
        '''记录当前网关会话产生的 WebSocket 回调异常。'''
        if session_id == self._ws_session_id and error:
            self._report_error(
                "QQBOT-1302",
                "官机 WebSocket 回调异常",
                [
                    f"异常类型: {type(error).__name__}",
                    f"异常信息: {error}",
                ],
            )

    def _resolve_or_discover(self, openid):
        '''解析官方群 OpenID 对应群号，或安全绑定唯一待绑定群。'''
        for group_id, mapped_openid in self._openid_map.items():
            if mapped_openid == openid:
                return int(group_id)
        openid_text = str(openid)
        if openid_text.isdigit() and int(openid_text) in self._group_ids:
            group_id = int(openid_text)
        else:
            mapped_groups = {int(group_id) for group_id in self._openid_map}
            unbound_groups = [
                group_id for group_id in self._group_ids
                if group_id not in mapped_groups
            ]
            if len(unbound_groups) != 1:
                self._log(
                    f"收到未知群 OpenID，但有 {len(unbound_groups)} 个待绑定群，"
                    "无法安全自动判断对应群号"
                )
                return None
            group_id = unbound_groups[0]
        self._openid_map[str(group_id)] = openid
        self._log(f"已发现群 OpenID: 群{group_id} -> {openid}")
        if self.on_openid_discovered:
            self.on_openid_discovered(group_id, openid)
        return group_id

    @staticmethod
    def openid_to_userid(openid):
        '''把无法直接作为 QQ 号使用的 OpenID 转为稳定会话标识。'''
        if not openid:
            return 0
        value = 0
        for char in str(openid)[-16:]:
            value = (value * 31 + ord(char)) & 0x7FFFFFFF
        return value


    def _on_open(self, ws, session_id):
        '''在当前网关会话打开后发送官机鉴权数据。'''
        if session_id != self._ws_session_id or ws is not self._ws:
            return
        ws.send(json.dumps({
            "op": 2,
            "d": {
                "token": f"QQBot {self._get_token()}",
                "intents": 1 << 25,
                "shard": [0, 1],
            },
        }))

    def _on_message(self, ws, raw, session_id):
        '''解析当前网关会话收到的事件并分派对应处理。'''
        if session_id != self._ws_session_id or ws is not self._ws:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        operation = data.get("op")
        if operation == 10:
            interval = max(
                data["d"].get("heartbeat_interval", 41250) / 1000.0,
                1.0,
            )
            self._start_heartbeat(ws, interval)
        elif operation == 0:
            event_type = data.get("t", "")
            event = data.get("d", {})
            if event_type == "READY":
                self._ws_available = True
                user = event.get("user", {})
                self._log(f"官机已就绪: {user.get('username', '?')}")
            elif event_type in (
                "GROUP_MESSAGE_CREATE",
                "GROUP_AT_MESSAGE_CREATE",
            ):
                self._handle_group_message(event)
        elif operation == 9:
            self._report_error(
                "QQBOT-1304",
                "官机网关鉴权失败",
                ["网关操作码: 9", f"网关响应: {data.get('d')}"],
            )
            ws.close()

    def _on_close(self, ws, code, reason, session_id):
        '''处理当前网关会话关闭并输出异常关闭码。'''
        if session_id != self._ws_session_id or ws is not self._ws:
            return
        self._ws_available = False
        self._stop_heartbeat()
        if self._ws_active and code not in (1000, 1001):
            self._report_error(
                "QQBOT-1303",
                "官机 WebSocket 异常关闭",
                [
                    f"WebSocket 关闭码: {code if code is not None else '未知'}",
                    f"关闭原因: {reason or '未提供'}",
                    "10 秒后尝试重连",
                ],
            )

    def _start_heartbeat(self, ws, interval):
        '''为当前官机网关连接启动心跳线程。'''
        self._stop_heartbeat()
        done = threading.Event()
        self._ws_heartbeat_done = done

        def heartbeat_loop():
            '''按网关要求的间隔持续发送心跳包。'''
            while not done.wait(interval):
                try:
                    ws.send(json.dumps({"op": 1, "d": 0}))
                except Exception as error:
                    self._report_error(
                        "QQBOT-1401",
                        "官机网关心跳发送失败",
                        [
                            f"异常类型: {type(error).__name__}",
                            f"异常信息: {error}",
                        ],
                    )
                    break

        threading.Thread(
            target=heartbeat_loop,
            name="QQBotHeartbeat",
            daemon=True,
        ).start()

    def _stop_heartbeat(self):
        '''停止并清除当前官机网关心跳任务。'''
        done = self._ws_heartbeat_done
        if done is not None:
            done.set()
            self._ws_heartbeat_done = None

    def _handle_group_message(self, event):
        '''把官机群事件转换为 Ultra 所需的群消息参数。'''
        if self.on_group_message is None:
            return
        group_openid = event.get("group_openid") or event.get("group_id", "")
        if not group_openid:
            return
        group_id = self._resolve_or_discover(group_openid)
        if group_id is None:
            return
        author = event.get("author", {})
        content = normalize_official_group_content(event.get("content", ""))
        if not content:
            return
        user_openid = (
            author.get("member_openid")
            or author.get("id")
            or author.get("user_openid")
            or author.get("openid")
            or ""
        )
        if not user_openid:
            self._log("收到官机群消息，但事件缺少成员 OpenID，已忽略")
            return
        self.on_group_message(
            group_id,
            self.openid_to_userid(user_openid),
            author.get("username") or author.get("nickname") or "QQ成员",
            content,
            bool(author.get("bot")),
            user_openid,
            author.get("member_role") or author.get("role") or "member",
        )


def normalize_official_group_content(content):
    """移除官机群事件内容开头的机器人提及，并整理首尾空白。"""
    text = str(content or "")
    text = re.sub(r"^\s*<@![^>]+>\s*", "", text, count=1)
    return text.strip()


def convert_cq_at_to_official(message, display_name_of=None):
    """把 OneBot at 片段转换为官机可读的 @昵称纯文本。"""
    mapping = display_name_of or {}

    def replace(match):
        '''把单个 CQ at 片段替换为可读昵称。'''
        user_id = int(match.group(1))
        display_name = str(mapping.get(user_id, "QQ成员")).strip() or "QQ成员"
        return f"@{display_name}"

    return re.sub(r"\[CQ:at,qq=(\d+)\]", replace, message)

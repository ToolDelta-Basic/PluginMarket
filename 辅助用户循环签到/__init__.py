from __future__ import annotations

import hashlib
import threading
from typing import Any, Dict, Optional, Tuple

import requests
from tooldelta import Plugin, ToolDelta, Print, cfg, plugin_entry, utils


class NV1TimedSignIn(Plugin):
    """循环签到插件"""

    name = "辅助用户循环签到"
    author = "丸山彩"
    version = (0, 0, 2)

    API_BASE = "https://nv1.nethard.pro/api"

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)

        self.config = {
            "username": "",
            "password": "",
            "是否启用循环签到": True,
            "签到间隔分钟": 15,
            "请求超时秒": 10.0,
        }
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, {}, self.config, self.version
        )

        self._stop_evt = threading.Event()

        self._sess: Optional[requests.Session] = None

        self._pwd_plain_cached: Optional[str] = None
        self._pwd_hash_cached: Optional[str] = None

        self._logged_in = False

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_exit)

    def on_preload(self):
        """Preload"""
        self.frame.add_console_cmd_trigger(
            ["nv1sign"],
            "手动执行一次 NV1 登录+签到",
            "用法：nv1sign",
            self.cmd_nv1sign,
        )

    def on_active(self):
        """Active"""
        if self.config.get("是否启用循环签到", True):
            utils.createThread(self._interval_loop, (), f"{self.name}-interval")

    def on_exit(self, *_):
        """Exit"""
        self._stop_evt.set()

    def cmd_nv1sign(self, _args):
        """控制台手动签到"""
        utils.createThread(self._run_once_safe, (), f"{self.name}-manual")

    def _interval_loop(self):
        """循环签到"""
        while not self._stop_evt.is_set():
            self._run_once_safe()

            interval_min = self.config.get("签到间隔分钟", 15)
            try:
                interval_sec = float(interval_min) * 60.0
            except Exception:
                interval_sec = 15.0 * 60.0

            interval_sec = max(5.0, interval_sec)

            if self._stop_evt.wait(interval_sec):
                break

    def _run_once_safe(self):
        """执行一次签到"""
        try:
            self._login_and_sign()
        except Exception as e:
            Print.print_err(f"[{self.name}] 执行出错：{e}")

    @staticmethod
    def _sha256_hex(s: str) -> str:
        """字符串做 SHA-256"""
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def _get_timeout(self) -> float:
        """从配置读取并解析请求超时秒"""
        timeout = self.config.get("请求超时秒", 10.0)
        try:
            timeout_f = float(timeout)
        except Exception:
            timeout_f = 10.0
        return timeout_f

    def _get_session(self) -> requests.Session:
        """获取/创建复用的 requests.Session"""
        if self._sess is None:
            self._sess = requests.Session()
        return self._sess

    def _get_password_hash(self, password_plain: str) -> str:
        """缓存 password 的 SHA-256"""
        if self._pwd_plain_cached == password_plain and isinstance(
            self._pwd_hash_cached, str
        ):
            return self._pwd_hash_cached
        pwd_hash = self._sha256_hex(password_plain)
        self._pwd_plain_cached = password_plain
        self._pwd_hash_cached = pwd_hash
        return pwd_hash

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
    ) -> Tuple[Optional[Dict[str, Any]], int, str]:
        """请求封装统一用 resp.json()"""
        url = f"{self.API_BASE}{endpoint}"
        sess = self._get_session()
        resp = sess.request(
            method,
            url,
            json=json_body,
            headers=headers,
            timeout=timeout,
        )
        status = int(getattr(resp, "status_code", 0) or 0)
        text = (getattr(resp, "text", "") or "")[:300]

        try:
            obj = resp.json()
        except Exception:
            return None, status, text

        return obj if isinstance(obj, dict) else None, status, text

    @staticmethod
    def _is_login_expired(j: Optional[Dict[str, Any]]) -> bool:
        """判断登录失效：success=false 且 message=请先登录"""
        if not isinstance(j, dict):
            return False
        return (j.get("success") is False) and (j.get("message") == "请先登录")

    def _ensure_login(
        self,
        username: str,
        password_hash: str,
        headers: Dict[str, str],
        timeout: float,
    ) -> bool:
        """执行登录请求并更新登录状态"""
        payload = {"username": username, "password": password_hash}
        j, _status, text = self._request_json(
            "POST",
            "/user/login",
            json_body=payload,
            headers=headers,
            timeout=timeout,
        )

        if j is None:
            Print.print_err(f"[{self.name}] 登录失败：{text}")
            self._logged_in = False
            return False

        if not bool(j.get("success", False)):
            msg = j.get("message", "登录失败")
            Print.print_err(f"[{self.name}] 登录失败：{msg}")
            self._logged_in = False
            return False

        self._logged_in = True
        return True

    def _do_sign(
        self,
        headers: Dict[str, str],
        timeout: float,
    ) -> Optional[Dict[str, Any]]:
        """执行签到请求并返回响应"""
        j, _status, text = self._request_json(
            "GET",
            "/helper-bot/daily-sign",
            headers=headers,
            timeout=timeout,
        )

        if j is None:
            Print.print_err(f"[{self.name}] 签到失败：{text}")
            return None

        if self._is_login_expired(j):
            return j

        success = bool(j.get("success", False))
        if not success:
            msg = j.get("message", "签到失败")
            Print.print_err(f"[{self.name}] success=false：{msg}")
            return None

        return j

    def _login_and_sign(self):
        """登录 NV1 并签到，复用 Session，登录失效时重登一次"""
        username = str(self.config.get("username", "")).strip()
        password_plain = str(self.config.get("password", ""))

        if not username or not password_plain:
            Print.print_err(f"[{self.name}] 请先在配置中填写 username/password")
            return

        password_hash = self._get_password_hash(password_plain)
        timeout_f = self._get_timeout()

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://nv1.nethard.pro",
            "Referer": "https://nv1.nethard.pro/login",
            "User-Agent": "Mozilla/5.0",
        }

        sign_json = self._do_sign(headers=headers, timeout=timeout_f)

        if sign_json is not None and self._is_login_expired(sign_json):
            if self._ensure_login(username, password_hash, headers, timeout_f):
                sign_json = self._do_sign(headers=headers, timeout=timeout_f)
            else:
                return

        if sign_json is None:
            return

        if not bool(sign_json.get("success", False)):
            msg = sign_json.get("message", "签到失败")
            Print.print_err(f"[{self.name}] success=false：{msg}")
            return

        data = sign_json.get("data", {})
        nickname = ""
        level = None
        if isinstance(data, dict):
            nickname = str(data.get("nickname", "") or "")
            level = data.get("level", None)

        Print.print_inf(f"[{self.name}] success=true：nickname={nickname} level={level}")


entry = plugin_entry(NV1TimedSignIn)

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, Optional

from tooldelta import Plugin, ToolDelta, Print, cfg, plugin_entry, utils


class NV1TimedSignIn(Plugin):
    """循环签到插件"""

    name = "辅助用户循环签到"
    author = "丸山彩"
    version = (0, 0, 1)

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
        if bool(self.config.get("是否启用循环签到", True)):
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

    def _login_and_sign(self):
        """登录 NV1 并签到"""
        import requests

        username = str(self.config.get("username", "")).strip()
        password_plain = str(self.config.get("password", ""))

        if not username or not password_plain:
            Print.print_err(f"[{self.name}] 请先在配置中填写 username/password")
            return

        password_hash = self._sha256_hex(password_plain)

        timeout = self.config.get("请求超时秒", 10.0)
        try:
            timeout_f = float(timeout)
        except Exception:
            timeout_f = 10.0

        login_url = "https://nv1.nethard.pro/api/user/login"
        sign_url = "https://nv1.nethard.pro/api/helper-bot/daily-sign"

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://nv1.nethard.pro",
            "Referer": "https://nv1.nethard.pro/login",
            "User-Agent": "Mozilla/5.0",
        }

        sess = requests.Session()

        payload = {"username": username, "password": password_hash}
        r1 = sess.post(login_url, json=payload, headers=headers, timeout=timeout_f)
        login_json = self._safe_json_dict(r1.text)

        if login_json is None:
            Print.print_err(f"[{self.name}] 登录失败：{r1.text[:300]}")
            return

        if not bool(login_json.get("success", False)):
            msg = login_json.get("message", "登录失败")
            Print.print_err(f"[{self.name}] 登录失败：{msg}")
            return

        r2 = sess.get(sign_url, headers=headers, timeout=timeout_f)
        sign_json = self._safe_json_dict(r2.text)

        if sign_json is None:
            Print.print_err(f"[{self.name}] 签到失败：{r2.text[:300]}")
            return

        success = bool(sign_json.get("success", False))
        if not success:
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

    @staticmethod
    def _safe_json_dict(text: str) -> Optional[Dict[str, Any]]:
        """将文本解析为 dict JSON"""
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None


entry = plugin_entry(NV1TimedSignIn)

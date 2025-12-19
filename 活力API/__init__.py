"""活力 API 保活插件 - 自动刷新 G79 Token"""

from __future__ import annotations
import threading
from typing import Any
import requests
from requests.exceptions import RequestException

from tooldelta import FrameExit, Plugin, ToolDelta, cfg, fmts, plugin_entry


class VitalityKeepalive(Plugin):
    name = "活力API"
    author = "Q3CC"
    version = (0, 1, 5)

    def __init__(self, frame: ToolDelta) -> None:
        super().__init__(frame)
        default_cfg = {
            "OpenAPI地址": "https://nv1.nethard.pro/api/open-api",
            "API密钥": "your-api-key-uuid",
            "调用方": "helperbot",
            "自动刷新间隔(分钟)": 25,
            "启用自动保活": True,
            "启动时立即刷新": True,
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name,
            cfg.auto_to_std(default_cfg),
            default_cfg,
            (0, 1, 5),
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_frame_exit)

    def on_active(self) -> None:
        fmts.print_inf("[活力保活] 插件已加载")
        if self.cfg["API密钥"] == "your-api-key-uuid":
            fmts.print_err("[活力保活] 请先在配置文件中设置有效的API密钥")
            return
        if self.cfg["启用自动保活"] and self._thread is None:
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def on_frame_exit(self, _: FrameExit) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _get_base_url(self) -> str:
        url: str = self.cfg["OpenAPI地址"].rstrip("/")
        if url.endswith("/open-api"):
            return url[:-9]
        return url.rsplit("/api/", 1)[0] + "/api" if "/api/" in url else url

    def _get_headers(self) -> dict[str, str]:
        return {
            "authorization": self.cfg["API密钥"],
            "X-Caller": self.cfg["调用方"],
        }

    def _parse_json(self, resp: requests.Response) -> dict[str, Any] | None:
        try:
            data = resp.json()
            return data if isinstance(data, dict) else None
        except (ValueError, TypeError):
            return None

    def _fetch_sdkuid(self) -> str | None:
        try:
            resp = requests.get(
                f"{self.cfg['OpenAPI地址'].rstrip('/')}/user/getLoginUserSAuth",
                headers=self._get_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = self._parse_json(resp)
            if data is None:
                return None
            sauth = data.get("data", {}).get("sauth", {})
            return sauth.get("sdkuid") if isinstance(sauth, dict) else None
        except RequestException as e:
            fmts.print_err(f"[活力保活] 获取 sauth 失败: {e}")
            return None

    def _refresh(self, sdkuid: str) -> dict[str, Any]:
        try:
            resp = requests.post(
                f"{self._get_base_url()}/vitalityApi/refresh",
                json={"sdkuid": sdkuid},
                headers=self._get_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = self._parse_json(resp)
            return data if data is not None else {"success": False, "error": "Invalid JSON"}
        except RequestException as e:
            fmts.print_err(f"[活力保活] refresh 请求异常: {e}")
            return {"success": False, "error": str(e)}

    def _do_keepalive(self) -> None:
        sdkuid = self._fetch_sdkuid()
        if not sdkuid:
            fmts.print_war("[活力保活] 未获取到 sdkuid")
            return
        result = self._refresh(sdkuid)
        if result.get("success"):
            data = result.get("data", {})
            if isinstance(data, dict):
                fmts.print_suc(
                    f"[活力保活] 刷新成功 | TTL: {data.get('ttl')} | 过期: {data.get('expiry')}"
                )
            else:
                fmts.print_suc("[活力保活] 刷新成功")
        else:
            fmts.print_err(f"[活力保活] 刷新失败: {result.get('error')}")

    def _get_interval(self) -> int:
        try:
            return max(1, int(self.cfg["自动刷新间隔(分钟)"])) * 60
        except (ValueError, TypeError):
            fmts.print_war("[活力保活] 间隔配置无效，使用默认值 25 分钟")
            return 25 * 60

    def _loop(self) -> None:
        interval = self._get_interval()
        fmts.print_inf(f"[活力保活] 自动保活已启动，间隔 {interval // 60} 分钟")
        if self.cfg["启动时立即刷新"]:
            self._do_keepalive()
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=interval):
                break
            self._do_keepalive()


entry = plugin_entry(VitalityKeepalive)

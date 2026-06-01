"""模块市场服务器 + 多源聚合器。"""
import http.server
import json
import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

from .handler import MarketHandler

try:
    from urllib.request import urlopen as _urlopen
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

_log = logging.getLogger(__name__)

_MODULE_DIR_NAME = "插件数据文件/模块源件"


class ModuleMarketServer:
    """内建模块市场 HTTP 服务器。"""

    def __init__(self, data_path: str, host: str = "127.0.0.1",
                 port: int = 8380, upload_token: str = "",
                 whitelist: Optional[List[str]] = None,
                 sign_secret: str = "", strict_sign: bool = False,
                 per_page: int = 20):
        self._host = host
        self._port = port
        self._token = upload_token
        self._data_path = data_path
        self._whitelist = set(whitelist or [])
        self._sign_secret = sign_secret
        self._strict_sign = strict_sign
        self._per_page = per_page
        self._httpd: Optional[http.server.HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def modules_dir(self) -> str:
        path = os.path.join(self._data_path, _MODULE_DIR_NAME)
        os.makedirs(path, exist_ok=True)
        return path

    def start(self):
        conf = {
            "modules_dir": self.modules_dir,
            "upload_token": self._token,
            "whitelist": self._whitelist,
            "sign_secret": self._sign_secret,
            "strict_sign": self._strict_sign,
            "per_page": self._per_page,
        }
        _c = conf

        class _Bound(MarketHandler):
            market_conf = _c

        self._httpd = http.server.HTTPServer((self._host, self._port), _Bound)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"


class MarketSourceAggregator:
    """多源模块市场聚合器。"""

    def __init__(self, source_urls: List[str], timeout: float = 5.0):
        self._sources = source_urls
        self._timeout = timeout

    def list_all(self, page: int = 1, per_page: int = 20, category: str = "") -> Dict[str, Any]:
        if not HAS_URLLIB:
            return {"modules": [], "sources": [], "conflicts": [], "error": "urllib unavailable"}
        seen: Dict[str, dict] = {}
        conflicts: List[dict] = []
        sources_ok: List[str] = []
        for url in self._sources:
            list_url = f"{url}/modules/list"
            if category:
                list_url += f"?category={category}"
            try:
                resp = _urlopen(list_url, timeout=self._timeout)
                data = json.loads(resp.read().decode("utf-8"))
                sources_ok.append(url)
                for mod in data.get("items", data.get("modules", [])):
                    name = mod.get("name", "")
                    if not name:
                        continue
                    if name in seen:
                        conflicts.append({"name": name, "kept_source": seen[name].get("_source", "?"),
                                         "skipped_source": url})
                        continue
                    mod["_source"] = url
                    seen[name] = mod
            except Exception as e:
                _log.debug("市场源 %s 不可达: %s", url, e)
        result = sorted(seen.values(), key=lambda m: m.get("name", ""))
        total = len(result)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        return {
            "items": result[start: start + per_page],
            "page": page, "per_page": per_page,
            "total": total, "total_pages": total_pages,
            "sources": sources_ok, "conflicts": conflicts,
        }

    def search(self, keyword: str) -> Dict[str, Any]:
        all_mods = self.list_all(per_page=200)
        kw = keyword.lower()
        filtered = [m for m in all_mods["items"]
                    if kw in (m.get("name", "") + m.get("description", "") + m.get("author", "")).lower()]
        return {"modules": filtered, "query": keyword, "sources": all_mods["sources"]}

    def download_url(self, module_name: str) -> Optional[str]:
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", module_name)
        for url in self._sources:
            try:
                resp = _urlopen(f"{url}/modules/download/{safe}", timeout=self._timeout)
                if resp.status == 200:
                    return f"{url}/modules/download/{safe}"
            except Exception:
                continue
        return None

    def fetch_module(self, module_name: str, data_path: str) -> Optional[str]:
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", module_name)
        for url in self._sources:
            try:
                resp = _urlopen(f"{url}/modules/download/{safe}", timeout=self._timeout)
                if resp.status != 200:
                    continue
                data = resp.read()
                mod_dir = os.path.join(data_path, _MODULE_DIR_NAME)
                os.makedirs(mod_dir, exist_ok=True)
                dest = os.path.join(mod_dir, f"{safe}.py")
                with open(dest, "wb") as f:
                    f.write(data)
                _log.info("从 %s 下载模块 %s (%d bytes)", url, safe, len(data))
                return safe
            except Exception as e:
                _log.debug("源 %s 下载失败: %s", url, e)
        return None

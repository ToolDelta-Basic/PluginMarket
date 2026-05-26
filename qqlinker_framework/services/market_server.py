"""模块市场 — 内建 HTTP 服务 + 远程源聚合

══════════════════════════════════════════════════════════════
架构
══════════════════════════════════════════════════════════════
本模块提供两个组件:

1. ModuleMarketServer — 内建 HTTP 服务模块市场（本地）
    支持模块的列表、搜索、下载、上传。
    可配置上传密钥和白名单（不在白名单的模块对未认证请求隐藏）。

2. MarketSourceAggregator — 多源聚合器
    按优先级顺序查询多个市场源（本地 + 远程），
    发现同名模块时以先返回的为准。

══════════════════════════════════════════════════════════════
配置 (config.json)
══════════════════════════════════════════════════════════════
{
  "模块市场": {
    "启用": false,
    "地址": "127.0.0.1",
    "端口": 8380,
    "上传密钥": "",
    "白名单模块": [],
    "源列表": [
      "http://127.0.0.1:8380"
    ]
  }
}

- 源列表: 按优先级排列的市场 URL，作为客户端查询时按顺序扫描
- 白名单模块: 内建市场中，仅这些模块对未认证请求可见
- 上传密钥: 非空时上传需要 Bearer 或 ?token= 认证；空 = 无需认证

通用性:
  - 内建市场服务 (ModuleMarketServer): 提供完整 REST API
  - 远程源只需实现 /modules/list 和 /modules/download/<name> 即可接入
  - 用户可通过 qqdeps module add <URL> 从任意源下载
══════════════════════════════════════════════════════════════
"""
import hashlib
import hmac
import http.server
import json
import logging
import os
import re
import threading
import time
import cgi
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    from urllib.request import urlopen as _urlopen
    from urllib.error import URLError
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

_logger = logging.getLogger(__name__)

_MODULE_DIR_NAME = "插件数据文件/模块源件"


# ═══════════════════════════════════════════════════════════════
# 签名工具
# ═══════════════════════════════════════════════════════════════

def sign_module(name: str, version: str, secret: str) -> str:
    """为模块生成 HMAC-SHA256 签名（用于上传到市场时携带）。

    签名 = HMAC-SHA256(secret, f"{name}:{version}").hexdigest()[:16]
    """
    msg = f"{name}:{version}".encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"), msg, hashlib.sha256
    ).hexdigest()[:16]


def verify_signature(
    name: str, version: str, signature: str, secret: str
) -> bool:
    """验证模块签名是否有效（恒定时间比较）。"""
    return hmac.compare_digest(
        sign_module(name, version, secret),
        signature,
    )


# ═══════════════════════════════════════════════════════════════
# 内建市场 HTTP 服务
# ═══════════════════════════════════════════════════════════════

class _MarketHandler(http.server.BaseHTTPRequestHandler):
    """模块市场 REST API 处理器。

    每个实例由 ModuleMarketServer 通过工厂函数注入属性。
    不再使用类变量（避免多服务器时相互覆盖）。
    """

    # 类级默认值（仅用于类型提示）
    market_conf: dict = {}

    def log_message(self, fmt, *args):
        _logger.debug(fmt, *args)

    # ── 认证 ──

    def _is_authenticated(self) -> bool:
        token_cfg = self.market_conf.get("upload_token", "")
        if not token_cfg:
            return True
        qs = parse_qs(urlparse(self.path).query)
        token = (
            qs.get("token", [""])[0]
            or self.headers.get("Authorization", "")
            .replace("Bearer ", "")
        )
        return token == token_cfg

    def _allow_module(self, name: str) -> bool:
        whitelist = self.market_conf.get("whitelist", set())
        if not whitelist:
            return True
        if self._is_authenticated():
            return True
        return name in whitelist

    # ── 路由 ──

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/health":
            return self._ok()
        if path == "/modules/list":
            return self._handle_list(qs)
        m = re.match(r"^/modules/info/([^/]+)$", path)
        if m:
            return self._handle_info(m.group(1))
        m = re.match(r"^/modules/download/([^/]+)$", path)
        if m:
            return self._handle_download(m.group(1))
        if path == "/modules/search":
            return self._handle_search(qs)

        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.rstrip("/")
        if path == "/modules/upload":
            self._handle_upload()
        else:
            self._json(404, {"error": "not found"})

    # ── 实现 ──

    def _ok(self):
        self._json(200, {"status": "ok", "time": time.time()})

    def _handle_list(self, qs):
        auth = self._is_authenticated()
        mods = []
        for fname in sorted(os.listdir(self.market_conf["modules_dir"])):
            if fname.startswith("__") or not fname.endswith(".py"):
                continue
            info = self._scan_file(fname)
            name = info.get("name", fname[:-3])
            if not self._allow_module(name):
                continue
            if auth:
                mods.append(info)
            else:
                # 公开列表只暴露基本信息
                mods.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "version": info.get("version", "?"),
                })
        self._json(200, {"modules": mods, "authenticated": auth})

    def _handle_info(self, name: str):
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
        if safe != name:
            self._json(400, {"error": "invalid"})
            return
        fname = f"{safe}.py"
        path = os.path.join(self.market_conf["modules_dir"], fname)
        if not os.path.exists(path):
            self._json(404, {"error": "not found"})
            return
        info = self._scan_file(fname)
        info["download_url"] = f"/modules/download/{safe}"
        self._json(200, info)

    def _handle_download(self, name: str):
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
        if safe != name:
            self._json(400, {"error": "invalid"})
            return
        # 检查白名单
        if not self._allow_module(safe):
            self._json(403, {"error": "not in whitelist"})
            return
        fpath = os.path.join(self.market_conf["modules_dir"], f"{safe}.py")
        if not os.path.exists(fpath):
            self._json(404, {"error": "not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/x-python; charset=utf-8")
        fname = f"{safe}.py"
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{fname}"',
        )
        self.end_headers()
        with open(fpath, "rb") as f:
            self.wfile.write(f.read())

    def _handle_search(self, qs):
        keyword = qs.get("q", [""])[0].lower()
        auth = self._is_authenticated()
        mods = []
        for fname in sorted(os.listdir(self.market_conf["modules_dir"])):
            if fname.startswith("__") or not fname.endswith(".py"):
                continue
            info = self._scan_file(fname)
            name = info.get("name", fname[:-3])
            if not self._allow_module(name):
                continue
            text = (
                info.get("name", "")
                + info.get("description", "")
                + info.get("author", "")
            ).lower()
            if keyword in text:
                if auth:
                    mods.append(info)
                else:
                    mods.append({
                        "name": name,
                        "description": info.get("description", ""),
                        "version": info.get("version", "?"),
                    })
        self._json(200, {"modules": mods, "query": keyword, "authenticated": auth})

    def _handle_upload(self):
        # 鉴权
        if self.market_conf["upload_token"] and not self._is_authenticated():
            self._json(401, {"error": "unauthorized"})
            return

        ct = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ct:
            self._json(400, {"error": "use multipart/form-data"})
            return

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ct},
            )
        except Exception as e:
            self._json(400, {"error": f"parse: {e}"})
            return

        file_item = (
            form.getfirst("file")
            if hasattr(form, "getfirst")
            else form.getvalue("file")
        )
        if file_item is None:
            self._json(400, {"error": "missing file"})
            return

        if hasattr(file_item, "file"):
            data = file_item.file.read()
            upload_name = getattr(file_item, "filename", "unknown.py")
        elif isinstance(file_item, bytes):
            data = file_item
            upload_name = "unknown.py"
        else:
            data = str(file_item).encode("utf-8")
            upload_name = "unknown.py"

        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "", upload_name)
        if not safe_name.endswith(".py"):
            self._json(400, {"error": "only .py allowed"})
            return

        # 签名校验（可选）
        sig = (
            form.getfirst("signature")
            if hasattr(form, "getfirst")
            else form.getvalue("signature")
        )
        if self.market_conf["sign_secret"]:
            expected = sign_module(
                safe_name[:-3], "0.0.0", self.market_conf["sign_secret"]
            )
            # 只做软校验——签名不匹配时记录警告但仍允许上传
            if sig and not hmac.compare_digest(sig, expected):
                _logger.warning(
                    "上传签名不匹配: %s (期望 %s)", sig, expected
                )
                # 可选: 如果要求强校验则拒绝
                # self._json(403, {"error":"bad signature"}); return

        dest = os.path.join(self.market_conf["modules_dir"], safe_name)
        with open(dest, "wb") as f:
            f.write(data)

        _logger.info("上传模块: %s (%d bytes)", safe_name, len(data))
        self._json(200, {"ok": True, "name": safe_name[:-3], "size": len(data)})

    # ── 文件解析 ──

    def _scan_file(self, fname: str) -> dict:
        filepath = os.path.join(self.market_conf["modules_dir"], fname)
        info: Dict[str, Any] = {
            "name": fname[:-3],
            "author": "?",
            "version": "?",
            "description": "",
            "size": os.path.getsize(filepath),
        }
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read(4096)
        except Exception:
            return info

        for pat, key in [
            (r'name\s*=\s*["\']([^"\']{1,64})["\']', "name"),
            (r'author\s*=\s*["\']([^"\']{1,64})["\']', "author"),
            (r'version\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)', "version"),
        ]:
            m = re.search(pat, content)
            if m:
                if key == "version":
                    info[key] = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
                else:
                    info[key] = m.group(1)

        m = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if m:
            desc = m.group(1).strip().split("\n")[0].strip()
            if desc and len(desc) < 200:
                info["description"] = desc

        return info

    def _json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ModuleMarketServer:
    """内建模块市场 HTTP 服务器。"""

    def __init__(
        self,
        data_path: str,
        host: str = "127.0.0.1",
        port: int = 8380,
        upload_token: str = "",
        whitelist: Optional[List[str]] = None,
        sign_secret: str = "",
    ):
        self._host = host
        self._port = port
        self._token = upload_token
        self._data_path = data_path
        self._whitelist = set(whitelist or [])
        self._sign_secret = sign_secret
        self._httpd: Optional[http.server.HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def modules_dir(self) -> str:
        path = os.path.join(self._data_path, _MODULE_DIR_NAME)
        os.makedirs(path, exist_ok=True)
        return path

    def start(self):
        """启动 HTTP 服务器。

        BoundHandler 用闭包捕获配置，每个服务器实例独立。
        """
        conf = {
            "modules_dir": self.modules_dir,
            "upload_token": self._token,
            "whitelist": self._whitelist,
            "sign_secret": self._sign_secret,
        }
        _c = conf

        class _Bound(_MarketHandler):
            market_conf = _c

        self._httpd = http.server.HTTPServer(
            (self._host, self._port), _Bound
        )
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True
        )
        self._thread.start()
        _logger.info("模块市场已启动 http://%s:%d", self._host, self._port)

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"


# ═══════════════════════════════════════════════════════════════
# 多源聚合器 — 按优先级扫描多个市场
# ═══════════════════════════════════════════════════════════════

class MarketSourceAggregator:
    """多源模块市场聚合器。

    按配置的 source_urls 顺序查询：
      1. 每个源 GET /modules/list 获取模块列表
      2. 同名模块以先查到的为准
      3. 冲突时在合并结果中标注 source 来源
      4. 支持无认证（公开源）和带 token 认证（私有源）

    用法:
        agg = MarketSourceAggregator([
            "http://127.0.0.1:8380",
            "https://friend-server.example.com/market",
        ])
        modules = agg.list_all()
    """

    def __init__(self, source_urls: List[str], timeout: float = 5.0):
        self._sources = source_urls
        self._timeout = timeout

    def list_all(self) -> Dict[str, Any]:
        """合并所有源的模块列表。

        Returns:
            {"modules": [...], "sources": [...], "conflicts": [...]}
        """
        if not HAS_URLLIB:
            return {"modules": [], "sources": [], "conflicts": [], "error": "urllib unavailable"}

        seen: Dict[str, dict] = {}
        conflicts: List[dict] = []
        sources_ok: List[str] = []

        for url in self._sources:
            try:
                resp = _urlopen(f"{url}/modules/list", timeout=self._timeout)
                data = json.loads(resp.read().decode("utf-8"))
                sources_ok.append(url)
                for mod in data.get("modules", []):
                    name = mod.get("name", "")
                    if not name:
                        continue
                    if name in seen:
                        conflicts.append({
                            "name": name,
                            "kept_source": seen[name].get("_source", "?"),
                            "skipped_source": url,
                        })
                        continue
                    mod["_source"] = url
                    seen[name] = mod
            except Exception as e:
                _logger.debug("市场源 %s 不可达: %s", url, e)

        result = sorted(seen.values(), key=lambda m: m.get("name", ""))
        return {
            "modules": result,
            "sources": sources_ok,
            "conflicts": conflicts,
        }

    def search(self, keyword: str) -> Dict[str, Any]:
        """按关键词在多源中搜索。"""
        all_mods = self.list_all()
        kw = keyword.lower()
        filtered = [
            m
            for m in all_mods["modules"]
            if kw in (
                m.get("name", "")
                + m.get("description", "")
                + m.get("author", "")
            ).lower()
        ]
        return {
            "modules": filtered,
            "query": keyword,
            "sources": all_mods["sources"],
        }

    def download_url(self, module_name: str) -> Optional[str]:
        """查找模块的下载 URL（从第一个可用的源）。

        Returns:
            下载 URL 或 None。
        """
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", module_name)
        for url in self._sources:
            try:
                resp = _urlopen(
                    f"{url}/modules/download/{safe}",
                    timeout=self._timeout,
                )
                if resp.status == 200:
                    return f"{url}/modules/download/{safe}"
            except Exception:
                continue
        return None

    def fetch_module(
        self, module_name: str, data_path: str
    ) -> Optional[str]:
        """从多源中下载模块到本地 模块源件/。

        Returns:
            模块名（成功）或 None。
        """
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", module_name)
        for url in self._sources:
            try:
                resp = _urlopen(
                    f"{url}/modules/download/{safe}",
                    timeout=self._timeout,
                )
                if resp.status != 200:
                    continue
                data = resp.read()
                mod_dir = os.path.join(data_path, _MODULE_DIR_NAME)
                os.makedirs(mod_dir, exist_ok=True)
                dest = os.path.join(mod_dir, f"{safe}.py")
                with open(dest, "wb") as f:
                    f.write(data)
                _logger.info(
                    "从 %s 下载模块 %s (%d bytes)", url, safe, len(data)
                )
                return safe
            except Exception as e:
                _logger.debug("源 %s 下载失败: %s", url, e)
        return None

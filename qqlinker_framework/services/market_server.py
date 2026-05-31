"""模块市场 — 内建 HTTP 服务 + 远程源聚合

══════════════════════════════════════════════════════════════
架构
══════════════════════════════════════════════════════════════
本模块提供两个组件:

1. ModuleMarketServer — 内建 HTTP 服务模块市场（本地）
    支持模块的列表、搜索、下载、上传、分类、分页、统计。
    可配置上传密钥和白名单（不在白名单的模块对未认证请求隐藏）。

2. MarketSourceAggregator — 多源聚合器
    按优先级顺序查询多个市场源（本地 + 远程），
    发现同名模块时以先返回的为准。

══════════════════════════════════════════════════════════════
REST API
══════════════════════════════════════════════════════════════
  GET  /health                              → {"status":"ok"}
  GET  /modules/list                        → 模块列表 (支持 ?page=&per_page=&category=)
  GET  /modules/search?q=xxx                → 全文搜索 (支持 ?category=&page=&per_page=)
  GET  /modules/info/<name>                 → 单个模块详情
  GET  /modules/download/<name>             → 下载 .py 源文件
  GET  /modules/stats                       → 市场统计
  GET  /modules/categories                  → 模块分类列表
  POST /modules/upload  (multipart)          → 上传模块

配置 (config.json):
══════════════════════════════════════════════════════════════
{
  "模块市场": {
    "启用": false,
    "地址": "127.0.0.1",
    "端口": 8380,
    "上传密钥": "",
    "签名密钥": "",
    "强制签名校验": false,
    "白名单模块": [],
    "每页数量": 20,
    "源列表": ["http://127.0.0.1:8380"]
  }
}

新增:
  - 强制签名校验: true 时上传必须带有效签名
  - 每页数量: 分页的默认每页数量
  - 模块分类: 从源文件 __category__ = "分类名" 提取
  - 下载统计: 每次下载记录时间戳，/modules/stats 返回
  - 分页: page / per_page 参数
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
from email.parser import BytesParser
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
_MAX_UPLOAD_SIZE = 16 * 1024 * 1024  # 16MB

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
            or self.headers.get("Authorization", "").replace("Bearer ", "")
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
        if path == "/modules/search":
            return self._handle_search(qs)
        if path == "/modules/stats":
            return self._handle_stats()
        if path == "/modules/categories":
            return self._handle_categories()
        m = re.match(r"^/modules/info/([^/]+)$", path)
        if m:
            return self._handle_info(m.group(1))
        m = re.match(r"^/modules/download/([^/]+)$", path)
        if m:
            return self._handle_download(m.group(1))

        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path == "/modules/upload":
            self._handle_upload()
        else:
            self._json(404, {"error": "not found"})

    # ── 分页 & 辅助 ──

    @staticmethod
    def _paginate(items: list, qs: dict, default_per_page: int = 20):
        """对列表做分页，返回分页信息。"""
        try:
            page = int(qs.get("page", ["1"])[0])
            page = max(1, page)
        except (ValueError, IndexError):
            page = 1
        try:
            per_page = int(qs.get("per_page", [str(default_per_page)])[0])
            per_page = min(max(1, per_page), 100)
        except (ValueError, IndexError):
            per_page = default_per_page

        total = len(items)
        total_pages = max(1, (total + per_page - 1) // per_page)
        if page > total_pages:
            page = total_pages
        start = (page - 1) * per_page
        page_items = items[start : start + per_page]

        return {
            "items": page_items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        }

    # ── 实现 ──

    def _ok(self):
        self._json(200, {"status": "ok", "time": time.time()})

    def _handle_list(self, qs):
        auth = self._is_authenticated()
        category_filter = qs.get("category", [""])[0].strip().lower()

        mods = []
        for fname in sorted(os.listdir(self.market_conf["modules_dir"])):
            if fname.startswith("__") or not fname.endswith(".py"):
                continue
            info = self._scan_file(fname)
            name = info.get("name", fname[:-3])
            if not self._allow_module(name):
                continue

            # 分类过滤
            if category_filter:
                cats = info.get("categories", [])
                if category_filter not in [c.lower() for c in cats]:
                    continue

            if auth:
                mods.append(info)
            else:
                mods.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "version": info.get("version", "?"),
                    "categories": info.get("categories", []),
                })

        # 分页
        default_per = self.market_conf.get("per_page", 20)
        page_info = self._paginate(mods, qs, default_per_page=default_per)
        self._json(200, {
            **page_info,
            "authenticated": auth,
            "category": category_filter or None,
        })

    def _handle_info(self, name: str):
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
        if safe != name:
            self._json(400, {"error": "invalid name"})
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
            self._json(400, {"error": "invalid name"})
            return
        if not self._allow_module(safe):
            self._json(403, {"error": "not in whitelist"})
            return
        fpath = os.path.join(self.market_conf["modules_dir"], f"{safe}.py")
        if not os.path.exists(fpath):
            self._json(404, {"error": "not found"})
            return

        # 记录下载统计
        self._record_download(safe)

        self.send_response(200)
        self.send_header("Content-Type", "text/x-python; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{safe}.py"',
        )
        self.end_headers()
        with open(fpath, "rb") as f:
            self.wfile.write(f.read())

    def _handle_search(self, qs):
        keyword = qs.get("q", [""])[0].lower()
        category_filter = qs.get("category", [""])[0].strip().lower()
        auth = self._is_authenticated()

        if not keyword and not category_filter:
            # 无筛选条件 → 返回全部（同 /modules/list）
            return self._handle_list(qs)

        mods = []
        for fname in sorted(os.listdir(self.market_conf["modules_dir"])):
            if fname.startswith("__") or not fname.endswith(".py"):
                continue
            info = self._scan_file(fname)
            name = info.get("name", fname[:-3])
            if not self._allow_module(name):
                continue

            # 分类过滤
            if category_filter:
                cats = info.get("categories", [])
                if category_filter not in [c.lower() for c in cats]:
                    continue

            # 关键词搜索（匹配 name / description / author）
            if keyword:
                text = (
                    info.get("name", "")
                    + info.get("description", "")
                    + info.get("author", "")
                ).lower()
                if keyword not in text:
                    continue

            if auth:
                mods.append(info)
            else:
                mods.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "version": info.get("version", "?"),
                    "categories": info.get("categories", []),
                })

        default_per = self.market_conf.get("per_page", 20)
        page_info = self._paginate(mods, qs, default_per_page=default_per)
        self._json(200, {
            **page_info,
            "query": keyword or None,
            "category": category_filter or None,
            "authenticated": auth,
        })

    def _handle_stats(self):
        """返回市场统计信息（不经过白名单过滤，反映全部模块数据）。"""
        mod_dir = self.market_conf["modules_dir"]
        modules = []
        total_size = 0
        all_categories: Dict[str, int] = {}
        downloads: Dict[str, list] = {}

        for fname in sorted(os.listdir(mod_dir)):
            if fname.startswith("__") or not fname.endswith(".py"):
                continue
            info = self._scan_file(fname)
            name = info.get("name", fname[:-3])
            modules.append(name)
            total_size += info.get("size", 0)
            for cat in info.get("categories", []):
                all_categories[cat] = all_categories.get(cat, 0) + 1

        # 读取下载统计
        stats_path = os.path.join(mod_dir, "_download_stats.json")
        if os.path.exists(stats_path):
            try:
                with open(stats_path, "r", encoding="utf-8") as f:
                    downloads = json.load(f)
            except Exception:
                downloads = {}

        # 热门模块（下载次数）
        top_downloads = sorted(
            [
                {"name": k, "count": len(v)}
                for k, v in downloads.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        self._json(200, {
            "total_modules": len(modules),
            "total_size_bytes": total_size,
            "categories": dict(
                sorted(all_categories.items(), key=lambda x: -x[1])
            ),
            "top_downloads": top_downloads,
            "whitelist_enabled": bool(self.market_conf.get("whitelist")),
        })

    def _handle_categories(self):
        """返回所有模块分类及计数（不经过白名单过滤）。"""
        mod_dir = self.market_conf["modules_dir"]
        cat_counts: Dict[str, int] = {}

        for fname in sorted(os.listdir(mod_dir)):
            if fname.startswith("__") or not fname.endswith(".py"):
                continue
            info = self._scan_file(fname)
            name = info.get("name", fname[:-3])
            for cat in info.get("categories", []):
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

        self._json(200, {
            "categories": dict(
                sorted(cat_counts.items(), key=lambda x: -x[1])
            ),
        })

    # ── multipart/form-data 解析（替代 cgi.FieldStorage，兼容 Python 3.13+）──

    @staticmethod
    def _parse_multipart(content_type: str, body: bytes) -> dict:
        """解析 multipart/form-data，返回 {字段名: [(payload_bytes, filename_or_None), ...]}。

        兼容 Python 3.13+（cgi 模块已被移除），使用标准库 email 模块。
        """
        result: Dict[str, List[Tuple[bytes, Optional[str]]]] = {}
        msg = BytesParser().parsebytes(
            b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
        )
        if not msg.is_multipart():
            return result
        for part in msg.walk():
            cdisp = part.get_content_disposition()
            if cdisp != "form-data":
                continue
            field_name = part.get_param("name", header="Content-Disposition")
            if field_name is None:
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = b""
            result.setdefault(field_name, []).append((payload, filename))
        return result

    def _handle_upload(self):
        # 鉴权
        if self.market_conf.get("upload_token") and not self._is_authenticated():
            self._json(401, {"error": "unauthorized"})
            return

        ct = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ct:
            self._json(400, {"error": "use multipart/form-data"})
            return

        content_len = int(self.headers.get("Content-Length", "0"))
        if content_len == 0:
            self._json(400, {"error": "empty body"})
            return
        if content_len > _MAX_UPLOAD_SIZE:
            self._json(413, {"error": f"too large (max {_MAX_UPLOAD_SIZE // 1024 // 1024}MB)"})
            return

        body = self.rfile.read(content_len)

        try:
            form = self._parse_multipart(ct, body)
        except Exception as e:
            self._json(400, {"error": f"parse error: {e}"})
            return

        file_entries = form.get("file", [])
        if not file_entries:
            self._json(400, {"error": "missing 'file' field"})
            return

        data, upload_name_raw = file_entries[0]
        upload_name = upload_name_raw or "unknown.py"
        if not isinstance(data, bytes):
            data = str(data).encode("utf-8")

        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "", upload_name)
        if not safe_name.endswith(".py"):
            self._json(400, {"error": "only .py files allowed"})
            return
        if not safe_name or safe_name == ".py":
            self._json(400, {"error": "invalid filename"})
            return

        module_name = safe_name[:-3]

        # 签名校验
        sig_entries = form.get("signature", [])
        sig = (
            sig_entries[0][0].decode("utf-8", errors="replace")
            if sig_entries else None
        )
        sign_secret = self.market_conf.get("sign_secret", "")
        strict_sign = self.market_conf.get("strict_sign", False)

        if sign_secret:
            # 从上传文件中尝试提取版本
            version = "0.0.0"
            mod_body = data.decode("utf-8", errors="replace")
            ver_match = re.search(r"version\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)", mod_body)
            if ver_match:
                version = f"{ver_match[1]}.{ver_match[2]}.{ver_match[3]}"

            expected = sign_module(module_name, version, sign_secret)

            if sig and not hmac.compare_digest(sig, expected):
                msg = f"签名不匹配: got={sig} expected={expected}"
                _logger.warning("上传 %s: %s", safe_name, msg)
                if strict_sign:
                    self._json(403, {"error": "bad signature", "detail": msg})
                    return
            elif not sig and strict_sign:
                self._json(403, {"error": "signature required (strict mode)"})
                return

        dest = os.path.join(self.market_conf["modules_dir"], safe_name)
        with open(dest, "wb") as f:
            f.write(data)

        _logger.info("上传模块: %s (%d bytes)", safe_name, len(data))
        self._json(200, {"ok": True, "name": module_name, "size": len(data)})

    # ── 文件解析 ──

    _SCAN_CACHE: Dict[str, Tuple[float, dict]] = {}
    _SCAN_CACHE_TTL = 5.0  # 5秒缓存

    def _scan_file(self, fname: str) -> dict:
        """解析 .py 模块文件的元信息，带短缓存。

        提取: name, author, version, description, categories, size, mtime。
        """
        filepath = os.path.join(self.market_conf["modules_dir"], fname)
        mtime = os.path.getmtime(filepath)
        cached = self._SCAN_CACHE.get(fname)
        if cached and cached[0] == mtime:
            return dict(cached[1])

        fsize = os.path.getsize(filepath)
        info: Dict[str, Any] = {
            "name": fname[:-3],
            "author": "?",
            "version": "?",
            "description": "",
            "categories": [],
            "size": fsize,
            "mtime": int(mtime),
        }
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read(8192)
        except Exception:
            self._SCAN_CACHE[fname] = (mtime, info)
            return info

        # name / author / version
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

        # 分类: __category__ 或 __categories__
        cat_match = re.search(
            r'__categories?__\s*=\s*\[(.*?)\]',
            content, re.DOTALL,
        )
        if cat_match:
            cats_str = cat_match.group(1)
            info["categories"] = [
                c.strip().strip("\"'")
                for c in cats_str.split(",")
                if c.strip()
            ]
        else:
            # 单分类
            single = re.search(
                r'__category__\s*=\s*["\']([^"\']{1,32})["\']',
                content,
            )
            if single:
                info["categories"] = [single.group(1)]

        # description
        m = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if m:
            desc = m.group(1).strip().split("\n")[0].strip()
            if desc and len(desc) < 200:
                info["description"] = desc

        self._SCAN_CACHE[fname] = (mtime, info)
        return dict(info)

    # ── 下载统计 ──

    def _record_download(self, module_name: str):
        """记录一次下载（持久化到 _download_stats.json）。"""
        stats_path = os.path.join(
            self.market_conf["modules_dir"], "_download_stats.json"
        )
        downloads: Dict[str, list] = {}
        if os.path.exists(stats_path):
            try:
                with open(stats_path, "r", encoding="utf-8") as f:
                    downloads = json.load(f)
            except Exception:
                downloads = {}
        downloads.setdefault(module_name, []).append(int(time.time()))
        # 最多保留 1000 条记录
        for k in downloads:
            downloads[k] = downloads[k][-1000:]
        try:
            with open(stats_path, "w", encoding="utf-8") as f:
                json.dump(downloads, f, ensure_ascii=False)
        except Exception as e:
            _logger.debug("写入下载统计失败: %s", e)

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
        strict_sign: bool = False,
        per_page: int = 20,
    ):
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
        """启动 HTTP 服务器。

        BoundHandler 用闭包捕获配置，每个服务器实例独立。
        """
        conf = {
            "modules_dir": self.modules_dir,
            "upload_token": self._token,
            "whitelist": self._whitelist,
            "sign_secret": self._sign_secret,
            "strict_sign": self._strict_sign,
            "per_page": self._per_page,
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

    def list_all(
        self, page: int = 1, per_page: int = 20, category: str = ""
    ) -> Dict[str, Any]:
        """合并所有源的模块列表（支持分页和分类过滤）。

        Returns:
            {"modules": [...], "sources": [...], "conflicts": [...], ...}
        """
        if not HAS_URLLIB:
            return {
                "modules": [], "sources": [], "conflicts": [],
                "error": "urllib unavailable",
            }

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
                items = data.get("items", data.get("modules", []))
                for mod in items:
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
        # 分页
        total = len(result)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        paged = result[start : start + per_page]

        return {
            "items": paged,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "sources": sources_ok,
            "conflicts": conflicts,
        }

    def search(self, keyword: str) -> Dict[str, Any]:
        """按关键词在多源中搜索。"""
        all_mods = self.list_all(per_page=200)
        kw = keyword.lower()
        filtered = [
            m
            for m in all_mods["items"]
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
        """查找模块的下载 URL（从第一个可用的源）。"""
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
        """从多源中下载模块到本地 模块源件/。"""
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

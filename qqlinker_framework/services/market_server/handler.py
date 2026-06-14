"""模块市场 REST API 处理器 — 列表/搜索/下载/上传/统计。

安全特性:
  - 上传文件名校验（禁止路径分隔符、..、特殊字符）
  - 文件大小限制（10 MB）
  - MIME 类型校验（仅允许 zip 或 application/octet-stream）
  - ZipSlip 防护（拒绝符号链接、.. 路径、绝对路径）
  - 拒绝 __pycache__ 和 .pyc 编译文件
  - 上传速率限制（每 IP 每分钟 3 次）
"""
import http.server
import json
import logging
import os
import re
import time
import traceback
import zipfile
from email.parser import BytesParser
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

from .signer import verify_signature

_log = logging.getLogger(__name__)

_MODULE_DIR_NAME = "插件数据文件/模块源件"
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB 文件大小限制
_MAX_UPLOAD_RATE_PER_IP = 3          # 每 IP 每分钟最大上传次数
_UPLOAD_RATE_WINDOW = 60             # 速率窗口（秒）


class MarketHandler(http.server.BaseHTTPRequestHandler):
    """模块市场 REST API 处理器。"""

    market_conf: Dict[str, Any] = {}
    # 类级别的上传速率限制（按 IP）
    _upload_rate_map: Dict[str, List[float]] = {}
    # 测试用：设为 True 跳过速率限制
    _rate_limit_disabled: bool = False

    @property
    def modules_dir(self) -> str:
        """模块目录路径。"""
        return self.market_conf.get("modules_dir", "")

    @property
    def upload_token(self) -> str:
        """上传令牌。"""
        return self.market_conf.get("upload_token", "")

    @property
    def whitelist(self) -> set:
        """模块白名单。"""
        return self.market_conf.get("whitelist", set())

    @property
    def sign_secret(self) -> str:
        """签名密钥。"""
        return self.market_conf.get("sign_secret", "")

    @property
    def strict_sign(self) -> bool:
        """是否严格验证签名。"""
        return self.market_conf.get("strict_sign", False)

    @property
    def per_page(self) -> int:
        """每页模块数。"""
        return self.market_conf.get("per_page", 20)

    def log_message(self, format, *args):
        """自定义日志格式。"""
        _log.debug("%s %s", self.command, format % args)

    def _is_authenticated(self) -> bool:
        qs = parse_qs(urlparse(self.path).query)
        token = qs.get("token", [None])[0]
        return token == self.upload_token if self.upload_token else True

    def _allow_module(self, name: str) -> bool:
        return not self.whitelist or name in self.whitelist

    # ── 路由 ──

    def do_GET(self):
        """处理 GET 请求。"""
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/health":
            return self._ok({"status": "ok"})

        if path == "/modules/list":
            return self._handle_list(qs, auth_required=False)

        if path == "/modules/search":
            return self._handle_search(qs)

        if path == "/modules/stats":
            return self._handle_stats()

        if path == "/modules/categories":
            return self._handle_categories()

        m = re.match(r"^/modules/info/([a-zA-Z0-9_\-]+)$", path)
        if m:
            return self._handle_info(m.group(1))

        m = re.match(r"^/modules/download/([a-zA-Z0-9_\-]+)$", path)
        if m:
            return self._handle_download(m.group(1))

        self.send_error(404)

    def do_POST(self):
        """处理 POST 请求。"""
        if self.path.startswith("/modules/upload"):
            self._handle_upload()
        else:
            self.send_error(404)

    # ── 分页工具 ──

    @staticmethod
    def _paginate(items: list, qs: dict, default_per_page: int = 20):
        try:
            page = max(1, int(qs.get("page", ["1"])[0]))
        except (ValueError, IndexError):
            page = 1
        try:
            per_page = max(1, min(100, int(qs.get("per_page", [str(default_per_page)])[0])))
        except (ValueError, IndexError):
            per_page = default_per_page
        total = len(items)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        return {
            "items": items[start: start + per_page],
            "page": page, "per_page": per_page,
            "total": total, "total_pages": total_pages,
        }

    def _ok(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    # ── 列表 ──

    def _handle_list(self, qs: dict, auth_required: bool = False):
        if auth_required and not self._is_authenticated():
            self.send_error(401)
            return
        category = qs.get("category", [""])[0]
        modules = self._scan_modules(self.modules_dir)
        if not self._is_authenticated():
            modules = [m for m in modules if self._allow_module(m.get("name", ""))]
        if category:
            modules = [m for m in modules if m.get("category", "") == category]
        result = self._paginate(modules, qs, self.per_page)
        self._ok(result)

    def _handle_info(self, name: str):
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
        filepath = os.path.join(self.modules_dir, f"{safe}.py")
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        info = self._parse_module_file(filepath)
        self._ok(info)

    def _handle_download(self, name: str):
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
        if not self._allow_module(safe) and not self._is_authenticated():
            self.send_error(403)
            return
        filepath = os.path.join(self.modules_dir, f"{safe}.py")
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        # 记录下载统计
        self._record_download(safe)
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/x-python; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_search(self, qs: dict):
        if not self._is_authenticated():
            return self._handle_list(qs, auth_required=False)
        keyword = qs.get("q", [""])[0].lower()
        modules = self._scan_modules(self.modules_dir)
        if keyword:
            modules = [
                m for m in modules
                if keyword in (m.get("name", "") + m.get("description", "") + m.get("author", "")).lower()
            ]
        result = self._paginate(modules, qs, self.per_page)
        self._ok(result)

    def _handle_stats(self):
        modules = self._scan_modules(self.modules_dir)
        downloads = self._load_downloads()
        total_downloads = sum(downloads.values())
        top = sorted(downloads.items(), key=lambda x: x[1], reverse=True)[:10]
        categories = {}
        for m in modules:
            cat = m.get("category", "其它")
            categories[cat] = categories.get(cat, 0) + 1
        self._ok({
            "total_modules": len(modules),
            "total_downloads": total_downloads,
            "top_downloaded": [{"name": n, "count": c} for n, c in top],
            "categories": categories,
        })

    def _handle_categories(self):
        modules = self._scan_modules(self.modules_dir)
        cats = {}
        for m in modules:
            cat = m.get("category", "其它")
            cats[cat] = cats.get(cat, 0) + 1
        self._ok({"categories": cats})

    # ── 上传 ──

    @staticmethod
    def _parse_multipart(content_type: str, body: bytes) -> dict:
        """解析 multipart/form-data，返回 {field_name: (filename, content_bytes, content_type)}。"""
        result = {}
        try:
            boundary = content_type.split("boundary=")[1].strip()
        except (IndexError, AttributeError):
            return result
        delimiter = f"--{boundary}".encode()
        parts = body.split(delimiter)
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            try:
                # 去掉前导 \r\n 或 \n
                part = part.lstrip(b"\r\n")
                parser = BytesParser()
                header_end = part.find(b"\r\n\r\n")
                if header_end < 0:
                    header_end = part.find(b"\n\n")
                    if header_end < 0:
                        continue
                    sep_len = 2
                else:
                    sep_len = 4
                headers_block = part[:header_end]
                try:
                    headers = parser.parsebytes(
                        b"Content-Type: text/plain\r\n" + headers_block
                    )
                except Exception:
                    continue
                disp = headers.get("Content-Disposition", "")
                name_match = re.search(r'name="([^"]+)"', disp)
                if not name_match:
                    continue
                name = name_match.group(1)
                filename_match = re.search(r'filename="([^"]+)"', disp)
                filename = filename_match.group(1) if filename_match else None
                content = part[header_end + sep_len:]
                # 去掉尾随 \r\n 和 boundary 尾部
                content = content.rstrip(b"\r\n-")
                result[name] = (filename, content, headers.get("Content-Type", ""))
            except Exception:
                continue
        return result

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """净化上传文件名：移除路径分隔符、拒绝 ..、只保留安全字符。

        Args:
            filename: 原始文件名。

        Returns:
            净化后的文件名，如果文件名非法则返回空字符串。
        """
        if not filename:
            return ""
        # 拒绝包含 .. 的文件名
        if ".." in filename:
            return ""
        # 移除路径分隔符
        filename = filename.replace("\\", "").replace("/", "")
        # 只保留字母数字、下划线、连字符、点
        safe = re.sub(r"[^a-zA-Z0-9_\-.]", "", filename)
        # 拒绝空文件名或以点开头的隐藏文件
        if not safe or safe.startswith("."):
            return ""
        return safe

    @staticmethod
    def _check_upload_rate(client_ip: str) -> bool:
        """检查上传速率限制（每 IP 每分钟最多 _MAX_UPLOAD_RATE_PER_IP 次）。

        Args:
            client_ip: 客户端 IP 地址。

        Returns:
            True 如果允许上传。
        """
        if MarketHandler._rate_limit_disabled:
            return True
        now = time.time()
        rate_map = MarketHandler._upload_rate_map
        hits = rate_map.get(client_ip, [])
        # 清理过期的
        cutoff = now - _UPLOAD_RATE_WINDOW
        hits = [t for t in hits if t >= cutoff]
        if len(hits) >= _MAX_UPLOAD_RATE_PER_IP:
            rate_map[client_ip] = hits
            return False
        hits.append(now)
        rate_map[client_ip] = hits
        return True

    @staticmethod
    def _check_zip_safety(content: bytes) -> bool:
        """检查 zip 文件内容是否安全（ZipSlip 防护 + 内容检查）。

        拒绝：
          - 符号链接条目
          - 包含 .. 的路径
          - 绝对路径
          - __pycache__ 目录
          - .pyc 编译文件

        Args:
            content: zip 文件的原始字节。

        Returns:
            True 如果 zip 文件安全。
        """
        import io
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                for info in zf.infolist():
                    # 检查是否为符号链接（Python 3.12+ 有 is_symlink，3.11 兼容回退）
                    is_link = (
                        info.is_symlink()
                        if hasattr(info, 'is_symlink')
                        else bool(getattr(info.external_attr, '__bool__', lambda: False)())
                        if hasattr(info, 'external_attr') and (info.external_attr >> 16) == 0o120000
                        else False
                    )
                    if is_link:
                        _log.warning("上传 zip 包含符号链接: %s", info.filename)
                        return False

                    # ZipSlip: 拒绝 .. 和绝对路径
                    filename = info.filename
                    if ".." in filename or filename.startswith("/"):
                        _log.warning("上传 zip 包含不安全路径: %s", filename)
                        return False

                    # 拒绝 __pycache__ 目录
                    if "__pycache__" in filename.replace("\\", "/").split("/"):
                        _log.warning("上传 zip 包含 __pycache__: %s", filename)
                        return False

                    # 拒绝 .pyc 编译文件
                    if filename.endswith(".pyc"):
                        _log.warning("上传 zip 包含 .pyc 文件: %s", filename)
                        return False

                return True
        except zipfile.BadZipFile:
            _log.warning("上传的文件不是有效的 zip")
            return False
        except Exception:
            _log.warning("zip 安全检查异常: %s", traceback.format_exc())
            return False

    def _handle_upload(self):
        if not self._is_authenticated():
            self.send_error(401)
            return

        # ── IP 速率限制 ──
        client_ip = self.client_address[0]
        if not self._check_upload_rate(client_ip):
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"ok": False, "error": "上传过于频繁，请稍后再试"},
                ensure_ascii=False
            ).encode("utf-8"))
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error(400)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > _MAX_UPLOAD_SIZE:
            self.send_error(413)
            return

        body = self.rfile.read(length)
        parts = self._parse_multipart(content_type, body)
        file_part = parts.get("file")
        if not file_part or not file_part[0]:
            self.send_error(400)
            return
        filename_orig, content, mime = file_part

        # ── MIME 类型校验（基于实际文件 content-type）──
        if mime:
            mime_lower = mime.lower()
            is_zip = "application/zip" in mime_lower or "application/x-zip" in mime_lower
            is_octet = "application/octet-stream" in mime_lower
            is_py = "text/x-python" in mime_lower or "text/plain" in mime_lower
            if not (is_zip or is_octet or is_py):
                self.send_response(415)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(
                    {"ok": False, "error": "仅接受 zip 模块包或 .py 文件"},
                    ensure_ascii=False
                ).encode("utf-8"))
                return

        # ── 文件名净化 ──
        filename = self._sanitize_filename(filename_orig)
        if not filename:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"ok": False, "error": "文件名包含非法字符"},
                ensure_ascii=False
            ).encode("utf-8"))
            return

        # ── 仅接受 .py 或 .zip 文件 ──
        if not (filename.endswith(".py") or filename.endswith(".zip")):
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"ok": False, "error": "只接受 .py 模块文件或 .zip 模块包"},
                ensure_ascii=False
            ).encode("utf-8"))
            return

        # ── zip 文件安全检查 ──
        if filename.endswith(".zip"):
            if not self._check_zip_safety(content):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(
                    {"ok": False, "error": "模块包包含不安全内容"},
                    ensure_ascii=False
                ).encode("utf-8"))
                return

        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", filename[:-3] if filename.endswith(".py") else filename[:-4])
        info = self._parse_module_source(content)
        if info.get("version"):
            sig_part = parts.get("signature")
            sig = sig_part[1].decode("utf-8").strip() if sig_part else ""
            if self.strict_sign and self.sign_secret:
                if not sig and not self.upload_token:
                    self._ok({"ok": False, "error": "需要签名"})
                    return
                if sig and not verify_signature(safe_name, info["version"], sig, self.sign_secret):
                    self._ok({"ok": False, "error": "签名无效"})
                    return
        dest = os.path.join(self.modules_dir, filename)
        os.makedirs(self.modules_dir, exist_ok=True)  # 确保目录存在
        with open(dest, "wb") as f:
            f.write(content)
        _log.info("上传模块: %s (%d bytes)", filename, len(content))
        self._ok({"ok": True, "name": safe_name})

    # ── 模块文件扫描 ──

    def _scan_modules(self, dir_path: str) -> List[dict]:
        if not os.path.isdir(dir_path):
            return []
        results = []
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(dir_path, fname)
            info = self._parse_module_file(filepath)
            info["name"] = info.get("name", fname[:-3])
            results.append(info)
        return results

    @staticmethod
    def _parse_module_file(filepath: str) -> dict:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return MarketHandler._parse_module_source(f.read().encode("utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _parse_module_source(content: bytes) -> dict:
        info = {}
        text = content.decode("utf-8", errors="replace")
        patterns = {
            "name": r'^name\s*=\s*["\']([^"\']+)["\']',
            "version": r'^version\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)',
            "author": r'^author\s*=\s*["\']([^"\']+)["\']',
            "description": r'^description\s*=\s*["\']([^"\']+)["\']',
            "category": r'^__category__\s*=\s*["\']([^"\']+)["\']',
        }
        for line in text.split("\n"):
            for key, pat in patterns.items():
                m = re.match(pat, line.strip())
                if m:
                    if key == "version":
                        info[key] = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
                    else:
                        info[key] = m.group(1)
        return info

    # ── 下载统计 ──

    def _downloads_file(self) -> str:
        return os.path.join(self.modules_dir, ".download_stats.json")

    def _load_downloads(self) -> Dict[str, int]:
        path = self._downloads_file()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _record_download(self, name: str):
        downloads = self._load_downloads()
        downloads[name] = downloads.get(name, 0) + 1
        try:
            with open(self._downloads_file(), "w") as f:
                json.dump(downloads, f)
        except Exception:
            pass

import asyncio
import os
import json
import re
import time
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from ...core.module import Module
from ...core.kernel.events import GroupMessageEvent, GameChatEvent
_log = logging.getLogger(__name__)

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)

# ── 敏感信息遮蔽 ──
# 需要遮蔽的字段名模式
_SENSITIVE_FIELD_PATTERNS = re.compile(
    r"(token|password|secret|key|authorization|api_key|access_key)",
    re.IGNORECASE,
)
# IP 地址正则
_IP_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
)
# 默认保留天数和最大日志目录大小
_DEFAULT_RETENTION_DAYS = 7
_DEFAULT_MAX_LOG_DIR_SIZE_MB = 500  # 默认最大 500 MB


def _mask_sensitive(data: dict) -> dict:
    """递归遮蔽字典中的敏感字段。

    遮蔽内容：
      - 键名匹配 token/password/secret/key 等模式的字段值
      - raw 数据中包含的 IP 地址

    Args:
        data: 原始数据字典。

    Returns:
        遮蔽后的数据字典（浅拷贝）。
    """
    if not isinstance(data, dict):
        return data

    masked = {}
    for key, value in data.items():
        # 检查字段名是否为敏感字段
        if isinstance(key, str) and _SENSITIVE_FIELD_PATTERNS.search(key):
            masked[key] = "[REDACTED]"
            continue
        # 递归处理嵌套字典
        if isinstance(value, dict):
            masked[key] = _mask_sensitive(value)
        elif isinstance(value, str):
            # 遮蔽 IP 地址
            masked[key] = _IP_PATTERN.sub("[IP_REDACTED]", value)
        else:
            masked[key] = value
    return masked


def _get_dir_size_mb(dir_path: str) -> float:
    """计算目录总大小（MB）。

    Args:
        dir_path: 目录路径。

    Returns:
        目录大小（MB）。
    """
    total = 0
    try:
        for root, _, files in os.walk(dir_path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError as e:
                    _log.debug("chat._get_dir_size_mb: %s", e)
    except OSError as e:
        _log.debug("chat._get_dir_size_mb: %s", e)
    return total / (1024 * 1024)


class ChatLogService:
    """聊天日志存储与查询服务。"""

    def __init__(
        self,
        base_dir: str,
        max_records: int = 100,
        enable_images: bool = True,
        retention_days: int = _DEFAULT_RETENTION_DAYS,
        max_log_size_mb: int = _DEFAULT_MAX_LOG_DIR_SIZE_MB,
    ):
        self._base = base_dir
        self._max = max_records
        self._images_enabled = enable_images
        self._retention_days = retention_days
        self._max_log_size_mb = max_log_size_mb
        self._write_lock = asyncio.Lock()

    def _msgs_dir(self) -> str:
        """返回当天消息日志目录路径。"""
        now = datetime.now()
        path = os.path.join(self._base, "msgs", now.strftime("%Y%m%d"))
        os.makedirs(path, exist_ok=True)
        return path

    def _pics_dir(self) -> str:
        """返回图片存储目录路径。"""
        path = os.path.join(self._base, "pics")
        os.makedirs(path, exist_ok=True)
        return path

    def _current_file(self) -> str:
        """返回当前小时的 JSONL 日志文件路径。"""
        hour = datetime.now().strftime("%H")
        return os.path.join(self._msgs_dir(), f"{hour}.jsonl")

    async def record_message(
        self,
        source: str,
        user_id: int,
        group_id: int,
        nickname: str,
        content: str,
        raw: dict,
    ) -> str:
        """记录一条消息，处理图片保存，返回生成的 message_id。

        敏感字段（IP、token 等）在记录前遮蔽。
        """
        msg_id = f"msg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        # ── 遮蔽 raw 中的敏感字段 ──
        safe_raw = _mask_sensitive(raw) if raw else {}
        record = {
            "id": msg_id,
            "timestamp": time.time(),
            "source": source,
            "user_id": user_id,
            "group_id": group_id,
            "nickname": nickname,
            "content": content,
            "raw": safe_raw,
        }

        if self._images_enabled and source == "group":
            cq_images = self._extract_images(content)
            if cq_images:
                record["images"] = cq_images

        try:
            async with self._write_lock:
                with open(self._current_file(), "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            _logger.error("写入聊天日志失败: %s", e)

        self._cleanup_old_logs()
        return msg_id

    @staticmethod
    def _extract_images(text: str) -> List[Dict[str, str]]:
        """提取 CQ 图片码，返回包含 url 的列表。"""
        import re
        matches = re.findall(r'\[CQ:image,file=([^\]]+)\]', text)
        return [{"url": m} for m in matches]

    def _cleanup_old_logs(self):
        """删除超过保留天数的旧日志目录 + 磁盘空间检查。

        防止磁盘耗尽：
          1. 按日期清理过期日志
          2. 检查总大小，超限时清理最旧日志
        """
        try:
            base = os.path.join(self._base, "msgs")
            if not os.path.exists(base):
                return

            # ── 清理 1: 按保留天数 ──
            cutoff = datetime.now() - timedelta(days=self._retention_days)
            for dirname in os.listdir(base):
                dirpath = os.path.join(base, dirname)
                if not os.path.isdir(dirpath):
                    continue
                try:
                    dir_date = datetime.strptime(dirname, "%Y%m%d")
                    if dir_date < cutoff:
                        import shutil
                        shutil.rmtree(dirpath)
                        _logger.info("已清理过期日志目录: %s", dirname)
                except ValueError as e:
                    _log.debug("chat._cleanup_old_logs: %s", e)

            # ── 清理 2: 磁盘空间检查 ──
            total_size_mb = _get_dir_size_mb(base)
            if total_size_mb > self._max_log_size_mb:
                _logger.warning(
                    "日志目录大小 %.1f MB 超过限制 %d MB, 开始清理最旧日志",
                    total_size_mb, self._max_log_size_mb,
                )
                # 按日期升序排列，删除最旧的直到大小低于限制
                dated_dirs = []
                for dirname in os.listdir(base):
                    dirpath = os.path.join(base, dirname)
                    if not os.path.isdir(dirpath):
                        continue
                    try:
                        dir_date = datetime.strptime(dirname, "%Y%m%d")
                        dated_dirs.append((dir_date, dirpath))
                    except ValueError as e:
                        _log.debug("chat.chat: %s", e)
                dated_dirs.sort(key=lambda x: x[0])
                # 保留最近几天的
                while (len(dated_dirs) > max(2, self._retention_days) and
                       _get_dir_size_mb(base) > self._max_log_size_mb * 0.8):
                    _, oldest_path = dated_dirs.pop(0)
                    import shutil
                    shutil.rmtree(oldest_path)
                    _logger.info("已清理最旧日志目录（空间不足）: %s", oldest_path)
        except Exception as e:
            _logger.error("清理过期日志失败: %s", e)

    async def search_messages(
        self,
        group_id: int = None,
        user_id: int = None,
        keyword: str = None,
        start_time: float = None,
        end_time: float = None,
        limit: int = 50,
    ) -> List[Dict]:
        """根据条件搜索消息，返回列表（按时间正序）。"""
        results: List[Dict] = []
        today_dir = self._msgs_dir()
        if not os.path.exists(today_dir):
            return results
        for fname in sorted(os.listdir(today_dir)):
            if not fname.endswith(".jsonl"):
                continue
            path = os.path.join(today_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    rec = self._parse_record(line)
                    if rec is None:
                        continue
                    if not self._match_filter(
                        rec, group_id, user_id, keyword,
                        start_time, end_time,
                    ):
                        continue
                    results.append(rec)
                    if len(results) >= limit:
                        return results
        return results

    @staticmethod
    def _parse_record(line: str) -> Optional[Dict]:
        """解析一行 JSONL 记录，失败返回 None。"""
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _match_filter(
        rec: Dict,
        group_id: Optional[int],
        user_id: Optional[int],
        keyword: Optional[str],
        start_time: Optional[float],
        end_time: Optional[float],
    ) -> bool:
        """检查记录是否匹配过滤条件。"""
        if group_id is not None and rec.get("group_id") != group_id:
            return False
        if user_id is not None and rec.get("user_id") != user_id:
            return False
        if keyword and keyword not in rec.get("content", ""):
            return False
        ts = rec.get("timestamp", 0)
        if start_time is not None and ts < start_time:
            return False
        if end_time is not None and ts > end_time:
            return False
        return True


class GlobalChatLogModule(Module):
    """全局聊天日志模块。"""
    background = True
    """全局聊天日志模块，记录聊天消息并提供查询服务。"""

    name = "global_chat_log"
    mid = 100  # TIER_DAEMON  # daemon: 系统守护
    tier = 100  # deprecated, use mid
    version = (1, 0, 0)
    required_services = ["config", "message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._service: Optional[ChatLogService] = None

    async def on_init(self):
        """注册配置节、初始化日志服务、订阅事件。"""
        cfg = self.config.get("全局聊天日志")
        if cfg is None:
            cfg = {}
        if not cfg.get("启用", True):
            return

        base = os.path.join(self.data_dir)
        self._service = ChatLogService(
            base,
            max_records=cfg.get("最大记录数", 100),
            enable_images=cfg.get("启用图片存储", False),
            retention_days=cfg.get("日志保留天数", _DEFAULT_RETENTION_DAYS),
            max_log_size_mb=cfg.get(
                "日志最大大小MB", _DEFAULT_MAX_LOG_DIR_SIZE_MB
            ),
        )
        self._root_services.register("global_chat_log", self._service)

        self.listen(GroupMessageEvent, self._on_group_msg, priority=0)
        self.listen(GameChatEvent, self._on_game_chat, priority=0)

    async def _on_group_msg(self, event):
        """处理群消息事件，记录到日志。"""
        if event.handled:
            return
        await self._service.record_message(
            source="group",
            user_id=event.user_id,
            group_id=event.group_id,
            nickname=event.nickname,
            content=event.message,
            raw=event.raw_data,
        )

    async def _on_game_chat(self, event):
        """处理游戏聊天事件，记录到日志。"""
        await self._service.record_message(
            source="game",
            user_id=0,
            group_id=0,
            nickname=event.player_name,
            content=event.message,
            raw={},
        )

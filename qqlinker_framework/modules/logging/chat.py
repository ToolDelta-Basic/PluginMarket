"""全局聊天日志服务，记录、查询所有群消息和游戏消息。"""
import asyncio
import os
import json
import time
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from ...core.module import Module
from ...core.events import GroupMessageEvent, GameChatEvent

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


class ChatLogService:
    """聊天日志存储与查询服务。"""

    def __init__(
        self,
        base_dir: str,
        max_records: int = 100,
        enable_images: bool = True,
    ):
        self._base = base_dir
        self._max = max_records
        self._images_enabled = enable_images
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
        """记录一条消息，处理图片保存，返回生成的 message_id。"""
        msg_id = f"msg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        record = {
            "id": msg_id,
            "timestamp": time.time(),
            "source": source,
            "user_id": user_id,
            "group_id": group_id,
            "nickname": nickname,
            "content": content,
            "raw": raw,
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
        """删除超过 7 天的旧日志目录。"""
        try:
            base = os.path.join(self._base, "msgs")
            if not os.path.exists(base):
                return
            cutoff = datetime.now() - timedelta(days=7)
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
                except ValueError:
                    pass
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
    """全局聊天日志模块，记录聊天消息并提供查询服务。"""

    name = "global_chat_log"
    uid = 100  # daemon: 系统守护
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
        )
        self.services.register("global_chat_log", self._service)

        self.listen("GroupMessageEvent", self._on_group_msg, priority=0)
        self.listen("GameChatEvent", self._on_game_chat, priority=0)

    async def _on_group_msg(self, event: GroupMessageEvent):
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

    async def _on_game_chat(self, event: GameChatEvent):
        """处理游戏聊天事件，记录到日志。"""
        await self._service.record_message(
            source="game",
            user_id=0,
            group_id=0,
            nickname=event.player_name,
            content=event.message,
            raw={},
        )

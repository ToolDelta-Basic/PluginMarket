"""全局聊天日志服务，记录、查询所有群消息和游戏消息，支持图片存储。"""
import os
import json
import time
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from ..core.module import Module
from ..core.events import GroupMessageEvent, GameChatEvent

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


class ChatLogService:
    """聊天日志存储与查询服务。"""

    def __init__(self, base_dir: str, max_records: int = 100, enable_images: bool = True):
        self._base = base_dir
        self._max = max_records
        self._images_enabled = enable_images

    def _msgs_dir(self) -> str:
        now = datetime.now()
        path = os.path.join(self._base, "msgs", now.strftime("%Y%m%d"))
        os.makedirs(path, exist_ok=True)
        return path

    def _pics_dir(self) -> str:
        path = os.path.join(self._base, "pics")
        os.makedirs(path, exist_ok=True)
        return path

    def _current_file(self) -> str:
        hour = datetime.now().strftime("%H")
        return os.path.join(self._msgs_dir(), f"{hour}.jsonl")

    async def record_message(self, source: str, user_id: int, group_id: int,
                               nickname: str, content: str, raw: dict) -> str:
        """记录一条消息，处理图片保存，返回生成的 message_id。"""
        msg_id = f"msg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        record = {
            "id": msg_id,
            "timestamp": time.time(),
            "source": source,          # "group" 或 "game"
            "user_id": user_id,
            "group_id": group_id,
            "nickname": nickname,
            "content": content,
            "raw": raw,
        }

        # 图片处理预留
        if self._images_enabled and source == "group":
            cq_images = self._extract_images(content)
            if cq_images:
                # 目前只记录图片URL，不下载
                record["images"] = cq_images

        # 写入 JSONL
        try:
            with open(self._current_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            _logger.error("写入聊天日志失败: %s", e)

        # 清理过期日志（保持磁盘占用）
        self._cleanup_old_logs()
        return msg_id

    @staticmethod
    def _extract_images(text: str) -> List[Dict[str, str]]:
        """提取 CQ 图片码，返回包含 url 的列表。"""
        import re
        pattern = r'\[CQ:image,file=([^\]]+)\]'
        matches = re.findall(pattern, text)
        return [{"url": m} for m in matches]

    def _cleanup_old_logs(self):
        """删除超过保留期限的日志文件（默认7天）。"""
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

    async def search_messages(self, group_id: int = None, user_id: int = None,
                              keyword: str = None, start_time: float = None,
                              end_time: float = None, limit: int = 50) -> List[Dict]:
        """根据条件搜索消息，返回列表（按时间正序）。"""
        # 简化实现：仅扫描今天的日志（按需求可扩展）
        results = []
        today_dir = self._msgs_dir()
        if not os.path.exists(today_dir):
            return []
        for fname in sorted(os.listdir(today_dir)):
            if not fname.endswith(".jsonl"):
                continue
            with open(os.path.join(today_dir, fname), "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # 过滤
                    if group_id is not None and rec.get("group_id") != group_id:
                        continue
                    if user_id is not None and rec.get("user_id") != user_id:
                        continue
                    if keyword and keyword not in rec.get("content", ""):
                        continue
                    ts = rec.get("timestamp", 0)
                    if start_time and ts < start_time:
                        continue
                    if end_time and ts > end_time:
                        continue
                    results.append(rec)
                    if len(results) >= limit:
                        return results
        return results


class GlobalChatLogModule(Module):
    """全局聊天日志模块，记录聊天消息并提供查询服务。"""

    name = "global_chat_log"
    version = (1, 0, 0)
    required_services = ["config", "message"]

    async def on_init(self):
        self.config.register_section("全局聊天日志", {
            "启用": True,
            "最大记录数": 100,
            "启用图片存储": False,
        })
        cfg = self.config.get("全局聊天日志")
        if not cfg.get("启用", True):
            return

        base = os.path.join(self.get_data_dir())
        self._service = ChatLogService(
            base,
            max_records=cfg.get("最大记录数", 100),
            enable_images=cfg.get("启用图片存储", False),
        )
        self.services.register("global_chat_log", self._service)

        self.listen("GroupMessageEvent", self._on_group_msg, priority=0)
        self.listen("GameChatEvent", self._on_game_chat, priority=0)

    async def _on_group_msg(self, event: GroupMessageEvent):
        if event.handled:
            return  # 避免重复记录已处理的命令
        await self._service.record_message(
            source="group",
            user_id=event.user_id,
            group_id=event.group_id,
            nickname=event.nickname,
            content=event.message,
            raw=event.raw_data,
        )

    async def _on_game_chat(self, event: GameChatEvent):
        await self._service.record_message(
            source="game",
            user_id=0,                # 游戏内暂无QQ号
            group_id=0,
            nickname=event.player_name,
            content=event.message,
            raw={},
        )

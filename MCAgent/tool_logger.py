import json
import os
import time
from typing import TYPE_CHECKING, Dict, Any, Optional, List
from tooldelta import Player
if TYPE_CHECKING:
    from . import MCAgent
    
class ToolLogger:
    def __init__(self, plugin: "MCAgent"):
        self.plugin = plugin
        self.log_file_path = self._get_log_file_path()
        self.logged_tools = [
            "execute_command",
            "fill_blocks",
            "place_command_block"
        ]
    
    def _get_log_file_path(self) -> str:
        self.plugin.make_data_path()
        date_str = time.strftime("%Y-%m-%d", time.localtime())
        log_filename = f"tool_calls_{date_str}.json"
        return os.path.join(self.plugin.data_path, log_filename)
    
    def _load_logs(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.log_file_path):
            return []
        
        try:
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    
    def _save_logs(self, logs: List[Dict[str, Any]]) -> None:
        try:
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"保存日志失败: {e}")
    
    def log_tool_call(
        self,
        tool_name: str,
        caller: Optional[Player],
        parameters: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        if tool_name not in self.logged_tools:
            return
        
        timestamp = int(time.time())
        date_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        
        log_entry = {
            "timestamp": timestamp,
            "datetime": date_time,
            "tool_name": tool_name,
            "caller": {
                "name": caller.name if caller else "System",
                "uuid": caller.uuid if caller else None,
                "xuid": caller.xuid if caller else None
            },
            "parameters": parameters,
            "result": {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "error": result.get("error", None)
            }
        }
        
        logs = self._load_logs()
        logs.append(log_entry)
        self._save_logs(logs)
    
    def get_logs_by_tool(self, tool_name: str) -> List[Dict[str, Any]]:
        logs = self._load_logs()
        return [log for log in logs if log.get("tool_name") == tool_name]
    
    def get_logs_by_caller(self, caller_name: str) -> List[Dict[str, Any]]:
        logs = self._load_logs()
        return [log for log in logs if log.get("caller", {}).get("name") == caller_name]
    
    def get_logs_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        logs = self._load_logs()
        return [log for log in logs if log.get("datetime", "").startswith(date_str)]
    
    def clear_old_logs(self, days: int = 7) -> int:
        logs = self._load_logs()
        current_time = int(time.time())
        cutoff_time = current_time - (days * 24 * 60 * 60)
        
        filtered_logs = [log for log in logs if log.get("timestamp", 0) >= cutoff_time]
        removed_count = len(logs) - len(filtered_logs)
        
        if removed_count > 0:
            self._save_logs(filtered_logs)
        
        return removed_count

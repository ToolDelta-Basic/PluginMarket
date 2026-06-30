import os
import json
import time
import uuid
from typing import Any


class TaskStore:
    """TaskStore manages unfinished import tasks persistence.

    Structure of file:
    {
        "tasks": [
            {
                "task_id": str,
                "world_name": str,
                "dimension": int,
                "source_start": list[int, int, int],
                "source_end": list[int, int, int],
                "dest_start": list[int, int, int],
                "progress_index": int,
                "total_chunks": int,
                "updated_at": int
            }
        ]
    }
    """

    def __init__(self, file_path: str):
        self.file_path = file_path

    def _empty(self) -> dict[str, Any]:
        return {"tasks": []}

    def _read(self) -> dict[str, Any]:
        if not os.path.isfile(self.file_path):
            return self._empty()
        try:
            with open(self.file_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if not isinstance(data, dict) or "tasks" not in data or not isinstance(data["tasks"], list):
                    return self._empty()
                return data
        except Exception:
            return self._empty()

    def _write(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

    def list_unfinished(self) -> list[dict[str, Any]]:
        data = self._read()
        result: list[dict[str, Any]] = []
        for task in data["tasks"]:
            try:
                if int(task.get("progress_index", 0)) < int(task.get("total_chunks", 0)):
                    result.append(task)
            except Exception:
                continue
        return result

    def add_task(self, task: dict[str, Any]) -> str:
        data = self._read()
        if "task_id" not in task or not task["task_id"]:
            task["task_id"] = str(uuid.uuid4())
        task["updated_at"] = int(time.time())
        data["tasks"].append(task)
        self._write(data)
        return task["task_id"]

    def update_progress(self, task_id: str, progress_index: int) -> None:
        data = self._read()
        changed = False
        for task in data["tasks"]:
            if task.get("task_id") == task_id:
                task["progress_index"] = int(progress_index)
                task["updated_at"] = int(time.time())
                changed = True
                break
        if changed:
            self._write(data)

    def remove_task(self, task_id: str) -> None:
        data = self._read()
        new_tasks: list[dict[str, Any]] = []
        for task in data["tasks"]:
            if task.get("task_id") != task_id:
                new_tasks.append(task)
        data["tasks"] = new_tasks
        self._write(data)

    def find_task_by_id(self, task_id: str) -> dict[str, Any] | None:
        data = self._read()
        for task in data["tasks"]:
            if task.get("task_id") == task_id:
                return task
        return None 

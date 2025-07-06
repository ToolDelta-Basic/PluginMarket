from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class ChunkPos:
    posx: int = 0
    posz: int = 0


class RequestQueue:
    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._pending_list: dict[ChunkPos, bool] = {}
        self._wait_to_unix_time: dict[ChunkPos, int] = {}

    def append_request(self, chunks: list[ChunkPos]):
        with self._mu:
            for i in chunks:
                self._pending_list[i] = True

    def pop_request(self) -> list[ChunkPos]:
        with self._mu:
            result: list[ChunkPos] = []

            for key in self._pending_list:
                if key not in self._wait_to_unix_time:
                    result.append(key)

            for key in result:
                del self._pending_list[key]

            return result

    def set_wait_to_unix_time(self, chunks: list[ChunkPos], wait_time_seconds: int):
        with self._mu:
            target_time = int(time.time()) + wait_time_seconds
            for i in chunks:
                self._wait_to_unix_time[i] = target_time

    def flush_wait_to_unix_time(self):
        with self._mu:
            current_time = int(time.time())
            keys_to_delete: list[ChunkPos] = []

            for key, value in self._wait_to_unix_time.items():
                if current_time >= value:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._wait_to_unix_time[key]

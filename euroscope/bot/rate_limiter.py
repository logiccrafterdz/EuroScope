import asyncio
import time
from typing import Tuple


class RateLimiter:
    def __init__(self, max_requests: int, window_minutes: int):
        self.max_requests = max_requests
        self.window_seconds = max(0, window_minutes) * 60
        self._lock = asyncio.Lock()
        self._requests: dict[int, list[float]] = {}

    async def is_allowed(self, chat_id: int) -> Tuple[bool, int]:
        now = time.monotonic()
        async with self._lock:
            timestamps = self._requests.get(chat_id, [])
            if self.window_seconds > 0:
                timestamps = [t for t in timestamps if now - t <= self.window_seconds]
            else:
                timestamps = []

            if len(timestamps) < self.max_requests:
                timestamps.append(now)
                self._requests[chat_id] = timestamps
                return True, self.max_requests - len(timestamps)

            self._requests[chat_id] = timestamps
            return False, 0

    async def reset(self, chat_id: int):
        async with self._lock:
            self._requests.pop(chat_id, None)

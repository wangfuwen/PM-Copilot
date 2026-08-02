"""Simple in-memory per-IP daily rate limiter for public demos."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock


class DailyRateLimiter:
    def __init__(self, limit: int):
        self.limit = limit
        self._lock = Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> tuple[bool, int, int]:
        """
        Returns (allowed, remaining, limit).
        """
        if self.limit <= 0:
            return True, -1, self.limit

        now = time.time()
        window_start = now - 86400
        with self._lock:
            hits = [t for t in self._hits[key] if t >= window_start]
            self._hits[key] = hits
            if len(hits) >= self.limit:
                return False, 0, self.limit
            hits.append(now)
            self._hits[key] = hits
            remaining = max(0, self.limit - len(hits))
            return True, remaining, self.limit

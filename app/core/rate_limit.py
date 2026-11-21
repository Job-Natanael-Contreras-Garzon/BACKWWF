import time
from collections import deque


# shortcut: in-memory sliding-window rate limiter (single-process only), migrate to Redis in HU-08.
class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def check_and_record(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        for stale_key in [k for k, b in self._hits.items() if not b or b[-1] <= cutoff]:
            del self._hits[stale_key]

        bucket = self._hits.get(key)
        if bucket is None:
            if limit <= 0:
                return False
            self._hits[key] = deque([now])
            return True
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()

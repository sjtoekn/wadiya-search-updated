"""Request-body size protection (framework-independent; api/app.py feeds it the request stream)."""
from __future__ import annotations

import time
import threading

from typing import Optional

MAX_LOGIN_BODY = 4096          # bytes; a login payload is a few dozen bytes


class BodyTooLarge(Exception):
    pass


def parse_declared_length(value) -> Optional[int]:
    """Content-Length header -> int. None if absent; ValueError if malformed."""
    if value is None:
        return None
    v = value.strip()
    if not v or not v.isascii() or not v.isdigit() or len(v) > 12:
        raise ValueError("invalid content-length")
    return int(v)


class BodyLimiter:
    """Rejects early on a declared Content-Length over the limit, and also counts the bytes actually streamed
    (covers chunked uploads and clients that lie about Content-Length)."""
    def __init__(self, limit: int):
        self.limit, self.total, self._chunks = limit, 0, []

    def declare(self, content_length_header) -> None:
        n = parse_declared_length(content_length_header)
        if n is not None and n > self.limit:
            raise BodyTooLarge(f"declared {n} bytes > limit {self.limit}")

    def feed(self, chunk: bytes) -> None:
        self.total += len(chunk)
        if self.total > self.limit:
            raise BodyTooLarge(f"body exceeds {self.limit} bytes")
        self._chunks.append(chunk)

    def body(self) -> bytes:
        return b"".join(self._chunks)


class SubmitLimiter:
    """Limit public website submissions per client key in memory."""
    def __init__(self, limit: int = 10, window: int = 600, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits = {}
        self._lock = threading.Lock()

    def _recent_locked(self, key, now):
        recent = [t for t in self._hits.get(key, []) if now - t < self.window]
        if recent:
            self._hits[key] = recent
        else:
            self._hits.pop(key, None)
        return recent

    def _recent(self, key):
        with self._lock:
            return self._recent_locked(key, self._clock())

    def allowed(self, key) -> bool:
        with self._lock:
            return len(self._recent_locked(key, self._clock())) < self.limit

    def hit(self, key) -> None:
        with self._lock:
            now = self._clock()
            self._recent_locked(key, now)
            self._hits.setdefault(key, []).append(now)
            if len(self._hits) > 10000:
                cutoff = now - self.window
                for k in list(self._hits):
                    self._recent_locked(k, cutoff)

    def retry_after(self, key) -> int:
        with self._lock:
            recent = self._recent_locked(key, self._clock())
            if not recent:
                return 0
            remaining = self.window - (self._clock() - recent[0])
            return max(1, int(remaining + 0.999))

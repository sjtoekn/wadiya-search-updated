"""Request-body size protection (framework-independent; api/app.py feeds it the request stream)."""
from __future__ import annotations

import time

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

    def _recent(self, key):
        now = self._clock()
        self._hits[key] = [
            t for t in self._hits.get(key, [])
            if now - t < self.window
        ]
        return self._hits[key]

    def allowed(self, key) -> bool:
        return len(self._recent(key)) < self.limit

    def hit(self, key) -> None:
        self._recent(key).append(self._clock())

    def retry_after(self, key) -> int:
        recent = self._recent(key)
        if not recent:
            return 0

        remaining = self.window - (self._clock() - recent[0])
        return max(1, int(remaining + 0.999))

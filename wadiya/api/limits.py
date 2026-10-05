"""Request-body size protection (framework-independent; api/app.py feeds it the request stream)."""
from __future__ import annotations

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

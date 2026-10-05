"""SSRF-safe HTTP fetcher (stdlib only).
- every URL and every redirect hop is validated and DNS-resolved by check_url()
- the TCP connection is pinned to the vetted IP (no second DNS lookup => no rebinding)
- TLS SNI / certificate checks use the original hostname
- size, time, content-type and encoding limits; bounded redirects and retries."""
from __future__ import annotations

import http.client
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlsplit

from .urls import UnsafeURLError, UrlPolicy, check_url, normalize_url

HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_REDIRECTS = (301, 302, 303, 307, 308)
_RETRY_STATUS = (429, 500, 502, 503, 504)


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: Optional[int]
    content_type: Optional[str]
    body: bytes
    elapsed_ms: float = 0.0
    error: Optional[str] = None
    redirects: int = 0
    x_robots_tag: tuple = ()          # each X-Robots-Tag header instance, verbatim

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and 200 <= self.status < 300


class _Pinned:
    def _connect_pinned(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return sock


class _PinnedHTTP(_Pinned, http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = self._connect_pinned()


class _PinnedHTTPS(_Pinned, http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout, ctx):
        super().__init__(host, port, timeout=timeout, context=ctx)
        self._ip, self._ctx = ip, ctx

    def connect(self):
        self.sock = self._ctx.wrap_socket(self._connect_pinned(), server_hostname=self.host)


class Fetcher:
    def __init__(self, settings, policy: Optional[UrlPolicy] = None,
                 resolver: Callable = socket.getaddrinfo, sleep: Callable = time.sleep):
        self.s = settings
        self.policy = policy or UrlPolicy(allowed_ports=settings.allowed_ports,
                                          allow_private_networks=settings.allow_private_networks)
        self._resolver, self._sleep = resolver, sleep
        self._ctx = ssl.create_default_context()

    # ------------------------------------------------------------------ public
    def fetch(self, url: str, *, accept_types=HTML_TYPES, max_bytes: Optional[int] = None,
              redirect_filter: Optional[Callable[[str], bool]] = None) -> FetchResult:
        limit = max_bytes or self.s.max_response_bytes
        start = time.monotonic()
        attempt = 0
        while True:
            res = self._follow(url, accept_types, limit, redirect_filter,
                               deadline=time.monotonic() + self.s.total_fetch_timeout)
            retryable = res.error in ("timeout", "connection_error") or res.status in _RETRY_STATUS
            if retryable and attempt < self.s.max_retries:
                attempt += 1
                self._sleep(self.s.retry_backoff * 2 ** (attempt - 1))
                continue
            res.elapsed_ms = round((time.monotonic() - start) * 1000, 1)
            return res

    def validate(self, url: str) -> Optional[str]:
        """Pre-flight SSRF check. Returns an error string (or None if the URL is safe to fetch)."""
        try:
            check_url(url, self.policy, self._resolver)
            return None
        except UnsafeURLError as e:
            return f"unsafe_url: {e}"

    # ------------------------------------------------------------------ internals
    def _follow(self, url, accept_types, limit, redirect_filter, deadline) -> FetchResult:
        current = url
        for hop in range(self.s.max_redirects + 1):
            try:
                ips = check_url(current, self.policy, self._resolver)
            except UnsafeURLError as e:
                return FetchResult(url, current, None, None, b"", error=f"unsafe_url: {e}", redirects=hop)
            status, headers, body, ctype, err = self._request(current, ips, accept_types, limit, deadline)
            if err:
                return FetchResult(url, current, status, ctype, b"", error=err, redirects=hop)
            if status in _REDIRECTS:
                nxt = normalize_url(headers.get("location", ""), base=current)
                if not nxt:
                    return FetchResult(url, current, status, None, b"", error="bad_redirect", redirects=hop)
                if redirect_filter and not redirect_filter(nxt):
                    return FetchResult(url, nxt, status, None, b"", error="redirect_blocked", redirects=hop + 1)
                current = nxt
                continue
            return FetchResult(url, current, status, ctype, body, redirects=hop,
                               x_robots_tag=tuple(headers.get("_x_robots_tag", ())))
        return FetchResult(url, current, None, None, b"", error="too_many_redirects", redirects=self.s.max_redirects)

    def _request(self, url, ips, accept_types, limit, deadline):
        """Returns (status, headers, body, content_type, error)."""
        parts = urlsplit(url)
        https = parts.scheme == "https"
        port = parts.port or (443 if https else 80)
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        headers = {"User-Agent": self.s.user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                   "Accept-Encoding": "identity", "Connection": "close"}
        conn, resp, last = None, None, "connection_error"
        for ip in ips:
            try:
                conn = (_PinnedHTTPS(parts.hostname, port, ip, self.s.request_timeout, self._ctx) if https
                        else _PinnedHTTP(parts.hostname, port, ip, self.s.request_timeout))
                conn.request("GET", target, headers=headers)
                resp = conn.getresponse()
                break
            except (socket.timeout, TimeoutError):
                last = "timeout"
            except (OSError, http.client.HTTPException, ssl.SSLError):
                last = "connection_error"
            if conn:
                conn.close()
            conn = None
        if resp is None:
            return None, {}, b"", None, last
        try:
            hdrs = {k.lower(): v for k, v in resp.getheaders()}
            hdrs["_x_robots_tag"] = [v for k, v in resp.getheaders() if k.lower() == "x-robots-tag"]
            status = resp.status
            ctype = hdrs.get("content-type", "").split(";")[0].strip().lower() or None
            if status in _REDIRECTS or not 200 <= status < 300:
                return status, hdrs, b"", ctype, None
            if hdrs.get("content-encoding", "identity").lower() not in ("identity", ""):
                return status, hdrs, b"", ctype, "unsupported_encoding"
            if accept_types is not None and ctype not in accept_types:
                return status, hdrs, b"", ctype, "unsupported_content_type"
            try:
                if int(hdrs.get("content-length", "0")) > limit:
                    return status, hdrs, b"", ctype, "too_large"
            except ValueError:
                pass
            chunks, total = [], 0
            while True:
                if time.monotonic() > deadline:
                    return status, hdrs, b"", ctype, "timeout"
                chunk = resp.read(16384)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    return status, hdrs, b"", ctype, "too_large"
                chunks.append(chunk)
            return status, hdrs, b"".join(chunks), ctype, None
        except (socket.timeout, TimeoutError):
            return None, {}, b"", None, "timeout"
        except (OSError, http.client.HTTPException, ssl.SSLError):
            return None, {}, b"", None, "connection_error"
        finally:
            conn.close()

"""URL normalization and SSRF protection. Every crawl URL is untrusted input."""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|msclkid|mc_eid|ref_src)$", re.I)
_PCT = re.compile(r"%([0-9a-fA-F]{2})")
_UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".pdf", ".zip", ".gz", ".tar",
    ".tgz", ".rar", ".7z", ".mp3", ".mp4", ".avi", ".mov", ".wav", ".webm", ".exe", ".dmg", ".iso",
    ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".ttf", ".eot", ".doc", ".docx", ".xls",
    ".xlsx", ".ppt", ".pptx", ".apk",
}


class UnsafeURLError(ValueError):
    """Raised when a URL (or what it resolves to) must not be fetched."""


def site_key(host: str) -> str:
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _norm_percent(path: str) -> str:
    path = quote(path, safe="/%:@!$&'()*+,;=-._~")

    def fix(m):
        ch = chr(int(m.group(1), 16))
        return ch if ch in _UNRESERVED else "%" + m.group(1).upper()
    return _PCT.sub(fix, path)


def _remove_dot_segments(path: str) -> str:
    out = []
    segs = path.split("/")
    for seg in segs:
        if seg == ".":
            continue
        if seg == "..":
            if len(out) > 1:
                out.pop()
            continue
        out.append(seg)
    if segs[-1] in (".", ".."):
        out.append("")
    return "/".join(out) or "/"


def normalize_url(url, base: Optional[str] = None, max_length: int = 2048) -> Optional[str]:
    """Return a canonical absolute http(s) URL, or None if unusable."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or len(url) > max_length:
        return None
    try:
        if base:
            url = urljoin(base, url)
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https") or parts.username or parts.password:
            return None
        host, port = parts.hostname, parts.port
        if not host:
            return None
        host = host.encode("idna").decode("ascii").lower().rstrip(".")
    except (ValueError, UnicodeError):
        return None
    if ":" in host:
        host = f"[{host}]"
    default = 80 if scheme == "http" else 443
    netloc = host if port in (None, default) else f"{host}:{port}"
    path = _remove_dot_segments(_norm_percent(parts.path or "/"))
    pairs = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k))
    return urlunsplit((scheme, netloc, path, urlencode(pairs), ""))


def looks_crawlable(url: str) -> bool:
    path = urlsplit(url).path.lower()
    dot = path.rfind(".")
    return dot == -1 or path[dot:] not in SKIP_EXTENSIONS


# ----------------------------------------------------------------------------- SSRF
@dataclass(frozen=True)
class UrlPolicy:
    allowed_ports: Optional[tuple] = (80, 443)   # None = any port (tests only)
    allow_private_networks: bool = False          # True = skip IP checks (tests only)


BLOCKED_HOSTS = {"localhost", "metadata", "metadata.google.internal", "instance-data"}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".lan", ".home.arpa")
_BLOCKED_NETS = [ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16")]


def ip_is_public(ip) -> bool:
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip.split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.version == 6 and any(ip in n for n in _BLOCKED_NETS):
        return False
    return ip.is_global and not ip.is_multicast


def check_url(url: str, policy: UrlPolicy = UrlPolicy(),
              resolver: Callable = socket.getaddrinfo) -> list:
    """Validate a URL and its DNS resolution. Returns the vetted IP list to connect to.
    Raises UnsafeURLError. Callers must connect to these IPs (not re-resolve) to defeat DNS rebinding."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise UnsafeURLError("malformed url")
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError("unsupported scheme")
    if parts.username or parts.password:
        raise UnsafeURLError("credentials in url")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("missing host")
    port = port or (80 if parts.scheme == "http" else 443)
    if policy.allowed_ports is not None and port not in policy.allowed_ports:
        raise UnsafeURLError(f"port {port} not allowed")
    h = host.lower().rstrip(".")
    if not policy.allow_private_networks and (h in BLOCKED_HOSTS or h.endswith(BLOCKED_SUFFIXES)):
        raise UnsafeURLError("blocked hostname")
    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        raise UnsafeURLError("dns resolution failed")
    ips = []
    for info in infos:
        addr = info[4][0].split("%")[0]
        try:
            ipobj = ipaddress.ip_address(addr)
        except ValueError:
            raise UnsafeURLError("unparseable address")
        if not policy.allow_private_networks and not ip_is_public(ipobj):
            raise UnsafeURLError("resolves to non-public address")   # reject if ANY record is internal
        if addr not in ips:
            ips.append(addr)
    if not ips:
        raise UnsafeURLError("no addresses")
    return ips

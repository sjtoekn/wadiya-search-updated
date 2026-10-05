"""RFC 9309-style robots.txt parsing (wildcards, longest-match) and a caching checker."""
from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import urlsplit

_PCT = re.compile(r"%([0-9a-fA-F]{2})")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def canonical_path(s: str) -> str:
    """RFC 9309 s2.2.2: put robots patterns AND URL paths in one canonical percent-encoding before comparing.
    Non-ASCII/whitespace -> UTF-8 %XX; %XX of an unreserved char -> the char itself; other %xx -> upper-case hex.
    Reserved characters (e.g. %2F) stay encoded, so they remain distinct from their literal form. '*' and '$' are untouched."""
    s = re.sub(r"[^\x21-\x7e]", lambda m: "".join("%%%02X" % b for b in m.group().encode("utf-8")), s)

    def fix(m):
        ch = chr(int(m.group(1), 16))
        return ch if ch in _UNRESERVED else "%" + m.group(1).upper()
    return _PCT.sub(fix, s)


MAX_RULES = 5000
MAX_PATTERN = 512
MAX_WILDCARDS = 8


class RobotsRules:
    def __init__(self, rules=None, delay: Optional[float] = None, disallow_all=False,
                 unavailable=False, sitemaps=None):
        self.delay = delay
        self.disallow_all = disallow_all
        self.unavailable = unavailable      # True when 'disallow all' only means robots.txt could not be fetched
        self.sitemaps = tuple(sitemaps or ())
        self._rules = []
        for allow, pattern in (rules or [])[:MAX_RULES]:
            pattern = canonical_path(pattern)     # same canonical form as the URL path (specificity measured after this)
            if len(pattern) > MAX_PATTERN or pattern.count("*") > MAX_WILDCARDS:
                continue   # ReDoS guard
            p = re.sub(r"(\\\*)+", r"\\*", re.escape(pattern)).replace(r"\*", ".*")
            if p.endswith(r"\$"):
                p = p[:-2] + "$"
            self._rules.append((allow, len(pattern), re.compile(p)))

    def allowed(self, path_and_query: str) -> bool:
        if self.disallow_all:
            return False
        path_and_query = canonical_path(path_and_query)
        best_len, best_allow = -1, True
        for allow, length, rx in self._rules:
            if rx.match(path_and_query) and (length > best_len or (length == best_len and allow)):
                best_len, best_allow = length, allow
        return best_allow


def parse_robots(text: str, token: str) -> RobotsRules:
    token = token.lower()
    groups, cur, last_agent = [], None, False
    sitemaps = []
    seen_sitemaps = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "sitemap":
            if value:
                sitemap = value.strip()
                if sitemap and sitemap not in seen_sitemaps:
                    seen_sitemaps.add(sitemap)
                    sitemaps.append(sitemap)
            continue
        if key == "user-agent":
            if cur is None or not last_agent:
                cur = {"agents": [], "rules": [], "delay": None}
                groups.append(cur)
            cur["agents"].append(value.lower())
            last_agent = True
            continue
        last_agent = False
        if cur is None:
            continue
        if key in ("allow", "disallow"):
            if value:
                cur["rules"].append((key == "allow", value))
        elif key == "crawl-delay":
            try:
                d = float(value)
                if d >= 0:
                    cur["delay"] = d
            except ValueError:
                pass
    chosen = [g for g in groups if token in g["agents"]] or [g for g in groups if "*" in g["agents"]]
    rules = [r for g in chosen for r in g["rules"]]
    delay = next((g["delay"] for g in chosen if g["delay"] is not None), None)
    return RobotsRules(rules, delay, sitemaps=sitemaps)


class RobotsChecker:
    """Fetches (via the SSRF-safe fetcher) and caches robots.txt per origin.
    Unreachable robots.txt (5xx / 429 / 401 / 403 / network error) => disallow everything (conservative).
    Other 4xx (e.g. 404) => no restrictions."""

    def __init__(self, fetcher, token: str, ttl: int = 3600, max_bytes: int = 512 * 1024,
                 clock=time.monotonic):
        self._fetcher, self._token, self._ttl, self._max = fetcher, token, ttl, max_bytes
        self._clock = clock
        self._cache = {}

    def _rules_for(self, url: str) -> RobotsRules:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        hit = self._cache.get(origin)
        now = self._clock()
        if hit and hit[1] > now:
            return hit[0]
        res = self._fetcher.fetch(origin + "/robots.txt", accept_types=None, max_bytes=self._max)
        ttl = self._ttl
        if res.error or res.status is None:
            rules, ttl = RobotsRules(disallow_all=True, unavailable=True), min(self._ttl, 600)
        elif 200 <= res.status < 300:
            rules = parse_robots(res.body.decode("utf-8", errors="replace"), self._token)
        elif res.status in (401, 403, 429) or res.status >= 500:
            rules, ttl = RobotsRules(disallow_all=True, unavailable=True), min(self._ttl, 600)
        else:
            rules = RobotsRules()
        self._cache[origin] = (rules, now + ttl)
        return rules

    def is_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        return self._rules_for(url).allowed(target)

    def block_reason(self, url: str) -> Optional[str]:
        """None if allowed; 'rules' if robots.txt affirmatively disallows; 'unavailable' if robots.txt could not be read."""
        rules = self._rules_for(url)
        if rules.unavailable:
            return "unavailable"
        return None if self.is_allowed(url) else "rules"

    def crawl_delay(self, url: str) -> Optional[float]:
        return self._rules_for(url).delay

    def sitemap_urls(self, url: str) -> tuple:
        """Return sitemap URLs declared by the origin's robots.txt."""
        return self._rules_for(url).sitemaps


_XRT_DIRECTIVES = {"all", "none", "noindex", "nofollow", "noarchive", "nosnippet", "notranslate", "noimageindex",
                   "unavailable_after", "max-snippet", "max-image-preview", "max-video-preview", "indexifembedded"}


def parse_x_robots_tag(values, token: str) -> tuple:
    """Parse X-Robots-Tag header value(s) -> (noindex, nofollow). Each element of `values` is one header instance.
    A leading 'botname:' scopes the directives to that bot; unscoped directives apply to everyone.
    Supported: noindex, nofollow, none. Other directives (noarchive, unavailable_after, ...) are ignored."""
    token = token.lower()
    noindex = nofollow = False
    for raw in values or ():
        text = (raw or "").strip().lower()
        m = re.match(r"^([a-z0-9_\-\.]+)\s*:\s*(.*)$", text)
        if m and m.group(1) not in _XRT_DIRECTIVES:         # "googlebot: noindex" (but not "unavailable_after: date")
            if m.group(1) not in (token, "*"):
                continue
            text = m.group(2)
        for d in (x.strip() for x in text.split(",")):
            if d in ("noindex", "none"):
                noindex = True
            if d in ("nofollow", "none"):
                nofollow = True
    return noindex, nofollow

"""HTML -> structured page. Pure function: no network, no storage, no crawling logic."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Union

from bs4 import BeautifulSoup

from .urls import normalize_url

_JUNK_TAGS = ["script", "style", "noscript", "template", "svg", "iframe", "object", "embed",
              "canvas", "select", "button", "option", "textarea", "input", "link", "meta"]
_BOILER_TAGS = {"nav", "aside", "header", "footer"}
_BOILER_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search"}
_WS = re.compile(r"\s+")
_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-:.]+)""", re.I)
_HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?([A-Za-z0-9_\-:.]+)", re.I)


@dataclass
class ExtractedPage:
    title: str = ""
    description: str = ""
    headings: list = field(default_factory=list)
    content: str = ""
    canonical_url: Optional[str] = None
    language: Optional[str] = None
    links: list = field(default_factory=list)
    feed_links: list = field(default_factory=list)
    noindex: bool = False
    nofollow: bool = False


def _decode(data: bytes, content_type: Optional[str]) -> str:
    charsets = []
    if content_type and (m := _HEADER_CHARSET.search(content_type)):
        charsets.append(m.group(1))
    if data.startswith(b"\xef\xbb\xbf"):
        charsets.insert(0, "utf-8-sig")
    if m := _CHARSET.search(data[:4096]):
        charsets.append(m.group(1).decode("ascii", "ignore"))
    for cs in charsets + ["utf-8"]:
        try:
            return data.decode(cs, errors="replace")
        except LookupError:
            continue
    return data.decode("utf-8", errors="replace")


def _clean(s: str, limit: int) -> str:
    return _WS.sub(" ", s or "").strip()[:limit]


def _is_boilerplate(tag) -> bool:
    if tag.attrs is None:
        return False
    if tag.has_attr("hidden") or tag.get("aria-hidden") == "true":
        return True
    if (tag.get("role") or "").lower() in _BOILER_ROLES:
        return True
    if tag.name in ("header", "footer"):   # keep <header>/<footer> that belong to an article/main
        return tag.find_parent(["article", "main"]) is None
    return tag.name in _BOILER_TAGS


def extract(content: Union[bytes, str], base_url: str, content_type: Optional[str] = None) -> ExtractedPage:
    html = _decode(content, content_type) if isinstance(content, bytes) else content
    soup = BeautifulSoup(html, "lxml")
    page = ExtractedPage()

    # --- metadata (before anything is removed) ---
    if soup.title and soup.title.get_text():
        page.title = _clean(soup.title.get_text(), 300)
    for m in soup.find_all("meta"):
        name = (m.get("name") or m.get("property") or "").lower()
        val = m.get("content") or ""
        if name == "description" and not page.description:
            page.description = _clean(val, 500)
        elif name == "og:description" and not page.description:
            page.description = _clean(val, 500)
        elif name in ("robots", "wadiyabot"):
            low = val.lower()
            page.noindex |= "noindex" in low or "none" in low
            page.nofollow |= "nofollow" in low or "none" in low
        elif (m.get("http-equiv") or "").lower() == "content-language" and not page.language:
            page.language = _lang(val)
    if soup.html and soup.html.get("lang"):
        page.language = _lang(soup.html.get("lang")) or page.language

    base = base_url
    bt = soup.find("base", href=True)
    if bt:
        base = normalize_url(bt["href"], base=base_url) or base_url

    seen_feeds = set()
    for link in soup.find_all("link", href=True):
        rel = [r.lower() for r in (link.get("rel") or [])]
        if "canonical" in rel and not page.canonical_url:
            page.canonical_url = normalize_url(link["href"], base=base)

        link_type = (link.get("type") or "").lower().split(";", 1)[0].strip()
        if "alternate" in rel and link_type in ("application/rss+xml", "application/atom+xml"):
            feed_url = normalize_url(link["href"], base=base)
            if feed_url and feed_url not in seen_feeds:
                seen_feeds.add(feed_url)
                page.feed_links.append(feed_url)

    seen = set()
    for a in soup.find_all("a", href=True):
        if "nofollow" in [r.lower() for r in (a.get("rel") or [])]:
            continue
        href = a["href"].strip()
        if href.startswith("#"):
            continue
        u = normalize_url(href, base=base)
        if u and u not in seen:
            seen.add(u)
            page.links.append(u)
    if page.nofollow:
        page.links = []

    h1 = soup.find("h1")
    if not page.title and h1:
        page.title = _clean(h1.get_text(" "), 300)

    # --- boilerplate removal ---
    for tag in soup(_JUNK_TAGS):
        tag.decompose()
    for tag in [t for t in soup.find_all(True) if _is_boilerplate(t)]:
        if not tag.decomposed:
            tag.decompose()

    body = soup.body or soup
    region = soup.find("main") or soup.find(attrs={"role": "main"})
    regions = [region] if region else soup.find_all("article")
    text = " ".join(" ".join(r.stripped_strings) for r in regions) if regions else ""
    if len(_WS.sub(" ", text).strip()) < 100:
        regions, text = [body], " ".join(body.stripped_strings)
    page.content = _clean(text, 10**7)

    seen_h = set()
    for r in regions:
        for h in r.find_all(["h1", "h2", "h3"]):
            t = _clean(h.get_text(" "), 200)
            if t and t not in seen_h and len(page.headings) < 50:
                seen_h.add(t)
                page.headings.append(t)
    return page


def _lang(value: str) -> Optional[str]:
    primary = (value or "").strip().lower().replace("_", "-").split("-")[0]
    return primary if re.fullmatch(r"[a-z]{2,3}", primary) else None

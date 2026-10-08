"""HTML -> structured page. Pure function: no network, no storage, no crawling logic."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Union
from urllib.parse import parse_qs, urlsplit

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
    images: list = field(default_factory=list)
    videos: list = field(default_factory=list)
    locations: list = field(default_factory=list)
    books: list = field(default_factory=list)
    noindex: bool = False
    nofollow: bool = False
    nosnippet: bool = False


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
            page.nosnippet |= "nosnippet" in low
        elif (m.get("http-equiv") or "").lower() == "content-language" and not page.language:
            page.language = _lang(val)
    if soup.html and soup.html.get("lang"):
        page.language = _lang(soup.html.get("lang")) or page.language

    base = base_url
    bt = soup.find("base", href=True)
    if bt:
        base = normalize_url(bt["href"], base=base_url) or base_url

    # --- structured Book candidates (JSON-LD / schema.org) ---
    seen_books = set()

    def add_book(value):
        if not isinstance(value, dict):
            return

        title = _clean(str(value.get("name") or value.get("headline") or ""), 500)
        if not title:
            return

        raw_authors = value.get("author")
        if isinstance(raw_authors, dict):
            raw_authors = [raw_authors]
        elif isinstance(raw_authors, str):
            raw_authors = [raw_authors]
        elif not isinstance(raw_authors, list):
            raw_authors = []

        authors = []
        for author in raw_authors:
            if isinstance(author, dict):
                name = _clean(str(author.get("name") or ""), 300)
            else:
                name = _clean(str(author or ""), 300)
            if name and name not in authors:
                authors.append(name)

        publisher = value.get("publisher")
        if isinstance(publisher, dict):
            publisher = publisher.get("name")
        publisher = _clean(str(publisher or ""), 300) or None

        cover_url = value.get("image")
        if isinstance(cover_url, list):
            cover_url = cover_url[0] if cover_url else None
        cover_url = (
            normalize_url(str(cover_url), base=base)
            if cover_url
            else None
        )

        book_url = value.get("url")
        book_url = (
            normalize_url(str(book_url), base=base)
            if book_url
            else base_url
        )

        language = value.get("inLanguage")
        if isinstance(language, dict):
            language = language.get("name") or language.get("value")
        language = _clean(str(language or ""), 50) or None

        isbn = _clean(str(value.get("isbn") or ""), 32) or None
        published_at = _clean(
            str(value.get("datePublished") or ""),
            100,
        ) or None
        description = _clean(
            str(value.get("description") or ""),
            1000,
        ) or None

        key = (book_url, isbn, title.lower())
        if key in seen_books:
            return
        seen_books.add(key)

        page.books.append({
            "title": title,
            "author": authors,
            "isbn": isbn,
            "cover_url": cover_url,
            "publisher": publisher,
            "published_at": published_at,
            "description": description,
            "url": book_url,
            "language": language,
            "source_url": base_url,
        })

    # --- structured location candidates (JSON-LD / schema.org) ---
    seen_locations = set()

    def add_location(value, source="json-ld"):
        if not isinstance(value, dict):
            return

        geo = value.get("geo") if isinstance(value.get("geo"), dict) else {}
        address = value.get("address") if isinstance(value.get("address"), dict) else {}

        lat = geo.get("latitude")
        lon = geo.get("longitude")
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return

        key = (lat, lon)
        if key in seen_locations:
            return
        seen_locations.add(key)

        page.locations.append({
            "latitude": lat,
            "longitude": lon,
            "address": _clean(str(address.get("streetAddress") or value.get("address") or ""), 500),
            "city": _clean(str(address.get("addressLocality") or ""), 200),
            "region": _clean(str(address.get("addressRegion") or ""), 200),
            "country": _clean(str(address.get("addressCountry") or ""), 200),
            "source": source,
        })

    def visit_jsonld(value):
        if isinstance(value, list):
            for item in value:
                visit_jsonld(item)
            return
        if not isinstance(value, dict):
            return

        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        types = {str(t).rsplit("/", 1)[-1].lower() for t in types}

        if "book" in types:
            add_book(value)

        if types & {"place", "localbusiness", "restaurant", "hotel", "store", "organization"}:
            add_location(value)

        for key, child in value.items():
            if key != "@context":
                visit_jsonld(child)

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            visit_jsonld(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    # --- explicit HTML coordinate metadata ---
    def add_coordinate_location(lat, lon, source):
        try:
            lat = float(str(lat).strip())
            lon = float(str(lon).strip())
        except (TypeError, ValueError):
            return

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return

        key = (lat, lon)
        if key in seen_locations:
            return
        seen_locations.add(key)

        page.locations.append({
            "latitude": lat,
            "longitude": lon,
            "address": "",
            "city": "",
            "region": "",
            "country": "",
            "source": source,
        })

    meta_coords = {}
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").strip().lower()
        content = (meta.get("content") or "").strip()
        if not content:
            continue

        if name in ("geo.position", "icbm"):
            parts = re.split(r"\s*[,;]\s*", content, maxsplit=1)
            if len(parts) == 2:
                add_coordinate_location(parts[0], parts[1], f"meta:{name}")
        elif name in ("latitude", "longitude"):
            meta_coords[name] = content

    if "latitude" in meta_coords and "longitude" in meta_coords:
        add_coordinate_location(
            meta_coords["latitude"],
            meta_coords["longitude"],
            "meta:latitude-longitude",
        )

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

    # --- image candidates ---
    seen_images = set()

    def add_image(image_url, alt_text="", title=""):
        if not image_url:
            return

        image_url = normalize_url(image_url, base=base)
        if not image_url:
            return

        if image_url in seen_images:
            return

        seen_images.add(image_url)
        page.images.append({
            "image_url": image_url,
            "source_page_url": base_url,
            "source_domain": "",
            "alt_text": _clean(alt_text, 300),
            "title": _clean(title, 300),
        })

    for img in soup.find_all("img"):
        image_url = img.get("src")

        if not image_url:
            srcset = img.get("srcset") or ""
            if srcset:
                image_url = srcset.split(",", 1)[0].strip().split(" ", 1)[0]

        add_image(
            image_url,
            alt_text=img.get("alt"),
            title=img.get("title"),
        )

    for m in soup.find_all("meta"):
        prop = (
            m.get("property")
            or m.get("name")
            or ""
        ).strip().lower()

        if prop in ("og:image", "og:image:url", "twitter:image"):
            add_image(m.get("content"))

    # --- video candidates ---
    seen_videos = set()

    video_embed_hosts = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
        "youtu.be",
        "vimeo.com",
        "www.vimeo.com",
        "player.vimeo.com",
    }

    def _youtube_embed(url):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()

        if host in {"youtube.com", "www.youtube.com", "m.youtube.com",
                    "youtube-nocookie.com", "www.youtube-nocookie.com"}:
            if parts.path == "/watch":
                video_id = parse_qs(parts.query).get("v", [None])[0]
                if video_id:
                    return f"https://www.youtube.com/embed/{video_id}"

            if parts.path.startswith("/embed/"):
                return url

        if host == "youtu.be":
            video_id = parts.path.strip("/").split("/", 1)[0]
            if video_id:
                return f"https://www.youtube.com/embed/{video_id}"

        return None

    def _vimeo_embed(url):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()

        if host == "player.vimeo.com" and parts.path.startswith("/video/"):
            return url

        if host in {"vimeo.com", "www.vimeo.com"}:
            video_id = parts.path.strip("/").split("/", 1)[0]
            if video_id and video_id.isdigit():
                return f"https://player.vimeo.com/video/{video_id}"

        return None

    def add_video(
        video_url,
        kind="direct",
        title="",
        thumbnail_url="",
    ):
        if not video_url:
            return

        video_url = normalize_url(video_url, base=base)
        if not video_url:
            return

        if video_url in seen_videos:
            return

        thumbnail_url = normalize_url(thumbnail_url, base=base) if thumbnail_url else ""

        if kind == "embed" and not thumbnail_url:
            parts = urlsplit(video_url)
            host = (parts.hostname or "").lower()

            if host == "www.youtube.com" and parts.path.startswith("/embed/"):
                video_id = parts.path.split("/embed/", 1)[1].split("/", 1)[0]
                if video_id:
                    thumbnail_url = (
                        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                    )

        if kind == "embed":
            parts = urlsplit(video_url)
            host = (parts.hostname or "").lower()
            if host not in video_embed_hosts:
                return

        seen_videos.add(video_url)
        page.videos.append({
            "video_url": video_url,
            "kind": kind,
            "source_page_url": base_url,
            "source_domain": "",
            "title": _clean(title, 300),
            "thumbnail_url": _clean(thumbnail_url, 1000),
        })

    # Native HTML5 video.
    for video in soup.find_all("video"):
        poster = video.get("poster") or ""

        direct_url = video.get("src")
        if direct_url:
            add_video(
                direct_url,
                kind="direct",
                title=video.get("title") or "",
                thumbnail_url=poster,
            )

        for source in video.find_all("source", src=True):
            add_video(
                source.get("src"),
                kind="direct",
                title=video.get("title") or "",
                thumbnail_url=poster,
            )

    # Common trusted video-provider iframes.
    for iframe in soup.find_all("iframe", src=True):
        raw = normalize_url(iframe.get("src"), base=base)
        if not raw:
            continue

        embed = _youtube_embed(raw) or _vimeo_embed(raw)
        if embed:
            add_video(
                embed,
                kind="embed",
                title=iframe.get("title") or "",
            )

    # Open Graph / Twitter video metadata.
    for m in soup.find_all("meta"):
        prop = (
            m.get("property")
            or m.get("name")
            or ""
        ).strip().lower()

        if prop in (
            "og:video",
            "og:video:url",
            "og:video:secure_url",
            "twitter:player:stream",
        ):
            raw = normalize_url(m.get("content"), base=base)
            if not raw:
                continue

            embed = _youtube_embed(raw) or _vimeo_embed(raw)
            if embed:
                add_video(embed, kind="embed")
            else:
                add_video(raw, kind="direct")

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

"""Safe parsing helpers for untrusted XML sitemap documents."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from .urls import normalize_url


MAX_SITEMAP_LOCS = 10_000
MAX_SITEMAP_XML_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class SitemapDocument:
    """Parsed sitemap document."""

    kind: str
    urls: tuple[str, ...]


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _loc_value(element: ET.Element) -> Optional[str]:
    for child in element:
        if _local_name(child.tag) == "loc":
            value = (child.text or "").strip()
            if value:
                return value
    return None


def parse_sitemap(data: bytes, base_url: str) -> SitemapDocument:
    """Parse a bounded sitemap XML document.

    Supports <urlset> and <sitemapindex>, including XML namespaces.
    Returned URLs are normalized and deduplicated.

    XML is parsed with the Python stdlib ElementTree parser. External
    entity/network resolution is not performed.
    """
    if len(data) > MAX_SITEMAP_XML_BYTES:
        raise ValueError("sitemap_too_large")

    if b"<!DOCTYPE" in data.upper():
        raise ValueError("malformed_sitemap")

    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError) as exc:
        raise ValueError("malformed_sitemap") from exc

    root_name = _local_name(root.tag)
    if root_name == "urlset":
        kind = "urlset"
    elif root_name == "sitemapindex":
        kind = "sitemapindex"
    else:
        raise ValueError("unsupported_sitemap_root")

    base = normalize_url(base_url)
    if not base:
        raise ValueError("invalid_base_url")

    seen = set()
    urls = []

    for element in root:
        if _local_name(element.tag) not in ("url", "sitemap"):
            continue

        raw = _loc_value(element)
        if not raw:
            continue

        normalized = normalize_url(raw, base=base)
        if not normalized:
            continue

        parts = urlsplit(normalized)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        urls.append(normalized)

        if len(urls) >= MAX_SITEMAP_LOCS:
            break

    return SitemapDocument(kind=kind, urls=tuple(urls))

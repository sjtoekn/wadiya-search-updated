"""Safe parsing helpers for untrusted RSS and Atom feed documents."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from .urls import normalize_url


MAX_FEED_LOCS = 10_000
MAX_FEED_XML_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class FeedDocument:
    """Parsed feed document."""

    kind: str
    urls: tuple[str, ...]


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _normalized_url(raw: Optional[str], base: str) -> Optional[str]:
    if not raw:
        return None

    normalized = normalize_url(raw.strip(), base=base)
    if not normalized:
        return None

    parts = urlsplit(normalized)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None

    return normalized


def _rss_link(item: ET.Element) -> Optional[str]:
    for child in item:
        if _local_name(child.tag) != "link":
            continue

        value = (child.text or "").strip()
        if value:
            return value

    return None


def _atom_link(entry: ET.Element) -> Optional[str]:
    alternate = None
    first = None

    for child in entry:
        if _local_name(child.tag) != "link":
            continue

        href = (child.attrib.get("href") or "").strip()
        if not href:
            continue

        if first is None:
            first = href

        rel = (child.attrib.get("rel") or "alternate").strip().lower()
        if rel == "alternate":
            alternate = href
            break

    return alternate or first


def parse_feed(data: bytes, base_url: str) -> FeedDocument:
    """Parse a bounded RSS or Atom XML document.

    Supports RSS <rss> feeds and Atom <feed> documents, including
    XML namespaces. Returned URLs are normalized and deduplicated.

    XML is parsed with the Python stdlib ElementTree parser. External
    entity/network resolution is not performed.
    """
    if len(data) > MAX_FEED_XML_BYTES:
        raise ValueError("feed_too_large")

    if b"<!DOCTYPE" in data.upper():
        raise ValueError("malformed_feed")

    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError) as exc:
        raise ValueError("malformed_feed") from exc

    root_name = _local_name(root.tag)

    if root_name == "rss":
        kind = "rss"
        target_name = "item"
        link_reader = _rss_link
    elif root_name == "feed":
        kind = "atom"
        target_name = "entry"
        link_reader = _atom_link
    else:
        raise ValueError("unsupported_feed_root")

    base = normalize_url(base_url)
    if not base:
        raise ValueError("invalid_base_url")

    seen = set()
    urls = []

    for element in root.iter():
        if element is root:
            continue

        if _local_name(element.tag) != target_name:
            continue

        raw = link_reader(element)
        normalized = _normalized_url(raw, base)
        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        urls.append(normalized)

        if len(urls) >= MAX_FEED_LOCS:
            break

    return FeedDocument(kind=kind, urls=tuple(urls))

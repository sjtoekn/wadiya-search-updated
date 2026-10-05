"""Seed list loading and crawl scope (domain / path restrictions)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlsplit

import yaml

from .urls import normalize_url, site_key


@dataclass
class Seed:
    url: str
    max_pages: Optional[int] = None
    max_depth: Optional[int] = None
    path_prefix: Optional[str] = None


def load_seeds(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    seeds = []
    for entry in data.get("seeds", []):
        if isinstance(entry, str):
            entry = {"url": entry}

        if not isinstance(entry, dict):
            continue

        url = entry.get("url")
        if not isinstance(url, str) or not url.strip():
            continue

        max_pages = entry.get("max_pages")
        max_depth = entry.get("max_depth")

        if isinstance(max_pages, bool) or (
            max_pages is not None
            and (not isinstance(max_pages, int) or max_pages < 1)
        ):
            continue

        if isinstance(max_depth, bool) or (
            max_depth is not None
            and (not isinstance(max_depth, int) or max_depth < 0)
        ):
            continue

        path_prefix = entry.get("path_prefix")
        if path_prefix is not None:
            if not isinstance(path_prefix, str) or not path_prefix.strip():
                continue
            path_prefix = "/" + path_prefix.strip().lstrip("/")
            if path_prefix != "/":
                path_prefix = path_prefix.rstrip("/")

        normalized = normalize_url(url.strip())
        if not normalized:
            continue

        seeds.append(
            Seed(
                url=normalized,
                max_pages=max_pages,
                max_depth=max_depth,
                path_prefix=path_prefix,
            )
        )

    return seeds


@dataclass
class SiteConfig:
    max_pages: int
    max_depth: int
    whole_site: bool = False
    prefixes: list = field(default_factory=list)


class Scope:
    """A URL is crawlable only if its site (host minus 'www.') came from a seed
    and, when the seed gave a path_prefix, its path is under that prefix."""

    def __init__(self, seeds, settings):
        self.sites = {}
        for s in seeds:
            u = normalize_url(s.url)
            if not u:
                continue
            parts = urlsplit(u)
            cfg = self.sites.setdefault(site_key(parts.hostname), SiteConfig(
                s.max_pages or settings.max_pages_per_domain,
                settings.max_depth if s.max_depth is None else s.max_depth))
            cfg.max_pages = max(cfg.max_pages, s.max_pages or 0)
            cfg.max_depth = max(cfg.max_depth, s.max_depth or 0)
            if s.path_prefix:
                prefix = "/" + s.path_prefix.strip().lstrip("/")
                if prefix != "/":
                    prefix = prefix.rstrip("/")
                cfg.prefixes.append(prefix)
            else:
                cfg.whole_site = True

    def config(self, site: str) -> Optional[SiteConfig]:
        return self.sites.get(site)

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        if not parts.hostname:
            return False
        cfg = self.sites.get(site_key(parts.hostname))
        if cfg is None:
            return False
        if cfg.whole_site:
            return True

        path = parts.path or "/"
        return any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in cfg.prefixes
        )

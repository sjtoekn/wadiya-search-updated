"""Central configuration. Defaults are safe; secrets come only from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # --- storage ---
    db_path: str = "data/wadiya.db"
    index_path: str = "data/wadiya_index.db"
    seeds_path: str = "wadiya/config/seeds.yaml"

    # --- crawler identity ---
    user_agent: str = "WadiyaBot/0.1 (+https://wadiya.com/bot)"
    robots_token: str = "WadiyaBot"  # product token matched against robots.txt groups

    # --- crawler limits ---
    max_depth: int = 2
    max_pages_per_domain: int = 50
    max_total_pages: int = 500
    max_workers: int = 4
    request_timeout: float = 10.0        # per socket operation
    total_fetch_timeout: float = 30.0    # wall-clock per attempt (slow-loris guard)
    max_retries: int = 2
    retry_backoff: float = 1.0
    max_response_bytes: int = 2 * 1024 * 1024
    max_robots_bytes: int = 512 * 1024
    default_crawl_delay: float = 1.0
    max_crawl_delay: float = 10.0
    max_redirects: int = 5
    max_content_chars: int = 200_000
    max_consecutive_failures: int = 3     # failed crawls in a row before an existing doc is dropped as 'unreachable'
    robots_cache_ttl: int = 3600
    allowed_ports: tuple = (80, 443)
    # Tests / local mock sites ONLY. Deliberately NOT readable from the environment.
    allow_private_networks: bool = False

    # --- search ---
    max_query_length: int = 200
    max_query_terms: int = 32
    page_size: int = 10
    max_pages: int = 10          # ranking window = page_size * max_pages
    count_cap: int = 10_000

    # --- admin ---
    admin_password_hash: str = ""
    secret_key: str = ""
    session_max_age: int = 8 * 3600
    cookie_secure: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        d = cls()
        return cls(
            db_path=e("WADIYA_DB_PATH", d.db_path),
            index_path=e("WADIYA_INDEX_PATH", d.index_path),
            seeds_path=e("WADIYA_SEEDS_PATH", d.seeds_path),
            user_agent=e("WADIYA_USER_AGENT", d.user_agent),
            admin_password_hash=e("WADIYA_ADMIN_PASSWORD_HASH", ""),
            secret_key=e("WADIYA_SECRET_KEY", ""),
            cookie_secure=_env_bool("WADIYA_COOKIE_SECURE", True),
        )

"""Framework-independent request handlers: (status, json-body). FastAPI only wires these up."""
from __future__ import annotations

from ..admin.dashboard import build_stats
from ..search.service import InvalidSearchRequest
from ..crawler.extractor import extract
from ..crawler.fetcher import Fetcher
from ..crawler.keywords import extract_keywords
from ..crawler.urls import normalize_url, site_key, looks_crawlable, is_safe_submission_target


def error(status: int, message: str) -> tuple:
    return status, {"error": {"code": status, "message": message}}


def parse_page(raw) -> int:
    if raw is None or raw == "":
        return 1
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdigit() or len(raw) > 4:
        raise InvalidSearchRequest("page must be a positive integer")
    return int(raw)


def handle_search(service, q, page_raw) -> tuple:
    try:
        return 200, service.search(q, parse_page(page_raw))
    except InvalidSearchRequest as e:
        return error(400, str(e))


def handle_login(auth, password, client_key: str) -> tuple:
    status, message, token = auth.login(password, client_key)
    return (status, {"ok": True}, token) if status == 200 else (*error(status, message), None)


def handle_stats(storage, indexer) -> tuple:
    return 200, build_stats(storage, indexer)


def handle_admin_discovery(
    storage,
    *,
    status: str | None = None,
    source: str | None = None,
    query: str | None = None,
    page: str | None = None,
    limit: str | None = None,
) -> tuple:
    allowed_statuses = {
        "pending",
        "active",
        "failed",
    }

    if status:
        status = status.strip().lower()
        if status not in allowed_statuses:
            return error(400, "invalid status")

    if source:
        source = source.strip().lower()
        if len(source) > 100 or any(ch.isspace() for ch in source):
            return error(400, "invalid source")

    if query is not None:
        query = query.strip()
        if len(query) > 253:
            return error(400, "query is too long")
        query = query or None

    try:
        parsed_page = int(page) if page else 1
        parsed_limit = int(limit) if limit else 50
    except (TypeError, ValueError):
        return error(400, "page and limit must be positive integers")

    if parsed_page < 1:
        return error(400, "page must be a positive integer")

    if parsed_limit not in (20, 50, 100):
        return error(400, "limit must be 20, 50, or 100")

    total = storage.count_discovered_sites_admin(
        status=status,
        source=source,
        query=query,
    )

    total_pages = (total + parsed_limit - 1) // parsed_limit
    offset = (parsed_page - 1) * parsed_limit

    sites = []
    if offset < total:
        sites = storage.list_discovered_sites_admin(
            status=status,
            source=source,
            query=query,
            limit=parsed_limit,
            offset=offset,
        )

    start = offset + 1 if sites else 0
    end = offset + len(sites) if sites else 0

    return 200, {
        "stats": storage.discovery_registry_stats(),
        "sites": sites,
        "pagination": {
            "page": parsed_page,
            "page_size": parsed_limit,
            "total": total,
            "total_pages": total_pages,
            "start": start,
            "end": end,
        },
    }


def handle_preview_website(settings, url: str, fetcher=None) -> tuple:
    """Safely fetch and analyze a public website without storing or queuing it."""
    if not isinstance(url, str):
        return error(400, "url is required")

    raw = url.strip()

    if not raw:
        return error(400, "url is required")

    if len(raw) > 2048:
        return error(400, "url is too long")

    normalized = normalize_url(raw)

    if not normalized or not looks_crawlable(normalized):
        return error(400, "invalid or unsupported website URL")

    if not is_safe_submission_target(normalized):
        return error(400, "unsafe website URL")

    fetcher = fetcher or Fetcher(settings)
    result = fetcher.fetch(
        normalized,
        max_bytes=settings.max_response_bytes,
    )

    if result.error:
        if result.error == "unsafe_url":
            return error(400, "unsafe website URL")

        if result.error == "timeout":
            return error(504, "website preview timed out")

        if result.error == "too_large":
            return error(413, "website page is too large")

        if result.error == "unsupported_content_type":
            return error(415, "website does not return an HTML page")

        return error(502, "website could not be fetched")

    if result.status is None or not 200 <= result.status < 300:
        return error(502, "website could not be fetched")

    if result.content_type not in {"text/html", "application/xhtml+xml"}:
        return error(415, "website does not return an HTML page")

    page = extract(
        result.body,
        result.final_url,
        result.content_type,
    )

    keywords = extract_keywords(
        title=page.title,
        headings=page.headings,
        description=page.description,
        content=page.content,
        limit=12,
    )

    return 200, {
        "ok": True,
        "url": normalized,
        "final_url": result.final_url,
        "canonical_url": page.canonical_url,
        "title": page.title,
        "description": page.description,
        "language": page.language,
        "headings": page.headings,
        "keywords": keywords,
        "robots": {
            "noindex": page.noindex,
            "nofollow": page.nofollow,
        },
    }


def handle_submit_website(storage, url: str) -> tuple:
    """Register a public website for automatic crawling and indexing."""
    if not isinstance(url, str):
        return error(400, "url is required")

    raw = url.strip()

    if not raw:
        return error(400, "url is required")

    if len(raw) > 2048:
        return error(400, "url is too long")

    normalized = normalize_url(raw)

    if not normalized or not looks_crawlable(normalized):
        return error(400, "invalid or unsupported website URL")

    if not is_safe_submission_target(normalized):
        return error(400, "unsafe website URL")

    domain = site_key(normalized)

    if not domain:
        return error(400, "invalid website URL")

    existing = storage.get_discovered_site(normalized)

    if existing:
        return 200, {
            "ok": True,
            "submitted": False,
            "status": existing.get("status", "pending"),
            "url": existing.get("url", normalized),
            "domain": existing.get("domain", domain),
            "message": "This website is already in the discovery queue.",
        }

    created = storage.register_discovered_site(
        normalized,
        domain,
        "website_submission",
        "pending",
    )

    if not created:
        existing = storage.get_discovered_site(normalized)
        return 200, {
            "ok": True,
            "submitted": False,
            "status": existing.get("status", "pending") if existing else "pending",
            "url": normalized,
            "domain": domain,
            "message": "This website is already in the discovery queue.",
        }

    return 202, {
        "ok": True,
        "submitted": True,
        "status": "pending",
        "url": normalized,
        "domain": domain,
        "message": "Website submitted successfully. It will be crawled automatically.",
    }


def handle_page(storage, url: str) -> tuple:
    if not isinstance(url, str):
        return error(400, "url is required")

    url = url.strip()
    if not url:
        return error(400, "url is required")

    page = storage.get_document_by_url(url)
    if page is None:
        return error(404, "page not found")

    return 200, {
        "url": page.url,
        "canonical_url": page.canonical_url,
        "domain": page.domain,
        "title": page.title,
        "description": page.description,
        "headings": page.headings,
        "content": page.content,
        "language": page.language,
        "crawled_at": page.crawled_at,
        "updated_at": page.updated_at,
    }


def handle_discovery(storage, domain: str) -> tuple:
    if not isinstance(domain, str):
        return error(400, "domain is required")

    domain = domain.strip().lower().rstrip(".")
    if not domain:
        return error(400, "domain is required")

    if len(domain) > 253 or any(ch.isspace() for ch in domain):
        return error(400, "invalid domain")

    result = storage.get_domain_discovery(domain)
    if result is None:
        return error(404, "website not found")

    return 200, result

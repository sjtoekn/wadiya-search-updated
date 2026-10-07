"""Small HTML image candidate extractor for Wadiya Images search."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".avif",
    ".svg",
)


def _clean(value: str | None, limit: int = 500) -> str:
    return " ".join((value or "").split())[:limit]


def _absolute_http_url(value: str | None, base_url: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None

    absolute = urljoin(base_url, value)

    try:
        parsed = urlparse(absolute)
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"}:
        return None

    return absolute


def _first_srcset_url(srcset: str | None, base_url: str) -> str | None:
    if not srcset:
        return None

    # Prefer the first valid candidate for the initial implementation.
    for candidate in srcset.split(","):
        value = candidate.strip().split(" ", 1)[0]
        image_url = _absolute_http_url(value, base_url)
        if image_url:
            return image_url

    return None


def _looks_like_image_url(image_url: str) -> bool:
    path = urlparse(image_url).path.lower()
    return path.endswith(IMAGE_EXTENSIONS)


def extract_image_candidates(html: str, page_url: str) -> list[dict]:
    """
    Extract useful image candidates from a crawled HTML page.

    Returns dictionaries containing:
      image_url
      source_page_url
      source_domain
      alt_text
      title
    """
    if not html or not page_url:
        return []

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []

    parsed_page = urlparse(page_url)
    source_domain = parsed_page.netloc.lower()

    results: list[dict] = []
    seen: set[str] = set()

    def add_image(
        image_url: str | None,
        *,
        alt_text: str = "",
        title: str = "",
    ) -> None:
        if not image_url:
            return

        image_url = image_url.strip()

        if not _looks_like_image_url(image_url):
            return

        if image_url in seen:
            return

        seen.add(image_url)

        results.append(
            {
                "image_url": image_url,
                "source_page_url": page_url,
                "source_domain": source_domain,
                "alt_text": _clean(alt_text, 300),
                "title": _clean(title, 300),
            }
        )

    # Standard <img src="...">
    for img in soup.find_all("img"):
        image_url = _absolute_http_url(img.get("src"), page_url)

        # Prefer srcset when src is absent.
        if not image_url:
            image_url = _first_srcset_url(img.get("srcset"), page_url)

        add_image(
            image_url,
            alt_text=img.get("alt"),
            title=img.get("title"),
        )

    # Open Graph image.
    for meta in soup.find_all("meta"):
        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).strip().lower()

        if prop in {"og:image", "og:image:url", "twitter:image"}:
            image_url = _absolute_http_url(
                meta.get("content"),
                page_url,
            )
            add_image(image_url)

    return results

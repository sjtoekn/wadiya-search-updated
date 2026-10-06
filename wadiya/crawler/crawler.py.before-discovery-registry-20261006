"""Crawl orchestration. Fetch -> robots -> extract -> store. No ranking, no index access."""
from __future__ import annotations

import hashlib
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..storage.base import Document, Storage, now_iso
from .extractor import extract
from .feed import parse_feed
from .lock import CrawlLock
from .robots import parse_x_robots_tag
from .sitemap import MAX_SITEMAP_XML_BYTES, parse_sitemap
from .urls import looks_crawlable, normalize_url, site_key


@dataclass
class CrawlStats:
    attempted: int = 0          # URLs we tried to crawl (after scope/limit checks)
    fetched: int = 0            # successfully fetched + extracted
    robots_blocked: int = 0
    failed: int = 0
    stored: int = 0
    duplicates: int = 0
    deactivated: int = 0        # previously searchable documents removed from search this run
    fetch_ms_total: float = 0.0
    fetch_count: int = 0
    duration_s: float = 0.0

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["avg_fetch_ms"] = round(self.fetch_ms_total / self.fetch_count, 1) if self.fetch_count else None
        return d


class Crawler:
    def __init__(self, settings, storage: Storage, fetcher, robots, *, clock=time.monotonic, sleep=time.sleep,
                 lock_path=None):
        self.s, self.storage, self.fetcher, self.robots = settings, storage, fetcher, robots
        self.lock_path = lock_path or (settings.db_path + ".crawl.lock")
        self._clock, self._sleep = clock, sleep
        self._ready_at = {}
        self._sitemap_lock = threading.Lock()
        self._sitemaps_seen = set()
        self._sitemap_pages_seen = set()
        self._sitemap_pages_enqueued = 0

    # ------------------------------------------------------------------ run loop
    def run(self, seeds, fresh: bool = False) -> CrawlStats:
        """Runs a crawl. Raises CrawlAlreadyRunning (touching nothing) if another crawler holds the lock."""
        with CrawlLock(self.lock_path):
            return self._run(seeds, fresh)

    def _run(self, seeds, fresh: bool) -> CrawlStats:
        from .seeds import Scope

        scope = Scope(seeds, self.s)
        self._ready_at = {}
        with self._sitemap_lock:
            self._sitemaps_seen.clear()
            self._sitemap_pages_seen.clear()
            self._sitemap_pages_enqueued = 0
        self.storage.requeue_stale()
        if fresh:
            self.storage.reset_queue()

        run_id = self.storage.start_run()
        stats, t0, state = CrawlStats(), self._clock(), "finished"

        try:
            for seed in seeds:
                u = normalize_url(seed.url)
                if not u or not scope.allows(u):
                    self.storage.log_crawl_event(
                        run_id, str(seed.url), "failed", None, None, "invalid_seed"
                    )
                    continue
                self.storage.enqueue(
                    u, site_key(urlsplit(u).hostname), 0, force=True
                )

            processed = 0
            active_domains = set()
            futures = {}

            with ThreadPoolExecutor(max_workers=max(1, self.s.max_workers)) as executor:
                while processed < self.s.max_total_pages or futures:
                    # Collect completed workers first.
                    completed = [
                        future for future in futures
                        if future.done()
                    ]

                    for future in completed:
                        domain = futures.pop(future)
                        active_domains.discard(domain)
                        self._merge_stats(stats, future.result())

                    # Fill available worker slots without exceeding the
                    # global page limit.
                    while (
                        processed < self.s.max_total_pages
                        and len(futures) < max(1, self.s.max_workers)
                    ):
                        now = self._clock()
                        blocked = {
                            domain
                            for domain, ready_at in self._ready_at.items()
                            if ready_at > now
                        }
                        excluded = blocked | active_domains

                        item = self.storage.claim_next(excluded)
                        if item is None:
                            break

                        processed += 1
                        active_domains.add(item.domain)
                        future = executor.submit(
                            self._process_worker,
                            item,
                            scope,
                            run_id,
                        )
                        futures[future] = item.domain

                    if futures:
                        # Wait until at least one worker finishes instead of
                        # busy-polling. Other domains continue concurrently.
                        done, _ = wait(
                            futures,
                            return_when=FIRST_COMPLETED,
                        )
                        for future in done:
                            domain = futures.pop(future)
                            active_domains.discard(domain)
                            self._merge_stats(stats, future.result())
                        continue

                    if processed >= self.s.max_total_pages:
                        break

                    now = self._clock()
                    blocked = [
                        ready_at
                        for ready_at in self._ready_at.values()
                        if ready_at > now
                    ]

                    if self.storage.queue_size() == 0:
                        break

                    if blocked:
                        self._sleep(max(min(blocked) - now, 0.01))
                        continue

                    # Nothing is active, nothing is delayed, but no item
                    # could be claimed. Avoid a busy loop.
                    self._sleep(0.01)

                # Drain any workers still finishing after the page limit.
                for future, domain in list(futures.items()):
                    self._merge_stats(stats, future.result())
                    active_domains.discard(domain)

            stats.duration_s = round(self._clock() - t0, 2)
            self.storage.update_run(run_id, stats.as_dict())

        except KeyboardInterrupt:
            state = "interrupted"
            raise
        finally:
            stats.duration_s = round(self._clock() - t0, 2)
            self.storage.finish_run(run_id, stats.as_dict(), state)

        return stats

    # ------------------------------------------------------------------ worker
    def _process_worker(self, item, scope, run_id):
        """Process one claimed URL in a worker and return isolated stats."""
        stats = CrawlStats()
        try:
            self._process(item, scope, stats, run_id)
        except Exception as e:
            stats.failed += 1
            self._finish(
                run_id,
                item.url,
                "failed",
                "failed",
                error=f"internal_error: {type(e).__name__}",
            )
        return stats

    def _merge_stats(self, target: CrawlStats, source: CrawlStats):
        """Merge worker-local counters into the crawl-wide stats."""
        target.attempted += source.attempted
        target.fetched += source.fetched
        target.robots_blocked += source.robots_blocked
        target.failed += source.failed
        target.stored += source.stored
        target.duplicates += source.duplicates
        target.deactivated += source.deactivated
        target.fetch_ms_total += source.fetch_ms_total
        target.fetch_count += source.fetch_count

    # --------------------------------------------------------------- sitemaps
    def _sitemap_resource_allowed(self, url, scope):
        normalized = normalize_url(url)
        if not normalized or not scope.allows(normalized):
            return None
        if self.fetcher.validate(normalized):
            return None
        return normalized

    def _sitemap_urls_for(self, url, scope):
        """Return normalized sitemap candidates declared by robots plus /sitemap.xml."""
        candidates = list(self.robots.sitemap_urls(url))
        parts = urlsplit(url)
        if parts.scheme and parts.netloc:
            candidates.append(f"{parts.scheme}://{parts.netloc}/sitemap.xml")

        result = []
        seen = set()
        for candidate in candidates:
            normalized = self._sitemap_resource_allowed(candidate, scope)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    def _enqueue_sitemap_pages(self, urls, item, cfg, scope):
        if item.depth >= cfg.max_depth:
            return

        depth = item.depth + 1
        for url in urls:
            if not looks_crawlable(url) or not scope.allows(url):
                continue

            if not self.robots.is_allowed(url):
                continue

            site = site_key(urlsplit(url).hostname)
            site_cfg = scope.config(site)
            if site_cfg is None:
                continue

            if self.storage.domain_url_count(site) >= site_cfg.max_pages * 5:
                continue

            with self._sitemap_lock:
                if url in self._sitemap_pages_seen:
                    continue
                if self._sitemap_pages_enqueued >= 100_000:
                    continue
                self._sitemap_pages_seen.add(url)
                self._sitemap_pages_enqueued += 1

            self.storage.enqueue(url, site, depth)

    def _discover_sitemaps(self, url, item, cfg, scope):
        """Discover sitemap resources and enqueue their page URLs safely."""
        if item.depth >= cfg.max_depth:
            return

        pending = self._sitemap_urls_for(url, scope)

        while pending:
            sitemap_url = pending.pop(0)

            with self._sitemap_lock:
                if sitemap_url in self._sitemaps_seen:
                    continue
                if len(self._sitemaps_seen) >= 64:
                    continue
                self._sitemaps_seen.add(sitemap_url)

            res = self.fetcher.fetch(
                sitemap_url,
                accept_types={"application/xml", "text/xml"},
                max_bytes=min(self.s.max_response_bytes, MAX_SITEMAP_XML_BYTES),
                redirect_filter=scope.allows,
            )
            if not res.ok:
                continue

            try:
                document = parse_sitemap(res.body, res.final_url or sitemap_url)
            except ValueError:
                continue

            if document.kind == "urlset":
                self._enqueue_sitemap_pages(document.urls, item, cfg, scope)
                continue

            for nested in document.urls:
                normalized = self._sitemap_resource_allowed(nested, scope)
                if normalized:
                    pending.append(normalized)

    def _discover_feeds(self, feed_urls, item, cfg, scope):
        """Fetch discovered RSS/Atom feeds and enqueue their page URLs safely."""
        if item.depth >= cfg.max_depth:
            return

        seen = set()
        for feed_url in feed_urls:
            if feed_url in seen:
                continue
            seen.add(feed_url)

            normalized = normalize_url(feed_url)
            if not normalized or not scope.allows(normalized):
                continue
            if not self.robots.is_allowed(normalized):
                continue

            res = self.fetcher.fetch(
                normalized,
                accept_types={"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"},
                max_bytes=min(self.s.max_response_bytes, 2 * 1024 * 1024),
                redirect_filter=scope.allows,
            )
            if not res.ok:
                continue

            try:
                document = parse_feed(res.body, res.final_url or normalized)
            except ValueError:
                continue

            self._enqueue_links(list(document.urls), item, cfg, scope)

    # ------------------------------------------------------------------ one URL
    def _finish(self, run_id, url, outcome, queue_status, http=None, ms=None, error=None):
        self.storage.mark_url(url, queue_status, http, error)
        self.storage.log_crawl_event(run_id, url, outcome, http, ms, error)

    def _delay_for(self, url) -> float:
        d = max(self.s.default_crawl_delay, self.robots.crawl_delay(url) or 0.0)
        return min(d, self.s.max_crawl_delay)

    def _deactivate(self, urls, reason, stats, by_canonical=True) -> bool:
        ids = self.storage.deactivate_document(urls, reason, by_canonical)
        stats.deactivated += len(ids)
        return bool(ids)

    def _process(self, item, scope, stats: CrawlStats, run_id):
        url, site = item.url, item.domain
        cfg = scope.config(site)
        if cfg is None or not scope.allows(url):
            return self._finish(run_id, url, "skipped", "skipped", error="out_of_scope")
        if self.storage.domain_crawled_count(site) >= cfg.max_pages:
            return self._finish(run_id, url, "skipped", "skipped", error="domain_page_limit")

        stats.attempted += 1
        unsafe = self.fetcher.validate(url)      # report the true reason before robots.txt is even consulted
        if unsafe:
            stats.failed += 1
            stats.deactivated += len(self.storage.record_fetch_failure([url], self.s.max_consecutive_failures))
            return self._finish(run_id, url, "failed", "failed", error=unsafe)
        if not self.robots.is_allowed(url):
            stats.robots_blocked += 1
            note = "disallowed by robots.txt"
            # only an affirmative Disallow removes a page; an unreadable robots.txt must not wipe good documents
            if self.robots.block_reason(url) == "rules" and self._deactivate([url], "robots", stats):
                note += " (removed from index)"
            return self._finish(run_id, url, "robots_blocked", "robots_blocked", error=note)

        res = self.fetcher.fetch(url, redirect_filter=scope.allows)
        self._ready_at[site] = self._clock() + self._delay_for(url)
        stats.fetch_ms_total += res.elapsed_ms
        stats.fetch_count += 1
        if not res.ok:
            stats.failed += 1
            err = res.error or f"http_{res.status}"
            if res.error is None and res.status in (404, 410):        # definitive: the page is gone
                if self._deactivate([url], "gone", stats):
                    err += " (removed from index)"
            else:                                                       # possibly temporary: keep the doc for now
                dropped = self.storage.record_fetch_failure([url], self.s.max_consecutive_failures)
                stats.deactivated += len(dropped)
                if dropped:
                    err += f" (removed from index after {self.s.max_consecutive_failures} failed crawls)"
            return self._finish(run_id, url, "failed", "failed", res.status, res.elapsed_ms, err)

        final = normalize_url(res.final_url) or url
        try:
            page = extract(res.body, final, res.content_type)
        except Exception as e:
            stats.failed += 1
            stats.deactivated += len(self.storage.record_fetch_failure([url], self.s.max_consecutive_failures))
            return self._finish(run_id, url, "failed", "failed", res.status, res.elapsed_ms,
                                f"extract_error: {type(e).__name__}")
        stats.fetched += 1
        final_site = site_key(urlsplit(final).hostname)

        hdr_noindex, hdr_nofollow = parse_x_robots_tag(res.x_robots_tag, self.s.robots_token)
        noindex, nofollow = page.noindex or hdr_noindex, page.nofollow or hdr_nofollow

        # canonical: honoured only when it stays on the same site (a page cannot claim another site's identity)
        canonical = final
        if page.canonical_url and site_key(urlsplit(page.canonical_url).hostname) == final_site:
            canonical = page.canonical_url
        links = [] if nofollow else list(page.links)
        if canonical != final and not nofollow:
            links.append(canonical)
        self._enqueue_links(links, item, cfg, scope)
        self._discover_feeds(page.feed_links, item, cfg, scope)
        self._discover_sitemaps(final, item, cfg, scope)

        if noindex:
            removed = self._deactivate([url, final, canonical], "noindex", stats)
            return self._finish(run_id, url, "noindex", "noindex", res.status, res.elapsed_ms,
                                "removed from index" if removed else None)
        content = page.content[: self.s.max_content_chars]
        if not content.strip():
            removed = self._deactivate([url, final, canonical], "empty", stats)
            return self._finish(run_id, url, "skipped", "skipped", res.status, res.elapsed_ms,
                                "empty_content" + (" (removed from index)" if removed else ""))
        if final != url:        # the requested URL now redirects: it no longer serves the page itself
            self._deactivate([url], "moved", stats, by_canonical=False)

        now = now_iso()
        doc = Document(id=None, url=final, canonical_url=canonical, domain=final_site, title=page.title,
                       description=page.description, content=content, language=page.language, status="ok",
                       content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                       crawled_at=now, updated_at=now, headings="\n".join(page.headings))
        saved = self.storage.save_document(doc)
        if saved.outcome == "duplicate":
            stats.duplicates += 1
            return self._finish(run_id, url, "duplicate", "duplicate", res.status, res.elapsed_ms)
        if saved.outcome in ("inserted", "updated", "reactivated"):
            stats.stored += 1
        self._finish(run_id, url, "stored" if saved.outcome == "inserted" else saved.outcome, "done",
                     res.status, res.elapsed_ms)

    def _enqueue_links(self, links, item, cfg, scope):
        if item.depth >= cfg.max_depth:
            return
        for link in links:
            if not looks_crawlable(link) or not scope.allows(link):
                continue
            site = site_key(urlsplit(link).hostname)
            site_cfg = scope.config(site)
            if self.storage.domain_url_count(site) >= site_cfg.max_pages * 5:   # bound queue growth
                continue
            self.storage.enqueue(link, site, item.depth + 1)

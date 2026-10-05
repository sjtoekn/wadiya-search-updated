# Wadiya — Project Context

## What this project is

Wadiya is an independent web search engine being built from the ground up.

The goal is to help people discover the web, not replace the web.

## Current architecture

Seeds / Discovery
        ↓
      Crawler
        ↓
     Storage
        ↓
      Indexer
        ↓
    Retrieval
        ↓
     Ranking
        ↓
     Search
        ↓
       API
        ↓
      Web UI

## Phase 0

Phase 0 is COMPLETE and FROZEN.

Verification:
- Python tests: 153/153 PASS
- Live HTTP: 45/45 PASS
- Browser: 42/42 PASS
- Total: 340/340 checks PASS

Phase 0 fixes:
- API security headers were fixed for JSON exception responses.
- Browser test timing/CSP handling was stabilized.

Do not modify Phase 0 unless a later phase requires a verified change.

## Phase 1

Current roadmap:

M1 Concurrent crawler workers
M2 URL discovery improvements
M3 Sitemap / feed discovery
M4 Persistent retry/backoff
M5 Recrawl scheduler
M6 Deduplication improvements
M7 Crawl observability
M8 Search quality/ranking
M9 Scale/storage migration

Current task: M1.

## M1 requirements

M1 should introduce multiple crawler workers while keeping the current architecture.

Requirements:
- One crawler process.
- Keep CrawlLock.
- Initial worker target: about 4 workers.
- Keep the existing SQLite queue.
- Different domains may fetch concurrently.
- The same domain must not be fetched concurrently.
- max_total_pages must remain exact under concurrency.
- A worker failure must not kill the entire crawl.
- Preserve robots.txt handling.
- Preserve crawl-delay handling.
- Preserve retries.
- Preserve redirect validation.
- Preserve SSRF protection.
- Preserve canonical/noindex/nofollow handling.
- Preserve duplicate handling.
- Preserve stale queue recovery.
- Preserve crawl statistics.
- Preserve SQLite integrity.
- Preserve index consistency.

Do not add Redis, Celery, PostgreSQL, asyncio, or distributed infrastructure for M1.

Make the smallest necessary source changes and add focused tests.

## SearchLab reference

An earlier experimental project called SearchLab exists separately.

Useful ideas from it:
- sitemap discovery
- title weighting
- exact phrase signals
- all-term matching

Do not merge SearchLab wholesale.

Wadiya already has the more mature architecture:
SQLite FTS5, BM25 ranking, persistent queue, interfaces, and security controls.

## Future direction

Long-term Wadiya may include:
- broader discovery mesh
- sitemap/feed discovery
- publisher submissions
- publisher notifications
- freshness-aware crawling
- discovery priority
- search-demand-driven discovery
- coverage-gap detection
- change-aware indexing
- web quality signals
- website identity
- local web discovery
- publisher/webmaster tools
- source-first AI answers
- knowledge graph
- eventual distributed crawling/indexing when actually needed

Core principle:

"Wadiya should help people discover the web, not replace the web."

"AI should help the web, not replace the web."

## Working rules

- Audit before changing code.
- One phase at a time.
- One topic at a time.
- Prefer small verified changes.
- Run focused tests after changes.
- Do not make unrelated refactors.
- Do not replace working architecture without evidence.
- Keep the project understandable to another developer or AI assistant.

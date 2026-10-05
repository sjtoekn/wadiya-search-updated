# Wadiya.com — Phase 0

Phase 0 is a **controlled prototype** of an independent search engine. It proves one loop works end to end:

```
seed URLs → crawl (robots.txt-respecting) → extract → store → index (SQLite FTS5) → rank (BM25) → API → web UI
```

**It is not production-scale web search.** It crawls a short, hand-picked list of sites (tens of sites, hundreds of
pages), on one machine, one page at a time. Treat everything below as prototype-level.

## Architecture

| Package | Responsibility (and nothing else) |
|---|---|
| `wadiya/crawler` | URL normalisation + SSRF checks, robots.txt, safe fetcher, HTML extractor, crawl orchestration, single-crawler lock |
| `wadiya/storage` | Documents, URL queue, crawl log, query log (interface + SQLite) |
| `wadiya/indexer` | The search index (interface + SQLite FTS5, its own database file) |
| `wadiya/ranking` | Result ordering (interface + BM25 with title > headings > description > body weights) |
| `wadiya/query` | Query text → terms / phrases (no index syntax) |
| `wadiya/search` | Orchestration: parse → retrieve → rank → hydrate → snippet |
| `wadiya/api` | HTTP: `handlers.py` (logic), `app.py` (FastAPI wiring), `security.py`, `limits.py` |
| `wadiya/admin` | Password hashing, signed sessions, dashboard data |
| `wadiya/web` | Plain HTML/CSS/JS UI (no framework, no inline scripts/styles) |
| `wadiya/pipeline.py` | The only place that knows both storage and index (keeps them in sync) |

The crawler never ranks, the API never crawls, the UI only talks to the API.

## Requirements

* Python 3.12 (the only version this was developed and tested on; 3.10+ is expected to work)
* `pip install -r requirements.txt` → fastapi, uvicorn, beautifulsoup4, lxml, itsdangerous, PyYAML
* To run tests: `pip install -r requirements-dev.txt` (adds pytest, httpx). `unittest` also works.
* SQLite with FTS5 (included in standard Python builds)
* Browser test only: Node.js + Playwright with Chromium

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m wadiya init            # creates data/wadiya.db and data/wadiya_index.db
```

## Environment variables

Defaults are safe. Secrets are read **only** from the environment; there are no built-in credentials.

| Variable | Default | Meaning |
|---|---|---|
| `WADIYA_DB_PATH` | `data/wadiya.db` | Documents, queue, logs |
| `WADIYA_INDEX_PATH` | `data/wadiya_index.db` | FTS5 index (can be rebuilt from the DB) |
| `WADIYA_SEEDS_PATH` | `wadiya/config/seeds.yaml` | Seed list |
| `WADIYA_USER_AGENT` | `WadiyaBot/0.1 (+https://wadiya.com/bot)` | **Set a real contact URL before crawling** |
| `WADIYA_ADMIN_PASSWORD_HASH` | *(empty → admin disabled)* | From `python -m wadiya hash-password` |
| `WADIYA_SECRET_KEY` | *(empty → admin disabled)* | ≥ 32 chars: `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `WADIYA_COOKIE_SECURE` | `true` | Set `false` only for local `http://` development |

Crawl limits (depth, pages per site, delay, timeouts, size caps, retry counts) are fields of
`wadiya/config/settings.py`.

## Run the server

```bash
python -m wadiya serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. The server does not terminate TLS — put it behind a reverse proxy for HTTPS (the admin
cookie is `Secure` by default and will not be sent over plain HTTP; for local development set
`WADIYA_COOKIE_SECURE=false`). Access logging is off so search queries are not written to server logs.

## Run the crawler

1. Edit `wadiya/config/seeds.yaml`. **Only add sites you are allowed to crawl.** The shipped entries are
   placeholders that were not reachable from the build environment — check each site's terms and robots.txt.
   ```yaml
   seeds:
     - url: https://example.org/docs/
       path_prefix: /docs/     # optional: stay under this path
       max_pages: 30           # optional per-site page cap
       max_depth: 1            # optional link depth (0 = seed only)
   ```
2. `python -m wadiya crawl` (add `--fresh` to reset the URL queue and re-crawl; documents are kept).
3. The crawl ends by syncing the index. Manual commands: `python -m wadiya index`, `reindex`, `stats`.

Behaviour: obeys robots.txt (wildcards, longest-match, crawl-delay) and `noindex`/`nofollow` in both `<meta robots>` and
the `X-Robots-Tag` header; stays inside the seed sites; only fetches public `http(s)` addresses on ports 80/443; follows
at most 5 redirects, re-validating each hop; caps response size and time. Only one crawler can run at a time
(`<db_path>.crawl.lock`, released by the OS if the process dies).

**Document lifecycle.** A page that now returns 404/410, is `noindex`, is newly disallowed by robots.txt, or moved, is
removed from search (its row is kept, its text cleared). A *temporary* failure (timeout, 5xx, 429, 401/403, DNS) keeps
the document; it is dropped only after 3 failed crawls in a row. A page that returns is searchable again.

## Search API

```
GET /api/search?q=<query>&page=<1..10>
```

```json
{"query": "wadi", "page": 1, "page_size": 10, "total_pages": 1, "result_count": 3,
 "result_count_exact": true, "match": "all", "latency_ms": 1.2,
 "results": [{"title": "…", "url": "https://…", "domain": "example.org", "snippet": "…"}]}
```

* `"quoted phrases"` are matched as phrases. All terms must match (`match: "all"`); if nothing matches, it falls back
  to any term (`match: "any"`).
* `q` is 1–200 characters; `page` is 1–10 (the ranking window is 100 results). Invalid input → `400`
  `{"error": {"code": 400, "message": "…"}}`. `GET /api/health` → `{"status": "ok"}`.

## Admin area

```bash
python -m wadiya hash-password                    # prompts, prints an export line for WADIYA_ADMIN_PASSWORD_HASH
export WADIYA_ADMIN_PASSWORD_HASH='scrypt$…'
export WADIYA_SECRET_KEY='…'
python -m wadiya serve
```

Open `/admin`: index size, domains, crawler status/queue, success/failure counts, recent errors, search count, average
latency, recent queries. Admin is **disabled** (login returns 503) unless both variables are set. Login is limited to
5 failures per 5 minutes per client address; login bodies are capped at 4 KB.

## Tests and verification

```bash
python -m unittest discover -s tests -t .          # or: pytest
python scripts/verify_live_http.py --spawn         # starts the REAL app and checks it over HTTP (needs fastapi/uvicorn)
PLAYWRIGHT_BROWSERS_PATH=… NODE_PATH=… node tests/browser/ui_browser_test.js   # real Chromium, 42 checks
```

Tests use a local mock website and never touch the internet. Without FastAPI installed the HTTP-level tests
(`tests/test_api_http.py`, one case in `tests/test_e2e.py`) are skipped — install the dev requirements to run them.
`tests/browser/dev_server.py` is a stdlib stand-in used only so the browser test can run without FastAPI; it is not the
application.

## Security model (summary)

* **SSRF:** every URL and every redirect hop is resolved and rejected if *any* address is non-public (loopback, private,
  link-local/cloud metadata, CGNAT, multicast, v4-mapped/NAT64/6to4 v6); the connection is pinned to the vetted IP
  (no second DNS lookup); TLS is validated against the hostname.
* **Crawled content is hostile:** the UI renders with `textContent` only; CSP is `default-src 'self'` with no inline
  script/style; result links must be `http(s)` and carry `rel="noopener noreferrer nofollow"`.
* **SQL:** all values are parameterised; user text is quoted into FTS5 phrases and can never become query syntax.
* **Admin:** scrypt hash from the environment, constant-time compare, signed expiring `HttpOnly; SameSite=Strict;
  Secure` cookie, JSON-only login (blocks cross-site form posts).

## Known limitations

* The FastAPI layer was **not executed in the build environment** (packages could not be installed there). Run
  `scripts/verify_live_http.py --spawn` and the full test suite on a normal machine before relying on it.
* Never run against real websites during development; seeds are placeholders. The fetcher sends
  `Accept-Encoding: identity`, so servers that insist on compressed responses will be recorded as failures.
* Admin sessions are stateless signed cookies: logging out clears the cookie but does not revoke a copied token before
  it expires (8 h). The login rate limiter is in-memory, per client address and per process (behind a proxy, configure
  forwarded client addresses or all users share one counter).
* Crawler: one page at a time, one crawler at a time, no JavaScript rendering, no sitemap support, no scheduling
  (re-crawls are manual), only `noindex`/`nofollow`/`none` are honoured from robots directives.
* Search: BM25 only (no link analysis, freshness or quality signals), English stemming, result window of 100, counts
  capped at 10,000, heuristic snippets that may repeat a page heading.
* A single 404 removes a page from search until it is crawled successfully again.
* Single machine, SQLite (WAL). Search queries (without IP addresses) are kept in `query_log` (last 10,000) and are
  visible to admins. `/admin` serves a static shell; all of its data endpoints require the session.

## Replacing SQLite / FTS5 later

Each layer is behind an interface: implement `Storage` (`wadiya/storage/base.py`) for another database,
`Indexer` (`wadiya/indexer/base.py`) for another engine, `Ranker` (`wadiya/ranking/base.py`) for other ordering, then
pass them to `create_app(settings, storage, indexer, ranker)` and the crawler. The API, UI, crawler and ranker never
import SQLite or FTS5 directly.

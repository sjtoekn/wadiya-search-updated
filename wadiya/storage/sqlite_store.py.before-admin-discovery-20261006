"""SQLite implementation of Storage. One short-lived connection per operation (WAL mode),
so the crawler process and the API process can safely share the same file."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Sequence

from .base import Document, QueueItem, SaveResult, Storage, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  canonical_url TEXT NOT NULL UNIQUE,
  domain TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  headings TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  language TEXT,
  status TEXT NOT NULL DEFAULT 'ok',
  content_hash TEXT NOT NULL,
  crawled_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  indexed_at TEXT,
  fail_count INTEGER NOT NULL DEFAULT 0,
  nosnippet INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);

CREATE TABLE IF NOT EXISTS urls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  domain TEXT NOT NULL,
  depth INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER,
  last_error TEXT,
  added_at TEXT NOT NULL,
  last_attempt_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_urls_pick ON urls(status, depth, id);
CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain, status);

CREATE TABLE IF NOT EXISTS crawl_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  state TEXT NOT NULL DEFAULT 'running',
  attempted INTEGER NOT NULL DEFAULT 0,
  fetched INTEGER NOT NULL DEFAULT 0,
  robots_blocked INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  stored INTEGER NOT NULL DEFAULT 0,
  duplicates INTEGER NOT NULL DEFAULT 0,
  fetch_ms_total REAL NOT NULL DEFAULT 0,
  fetch_count INTEGER NOT NULL DEFAULT 0,
  duration_s REAL NOT NULL DEFAULT 0,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS crawl_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER,
  url TEXT NOT NULL,
  at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  http_status INTEGER,
  fetch_ms REAL,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_crawl_log_outcome ON crawl_log(outcome, id);

CREATE TABLE IF NOT EXISTS query_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  query TEXT NOT NULL,
  result_count INTEGER NOT NULL,
  latency_ms REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS discovered_sites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  domain TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_crawled_at TEXT,
  crawl_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  next_attempt_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_discovered_sites_domain
  ON discovered_sites(domain);
CREATE INDEX IF NOT EXISTS idx_discovered_sites_status
  ON discovered_sites(status, id);
CREATE INDEX IF NOT EXISTS idx_discovered_sites_source
  ON discovered_sites(source, id);
"""

_RUN_COLS = ("attempted", "fetched", "robots_blocked", "failed", "stored",
             "duplicates", "fetch_ms_total", "fetch_count", "duration_s")
_DOC_COLS = ("url", "canonical_url", "domain", "title", "description", "headings", "content",
             "language", "status", "content_hash", "crawled_at", "updated_at", "nosnippet")
_COUNTED = ("done", "duplicate", "noindex")   # statuses that consumed a page of the domain budget
QUERY_LOG_KEEP = 10_000

# Database schema version. Increment this when a new migration is added.
SCHEMA_VERSION = 4


def _doc(row: sqlite3.Row) -> Document:
    return Document(**{k: row[k] for k in row.keys()})


class SQLiteStorage(Storage):
    def __init__(self, path: str):
        if path == ":memory:":
            raise ValueError("use a file path; connections are per-operation")
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self, write: bool = False):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.execute("COMMIT")
        except BaseException:
            if write and conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)

            current_version = int(
                c.execute("PRAGMA user_version").fetchone()[0]
            )

            if current_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema version {current_version} is newer "
                    f"than supported version {SCHEMA_VERSION}"
                )

            # Migration 1: add lifecycle failure tracking to older databases.
            # The CREATE TABLE schema already contains this column for new DBs,
            # so this only runs when upgrading an older schema.
            if current_version < 1:
                cols = {
                    r[1]
                    for r in c.execute("PRAGMA table_info(documents)")
                }
                if "fail_count" not in cols:
                    c.execute(
                        "ALTER TABLE documents "
                        "ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0"
                    )

                c.execute("PRAGMA user_version = 1")
                current_version = 1

            # Migration 2: automatic discovery registry.
            if current_version < 2:
                c.execute(
                    """
                    CREATE TABLE IF NOT EXISTS discovered_sites (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      url TEXT NOT NULL UNIQUE,
                      domain TEXT NOT NULL,
                      source TEXT NOT NULL,
                      status TEXT NOT NULL DEFAULT 'pending',
                      first_seen_at TEXT NOT NULL,
                      last_seen_at TEXT NOT NULL,
                      last_crawled_at TEXT,
                      crawl_count INTEGER NOT NULL DEFAULT 0,
                      failure_count INTEGER NOT NULL DEFAULT 0,
                      last_error TEXT
                    )
                    """
                )
                c.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "idx_discovered_sites_domain "
                    "ON discovered_sites(domain)"
                )
                c.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "idx_discovered_sites_status "
                    "ON discovered_sites(status, id)"
                )
                c.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "idx_discovered_sites_source "
                    "ON discovered_sites(source, id)"
                )
                c.execute("PRAGMA user_version = 2")
                current_version = 2

            # Migration 3: publisher snippet suppression.
            if current_version < 3:
                cols = {
                    r[1]
                    for r in c.execute("PRAGMA table_info(documents)")
                }
                if "nosnippet" not in cols:
                    c.execute(
                        "ALTER TABLE documents "
                        "ADD COLUMN nosnippet INTEGER NOT NULL DEFAULT 0"
                    )
                c.execute("PRAGMA user_version = 3")
                current_version = 3

            # Migration 4: retry scheduling for failed discovered sites.
            if current_version < 4:
                cols = {
                    r[1]
                    for r in c.execute("PRAGMA table_info(discovered_sites)")
                }
                if "next_attempt_at" not in cols:
                    c.execute(
                        "ALTER TABLE discovered_sites "
                        "ADD COLUMN next_attempt_at TEXT"
                    )

                c.execute("PRAGMA user_version = 4")
                current_version = 4

            if current_version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"database migration incomplete: "
                    f"version {current_version}, expected {SCHEMA_VERSION}"
                )

    # ------------------------------------------------------------------ documents
    def save_document(self, doc: Document) -> SaveResult:
        now = now_iso()
        vals = {k: getattr(doc, k) for k in _DOC_COLS}
        with self._conn(write=True) as c:
            ex = c.execute("SELECT id, url, content_hash, status FROM documents WHERE canonical_url=?",
                           (doc.canonical_url,)).fetchone()
            if ex:
                active = ex["status"] == "ok"
                if ex["url"] != doc.url:
                    # Same canonical page reached via another URL: the canonical URL itself wins,
                    # otherwise this is a duplicate.
                    clash = c.execute("SELECT 1 FROM documents WHERE url=? AND id<>?", (doc.url, ex["id"])).fetchone()
                    if clash or (active and doc.url != doc.canonical_url):
                        return SaveResult("duplicate", ex["id"])
                elif active and ex["content_hash"] == doc.content_hash:
                    c.execute(
                        "UPDATE documents SET crawled_at=?, fail_count=0, nosnippet=? WHERE id=?",
                        (now, int(bool(doc.nosnippet)), ex["id"]),
                    )
                    return SaveResult("unchanged", ex["id"])
                self._update(c, ex["id"], vals, now)
                return SaveResult("updated" if active else "reactivated", ex["id"])

            # only ACTIVE documents can make a new page a duplicate
            if c.execute("SELECT 1 FROM documents WHERE content_hash=? AND url<>? AND status='ok'",
                         (doc.content_hash, doc.url)).fetchone():
                return SaveResult("duplicate", None)

            byurl = c.execute("SELECT id, status FROM documents WHERE url=?", (doc.url,)).fetchone()
            if byurl:   # same URL, canonical changed
                self._update(c, byurl["id"], vals, now)
                return SaveResult("updated" if byurl["status"] == "ok" else "reactivated", byurl["id"])

            cur = c.execute(
                f"INSERT INTO documents ({','.join(_DOC_COLS)}) VALUES ({','.join('?' * len(_DOC_COLS))})",
                [vals[k] for k in _DOC_COLS])
            return SaveResult("inserted", cur.lastrowid)

    @staticmethod
    def _match_active(c, urls, by_canonical: bool):
        urls = [u for u in dict.fromkeys(urls) if u]
        if not urls:
            return []
        q = ",".join("?" * len(urls))
        cond = f"url IN ({q})" + (f" OR canonical_url IN ({q})" if by_canonical else "")
        return c.execute(f"SELECT id, fail_count FROM documents WHERE status='ok' AND ({cond})",
                         urls + (urls if by_canonical else [])).fetchall()

    @staticmethod
    def _deactivate(c, ids, status: str, now: str) -> None:
        c.execute(f"UPDATE documents SET status=?, content='', headings='', description='', fail_count=0, "
                  f"indexed_at=NULL, updated_at=? WHERE id IN ({','.join('?' * len(ids))})", [status, now] + list(ids))

    def deactivate_document(self, urls, status: str, by_canonical: bool = True) -> list:
        with self._conn(write=True) as c:
            ids = [r["id"] for r in self._match_active(c, urls, by_canonical)]
            if ids:
                self._deactivate(c, ids, status, now_iso())
            return ids

    def record_fetch_failure(self, urls, threshold: int) -> list:
        dropped, now = [], now_iso()
        with self._conn(write=True) as c:
            for r in self._match_active(c, urls, True):
                n = r["fail_count"] + 1
                if n >= threshold:
                    self._deactivate(c, [r["id"]], "unreachable", now)
                    dropped.append(r["id"])
                else:
                    c.execute("UPDATE documents SET fail_count=? WHERE id=?", (n, r["id"]))
        return dropped

    @staticmethod
    def _update(c, doc_id: int, vals: dict, now: str) -> None:
        cols = [k for k in _DOC_COLS if k not in ("crawled_at", "updated_at")]
        sets = ",".join(f"{k}=?" for k in cols)
        c.execute(f"UPDATE documents SET {sets}, crawled_at=?, updated_at=?, indexed_at=NULL, fail_count=0 WHERE id=?",
                  [vals[k] for k in cols] + [now, now, doc_id])

    def get_documents(self, ids: Sequence[int]) -> dict:
        ids = list(ids)
        if not ids:
            return {}
        with self._conn() as c:
            rows = c.execute(f"SELECT * FROM documents WHERE id IN ({','.join('?' * len(ids))})", ids)
            return {r["id"]: _doc(r) for r in rows}

    def get_document_by_url(self, url: str) -> Optional[Document]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM documents WHERE (url=? OR canonical_url=?) AND status='ok' LIMIT 1",
                (url, url),
            ).fetchone()
            return _doc(row) if row else None

    def documents_needing_index(self, limit: int) -> list:
        with self._conn() as c:
            return [_doc(r) for r in c.execute(
                "SELECT * FROM documents WHERE indexed_at IS NULL ORDER BY id LIMIT ?", (limit,))]

    def mark_indexed(self, ids: Sequence[int]) -> None:
        ids = list(ids)
        if ids:
            with self._conn(write=True) as c:
                c.execute(f"UPDATE documents SET indexed_at=? WHERE id IN ({','.join('?' * len(ids))})",
                          [now_iso()] + ids)

    def reset_indexed(self) -> None:
        with self._conn(write=True) as c:
            c.execute("UPDATE documents SET indexed_at=NULL")

    def count_documents(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM documents WHERE status='ok'").fetchone()[0]

    def count_domains(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(DISTINCT domain) FROM documents WHERE status='ok'").fetchone()[0]

    def get_domain_discovery(self, domain: str) -> dict | None:
        with self._conn() as c:
            summary = c.execute(
                "SELECT domain, count(*) AS page_count, "
                "min(crawled_at) AS first_crawled, max(crawled_at) AS last_crawled "
                "FROM documents WHERE status='ok' AND domain=? "
                "GROUP BY domain",
                (domain,),
            ).fetchone()

            if not summary:
                return None

            pages = c.execute(
                "SELECT url, title, description, language, crawled_at "
                "FROM documents WHERE status='ok' AND domain=? "
                "ORDER BY id",
                (domain,),
            ).fetchall()

            return {
                "domain": summary["domain"],
                "page_count": summary["page_count"],
                "first_crawled": summary["first_crawled"],
                "last_crawled": summary["last_crawled"],
                "pages": [dict(row) for row in pages],
            }

    # ---------------------------------------------------------- discovery registry
    def register_discovered_site(
        self,
        url: str,
        domain: str,
        source: str,
        status: str = "pending",
    ) -> bool:
        now = now_iso()
        with self._conn(write=True) as c:
            existing = c.execute(
                "SELECT id FROM discovered_sites WHERE url=?",
                (url,),
            ).fetchone()

            if existing:
                c.execute(
                    "UPDATE discovered_sites SET last_seen_at=? WHERE url=?",
                    (now, url),
                )
                return False

            c.execute(
                """
                INSERT INTO discovered_sites (
                  url, domain, source, status, first_seen_at, last_seen_at
                )
                VALUES (?,?,?,?,?,?)
                """,
                (url, domain, source, status, now, now),
            )
            return True

    def get_discovered_site(self, url: str) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM discovered_sites WHERE url=?",
                (url,),
            ).fetchone()
            return dict(row) if row else None

    def list_discovered_sites(
        self,
        status: str | None = None,
        limit: int = 100,
        *,
        eligible_only: bool = False,
    ) -> list:
        limit = max(1, min(int(limit), 1000))
        now = now_iso()

        with self._conn() as c:
            if eligible_only:
                rows = c.execute(
                    "SELECT * FROM discovered_sites "
                    "WHERE status='pending' "
                    "OR (status='failed' AND "
                    "(next_attempt_at IS NULL OR next_attempt_at<=?)) "
                    "ORDER BY id ASC LIMIT ?",
                    (now, limit),
                ).fetchall()
            elif status is None:
                rows = c.execute(
                    "SELECT * FROM discovered_sites "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM discovered_sites "
                    "WHERE status=? ORDER BY id DESC LIMIT ?",
                    (status, limit),
                ).fetchall()

            return [dict(row) for row in rows]

    def mark_discovered_site_crawled(
        self,
        url: str,
        success: bool,
        error: str | None = None,
        next_attempt_at: str | None = None,
    ) -> None:
        now = now_iso()
        with self._conn(write=True) as c:
            if success:
                c.execute(
                    """
                    UPDATE discovered_sites
                    SET status='active',
                        last_crawled_at=?,
                        crawl_count=crawl_count+1,
                        failure_count=0,
                        last_error=NULL,
                        next_attempt_at=NULL,
                        last_seen_at=?
                    WHERE url=?
                    """,
                    (now, now, url),
                )
            else:
                c.execute(
                    """
                    UPDATE discovered_sites
                    SET status='failed',
                        last_crawled_at=?,
                        crawl_count=crawl_count+1,
                        failure_count=failure_count+1,
                        last_error=?,
                        next_attempt_at=?,
                        last_seen_at=?
                    WHERE url=?
                    """,
                    (
                        now,
                        error[:300] if error else None,
                        next_attempt_at,
                        now,
                        url,
                    ),
                )

    # ------------------------------------------------------------------ queue
    def enqueue(self, url: str, domain: str, depth: int, force: bool = False) -> bool:
        with self._conn(write=True) as c:
            if force:
                cur = c.execute(
                    "INSERT INTO urls (url, domain, depth, added_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(url) DO UPDATE SET status='pending', depth=min(depth, excluded.depth) "
                    "WHERE status <> 'in_progress'", (url, domain, depth, now_iso()))
            else:
                cur = c.execute("INSERT OR IGNORE INTO urls (url, domain, depth, added_at) VALUES (?,?,?,?)",
                                (url, domain, depth, now_iso()))
            return cur.rowcount > 0

    def claim_next(self, exclude_domains: Sequence[str] = ()) -> Optional[QueueItem]:
        ex = list(exclude_domains)
        sql = "SELECT id, url, domain, depth, attempts FROM urls WHERE status='pending'"
        if ex:
            sql += f" AND domain NOT IN ({','.join('?' * len(ex))})"
        sql += " ORDER BY depth, id LIMIT 1"
        with self._conn(write=True) as c:
            r = c.execute(sql, ex).fetchone()
            if not r:
                return None
            c.execute("UPDATE urls SET status='in_progress', attempts=attempts+1, last_attempt_at=? WHERE id=?",
                      (now_iso(), r["id"]))
            return QueueItem(r["id"], r["url"], r["domain"], r["depth"], r["attempts"] + 1)

    def mark_url(self, url, status, http_status=None, error=None) -> None:
        with self._conn(write=True) as c:
            c.execute("UPDATE urls SET status=?, http_status=?, last_error=? WHERE url=?",
                      (status, http_status, error[:300] if error else None, url))

    def queue_size(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM urls WHERE status='pending'").fetchone()[0]

    def queue_counts(self) -> dict:
        with self._conn() as c:
            return {r[0]: r[1] for r in c.execute("SELECT status, count(*) FROM urls GROUP BY status")}

    def domain_crawled_count(self, domain: str) -> int:
        with self._conn() as c:
            return c.execute(
                f"SELECT count(*) FROM urls WHERE domain=? AND status IN ({','.join('?' * len(_COUNTED))})",
                (domain, *_COUNTED)).fetchone()[0]

    def domain_url_count(self, domain: str) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM urls WHERE domain=?", (domain,)).fetchone()[0]

    def requeue_stale(self) -> int:
        with self._conn(write=True) as c:
            return c.execute("UPDATE urls SET status='pending' WHERE status='in_progress'").rowcount

    def reset_queue(self) -> None:
        with self._conn(write=True) as c:
            c.execute("DELETE FROM urls")

    # ------------------------------------------------------------------ crawl metrics
    def start_run(self) -> int:
        with self._conn(write=True) as c:
            now = now_iso()
            return c.execute("INSERT INTO crawl_runs (started_at, updated_at) VALUES (?,?)",
                             (now, now)).lastrowid

    def update_run(self, run_id: int, stats: dict) -> None:
        sets = ",".join(f"{k}=?" for k in _RUN_COLS)
        with self._conn(write=True) as c:
            c.execute(f"UPDATE crawl_runs SET {sets}, updated_at=? WHERE id=?",
                      [stats.get(k, 0) for k in _RUN_COLS] + [now_iso(), run_id])

    def finish_run(self, run_id: int, stats: dict, state: str) -> None:
        self.update_run(run_id, stats)
        with self._conn(write=True) as c:
            c.execute("UPDATE crawl_runs SET state=?, finished_at=? WHERE id=?", (state, now_iso(), run_id))

    def log_crawl_event(self, run_id, url, outcome, http_status, fetch_ms, error) -> None:
        with self._conn(write=True) as c:
            c.execute("INSERT INTO crawl_log (run_id,url,at,outcome,http_status,fetch_ms,error) VALUES (?,?,?,?,?,?,?)",
                      (run_id, url[:2048], now_iso(), outcome, http_status, fetch_ms,
                       error[:300] if error else None))

    def last_run(self) -> Optional[dict]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT 1").fetchone()
            return dict(r) if r else None

    def recent_crawl_errors(self, limit: int = 15) -> list:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT at, url, outcome, http_status, error FROM crawl_log "
                "WHERE outcome IN ('failed','robots_blocked') ORDER BY id DESC LIMIT ?", (limit,))]

    # ------------------------------------------------------------------ search metrics
    def log_query(self, query: str, result_count: int, latency_ms: float) -> None:
        with self._conn(write=True) as c:
            c.execute("INSERT INTO query_log (at, query, result_count, latency_ms) VALUES (?,?,?,?)",
                      (now_iso(), query[:200], int(result_count), float(latency_ms)))
            c.execute("DELETE FROM query_log WHERE id <= (SELECT max(id) FROM query_log) - ?", (QUERY_LOG_KEEP,))

    def search_stats(self) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT count(*), avg(latency_ms) FROM query_log").fetchone()
            return {"search_count": r[0], "avg_latency_ms": round(r[1], 2) if r[1] is not None else None}

    def recent_queries(self, limit: int = 15) -> list:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT at, query, result_count, latency_ms FROM query_log ORDER BY id DESC LIMIT ?", (limit,))]

"""Read-only developer dashboard data. Uses only the Storage and Indexer interfaces."""
from __future__ import annotations

from datetime import datetime, timezone

STALE_AFTER_S = 120


def _crawler_status(last) -> str:
    if not last:
        return "never run"
    if last["state"] == "running":
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(last["updated_at"])).total_seconds()
        except Exception:
            age = 10 ** 9
        return "running" if age < STALE_AFTER_S else "stalled / interrupted"
    return "idle"


def build_stats(storage, indexer) -> dict:
    last = storage.last_run()
    counts = storage.queue_counts()
    last_out = None
    if last:
        n = last["fetch_count"]
        last_out = {k: last[k] for k in ("started_at", "finished_at", "state", "attempted", "fetched",
                                         "robots_blocked", "failed", "stored", "duplicates", "duration_s")}
        last_out["avg_fetch_ms"] = round(last["fetch_ms_total"] / n, 1) if n else None
    return {
        "documents": storage.count_documents(),
        "domains": storage.count_domains(),
        "index": indexer.info(),
        "crawler": {"status": _crawler_status(last), "queue_size": counts.get("pending", 0),
                    "successful_crawls": counts.get("done", 0), "failed_crawls": counts.get("failed", 0),
                    "robots_blocked": counts.get("robots_blocked", 0), "queue_by_status": counts,
                    "last_crawl": last_out},
        "recent_errors": storage.recent_crawl_errors(15),
        "search": {**storage.search_stats(), "recent_queries": storage.recent_queries(15)},
    }

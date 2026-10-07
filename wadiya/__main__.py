"""CLI:  python -m wadiya <command>
  init | crawl [--fresh] [--seeds FILE] | images-backfill [--batch N] [--delay SEC] | index | reindex | stats | serve [--host H --port P] | hash-password"""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from .config.settings import Settings
from .indexer.fts5 import FTS5Indexer
from .pipeline import index_pending, rebuild_index
from .storage.sqlite_store import SQLiteStorage


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wadiya")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    c = sub.add_parser("crawl"); c.add_argument("--fresh", action="store_true", help="reset the URL queue first")
    c.add_argument("--seeds"); c.add_argument("--no-index", action="store_true")
    c.add_argument("--continuous", action="store_true",
                   help="keep running crawl/discovery/index cycles")
    c.add_argument("--interval", type=float, default=60.0,
                   help="seconds between continuous crawl cycles")
    ib = sub.add_parser(
        "images-backfill",
        help="extract and persist images for existing documents that have no image rows",
    )
    ib.add_argument("--batch", type=int, default=50,
                    help="documents processed per batch")
    ib.add_argument("--delay", type=float, default=0.0,
                    help="minimum delay in seconds between fetches")
    ib.add_argument("--max-docs", type=int, default=0,
                    help="maximum total documents to process; 0 means no limit")
    sub.add_parser("index"); sub.add_parser("reindex"); sub.add_parser("stats"); sub.add_parser("hash-password")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--forwarded-allow-ips", default="127.0.0.1")
    args = ap.parse_args(argv)

    if args.cmd == "hash-password":
        from .admin.auth import hash_password
        pw = getpass.getpass("New admin password: ")
        if len(pw) < 12:
            print("Use at least 12 characters.", file=sys.stderr); return 1
        if pw != getpass.getpass("Repeat: "):
            print("Passwords differ.", file=sys.stderr); return 1
        print("\nexport WADIYA_ADMIN_PASSWORD_HASH='%s'" % hash_password(pw)); return 0

    settings = Settings.from_env()
    storage, indexer = SQLiteStorage(settings.db_path), FTS5Indexer(settings.index_path)
    storage.init(); indexer.init()

    if args.cmd == "init":
        print("Initialised", settings.db_path, "and", settings.index_path)
    elif args.cmd == "crawl":
        from .crawler.fetcher import Fetcher
        from .crawler.robots import RobotsChecker
        from .crawler.seeds import load_seeds
        from .crawler.lock import CrawlAlreadyRunning

        seeds = load_seeds(args.seeds or settings.seeds_path)
        fetcher = Fetcher(settings)
        robots = RobotsChecker(
            fetcher,
            settings.robots_token,
            settings.robots_cache_ttl,
            settings.max_robots_bytes,
        )

        if args.continuous:
            from .crawler.scheduler import ContinuousCrawler

            scheduler = ContinuousCrawler(
                settings,
                storage,
                None if args.no_index else indexer,
                fetcher,
                robots,
            )

            try:
                for cycle in scheduler.run(
                    seeds,
                    fresh=args.fresh,
                    interval=args.interval,
                ):
                    print(
                        "crawl cycle:",
                        json.dumps({
                            "cycle": cycle.number,
                            "crawl": cycle.stats.as_dict(),
                            "indexed": cycle.indexed,
                        }),
                        flush=True,
                    )
            except CrawlAlreadyRunning as e:
                print(f"error: {e}", file=sys.stderr)
                return 3
        else:
            from .crawler.crawler import Crawler

            try:
                stats = Crawler(
                    settings,
                    storage,
                    fetcher,
                    robots,
                ).run(seeds, fresh=args.fresh)
            except CrawlAlreadyRunning as e:
                print(f"error: {e}", file=sys.stderr)
                return 3

            print("crawl:", json.dumps(stats.as_dict()))
            if not args.no_index:
                print("indexed", index_pending(storage, indexer), "documents")
    elif args.cmd == "images-backfill":
        import time
        from time import sleep

        from .crawler.extractor import extract
        from .crawler.fetcher import Fetcher
        from .crawler.lock import CrawlAlreadyRunning, CrawlLock
        from .crawler.robots import RobotsChecker

        batch = max(1, args.batch)
        delay = max(0.0, args.delay)

        fetcher = Fetcher(settings)
        robots = RobotsChecker(
            fetcher,
            settings.robots_token,
            settings.robots_cache_ttl,
            settings.max_robots_bytes,
        )

        totals = {
            "processed": 0,
            "fetched": 0,
            "images": 0,
            "robots_blocked": 0,
            "failed": 0,
        }

        last_id = 0
        domain_ready_at = {}

        try:
            with CrawlLock(settings.db_path + ".crawl.lock"):
                while True:
                    docs = storage.documents_needing_image_backfill(
                        batch,
                        after_id=last_id,
                    )
                    if not docs:
                        break

                    for doc in docs:
                        if args.max_docs and totals["processed"] >= args.max_docs:
                            break

                        last_id = int(doc["id"])
                        totals["processed"] += 1
                        url = doc["url"]

                        try:
                            reason = robots.block_reason(url)
                            if reason is not None:
                                totals["robots_blocked"] += 1
                                print(
                                    "skip robots:",
                                    url,
                                    f"({reason})",
                                    flush=True,
                                )
                                continue

                            domain = str(doc.get("domain") or "").strip().lower()

                            crawl_delay = settings.default_crawl_delay
                            try:
                                robots_delay = robots.crawl_delay(url)
                                if robots_delay is not None:
                                    crawl_delay = max(
                                        crawl_delay,
                                        float(robots_delay),
                                    )
                            except Exception:
                                pass

                            crawl_delay = min(
                                max(crawl_delay, delay),
                                settings.max_crawl_delay,
                            )

                            if domain:
                                wait = domain_ready_at.get(domain, 0.0) - time.monotonic()
                                if wait > 0:
                                    sleep(wait)

                            res = fetcher.fetch(url)

                            if not res.ok:
                                totals["failed"] += 1
                                print(
                                    "fetch failed:",
                                    url,
                                    f"({res.error or res.status})",
                                    flush=True,
                                )
                                if domain:
                                    domain_ready_at[domain] = (
                                        time.monotonic() + crawl_delay
                                    )
                                continue

                            totals["fetched"] += 1

                            page = extract(
                                res.body,
                                res.final_url or url,
                                res.content_type,
                            )

                            # Backfill only image rows. Existing document
                            # content/title/index/canonical data is untouched.
                            count = storage.replace_document_images(
                                doc["id"],
                                page.images,
                            )
                            totals["images"] += count

                            print(
                                "ok:",
                                url,
                                f"images={count}",
                                flush=True,
                            )

                            if domain:
                                domain_ready_at[domain] = (
                                    time.monotonic() + crawl_delay
                                )

                        except Exception as e:
                            totals["failed"] += 1
                            print(
                                "backfill error:",
                                url,
                                f"{type(e).__name__}: {e}",
                                flush=True,
                            )

                            domain = str(
                                doc.get("domain") or ""
                            ).strip().lower()
                            if domain:
                                domain_ready_at[domain] = (
                                    time.monotonic()
                                    + min(
                                        max(
                                            settings.default_crawl_delay,
                                            delay,
                                        ),
                                        settings.max_crawl_delay,
                                    )
                                )

                    if args.max_docs and totals["processed"] >= args.max_docs:
                        break

        except CrawlAlreadyRunning as e:
            print(f"error: {e}", file=sys.stderr)
            return 3

        print(
            "images-backfill:",
            json.dumps(
                {
                    **totals,
                    "last_id": last_id,
                }
            ),
        )

    elif args.cmd == "index":
        print("indexed", index_pending(storage, indexer), "documents")
    elif args.cmd == "reindex":
        print("rebuilt index with", rebuild_index(storage, indexer), "documents")
    elif args.cmd == "stats":
        from .admin.dashboard import build_stats
        print(json.dumps(build_stats(storage, indexer), indent=2))
    elif args.cmd == "serve":
        import uvicorn
        if not settings.admin_password_hash or len(settings.secret_key) < 32:
            print("note: admin dashboard disabled (set WADIYA_ADMIN_PASSWORD_HASH and WADIYA_SECRET_KEY)", file=sys.stderr)
        uvicorn.run(
            "wadiya.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            access_log=False,
            proxy_headers=True,
            forwarded_allow_ips=args.forwarded_allow_ips,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

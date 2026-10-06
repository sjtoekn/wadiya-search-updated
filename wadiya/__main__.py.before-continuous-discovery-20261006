"""CLI:  python -m wadiya <command>
  init | crawl [--fresh] [--seeds FILE] | index | reindex | stats | serve [--host H --port P] | hash-password"""
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
    sub.add_parser("index"); sub.add_parser("reindex"); sub.add_parser("stats"); sub.add_parser("hash-password")
    s = sub.add_parser("serve"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8000)
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
        from .crawler.crawler import Crawler
        from .crawler.fetcher import Fetcher
        from .crawler.robots import RobotsChecker
        from .crawler.seeds import load_seeds
        seeds = load_seeds(args.seeds or settings.seeds_path)
        fetcher = Fetcher(settings)
        from .crawler.lock import CrawlAlreadyRunning
        try:
            stats = Crawler(settings, storage, fetcher,
                            RobotsChecker(fetcher, settings.robots_token, settings.robots_cache_ttl,
                                          settings.max_robots_bytes)).run(seeds, fresh=args.fresh)
        except CrawlAlreadyRunning as e:
            print(f"error: {e}", file=sys.stderr)
            return 3
        print("crawl:", json.dumps(stats.as_dict()))
        if not args.no_index:
            print("indexed", index_pending(storage, indexer), "documents")
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
        uvicorn.run("wadiya.api.app:create_app", factory=True, host=args.host, port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

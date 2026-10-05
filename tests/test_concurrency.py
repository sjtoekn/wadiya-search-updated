"""Single-machine concurrency: crawler process + server/search process sharing SQLite files (WAL)."""
import os
import sqlite3
import subprocess
import sys
import threading
import time

from tests.helpers import TempDirCase, make_doc
from wadiya.crawler.seeds import Seed
from wadiya.indexer.fts5 import FTS5Indexer
from wadiya.pipeline import sync_index
from wadiya.ranking.bm25 import BM25Ranker
from wadiya.search.service import SearchService

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITER = r'''
import sys
from tests.helpers import make_doc
from wadiya.pipeline import sync_index
from wadiya.storage.sqlite_store import SQLiteStorage
from wadiya.indexer.fts5 import FTS5Indexer
db, idx, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
s, ix = SQLiteStorage(db), FTS5Indexer(idx)
s.init(); ix.init()
for i in range(n):
    s.save_document(make_doc(url=f"https://w.example/{i}", title=f"Doc {i}", content=f"common writer doc number {i} filler", chash=f"w{i}"))
    s.enqueue(f"https://w.example/q{i}", "w.example", 1); s.log_crawl_event(None, f"https://w.example/{i}", "stored", 200, 1.0, None)
    if i % 25 == 24:
        s.deactivate_document([f"https://w.example/{i-1}"], "gone")      # lifecycle removals interleaved with inserts
    if i % 10 == 9:
        sync_index(s, ix)
sync_index(s, ix)
print("DONE", flush=True)
'''


class WalConfigTests(TempDirCase):
    def setUp(self):
        super().setUp()
        self.indexer = FTS5Indexer(self.settings.index_path); self.indexer.init()

    def test_wal_and_busy_timeout_configured(self):
        for name, path in (("storage", self.settings.db_path), ("index", self.settings.index_path)):
            c = sqlite3.connect(path)
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "wal", name)    # persistent, set in init()
            c.close()
        with self.storage._conn() as c:
            self.assertEqual(c.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
        with self.indexer._conn() as c:
            self.assertEqual(c.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
        with self.storage._conn() as c:
            self.assertEqual(c.execute("PRAGMA synchronous").fetchone()[0], 2)               # FULL: durable commits

    def test_readers_are_not_blocked_by_a_writer_and_writers_wait_instead_of_failing(self):
        self.storage.save_document(make_doc(content="common seed"))
        hold = sqlite3.connect(self.settings.db_path, isolation_level=None)
        hold.execute("BEGIN IMMEDIATE")                                                      # someone else owns the write lock
        t0 = time.monotonic()
        self.assertEqual(self.storage.count_documents(), 1)                                  # WAL: reads proceed immediately
        self.assertLess(time.monotonic() - t0, 0.5)
        result = {}

        def writer():
            t = time.monotonic()
            result["outcome"] = self.storage.save_document(make_doc(url="https://e.org/2", content="second", chash="h2")).outcome
            result["waited"] = time.monotonic() - t
        th = threading.Thread(target=writer); th.start()
        time.sleep(1.0)
        hold.execute("COMMIT"); hold.close()
        th.join(timeout=10)
        self.assertEqual(result["outcome"], "inserted")                                      # waited, then succeeded (no "database is locked")
        self.assertGreaterEqual(result["waited"], 0.9)


class CrashConsistencyTests(TempDirCase):
    def setUp(self):
        super().setUp()
        self.indexer = FTS5Indexer(self.settings.index_path); self.indexer.init()

    def test_crash_between_index_and_mark_indexed_is_repaired_without_duplicates(self):
        for i in range(5):
            self.storage.save_document(make_doc(url=f"https://e.org/{i}", content=f"common doc {i}", chash=f"h{i}"))
        real = self.storage.mark_indexed

        def crash(ids): raise RuntimeError("simulated crash after the index write, before the bookkeeping")
        self.storage.mark_indexed = crash
        with self.assertRaises(RuntimeError):
            sync_index(self.storage, self.indexer)
        self.assertEqual(self.indexer.count(), 5)                                            # index ahead of bookkeeping
        self.assertEqual(len(self.storage.documents_needing_index(50)), 5)
        self.storage.mark_indexed = real
        self.assertEqual(sync_index(self.storage, self.indexer), (5, 0))                     # re-sync replaces rows by id
        self.assertEqual(self.indexer.count(), 5)                                            # no duplicates
        self.assertEqual(self.storage.documents_needing_index(50), [])


class CrawlerProcessPlusSearchTests(TempDirCase):
    N = 150

    def test_separate_writer_process_while_searching_never_errors_or_corrupts(self):
        indexer = FTS5Indexer(self.settings.index_path); indexer.init()
        svc = SearchService(self.settings, self.storage, indexer, BM25Ranker())
        env = {**os.environ, "PYTHONPATH": ROOT}
        writer = subprocess.Popen([sys.executable, "-c", WRITER, self.settings.db_path, self.settings.index_path, str(self.N)],
                                  cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        errors, searches, stop = [], [0], threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    r = svc.search("common")                                                 # also logs a query (a write)
                    assert r["result_count"] >= 0 and all(x["url"].startswith("https://") for x in r["results"])
                    self.storage.count_documents(); self.storage.queue_size(); indexer.info()
                    searches[0] += 1
                except Exception as e:                                                       # any exception is a failure
                    errors.append(repr(e))
        threads = [threading.Thread(target=reader) for _ in range(3)]
        [t.start() for t in threads]
        out, err = writer.communicate(timeout=120)
        stop.set(); [t.join(timeout=30) for t in threads]
        self.assertIn("DONE", out, err)
        self.assertEqual(errors, [])                                                          # no "database is locked", no corrupt reads
        self.assertGreater(searches[0], 10)

        # final consistency: both databases are intact and the index mirrors the active documents exactly
        sync_index(self.storage, indexer)
        for path in (self.settings.db_path, self.settings.index_path):
            c = sqlite3.connect(path)
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok", path)
            c.close()
        c = sqlite3.connect(self.settings.index_path)
        c.execute("INSERT INTO docs_fts(docs_fts) VALUES('integrity-check')")                # FTS5's own structural check
        index_ids = {r[0] for r in c.execute("SELECT rowid FROM docs_fts")}
        c.close()
        d = sqlite3.connect(self.settings.db_path)
        active_ids = {r[0] for r in d.execute("SELECT id FROM documents WHERE status='ok'")}
        inactive = d.execute("SELECT count(*) FROM documents WHERE status<>'ok'").fetchone()[0]
        d.close()
        self.assertEqual(index_ids, active_ids)
        self.assertEqual(len(active_ids) + inactive, self.N)
        self.assertEqual(inactive, self.N // 25)                                              # the interleaved removals all landed
        print(f"\n   [{searches[0]} concurrent searches, 0 errors, {len(active_ids)} active / {inactive} removed, index == active set]")


class CrawlerWorkerConcurrencyTests(TempDirCase):
    """M1: verify crawler worker scheduling and failure isolation."""

    def _crawler(self, max_workers=2, max_total_pages=10):
        from tests.crawler_fixtures import Env

        class Site:
            base = "https://example.invalid"

        env = Env(
            self.settings,
            Site(),
            max_workers=max_workers,
            max_total_pages=max_total_pages,
        )
        return env

    def test_different_domains_run_in_parallel(self):
        env = self._crawler(max_workers=2, max_total_pages=2)
        crawler = env.crawler(self.storage)

        active = 0
        peak = 0
        lock = threading.Lock()
        barrier = threading.Barrier(2)

        def process(item, scope, stats, run_id):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(timeout=5)
            time.sleep(0.05)
            with lock:
                active -= 1

        crawler._process = process

        seeds = [
            Seed("https://a.example/"),
            Seed("https://b.example/"),
        ]

        crawler.run(seeds, fresh=False)

        self.assertEqual(peak, 2)

    def test_same_domain_never_runs_concurrently(self):
        env = self._crawler(max_workers=2, max_total_pages=2)
        crawler = env.crawler(self.storage)

        active = 0
        peak = 0
        lock = threading.Lock()

        def process(item, scope, stats, run_id):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1

        crawler._process = process

        seeds = [
            Seed("https://same.example/a"),
            Seed("https://same.example/b"),
        ]

        crawler.run(seeds, fresh=False)

        self.assertEqual(peak, 1)

    def test_max_total_pages_is_exact_under_concurrency(self):
        env = self._crawler(max_workers=4, max_total_pages=5)
        crawler = env.crawler(self.storage)

        calls = []
        lock = threading.Lock()

        def process(item, scope, stats, run_id):
            with lock:
                calls.append(item.url)
            time.sleep(0.02)

        crawler._process = process

        seeds = [
            Seed(f"https://domain{i}.example/")
            for i in range(10)
        ]

        crawler.run(seeds, fresh=False)

        self.assertEqual(len(calls), 5)

    def test_worker_failure_does_not_stop_other_workers(self):
        env = self._crawler(max_workers=2, max_total_pages=3)
        crawler = env.crawler(self.storage)

        calls = []
        lock = threading.Lock()

        def process(item, scope, stats, run_id):
            with lock:
                calls.append(item.url)

            if item.url.endswith("/fail"):
                raise RuntimeError("intentional worker failure")

            time.sleep(0.02)

        crawler._process = process

        seeds = [
            Seed("https://a.example/fail"),
            Seed("https://b.example/ok"),
            Seed("https://c.example/ok"),
        ]

        stats = crawler.run(seeds, fresh=False)

        self.assertEqual(len(calls), 3)
        self.assertIn("https://a.example/fail", calls)
        self.assertIn("https://b.example/ok", calls)
        self.assertIn("https://c.example/ok", calls)
        self.assertEqual(stats.failed, 1)

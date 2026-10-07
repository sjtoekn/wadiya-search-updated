import sqlite3
from pathlib import Path

from tests.helpers import TempDirCase, make_doc
from wadiya.storage.base import Document
from wadiya.storage.sqlite_store import SCHEMA_VERSION, SQLiteStorage



class MigrationTests(TempDirCase):
    def test_v0_database_migrates_to_latest(self):
        db = Path(self.tmp) / "legacy.sqlite"

        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE documents (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              url TEXT NOT NULL UNIQUE,
              canonical_url TEXT,
              domain TEXT NOT NULL,
              title TEXT,
              description TEXT,
              headings TEXT,
              body TEXT,
              content_hash TEXT,
              fetched_at TEXT,
              status TEXT,
              active INTEGER NOT NULL DEFAULT 1
            );
            PRAGMA user_version = 0;
        """)
        conn.commit()
        conn.close()

        storage = SQLiteStorage(str(db))
        storage.init()

        with sqlite3.connect(db) as check:
            version = check.execute("PRAGMA user_version").fetchone()[0]
            doc_cols = {
                row[1] for row in check.execute("PRAGMA table_info(documents)")
            }
            discovered_cols = {
                row[1]
                for row in check.execute(
                    "PRAGMA table_info(discovered_sites)"
                )
            }

        self.assertEqual(version, SCHEMA_VERSION)
        self.assertIn("next_attempt_at", discovered_cols)
        self.assertIn("fail_count", doc_cols)
        self.assertIn("nosnippet", doc_cols)
        self.assertIn("url", discovered_cols)
        self.assertIn("status", discovered_cols)

        with sqlite3.connect(db) as check:
            domain_cols = {
                row[1]
                for row in check.execute(
                    "PRAGMA table_info(domain_freshness)"
                )
            }
        self.assertIn("domain", domain_cols)
        self.assertIn("interval_seconds", domain_cols)
        self.assertIn("updated_at", domain_cols)


class V1MigrationTests(TempDirCase):
    def test_v1_database_migrates_to_latest(self):
        db = Path(self.tmp) / "v1.sqlite"

        # Build a valid current schema, then reduce it to the v1 state:
        # fail_count exists, but the v2 discovery registry does not.
        storage = SQLiteStorage(str(db))
        storage.init()

        with sqlite3.connect(db) as conn:
            conn.execute("DROP INDEX IF EXISTS idx_discovered_sites_domain")
            conn.execute("DROP INDEX IF EXISTS idx_discovered_sites_status")
            conn.execute("DROP INDEX IF EXISTS idx_discovered_sites_source")
            conn.execute("DROP TABLE discovered_sites")
            conn.execute("PRAGMA user_version = 1")

        migrated = SQLiteStorage(str(db))
        migrated.init()

        with sqlite3.connect(db) as check:
            version = check.execute("PRAGMA user_version").fetchone()[0]
            doc_cols = {
                row[1] for row in check.execute("PRAGMA table_info(documents)")
            }
            discovered_cols = {
                row[1]
                for row in check.execute(
                    "PRAGMA table_info(discovered_sites)"
                )
            }

        self.assertEqual(version, SCHEMA_VERSION)
        self.assertIn("next_attempt_at", discovered_cols)
        self.assertIn("fail_count", doc_cols)
        self.assertIn("nosnippet", doc_cols)
        self.assertIn("url", discovered_cols)
        self.assertIn("status", discovered_cols)


class DiscoveryAdminStorageTests(TempDirCase):
    def _seed_discovery(self):
        s = self.storage

        s.register_discovered_site(
            "https://alpha.example/",
            "alpha.example",
            source="link",
        )
        s.register_discovered_site(
            "https://beta.example/",
            "beta.example",
            source="sitemap",
        )
        s.register_discovered_site(
            "https://alpha.example/about",
            "alpha.example",
            source="link",
        )

        s.mark_discovered_site_crawled(
            "https://alpha.example/",
            success=True,
        )
        s.mark_discovered_site_crawled(
            "https://beta.example/",
            success=False,
            error="connection failed",
        )

    def test_discovery_registry_stats(self):
        self._seed_discovery()

        stats = self.storage.discovery_registry_stats()

        self.assertEqual(stats["total"], 3)
        self.assertEqual(
            stats["by_source"],
            {"link": 2, "sitemap": 1},
        )
        self.assertEqual(
            stats["by_status"],
            {"active": 1, "failed": 1, "pending": 1},
        )

    def test_list_discovered_sites_admin_filters(self):
        self._seed_discovery()

        rows = self.storage.list_discovered_sites_admin(limit=100)
        self.assertEqual(len(rows), 3)

        failed = self.storage.list_discovered_sites_admin(
            status="failed",
            limit=100,
        )
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["domain"], "beta.example")
        self.assertEqual(failed[0]["last_error"], "connection failed")

        sitemap = self.storage.list_discovered_sites_admin(
            source="sitemap",
            limit=100,
        )
        self.assertEqual(len(sitemap), 1)
        self.assertEqual(sitemap[0]["url"], "https://beta.example/")

        about = self.storage.list_discovered_sites_admin(
            query="about",
            limit=100,
        )
        self.assertEqual(len(about), 1)
        self.assertEqual(about[0]["url"], "https://alpha.example/about")

    def test_list_discovered_sites_admin_limit(self):
        self._seed_discovery()

        rows = self.storage.list_discovered_sites_admin(limit=2)

        self.assertEqual(len(rows), 2)

        rows = self.storage.list_discovered_sites_admin(
            limit=1,
            offset=1,
        )
        self.assertEqual(len(rows), 1)

        total = self.storage.count_discovered_sites_admin()
        self.assertEqual(total, 3)

        total = self.storage.count_discovered_sites_admin(
            source="sitemap",
        )
        self.assertEqual(total, 1)


class StorageTests(TempDirCase):
    def test_domain_freshness_override(self):
        self.assertIsNone(
            self.storage.get_domain_freshness("example.org")
        )

        self.storage.set_domain_freshness("example.org", 21600)
        self.assertEqual(
            self.storage.get_domain_freshness("example.org"),
            21600.0,
        )

        self.storage.set_domain_freshness("example.org", 259200)
        self.assertEqual(
            self.storage.get_domain_freshness("example.org"),
            259200.0,
        )

    def test_insert_and_get(self):
        r = self.storage.save_document(make_doc())
        self.assertEqual(r.outcome, "inserted")
        d = self.storage.get_documents([r.doc_id])[r.doc_id]
        self.assertEqual(d.title, "T")
        self.assertEqual(self.storage.count_documents(), 1)
        self.assertEqual(self.storage.count_domains(), 1)

    def test_get_document_by_url(self):
        r = self.storage.save_document(make_doc(url="https://example.org/page"))
        d = self.storage.get_document_by_url("https://example.org/page")
        self.assertIsNotNone(d)
        self.assertEqual(d.id, r.doc_id)
        self.assertEqual(d.url, "https://example.org/page")

    def test_unchanged_and_updated(self):
        r1 = self.storage.save_document(make_doc())
        self.assertEqual(self.storage.save_document(make_doc()).outcome, "unchanged")
        r3 = self.storage.save_document(make_doc(content="new content"))
        self.assertEqual((r3.outcome, r3.doc_id), ("updated", r1.doc_id))
        self.assertEqual(len(self.storage.documents_needing_index(10)), 1)

    def test_duplicate_by_content_hash(self):
        self.storage.save_document(make_doc(url="https://example.org/a", content="same body"))
        r = self.storage.save_document(make_doc(url="https://example.org/b", content="same body"))
        self.assertEqual(r.outcome, "duplicate")
        self.assertEqual(self.storage.count_documents(), 1)

    def test_duplicate_by_canonical(self):
        self.storage.save_document(make_doc(url="https://example.org/a", canonical="https://example.org/a", content="x1"))
        r = self.storage.save_document(make_doc(url="https://example.org/a?x=1", canonical="https://example.org/a", content="x2"))
        self.assertEqual(r.outcome, "duplicate")

    def test_canonical_url_wins_over_earlier_variant(self):
        self.storage.save_document(make_doc(url="https://example.org/v?x=1", canonical="https://example.org/v", content="c1"))
        r = self.storage.save_document(make_doc(url="https://example.org/v", canonical="https://example.org/v", content="c1b"))
        self.assertEqual(r.outcome, "updated")
        self.assertEqual(self.storage.count_documents(), 1)

    def test_index_tracking(self):
        r = self.storage.save_document(make_doc())
        self.assertEqual(len(self.storage.documents_needing_index(10)), 1)
        self.storage.mark_indexed([r.doc_id])
        self.assertEqual(self.storage.documents_needing_index(10), [])
        self.storage.reset_indexed()
        self.assertEqual(len(self.storage.documents_needing_index(10)), 1)

    def test_queue_lifecycle(self):
        s = self.storage
        self.assertTrue(s.enqueue("https://a.org/", "a.org", 0))
        self.assertFalse(s.enqueue("https://a.org/", "a.org", 1))   # dedupe
        s.enqueue("https://b.org/", "b.org", 0)
        self.assertEqual(s.queue_size(), 2)
        item = s.claim_next(exclude_domains=["a.org"])
        self.assertEqual(item.domain, "b.org")
        self.assertEqual(s.queue_size(), 1)
        s.mark_url(item.url, "done", 200)
        self.assertEqual(s.domain_crawled_count("b.org"), 1)
        self.assertIsNone(s.claim_next(exclude_domains=["a.org"]))
        self.assertEqual(s.requeue_stale(), 0)
        self.assertTrue(s.enqueue("https://b.org/", "b.org", 0, force=True))  # re-crawl
        self.assertEqual(s.queue_size(), 2)

    def test_queue_claim_order_is_depth_then_id(self):
        s = self.storage
        s.enqueue("https://example.org/deep", "example.org", 2)
        s.enqueue("https://example.org/shallow", "example.org", 0)
        s.enqueue("https://example.org/mid", "example.org", 1)

        first = s.claim_next()
        self.assertEqual(first.url, "https://example.org/shallow")

        s.mark_url(first.url, "done", 200)

        second = s.claim_next()
        self.assertEqual(second.url, "https://example.org/mid")

    def test_queue_skips_not_due_freshness_items(self):
        s = self.storage
        s.enqueue("https://example.org/future", "example.org", 0)

        s.mark_url(
            "https://example.org/future",
            "done",
            200,
            next_crawl_at="2099-01-01T00:00:00+00:00",
        )

        self.assertIsNone(s.claim_next())

    def test_queue_claims_due_freshness_items(self):
        s = self.storage
        s.enqueue("https://example.org/due", "example.org", 0)

        s.mark_url(
            "https://example.org/due",
            "pending",
            200,
            next_crawl_at="2000-01-01T00:00:00+00:00",
        )

        item = s.claim_next()
        self.assertIsNotNone(item)
        self.assertEqual(item.url, "https://example.org/due")

    def test_force_enqueue_preserves_shallower_depth(self):
        s = self.storage
        s.enqueue("https://example.org/page", "example.org", 1)

        self.assertTrue(
            s.enqueue("https://example.org/page", "example.org", 3, force=True)
        )

        item = s.claim_next()
        self.assertEqual(item.depth, 1)

    def test_requeue_stale_recovers_in_progress_items(self):
        s = self.storage
        self.assertTrue(
            s.enqueue("https://example.org/stale", "example.org", 0)
        )

        item = s.claim_next()
        self.assertIsNotNone(item)
        self.assertEqual(s.queue_size(), 0)

        self.assertEqual(s.requeue_stale(), 1)
        self.assertEqual(s.queue_size(), 1)

        recovered = s.claim_next()
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.url, "https://example.org/stale")

    def test_run_and_query_metrics(self):
        s = self.storage
        rid = s.start_run()
        s.finish_run(rid, {"attempted": 3, "fetched": 2, "failed": 1}, "finished")
        self.assertEqual(s.last_run()["attempted"], 3)
        s.log_crawl_event(rid, "https://x/", "failed", 500, 12.0, "boom")
        self.assertEqual(s.recent_crawl_errors()[0]["error"], "boom")
        s.log_query("hello", 3, 10.0); s.log_query("world", 0, 20.0)
        st = s.search_stats()
        self.assertEqual((st["search_count"], st["avg_latency_ms"]), (2, 15.0))
        import hashlib
        expected_hash = hashlib.sha256(
            "world".casefold().encode("utf-8")
        ).hexdigest()
        self.assertEqual(s.recent_queries()[0]["query"], expected_hash)

    def test_search_images_uses_word_boundary_matching(self):
        s = self.storage

        luma = make_doc(
            url="https://luma.com/",
            title="Luma",
            description="Discover and host memorable events",
            domain="luma.com",
        )
        luma.images = [
            {
                "image_url": "https://images.lumacdn.com/luma.png",
                "source_page_url": "https://luma.com/",
                "source_domain": "luma.com",
                "alt_text": "",
                "title": "Luma",
            }
        ]

        nalumango = make_doc(
            url="https://tum.wikipedia.org/wiki/Jani_likulu",
            title="Wikipedia",
            domain="tum.wikipedia.org",
        )
        nalumango.images = [
            {
                "image_url": "https://example.org/nalumango.jpg",
                "source_page_url": "https://tum.wikipedia.org/wiki/Jani_likulu",
                "source_domain": "tum.wikipedia.org",
                "alt_text": "Mutale Nalumango",
                "title": "Wikipedia",
            }
        ]

        s.save_document(luma)
        s.save_document(nalumango)

        rows = s.search_images("luma", limit=50)

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["image_url"],
            "https://images.lumacdn.com/luma.png",
        )
        self.assertEqual(
            rows[0]["source_page_url"],
            "https://luma.com/",
        )


class DiscoveryRegistryTests(TempDirCase):
    def test_register_discovered_site_deduplicates(self):
        s = self.storage

        self.assertTrue(
            s.register_discovered_site(
                "https://example.org/",
                "example.org",
                "link",
            )
        )

        self.assertFalse(
            s.register_discovered_site(
                "https://example.org/",
                "example.org",
                "sitemap",
            )
        )

        row = s.get_discovered_site("https://example.org/")
        self.assertIsNotNone(row)
        self.assertEqual(row["domain"], "example.org")
        self.assertEqual(row["source"], "link")
        self.assertEqual(row["status"], "pending")

    def test_discovered_site_retry_schedule_is_persisted(self):
        s = self.storage

        s.register_discovered_site(
            "https://retry.example/",
            "retry.example",
            "link",
        )

        s.mark_discovered_site_crawled(
            "https://retry.example/",
            success=False,
            error="temporary failure",
            next_attempt_at="2099-01-01T00:00:00+00:00",
        )

        row = s.get_discovered_site("https://retry.example/")

        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["crawl_count"], 1)
        self.assertEqual(row["failure_count"], 1)
        self.assertEqual(row["last_error"], "temporary failure")
        self.assertEqual(
            row["next_attempt_at"],
            "2099-01-01T00:00:00+00:00",
        )

        ready = s.list_discovered_sites(
            limit=100,
            eligible_only=True,
        )

        self.assertEqual(ready, [])

        s.mark_discovered_site_crawled(
            "https://retry.example/",
            success=True,
        )

        row = s.get_discovered_site("https://retry.example/")

        self.assertEqual(row["status"], "active")
        self.assertEqual(row["failure_count"], 0)
        self.assertIsNone(row["next_attempt_at"])


    def test_discovered_site_crawl_lifecycle(self):
        s = self.storage

        s.register_discovered_site(
            "https://example.org/",
            "example.org",
            "link",
        )

        s.mark_discovered_site_crawled(
            "https://example.org/",
            success=True,
        )

        row = s.get_discovered_site("https://example.org/")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["crawl_count"], 1)
        self.assertEqual(row["failure_count"], 0)

        s.mark_discovered_site_crawled(
            "https://example.org/",
            success=False,
            error="connection failed",
        )

        row = s.get_discovered_site("https://example.org/")
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["crawl_count"], 2)
        self.assertEqual(row["failure_count"], 1)
        self.assertEqual(row["last_error"], "connection failed")

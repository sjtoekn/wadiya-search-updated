from tests.helpers import TempDirCase, make_doc


class StorageTests(TempDirCase):
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
        self.assertEqual(s.recent_queries()[0]["query"], "world")

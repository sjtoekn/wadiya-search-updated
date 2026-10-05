"""Document lifecycle: a page the crawler has definitively determined should not be searchable must leave
search; a merely *temporary* failure must not delete a good document."""
from tests.crawler_fixtures import Env, page
from tests.helpers import TempDirCase
from tests.mock_site import MockSite
from wadiya.crawler.fetcher import FetchResult
from wadiya.crawler.seeds import Seed
from wadiya.indexer.fts5 import FTS5Indexer
from wadiya.pipeline import rebuild_index, sync_index
from wadiya.ranking.bm25 import BM25Ranker
from wadiya.search.service import SearchService

P_BODY = "alphaunique page body with enough words to be a realistic document for the lifecycle tests."
Q_BODY = "betaunique page body with enough words to be a realistic document for the lifecycle tests."


def routes():
    return {"/robots.txt": (404, "text/plain", "", {}),
            "/p": (200, *page("Page P", P_BODY)),
            "/q": (200, *page("Page Q", Q_BODY))}


class LifecycleCase(TempDirCase):
    def setUp(self):
        super().setUp()
        self.indexer = FTS5Indexer(self.settings.index_path); self.indexer.init()
        self.service = SearchService(self.settings, self.storage, self.indexer, BM25Ranker())

    def crawl(self, site, sync=True, flaky=None, **env_kw):
        env = Env(self.settings, site, **env_kw)
        if flaky:                                    # simulate transport-level failure for matching URLs
            real = env.fetcher.fetch
            env.fetcher.fetch = lambda url, **kw: (FetchResult(url, url, None, None, b"", error=flaky(url)) if url.endswith("/p") and flaky(url) else real(url, **kw))
        stats = env.crawler(self.storage).run([Seed(site.base + "/p", max_depth=0), Seed(site.base + "/q", max_depth=0)], fresh=True)
        if sync:
            sync_index(self.storage, self.indexer)
        return stats

    def urls_for(self, query):
        return sorted(r["url"].rsplit("/", 1)[1] for r in self.service.search(query)["results"])

    def doc(self, path):
        with self.storage._conn() as c:
            r = c.execute("SELECT * FROM documents WHERE url LIKE ?", ("%" + path,)).fetchone()
            return dict(r) if r else None


class LifecycleTests(LifecycleCase):
    def test_1_indexed_page_is_searchable(self):
        with MockSite(routes()) as site:
            stats = self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), ["p"])
            self.assertEqual((self.storage.count_documents(), self.indexer.count(), stats.deactivated), (2, 2, 0))

    def test_2_page_becomes_noindex_meta(self):
        R = routes()
        with MockSite(R) as site:
            self.crawl(site)
            R["/p"] = (200, *page("Page P", P_BODY, '<meta name="robots" content="noindex">'))
            stats = self.crawl(site, sync=False)
            self.assertEqual(stats.deactivated, 1)
            # defence in depth: even BEFORE the index is synced, search must not return it
            self.assertEqual(self.indexer.count(), 2)
            self.assertEqual(self.urls_for("alphaunique"), [])
            sync_index(self.storage, self.indexer)
            self.assertEqual(self.indexer.count(), 1)                                   # physically gone from the index
            d = self.doc("/p")
            self.assertEqual((d["status"], d["content"]), ("noindex", ""))               # text cleared, row kept
            self.assertEqual(self.urls_for("betaunique"), ["q"])                         # neighbour unaffected
            self.assertEqual(self.storage.count_documents(), 1)

    def test_3_page_returns_404_or_410(self):
        for status, label in ((404, "gone"), (410, "gone")):
            with self.subTest(status=status):
                R = routes()
                with MockSite(R) as site:
                    self.crawl(site)
                    R["/p"] = (status, "text/html", "nope", {})
                    self.crawl(site)
                    self.assertEqual(self.urls_for("alphaunique"), [])
                    self.assertEqual(self.doc("/p")["status"], label)
                    self.assertEqual(self.indexer.count(), 1)

    def test_4_temporary_failures_do_not_delete_a_good_document(self):
        R = routes()
        with MockSite(R) as site:
            self.crawl(site)
            R["/p"] = (503, "text/html", "down", {})
            self.crawl(site); self.crawl(site)                                           # 2 failures < threshold (3)
            self.assertEqual(self.urls_for("alphaunique"), ["p"])
            self.assertEqual(self.doc("/p")["fail_count"], 2)
            R["/p"] = (200, *page("Page P", P_BODY))
            self.crawl(site)                                                             # recovery resets the counter
            self.assertEqual(self.doc("/p")["fail_count"], 0)
            R["/p"] = (503, "text/html", "down", {})
            self.crawl(site); self.crawl(site)                                           # 2 more: NOT 3 in a row
            self.assertEqual(self.urls_for("alphaunique"), ["p"])
            stats = self.crawl(site)                                                     # 3rd consecutive failure
            self.assertEqual((self.urls_for("alphaunique"), self.doc("/p")["status"], stats.deactivated), ([], "unreachable", 1))

    def test_4b_network_timeouts_behave_like_other_temporary_failures(self):
        with MockSite(routes()) as site:
            self.crawl(site)
            for _ in range(2):
                self.crawl(site, flaky=lambda u: "timeout")
            self.assertEqual(self.urls_for("alphaunique"), ["p"])
            self.crawl(site, flaky=lambda u: "connection_error")
            self.assertEqual(self.urls_for("alphaunique"), [])

    def test_5_page_returns_later(self):
        R = routes()
        with MockSite(R) as site:
            self.crawl(site)
            first_id = self.doc("/p")["id"]
            R["/p"] = (404, "text/html", "gone", {})
            self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), [])
            R["/p"] = (200, *page("Page P", P_BODY))                                     # identical content comes back
            stats = self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), ["p"])
            d = self.doc("/p")
            self.assertEqual((d["status"], d["id"], stats.stored), ("ok", first_id, 1))   # same row reactivated
            R["/p"] = (404, "text/html", "gone", {}); self.crawl(site)
            R["/p"] = (200, *page("Page P v2", "gammaunique entirely new text for the returning page, long enough to be real."))
            self.crawl(site)
            self.assertEqual((self.urls_for("gammaunique"), self.urls_for("alphaunique")), (["p"], []))

    def test_6_reindexing_never_resurrects_removed_documents(self):
        R = routes()
        with MockSite(R) as site:
            self.crawl(site)
            R["/p"] = (404, "text/html", "gone", {}); self.crawl(site)
            self.assertEqual(rebuild_index(self.storage, self.indexer), 1)               # only the active doc is re-indexed
            self.assertEqual((self.indexer.count(), self.urls_for("alphaunique")), (1, []))
            self.assertEqual(sync_index(self.storage, self.indexer), (0, 0))             # idempotent
            self.indexer.index([])                                                        # stale rows can also be stripped by a rebuild after a crash:
            self.storage.reset_indexed()
            self.assertEqual(sync_index(self.storage, self.indexer), (1, 1))

    def test_robots_rule_removes_but_unreachable_robots_does_not(self):
        R = routes()
        with MockSite(R) as site:
            self.crawl(site)
            R["/robots.txt"] = (503, "text/plain", "down", {})                           # robots.txt temporarily broken
            self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), ["p"])                        # NOT removed
            R["/robots.txt"] = (200, "text/plain", "User-agent: *\nDisallow: /p\n", {})  # now affirmatively disallowed
            stats = self.crawl(site)
            self.assertEqual((self.urls_for("alphaunique"), self.doc("/p")["status"], stats.deactivated), ([], "robots", 1))
            self.assertEqual(self.urls_for("betaunique"), ["q"])
            R["/robots.txt"] = (404, "text/plain", "", {})                               # rule removed -> page returns
            self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), ["p"])

    def test_page_that_moved_leaves_old_url_behind(self):
        R = routes(); R["/p2"] = (200, *page("Page P", P_BODY))
        with MockSite(R) as site:
            self.crawl(site)
            R["/p"] = (301, None, "", {"Location": "/p2"})
            self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), ["p2"])                        # exactly one live copy, at the new URL
            self.assertEqual(self.doc("/p")["status"], "moved")

    def test_empty_content_removes_document(self):
        R = routes()
        with MockSite(R) as site:
            self.crawl(site)
            R["/p"] = (200, "text/html", "<html><head><title></title></head><body></body></html>", {})
            self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), [])

    def test_inactive_docs_do_not_count_or_block_duplicates(self):
        R = routes()
        with MockSite(R) as site:
            self.crawl(site)
            R["/p"] = (404, "text/html", "gone", {}); self.crawl(site)
            R["/q"] = (200, *page("Page Q", Q_BODY))                                      # unchanged
            self.assertEqual(self.storage.count_documents(), 1)
            R["/r"] = (200, *page("Page P", P_BODY))                                      # same text as the dead /p, new URL
            env = Env(self.settings, site)
            env.crawler(self.storage).run([Seed(site.base + "/r", max_depth=0)])
            sync_index(self.storage, self.indexer)
            self.assertEqual(self.urls_for("alphaunique"), ["r"])                         # not treated as duplicate of a dead doc


class XRobotsTagTests(LifecycleCase):
    def test_header_noindex_prevents_storage(self):
        R = routes(); R["/p"] = (200, *page("Page P", P_BODY)[:2], {"X-Robots-Tag": "noindex"})
        with MockSite(R) as site:
            stats = self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), [])
            self.assertIsNone(self.doc("/p"))
            self.assertEqual(self.urls_for("betaunique"), ["q"])
            self.assertEqual(stats.stored, 1)

    def test_header_noindex_removes_previously_indexed_page(self):
        R = routes()
        with MockSite(R) as site:
            self.crawl(site)
            self.assertEqual(self.urls_for("alphaunique"), ["p"])
            R["/p"] = (200, *page("Page P", P_BODY)[:2], {"X-Robots-Tag": "NoIndex, NoSnippet"})
            stats = self.crawl(site)
            self.assertEqual((self.urls_for("alphaunique"), self.doc("/p")["status"], stats.deactivated), ([], "noindex", 1))
            self.assertEqual(self.indexer.count(), 1)

    def test_header_variants(self):
        for value, indexed in (("none", False), ("wadiyabot: noindex", False), ("WadiyaBot: none", False),
                               ("otherbot: noindex", True), ("noarchive", True), ("all", True),
                               ("unavailable_after: 25 Jun 2030 15:00:00 PST", True), ("", True)):
            with self.subTest(header=value):
                self.setUp()                                                             # fresh storage per variant
                R = routes(); R["/p"] = (200, *page("Page P", P_BODY)[:2], {"X-Robots-Tag": value} if value else {})
                with MockSite(R) as site:
                    self.crawl(site)
                    self.assertEqual(self.urls_for("alphaunique") == ["p"], indexed)

    def test_header_nofollow_blocks_link_discovery(self):
        R = routes()
        R["/p"] = (200, *page("Page P", P_BODY, links=["/q", "/never"])[:2], {"X-Robots-Tag": "nofollow"})
        R["/never"] = (200, *page("Never", "neverunique should not be discovered through a nofollow page."))
        with MockSite(R) as site:
            env = Env(self.settings, site, max_depth=2)
            env.crawler(self.storage).run([Seed(site.base + "/p")], fresh=True)
            self.assertNotIn("/never", site.hits)
            self.assertNotIn("/q", site.hits)
            self.assertIsNotNone(self.doc("/p"))                                         # nofollow still indexes the page itself

    def test_fetcher_exposes_every_header_instance(self):
        R = routes()
        with MockSite(R) as site:
            R["/p"] = (200, "text/html", "<html><body>x</body></html>", {"X-Robots-Tag": "noindex"})
            r = Env(self.settings, site).fetcher.fetch(site.base + "/p")
            self.assertEqual(r.x_robots_tag, ("noindex",))
            R["/q"] = (200, "text/html", "<html><body>x</body></html>", {})
            self.assertEqual(Env(self.settings, site).fetcher.fetch(site.base + "/q").x_robots_tag, ())

"""Phase 0 end-to-end: seed -> crawl -> extract -> store -> index -> search -> rank -> API -> UI."""
import unittest

from tests.crawler_fixtures import Env, site_routes
from tests.helpers import TempDirCase
from tests.mock_site import MockSite
from wadiya.admin.dashboard import build_stats
from wadiya.api import handlers
from wadiya.crawler.seeds import Seed
from wadiya.indexer.fts5 import FTS5Indexer
from wadiya.pipeline import index_pending
from wadiya.ranking.bm25 import BM25Ranker
from wadiya.search.service import SearchService

try:
    import fastapi, httpx  # noqa
    HAVE_HTTP = True
except ImportError:
    HAVE_HTTP = False


class EndToEnd(TempDirCase):
    def build_world(self, site):
        env = Env(self.settings, site)
        stats = env.crawler(self.storage).run([Seed(site.base + "/")])
        self.indexer = FTS5Indexer(self.settings.index_path); self.indexer.init()
        indexed = index_pending(self.storage, self.indexer)
        self.service = SearchService(self.settings, self.storage, self.indexer, BM25Ranker())
        return stats, indexed

    def test_full_pipeline_through_api_handlers(self):
        with MockSite(site_routes()) as site:
            stats, indexed = self.build_world(site)
            self.assertEqual((stats.stored, indexed), (4, 4))
            status, body = handlers.handle_search(self.service, "wadi riverbed", "1")
            self.assertEqual(status, 200)
            self.assertEqual(body["result_count"], 1)                      # AND: only /a has both words (/dup was deduped)
            top = body["results"][0]
            self.assertEqual(top["url"], site.base + "/a")                 # best match ranks first
            self.assertEqual(top["title"], "Wadi guide")
            self.assertEqual(top["domain"], "127.0.0.1")
            self.assertIn("dry riverbed", top["snippet"])
            wide = handlers.handle_search(self.service, "wadi", "1")[1]
            self.assertEqual([r["title"] for r in wide["results"]], ["Wadi guide", "Deep page"])   # title match outranks body-only mention
            # content that robots.txt / noindex excluded can never be found
            for q in ("SECRETCONTENT", "NOINDEXCONTENT"):
                self.assertEqual(handlers.handle_search(self.service, q, "1")[1]["result_count"], 0)
            # an unrelated page is reachable by its own terms
            self.assertEqual(handlers.handle_search(self.service, "oasis", "1")[1]["results"][0]["title"], "Oasis facts")
            # metrics visible on the dashboard
            st = build_stats(self.storage, self.indexer)
            self.assertEqual((st["documents"], st["crawler"]["last_crawl"]["stored"], st["crawler"]["last_crawl"]["robots_blocked"]), (4, 4, 1))
            self.assertGreaterEqual(st["search"]["search_count"], 4)

    @unittest.skipUnless(HAVE_HTTP, "fastapi/httpx not installed in this environment")
    def test_full_pipeline_through_http_and_ui(self):
        from fastapi.testclient import TestClient
        from wadiya.api.app import create_app
        from dataclasses import replace
        with MockSite(site_routes()) as site:
            self.build_world(site)
            app = create_app(replace(self.settings, cookie_secure=False), self.storage, self.indexer)
            c = TestClient(app)
            r = c.get("/api/search", params={"q": "wadi", "page": 1})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["results"][0]["title"], "Wadi guide")
            home = c.get("/")                                              # the Wadiya UI shell that calls the API
            self.assertEqual(home.status_code, 200)
            self.assertIn("wadiya", home.text.lower())
            self.assertIn('id="searchForm"', home.text)
            js = c.get("/static/app.js")
            self.assertIn("/api/search", js.text)


if __name__ == "__main__":
    unittest.main()

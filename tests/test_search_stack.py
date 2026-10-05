import math

from tests.helpers import TempDirCase, make_doc
from wadiya.indexer.fts5 import FTS5Indexer
from wadiya.pipeline import index_pending, rebuild_index
from wadiya.query.parser import parse_query
from wadiya.ranking.bm25 import BM25Ranker
from wadiya.search.service import InvalidSearchRequest, SearchService


class SearchStackCase(TempDirCase):
    def setUp(self):
        super().setUp()
        self.indexer = FTS5Indexer(self.settings.index_path)
        self.indexer.init()
        self.ranker = BM25Ranker()
        self.svc = SearchService(self.settings, self.storage, self.indexer, self.ranker)

    def add(self, **kw):
        r = self.storage.save_document(make_doc(**kw)); return r.doc_id

    def build(self):
        index_pending(self.storage, self.indexer)


class IndexerTests(SearchStackCase):
    def test_index_and_search(self):
        a = self.add(url="https://e.org/1", title="Wadi guide", content="A wadi is a dry riverbed.")
        self.add(url="https://e.org/2", title="Cooking", content="Pasta and sauce recipes.")
        self.build()
        self.assertEqual(self.indexer.count(), 2)
        res = self.indexer.search(parse_query("wadi"), 10)
        self.assertEqual([h.doc_id for h in res.hits], [a])
        self.assertEqual(res.total, 1)
        self.assertEqual(self.storage.documents_needing_index(10), [])

    def test_stemming_phrase_and_and_or(self):
        self.add(url="https://e.org/1", content="rivers run through the dry riverbed slowly")
        self.add(url="https://e.org/2", content="a dry spell and a riverbed fish")
        self.build()
        s = lambda q, all_=True: {h.url for h in self.indexer.search(parse_query(q), 10, match_all=all_).hits}
        self.assertEqual(s("river"), {"https://e.org/1"})                       # porter stemming
        self.assertEqual(s('"dry riverbed"'), {"https://e.org/1"})              # phrase
        self.assertEqual(s("dry riverbed"), {"https://e.org/1", "https://e.org/2"})   # both contain both terms
        self.assertEqual(len(s("fish riverbed dry")), 1)                         # AND
        self.assertEqual(len(s("fish pasta", all_=False)), 1)                    # OR

    def test_reindex_replaces_not_duplicates(self):
        i = self.add(content="original text unique1")
        self.build()
        self.storage.save_document(make_doc(content="replacement text unique2"))
        self.build()
        self.assertEqual(self.indexer.count(), 1)
        self.assertEqual(self.indexer.search(parse_query("unique1"), 5).total, 0)
        self.assertEqual(self.indexer.search(parse_query("unique2"), 5).total, 1)

    def test_rebuild_and_remove(self):
        a = self.add(url="https://e.org/1", content="kiwi"); self.add(url="https://e.org/2", content="kiwi fruit")
        self.build()
        self.assertEqual(rebuild_index(self.storage, self.indexer), 2)
        self.indexer.remove([a])
        self.assertEqual(self.indexer.count(), 1)

    def test_malicious_query_text_is_safe(self):
        self.add(content="hello world")
        self.build()
        for q in ['"', "AND OR NOT", "hello NEAR/2 world", "col:hello", "hello* ^world", "') DROP TABLE docs_fts;--", "(((("]:
            try:
                self.indexer.search(parse_query(q), 5)
            except ValueError:
                pass   # parser rejection is fine; an exception from SQLite is not (would be OperationalError)
        self.assertEqual(self.indexer.count(), 1)

    def test_info(self):
        info = self.indexer.info()
        self.assertEqual(info["engine"], "sqlite-fts5")
        self.assertNotIn("path", info)


class RankingTests(SearchStackCase):
    def test_title_beats_body_and_bm25_orders(self):
        body = self.add(url="https://e.org/body", title="Misc notes", content="the wadi appears once in this long text " + "filler " * 50)
        title = self.add(url="https://e.org/title", title="Wadi", content="short page")
        many = self.add(url="https://e.org/many", title="Other", content="wadi wadi wadi wadi " + "filler " * 5)
        self.build()
        q = parse_query("wadi")
        ranked = self.ranker.rank(q, self.indexer.search(q, 10, weights=self.ranker.field_weights).hits)
        order = [h.doc_id for h in ranked]
        self.assertEqual(order[0], title)                       # title field weighted 5x
        self.assertLess(order.index(many), order.index(body))   # higher tf / shorter doc beats a single mention
        self.assertTrue(all(ranked[i].score >= ranked[i + 1].score for i in range(len(ranked) - 1)))

    def test_deterministic_ties(self):
        for i in range(3):
            self.add(url=f"https://e.org/{i}", content=f"same words tie{i % 1}", chash=f"h{i}")
        self.build()
        q = parse_query("same")
        ids = [h.doc_id for h in self.ranker.rank(q, self.indexer.search(q, 10).hits)]
        self.assertEqual(ids, sorted(ids))


class ServiceTests(SearchStackCase):
    def seed(self, n):
        for i in range(n):
            self.add(url=f"https://e.org/{i}", title=f"Doc {i}", content=f"common term plus unique{i} body text", chash=f"h{i}")
        self.build()

    def test_response_shape_and_snippet(self):
        self.seed(1)
        r = self.svc.search("unique0")
        self.assertEqual(set(r), {"query", "page", "page_size", "total_pages", "result_count", "result_count_exact",
                                  "match", "latency_ms", "results"})
        self.assertEqual(set(r["results"][0]), {"title", "url", "domain", "snippet"})
        self.assertIn("unique0", r["results"][0]["snippet"])
        self.assertEqual((r["result_count"], r["match"]), (1, "all"))
        self.assertGreaterEqual(r["latency_ms"], 0)

    def test_pagination(self):
        self.seed(25)
        p1, p2, p3 = (self.svc.search("common", p) for p in (1, 2, 3))
        self.assertEqual((len(p1["results"]), len(p2["results"]), len(p3["results"])), (10, 10, 5))
        self.assertEqual(p1["total_pages"], 3)
        urls = [x["url"] for p in (p1, p2, p3) for x in p["results"]]
        self.assertEqual(len(set(urls)), 25)                    # no overlap between pages
        self.assertEqual(self.svc.search("common", 4)["results"], [])   # beyond last page: empty, not an error

    def test_pagination_limits(self):
        self.seed(1)
        for bad in (0, -1, self.settings.max_pages + 1, "2", None, 1.5):
            with self.assertRaises(InvalidSearchRequest, msg=repr(bad)):
                self.svc.search("common", bad)

    def test_or_fallback(self):
        self.seed(2)
        r = self.svc.search("unique0 nonexistentword")
        self.assertEqual((r["match"], r["result_count"]), ("any", 1))

    def test_empty_and_invalid_queries(self):
        for q in ["", "   ", "!!!", "x" * 500, None]:
            with self.assertRaises(InvalidSearchRequest):
                self.svc.search(q)

    def test_no_results_and_logging(self):
        self.seed(1)
        r = self.svc.search("zzzzqqq")
        self.assertEqual((r["result_count"], r["results"], r["total_pages"]), (0, [], 0))
        self.assertEqual(self.storage.search_stats()["search_count"], 1)
        self.assertEqual(self.storage.recent_queries()[0]["query"], "zzzzqqq")

    def test_index_storage_desync_is_tolerated(self):
        self.seed(2)
        self.indexer.index([__import__("wadiya.indexer.base", fromlist=["x"]).IndexDocument(999, "https://ghost/", "ghost", "ghost common", "", "", "common")])
        r = self.svc.search("common")
        self.assertTrue(all(x["domain"] != "ghost" for x in r["results"]))

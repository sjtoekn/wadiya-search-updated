from tests.test_search_stack import SearchStackCase
from wadiya.admin.auth import AdminAuth, hash_password
from wadiya.api import handlers
from wadiya.config.settings import Settings


class HandlerTests(SearchStackCase):
    def seed(self):
        self.add(url="https://e.org/1", title="Wadi guide", content="A wadi is a dry riverbed.")
        self.build()

    def test_search_ok_hides_internals(self):
        self.seed()
        status, body = handlers.handle_search(self.svc, "wadi", "1")
        self.assertEqual(status, 200)
        flat = repr(body)
        for secret in ("content_hash", "indexed_at", "canonical_url", self.tmp, ".db", "rowid", "doc_id"):
            self.assertNotIn(secret, flat)

    def test_page_ok_returns_public_fields(self):
        self.seed()
        status, body = handlers.handle_page(self.storage, "https://e.org/1")
        self.assertEqual(status, 200)
        self.assertEqual(body["title"], "Wadi guide")
        self.assertEqual(body["url"], "https://e.org/1")
        self.assertEqual(body["domain"], "e.org")
        self.assertIn("description", body)
        self.assertIn("content", body)
        self.assertIn("crawled_at", body)

    def test_input_validation_returns_400_json(self):
        self.seed()
        cases = [("", "1"), ("   ", "1"), (None, "1"), ("x" * 201, "1"), ("wadi", "0"), ("wadi", "-1"),
                 ("wadi", "abc"), ("wadi", "1.5"), ("wadi", "99999"), ("wadi", str(self.settings.max_pages + 1)),
                 ("wadi", "１"), ("wadi", "1; DROP TABLE"), ("!!!", "1")]
        for q, p in cases:
            status, body = handlers.handle_search(self.svc, q, p)
            self.assertEqual(status, 400, (q, p))
            self.assertEqual(set(body["error"]), {"code", "message"})

    def test_page_defaults(self):
        self.seed()
        self.assertEqual(handlers.handle_search(self.svc, "wadi", None)[1]["page"], 1)
        self.assertEqual(handlers.handle_search(self.svc, "wadi", "")[1]["page"], 1)

    def test_admin_discovery_handler(self):
        self.storage.register_discovered_site(
            "https://alpha.example/",
            "alpha.example",
            source="link",
        )
        self.storage.register_discovered_site(
            "https://beta.example/",
            "beta.example",
            source="sitemap",
        )

        status, body = handlers.handle_admin_discovery(self.storage)

        self.assertEqual(status, 200)
        self.assertEqual(body["stats"]["total"], 2)
        self.assertEqual(len(body["sites"]), 2)

    def test_admin_discovery_handler_filters(self):
        self.storage.register_discovered_site(
            "https://alpha.example/",
            "alpha.example",
            source="link",
        )
        self.storage.register_discovered_site(
            "https://beta.example/",
            "beta.example",
            source="sitemap",
        )

        status, body = handlers.handle_admin_discovery(
            self.storage,
            source="sitemap",
        )

        self.assertEqual(status, 200)
        self.assertEqual(len(body["sites"]), 1)
        self.assertEqual(body["sites"][0]["domain"], "beta.example")

    def test_admin_discovery_handler_rejects_invalid_filters(self):
        cases = [
            {"status": "robots_blocked"},
            {"status": "unknown"},
            {"source": "bad source"},
            {"source": "x" * 101},
            {"query": "x" * 254},
            {"page": "abc"},
            {"page": "0"},
            {"page": "-1"},
            {"limit": "abc"},
            {"limit": "10"},
            {"limit": "200"},
        ]

        for kwargs in cases:
            status, body = handlers.handle_admin_discovery(
                self.storage,
                **kwargs,
            )
            self.assertEqual(status, 400, kwargs)
            self.assertEqual(
                set(body["error"]),
                {"code", "message"},
            )

    def test_admin_discovery_handler_pagination(self):
        for i in range(55):
            self.storage.register_discovered_site(
                f"https://site{i}.example/",
                "site.example",
                source="link",
            )

        status, body = handlers.handle_admin_discovery(
            self.storage,
            page="2",
            limit="20",
        )

        self.assertEqual(status, 200)
        self.assertEqual(
            body["pagination"],
            {
                "page": 2,
                "page_size": 20,
                "total": 55,
                "total_pages": 3,
                "start": 21,
                "end": 40,
            },
        )
        self.assertEqual(len(body["sites"]), 20)

    def test_login_and_stats(self):
        self.seed()
        auth = AdminAuth(Settings(admin_password_hash=hash_password("open sesame 123"), secret_key="k" * 40))
        self.assertEqual(handlers.handle_login(auth, "bad", "c")[0], 401)
        status, body, token = handlers.handle_login(auth, "open sesame 123", "c")
        self.assertEqual((status, body, bool(token)), (200, {"ok": True}, True))
        handlers.handle_search(self.svc, "wadi", "1")
        status, st = handlers.handle_stats(self.storage, self.indexer)
        self.assertEqual(status, 200)
        self.assertEqual((st["documents"], st["domains"], st["index"]["documents"]), (1, 1, 1))
        self.assertEqual(st["search"]["search_count"], 1)
        self.assertEqual(st["search"]["recent_queries"][0]["query"], "wadi")
        self.assertEqual(st["crawler"]["status"], "never run")
        self.assertNotIn("path", st["index"])

from tests.test_search_stack import SearchStackCase
from wadiya.admin.auth import AdminAuth, hash_password
from wadiya.api import handlers
from wadiya.config.settings import Settings
from wadiya.crawler.fetcher import Fetcher
from wadiya.crawler.urls import UrlPolicy


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


    def test_preview_website_extracts_metadata_and_keywords(self):
        from tests.mock_site import MockSite

        html = b"""
        <!doctype html>
        <html lang="en">
        <head>
          <title>Canadian Travel Guide</title>
          <meta name="description" content="A practical travel guide to Canada.">
          <link rel="canonical" href="/travel">
        </head>
        <body>
          <header>Navigation</header>
          <main>
            <h1>Canadian Travel Guide</h1>
            <h2>Travel in Canada</h2>
            <p>Explore Canadian destinations and travel information.</p>
          </main>
          <footer>Footer</footer>
        </body>
        </html>
        """

        settings = Settings(
            allow_private_networks=True,
            max_retries=0,
            request_timeout=3,
            total_fetch_timeout=5,
        )
        fetcher = Fetcher(
            settings,
            policy=UrlPolicy(
                allowed_ports=None,
                allow_private_networks=True,
            ),
        )

        from unittest.mock import patch

        with MockSite({
            "/": (200, "text/html; charset=utf-8", html, {}),
        }) as site, patch(
            "wadiya.api.handlers.is_safe_submission_target",
            return_value=True,
        ):
            status, body = handlers.handle_preview_website(
                settings,
                site.base + "/",
                fetcher=fetcher,
            )

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["title"], "Canadian Travel Guide")
        self.assertEqual(
            body["description"],
            "A practical travel guide to Canada.",
        )
        self.assertEqual(body["language"], "en")
        self.assertEqual(body["canonical_url"], site.base + "/travel")
        self.assertIn("Canadian Travel Guide", body["headings"])
        self.assertIn("canadian", body["keywords"])
        self.assertIn("travel", body["keywords"])
        self.assertFalse(body["robots"]["noindex"])
        self.assertFalse(body["robots"]["nofollow"])

    def test_preview_website_does_not_store_or_queue(self):
        from tests.mock_site import MockSite

        html = b"""
        <html>
          <head><title>Preview Only</title></head>
          <body><h1>Preview Only</h1></body>
        </html>
        """

        settings = Settings(
            allow_private_networks=True,
            max_retries=0,
            request_timeout=3,
            total_fetch_timeout=5,
        )
        fetcher = Fetcher(
            settings,
            policy=UrlPolicy(
                allowed_ports=None,
                allow_private_networks=True,
            ),
        )

        from unittest.mock import patch

        with MockSite({
            "/": (200, "text/html", html, {}),
        }) as site, patch(
            "wadiya.api.handlers.is_safe_submission_target",
            return_value=True,
        ):
            before = self.storage.discovery_registry_stats()
            status, body = handlers.handle_preview_website(
                settings,
                site.base + "/",
                fetcher=fetcher,
            )
            after = self.storage.discovery_registry_stats()

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(before, after)

    def test_preview_website_rejects_unsafe_url(self):
        for url in (
            "http://localhost/",
            "http://127.0.0.1/",
            "http://169.254.169.254/",
            "http://metadata/",
        ):
            with self.subTest(url=url):
                status, body = handlers.handle_preview_website(
                    Settings(),
                    url,
                )
                self.assertEqual(status, 400)
                self.assertFalse(body.get("ok", False))

    def test_preview_website_rejects_non_html(self):
        from tests.mock_site import MockSite

        settings = Settings(
            allow_private_networks=True,
            max_retries=0,
            request_timeout=3,
            total_fetch_timeout=5,
        )
        fetcher = Fetcher(
            settings,
            policy=UrlPolicy(
                allowed_ports=None,
                allow_private_networks=True,
            ),
        )

        from unittest.mock import patch

        with MockSite({
            "/image": (200, "image/png", b"not html", {}),
        }) as site, patch(
            "wadiya.api.handlers.is_safe_submission_target",
            return_value=True,
        ):
            status, body = handlers.handle_preview_website(
                settings,
                site.base + "/image",
                fetcher=fetcher,
            )

        self.assertEqual(status, 415)
        self.assertIn("HTML", body["error"]["message"])

    def test_preview_website_requires_url(self):
        for url in (None, "", "   ", "not-a-url"):
            with self.subTest(url=url):
                status, body = handlers.handle_preview_website(
                    Settings(),
                    url,
                )
                self.assertEqual(status, 400)
                self.assertIn("error", body)

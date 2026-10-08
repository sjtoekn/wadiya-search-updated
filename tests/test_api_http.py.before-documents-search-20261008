"""HTTP-level tests of the FastAPI wiring. Skipped automatically when fastapi/httpx are missing."""
import unittest
from unittest.mock import patch
from dataclasses import replace

from tests.test_search_stack import SearchStackCase
from wadiya.admin.auth import hash_password
from wadiya.crawler.fetcher import Fetcher
from wadiya.crawler.urls import UrlPolicy
from tests.mock_site import MockSite

try:
    from fastapi.testclient import TestClient
    from wadiya.api.app import create_app
    HAVE = True
except ImportError:
    HAVE = False

PW = "open sesame 123"


@unittest.skipUnless(HAVE, "fastapi/httpx not installed in this environment")
class ApiHttpTests(SearchStackCase):
    def setUp(self):
        super().setUp()
        self.add(url="https://e.org/1", title="Wadi guide", content="A wadi is a dry riverbed.")
        self.build()
        self.st = replace(self.settings, admin_password_hash=hash_password(PW), secret_key="k" * 48, cookie_secure=False)
        self.preview_fetcher = Fetcher(
            self.st,
            policy=UrlPolicy(
                allowed_ports=None,
                allow_private_networks=True,
            ),
        )
        self.client = TestClient(
            create_app(
                self.st,
                self.storage,
                self.indexer,
                fetcher=self.preview_fetcher,
            ),
            raise_server_exceptions=False,
        )

    def test_search_and_validation(self):
        c = self.client
        self.assertEqual(c.get("/api/search?q=wadi").json()["result_count"], 1)
        for url in ("/api/search", "/api/search?q=", "/api/search?q=wadi&page=0", "/api/search?q=wadi&page=x",
                    "/api/search?q=" + "a" * 500, "/api/search?q=wadi&page=999"):
            r = c.get(url)
            self.assertEqual(r.status_code, 400, url)
            self.assertIn("message", r.json()["error"])

    def test_search_query_operators(self):
        self.add(
            url="https://example.com/python.pdf",
            domain="example.com",
            title="Python Guide",
            content="python guide",
        )
        self.add(
            url="https://other.com/python.html",
            domain="other.com",
            title="General Guide",
            content="python django guide",
        )
        self.build()

        c = self.client

        r = c.get("/api/search", params={"q": "python site:example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result_count"], 1)

        r = c.get("/api/search", params={"q": "intitle:python"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result_count"], 1)

        r = c.get("/api/search", params={"q": "python filetype:pdf"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result_count"], 1)

        r = c.get("/api/search", params={"q": "python -django"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result_count"], 1)

    def test_health_404_and_no_docs(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        r = self.client.get("/nope"); self.assertEqual((r.status_code, r.json()["error"]["code"]), (404, 404))
        for p in ("/docs", "/redoc", "/openapi.json"):
            self.assertEqual(self.client.get(p).status_code, 404)

    def test_security_headers(self):
        h = self.client.get("/").headers
        self.assertIn("default-src 'self'", h["content-security-policy"])
        self.assertEqual((h["x-content-type-options"], h["x-frame-options"]), ("nosniff", "DENY"))

    def test_admin_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/stats").status_code, 401)
        self.client.cookies.set("wadiya_admin", "forged.token.value")
        self.assertEqual(self.client.get("/api/admin/stats").status_code, 401)

    def test_admin_discovery_requires_auth(self):
        r = self.client.get("/api/admin/discovery")
        self.assertEqual(r.status_code, 401)

    def test_admin_discovery_authenticated(self):
        c = self.client

        login = c.post("/api/admin/login", json={"password": PW})
        self.assertEqual(login.status_code, 200)

        r = c.get("/api/admin/discovery")
        self.assertEqual(r.status_code, 200)

        body = r.json()
        self.assertIn("stats", body)
        self.assertIn("sites", body)
        self.assertEqual(body["stats"]["total"], 0)
        self.assertEqual(body["sites"], [])

    def test_admin_discovery_validation(self):
        c = self.client

        self.assertEqual(
            c.post("/api/admin/login", json={"password": PW}).status_code,
            200,
        )

        cases = (
            "/api/admin/discovery?status=robots_blocked",
            "/api/admin/discovery?status=unknown",
            "/api/admin/discovery?source=bad%20source",
            "/api/admin/discovery?limit=abc",
            "/api/admin/discovery?limit=10",
            "/api/admin/discovery?page=0",
            "/api/admin/discovery?page=abc",
        )

        for url in cases:
            r = c.get(url)
            self.assertEqual(r.status_code, 400, url)
            self.assertIn("message", r.json()["error"])

    def test_admin_discovery_pagination_response(self):
        c = self.client

        self.assertEqual(
            c.post("/api/admin/login", json={"password": PW}).status_code,
            200,
        )

        for i in range(55):
            self.storage.register_discovered_site(
                f"https://site{i}.example/",
                "site.example",
                source="link",
            )

        r = c.get("/api/admin/discovery?page=2&limit=20")
        self.assertEqual(r.status_code, 200)

        body = r.json()
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

    def test_admin_login_flow_and_cookie_flags(self):
        c = self.client
        self.assertEqual(c.post("/api/admin/login", json={"password": "bad"}).status_code, 401)
        self.assertEqual(c.post("/api/admin/login", data={"password": PW}).status_code, 415)   # form posts refused
        self.assertEqual(c.post("/api/admin/login", content=b"{bad", headers={"content-type": "application/json"}).status_code, 400)
        r = c.post("/api/admin/login", json={"password": PW})
        self.assertEqual(r.status_code, 200)
        cookie = r.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie); self.assertIn("samesite=strict", cookie)
        self.assertNotIn(PW, r.text)
        s = c.get("/api/admin/stats"); self.assertEqual(s.status_code, 200)
        self.assertEqual(s.json()["documents"], 1)
        self.assertEqual(s.headers["cache-control"], "no-store")
        c.post("/api/admin/logout"); self.assertEqual(c.get("/api/admin/stats").status_code, 401)

    def test_secure_flag_on_by_default(self):
        st = replace(self.st, cookie_secure=True)
        c = TestClient(create_app(st, self.storage, self.indexer), base_url="https://testserver")
        r = c.post("/api/admin/login", json={"password": PW})
        self.assertIn("secure", r.headers["set-cookie"].lower())

    def test_login_rate_limit(self):
        for _ in range(5):
            self.client.post("/api/admin/login", json={"password": "bad"})
        self.assertEqual(self.client.post("/api/admin/login", json={"password": PW}).status_code, 429)

    def test_admin_disabled_without_config(self):
        c = TestClient(create_app(self.settings, self.storage, self.indexer))
        self.assertEqual(c.post("/api/admin/login", json={"password": PW}).status_code, 503)
        self.assertEqual(c.get("/api/admin/stats").status_code, 401)


    def test_submit_preview_over_http_extracts_metadata(self):
        html = """<!doctype html>
<html lang="en">
<head>
  <title>Canadian Travel Guide</title>
  <meta name="description" content="Practical travel information for Canadian destinations.">
  <link rel="canonical" href="{base}/canonical">
</head>
<body>
  <h1>Canadian Travel Guide</h1>
  <h2>Canada Destinations</h2>
  <p>Travel information for Canadian destinations and practical trip planning.</p>
</body>
</html>"""

        with MockSite({
            "/": (200, "text/html; charset=utf-8", html, {}),
        }) as site, patch(
            "wadiya.api.handlers.is_safe_submission_target",
            return_value=True,
        ):
            before = self.storage.discovery_registry_stats()
            r = self.client.post(
                "/api/submit/preview",
                json={"url": site.base + "/"},
            )
            after = self.storage.discovery_registry_stats()

        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["url"], site.base + "/")
        self.assertEqual(body["title"], "Canadian Travel Guide")
        self.assertIn("description", body)
        self.assertIn("language", body)
        self.assertIn("headings", body)
        self.assertIn("keywords", body)
        self.assertEqual(before, after)

    def test_submit_preview_over_http_validates_request(self):
        r = self.client.post(
            "/api/submit/preview",
            json={},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("message", r.json()["error"])

        r = self.client.post(
            "/api/submit/preview",
            content="{}",
            headers={"content-type": "text/plain"},
        )
        self.assertEqual(r.status_code, 415)

        r = self.client.post(
            "/api/submit/preview",
            content="{bad json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(r.status_code, 400)

    def test_submit_preview_over_http_rejects_unsafe_url(self):
        r = self.client.post(
            "/api/submit/preview",
            json={"url": "http://127.0.0.1/"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("unsafe", r.json()["error"]["message"].lower())

    def test_submit_preview_rate_limit(self):
        html = """<!doctype html>
<html>
<head><title>Preview Limit Test</title></head>
<body><h1>Preview Limit Test</h1></body>
</html>"""

        with MockSite({
            "/": (200, "text/html; charset=utf-8", html, {}),
        }) as site, patch(
            "wadiya.api.handlers.is_safe_submission_target",
            return_value=True,
        ):
            for _ in range(5):
                r = self.client.post(
                    "/api/submit/preview",
                    json={"url": site.base + "/"},
                )
                self.assertEqual(r.status_code, 200)

            r = self.client.post(
                "/api/submit/preview",
                json={"url": site.base + "/"},
            )

        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.headers.get("retry-after"), "600")
        self.assertEqual(
            r.json(),
            {
                "error": {
                    "code": 429,
                    "message": "too many website previews; try again later",
                }
            },
        )

    def test_submit_preview_over_http_rejects_non_html(self):
        with MockSite({
            "/image": (200, "image/png", b"not html", {}),
        }) as site, patch(
            "wadiya.api.handlers.is_safe_submission_target",
            return_value=True,
        ):
            r = self.client.post(
                "/api/submit/preview",
                json={"url": site.base + "/image"},
            )

        self.assertEqual(r.status_code, 415)
        self.assertIn("HTML", r.json()["error"]["message"])

    def test_submit_website_accepts_valid_url(self):
        r = self.client.post(
            "/api/submit",
            json={"url": "https://example.com"},
        )

        self.assertEqual(r.status_code, 202)

        body = r.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["submitted"])
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["url"], "https://example.com/")
        self.assertEqual(body["domain"], "example.com")


    def test_submit_website_rate_limit(self):
        for _ in range(10):
            r = self.client.post(
                "/api/submit",
                json={"url": "https://example.com"},
            )
            self.assertIn(r.status_code, (200, 202))

        r = self.client.post(
            "/api/submit",
            json={"url": "https://example.com/another"},
        )

        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.headers.get("retry-after"), "600")

        body = r.json()
        self.assertEqual(
            body,
            {
                "error": {
                    "code": 429,
                    "message": "too many website submissions; try again later",
                }
            },
        )

    def test_submit_website_duplicate_is_idempotent(self):
        first = self.client.post(
            "/api/submit",
            json={"url": "https://example.com"},
        )
        second = self.client.post(
            "/api/submit",
            json={"url": "https://example.com"},
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)

        body = second.json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["submitted"])
        self.assertEqual(body["status"], "pending")

    def test_submit_website_rejects_missing_url(self):
        r = self.client.post("/api/submit", json={})

        self.assertEqual(r.status_code, 400)
        self.assertIn("url", r.json()["error"]["message"])

    def test_submit_website_rejects_invalid_url(self):
        r = self.client.post(
            "/api/submit",
            json={"url": "not-a-valid-url"},
        )

        self.assertEqual(r.status_code, 400)

    def test_submit_website_rejects_unsafe_urls(self):
        unsafe_urls = [
            "http://localhost/",
            "http://127.0.0.1/",
            "http://169.254.169.254/",
            "http://metadata/",
        ]

        for url in unsafe_urls:
            with self.subTest(url=url):
                r = self.client.post(
                    "/api/submit",
                    json={"url": url},
                )

                self.assertEqual(r.status_code, 400)
                self.assertFalse(r.json().get("ok", False))

    def test_submit_website_requires_json(self):
        r = self.client.post(
            "/api/submit",
            content='{"url":"https://example.com"}',
            headers={"content-type": "text/plain"},
        )

        self.assertEqual(r.status_code, 415)

    def test_submit_website_rejects_invalid_json(self):
        r = self.client.post(
            "/api/submit",
            content='{"url":',
            headers={"content-type": "application/json"},
        )

        self.assertEqual(r.status_code, 400)


@unittest.skipUnless(HAVE, "fastapi/httpx not installed in this environment")
class ApiHttpHardeningTests(SearchStackCase):
    def setUp(self):
        super().setUp()
        for i in range(25):
            self.add(url=f"https://p.example/{i}", title=f"Paginate {i}", content=f"paginate sample {i}", chash=f"p{i}")
        self.add(url="https://e.org/wadi", title="Wadi", content="a wadi is a dry riverbed", chash="w")
        self.build()
        self.st = replace(self.settings, admin_password_hash=hash_password(PW), secret_key="k" * 48, cookie_secure=False)
        self.client = TestClient(create_app(self.st, self.storage, self.indexer), raise_server_exceptions=False)

    def test_pagination_over_http(self):
        p1, p3, p4 = (self.client.get(f"/api/search?q=paginate&page={n}").json() for n in (1, 3, 4))
        self.assertEqual((len(p1["results"]), p1["result_count"], p1["total_pages"], len(p3["results"]), p4["results"]), (10, 25, 3, 5, []))

    def test_500_is_json_and_leaks_nothing(self):
        from wadiya.storage.sqlite_store import SQLiteStorage

        class Broken(SQLiteStorage):
            def get_documents(self, ids):
                raise RuntimeError("secret internal detail /var/lib/wadiya/w.db")
        broken = Broken(self.settings.db_path)
        c = TestClient(create_app(self.st, broken, self.indexer), raise_server_exceptions=False)
        r = c.get("/api/search?q=wadi")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json(), {"error": {"code": 500, "message": "internal error"}})
        self.assertNotIn("secret", r.text); self.assertNotIn("/var/lib", r.text)
        self.assertIn("default-src 'self'", r.headers["content-security-policy"])        # headers survive error responses

    def test_oversized_login_body_is_rejected_without_buffering(self):
        c = self.client
        big = '{"password": "' + "x" * 200_000 + '"}'
        self.assertEqual(c.post("/api/admin/login", content=big, headers={"content-type": "application/json"}).status_code, 413)

        def gen():                                                                       # chunked: no Content-Length header at all
            yield b'{"password": "'
            for _ in range(100):
                yield b"x" * 2000
            yield b'"}'
        self.assertEqual(c.post("/api/admin/login", content=gen(), headers={"content-type": "application/json"}).status_code, 413)
        self.assertEqual(c.post("/api/admin/login", json={"password": PW}).status_code, 200)   # normal logins unaffected

    def test_static_path_traversal_refused(self):
        for p in ("/static/../config/settings.py", "/static/%2e%2e/config/settings.py", "/static/..%2fconfig%2fsettings.py"):
            r = self.client.get(p)
            self.assertNotEqual(r.status_code, 200, p)
            self.assertNotIn("class Settings", r.text)

    def test_ui_and_static_served(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200); self.assertIn('id="searchForm"', r.text)
        self.assertIn("javascript", self.client.get("/static/app.js").headers["content-type"])
        self.assertEqual(self.client.get("/admin").status_code, 200)

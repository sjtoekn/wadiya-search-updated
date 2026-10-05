"""HTTP-level tests of the FastAPI wiring. Skipped automatically when fastapi/httpx are missing."""
import unittest
from dataclasses import replace

from tests.test_search_stack import SearchStackCase
from wadiya.admin.auth import hash_password

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
        self.client = TestClient(create_app(self.st, self.storage, self.indexer), raise_server_exceptions=False)

    def test_search_and_validation(self):
        c = self.client
        self.assertEqual(c.get("/api/search?q=wadi").json()["result_count"], 1)
        for url in ("/api/search", "/api/search?q=", "/api/search?q=wadi&page=0", "/api/search?q=wadi&page=x",
                    "/api/search?q=" + "a" * 500, "/api/search?q=wadi&page=999"):
            r = c.get(url)
            self.assertEqual(r.status_code, 400, url)
            self.assertIn("message", r.json()["error"])

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

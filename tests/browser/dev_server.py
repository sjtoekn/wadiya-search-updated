"""STAND-IN server for real-browser UI tests (stdlib only).
Routes call the same handlers / AdminAuth / SECURITY_HEADERS as api/app.py, but this is NOT api/app.py:
it exists because FastAPI cannot be installed in the build sandbox. Run: python3 -m tests.browser.dev_server"""
import json
import shutil
import sys
import tempfile
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tests.helpers import make_doc
from wadiya.admin.auth import AdminAuth, hash_password
from wadiya.api import handlers
from wadiya.api.limits import MAX_LOGIN_BODY, BodyLimiter, BodyTooLarge, SubmitLimiter
from wadiya.api.security import COOKIE_NAME, SECURITY_HEADERS
from wadiya.config.settings import Settings
from wadiya.indexer.fts5 import FTS5Indexer
from wadiya.pipeline import index_pending
from wadiya.ranking.bm25 import BM25Ranker
from wadiya.search.service import SearchService
from wadiya.storage.sqlite_store import SQLiteStorage

WEB = Path(__file__).resolve().parents[2] / "wadiya" / "web"
ADMIN_PW = "browser-test-password"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


def build_world(tmp):
    st = Settings(db_path=f"{tmp}/w.db", index_path=f"{tmp}/i.db", cookie_secure=False,
                  admin_password_hash=hash_password(ADMIN_PW), secret_key="b" * 48)
    storage, indexer = SQLiteStorage(st.db_path), FTS5Indexer(st.index_path)
    storage.init(); indexer.init()
    add = lambda **kw: storage.save_document(make_doc(**kw))
    add(url="https://example.org/wadi", title="Wadi guide", domain="example.org",
        content="A wadi is a dry riverbed that fills with water after heavy rain in arid regions.")
    add(url="https://example.org/oasis", title="Oasis facts", domain="example.org",
        content="An oasis is a fertile spot in a desert. Some oases sit beside a wadi.")
    for i in range(25):
        add(url=f"https://paginate.example/{i}", title=f"Paginate item {i:02d}", domain="paginate.example",
            content=f"paginate sample document number {i} with some filler words", chash=f"p{i}")
    # hostile content exactly as the extractor would store it (entities decoded to literal characters)
    add(url="https://evil.example/a", title='<img src=x onerror="window.__pwned=1">', domain="evil.example",
        content='hostile text <script>window.__pwned=1</script> <img src=x onerror="window.__pwned=1"> end', chash="e1")
    add(url="javascript:window.__pwned=1", title="Js link hostile", domain="evil.example",
        content="hostile jslink payload", chash="e2")
    index_pending(storage, indexer)
    return st, storage, indexer, SearchService(st, storage, indexer, BM25Ranker()), AdminAuth(st)


def make_server(tmp, port=0):
    st, storage, indexer, service, auth = build_world(tmp)
    submit_limiter = SubmitLimiter()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _send(self, status, body, ctype="application/json", extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
            for k, v in {**SECURITY_HEADERS, **(extra or {})}.items():
                self.send_header(k, v)
            self.end_headers(); self.wfile.write(data)

        def _authed(self):
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE_NAME and auth.verify_token(v):
                    return True
            return False

        def do_GET(self):
            u = urlsplit(self.path); q = parse_qs(u.query)
            if u.path == "/api/search":
                code, body = handlers.handle_search(service, (q.get("q") or [""])[0], (q.get("page") or ["1"])[0])
                return self._send(code, body)
            if u.path == "/api/discovery":
                code, body = handlers.handle_discovery(storage, (q.get("domain") or [""])[0])
                return self._send(code, body)
            if u.path == "/api/health":
                return self._send(200, {"status": "ok"})
            if u.path == "/api/admin/stats":
                if not self._authed():
                    return self._send(401, handlers.error(401, "authentication required")[1])
                return self._send(*handlers.handle_stats(storage, indexer))
            page = {"/": "index.html", "/admin": "admin.html", "/discovery": "discovery.html"}.get(u.path)
            if u.path.startswith("/static/"):
                page = u.path[len("/static/"):]
            f = (WEB / page).resolve() if page else None
            if f and f.is_file() and WEB.resolve() in f.parents:
                return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
            return self._send(404, handlers.error(404, "Not Found")[1])

        def do_POST(self):
            u = urlsplit(self.path)

            if u.path == "/api/submit":
                if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                    return self._send(
                        415,
                        handlers.error(415, "expected application/json")[1],
                    )

                lim = BodyLimiter(4096)

                try:
                    lim.declare(self.headers.get("Content-Length"))
                    length = int(self.headers.get("Content-Length") or 0)
                    lim.feed(self.rfile.read(length))
                except BodyTooLarge:
                    return self._send(
                        413,
                        handlers.error(413, "request body too large")[1],
                    )
                except ValueError:
                    return self._send(
                        400,
                        handlers.error(400, "invalid content-length")[1],
                    )

                try:
                    data = json.loads(lim.body() or b"null")
                except Exception:
                    return self._send(
                        400,
                        handlers.error(400, "invalid json")[1],
                    )

                url = data.get("url") if isinstance(data, dict) else None
                client_key = self.client_address[0]

                if not submit_limiter.allowed(client_key):
                    retry_after = submit_limiter.retry_after(client_key)
                    return self._send(
                        429,
                        handlers.error(
                            429,
                            "too many website submissions; try again later",
                        )[1],
                        extra={"Retry-After": str(retry_after)},
                    )

                submit_limiter.hit(client_key)

                status, body = handlers.handle_submit_website(storage, url)
                return self._send(status, body)

            if u.path == "/api/admin/login":
                if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                    return self._send(
                        415,
                        handlers.error(415, "expected application/json")[1],
                    )

                lim = BodyLimiter(MAX_LOGIN_BODY)

                try:
                    lim.declare(self.headers.get("Content-Length"))
                    lim.feed(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                except BodyTooLarge:
                    return self._send(
                        413,
                        handlers.error(413, "request body too large")[1],
                    )
                except ValueError:
                    return self._send(
                        400,
                        handlers.error(400, "invalid content-length")[1],
                    )

                raw = lim.body()

                try:
                    data = json.loads(raw or b"null")
                except Exception:
                    return self._send(
                        400,
                        handlers.error(400, "invalid json")[1],
                    )

                pw = data.get("password") if isinstance(data, dict) else None
                code, body, token = handlers.handle_login(
                    auth,
                    pw,
                    self.client_address[0],
                )

                extra = (
                    {
                        "Set-Cookie": (
                            f"{COOKIE_NAME}={token}; "
                            "HttpOnly; SameSite=Strict; Path=/"
                        )
                    }
                    if token
                    else None
                )

                return self._send(code, body, extra=extra)

            if u.path == "/api/admin/logout":
                return self._send(
                    200,
                    {"ok": True},
                    extra={
                        "Set-Cookie": (
                            f"{COOKIE_NAME}=; Max-Age=0; Path=/"
                        )
                    },
                )

            return self._send(
                404,
                handlers.error(404, "Not Found")[1],
            )

    return ThreadingHTTPServer(("127.0.0.1", port), H)


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="wadiya-browser-")
    srv = make_server(tmp)
    print(f"PORT={srv.server_address[1]}", flush=True)
    try:
        srv.serve_forever()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

#!/usr/bin/env python3
"""Verify the REAL running Wadiya application over HTTP (stdlib only).

  python scripts/verify_live_http.py --spawn
      starts `python -m wadiya serve` on a free port with a throw-away database and admin credentials
  python scripts/verify_live_http.py --base-url http://127.0.0.1:8000 --admin-password PW
      checks an already-running server (checks that need control of the server are reported as SKIP)

Needs the project's requirements installed (fastapi, uvicorn). Exit code 0 only if every executed check passed."""
import argparse, http.client, json, os, socket, sqlite3, subprocess, sys, tempfile, time
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from wadiya.api.security import CSP  # noqa: E402

RESULTS, REAL = [], False
ADMIN_PW = "live-check-password-123"


def check(name, ok, detail="", real_only=False):
    if real_only and not REAL:
        RESULTS.append((name, "SKIP", "needs --spawn (control of the server)")); print(f"SKIP  {name}"); return
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   -> {detail}"))


class Client:
    def __init__(self, base): u = urlsplit(base); self.host, self.port = u.hostname, u.port

    def req(self, method, path, headers=None, body=None, chunked=False):
        c = http.client.HTTPConnection(self.host, self.port, timeout=15)
        try:
            c.request(method, path, body=body, headers=headers or {}, encode_chunked=chunked)
            r = c.getresponse(); data = r.read()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.msg.get_all("set-cookie") or [], data
        except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError) as e:
            return None, {}, [], repr(e).encode()
        finally:
            c.close()

    def json(self, method, path, **kw):
        s, h, ck, d = self.req(method, path, **kw)
        try: return s, h, ck, json.loads(d)
        except Exception: return s, h, ck, None


def run_checks(c, admin_pw):
    # ---------------- health / search / pagination / validation ----------------
    s, h, _, j = c.json("GET", "/api/health"); check("GET /api/health -> 200 {status: ok}", s == 200 and j == {"status": "ok"}, f"{s} {j}")
    s, h, _, j = c.json("GET", "/api/search?q=wadi")
    check("GET /api/search?q=wadi -> 200 with documented shape", s == 200 and {"query", "page", "page_size", "total_pages", "result_count", "match", "latency_ms", "results"} <= set(j or {}), f"{s} {j}")
    check("search results have title/url/domain/snippet and expose nothing internal", bool(j and j["results"]) and set(j["results"][0]) == {"title", "url", "domain", "snippet"} and "content_hash" not in json.dumps(j))
    s, _, _, p1 = c.json("GET", "/api/search?q=paginate&page=1"); s2, _, _, p3 = c.json("GET", "/api/search?q=paginate&page=3"); s4, _, _, p4 = c.json("GET", "/api/search?q=paginate&page=4")
    check("pagination: page 1 = 10 results, 25 total, 3 pages", s == 200 and len(p1["results"]) == 10 and p1["result_count"] == 25 and p1["total_pages"] == 3, str(p1 and (len(p1["results"]), p1["result_count"])))
    check("pagination: page 3 = 5 results; page 4 = empty (200, not an error)", s2 == 200 and len(p3["results"]) == 5 and s4 == 200 and p4["results"] == [])
    _, _, _, p2 = c.json("GET", "/api/search?q=paginate&page=2")
    check("pagination: pages do not overlap", not ({r["url"] for r in p1["results"]} & {r["url"] for r in p2["results"]}))
    bad = ["/api/search", "/api/search?q=", "/api/search?q=%20%20", "/api/search?q=" + "a" * 201, "/api/search?q=wadi&page=0", "/api/search?q=wadi&page=-1",
           "/api/search?q=wadi&page=abc", "/api/search?q=wadi&page=1.5", "/api/search?q=wadi&page=11", "/api/search?q=!!!"]
    codes = {u[-40:]: c.json("GET", u)[0] for u in bad}
    check("invalid query / page values -> 400 each", all(v == 400 for v in codes.values()), str(codes))
    s, _, _, j = c.json("GET", "/api/search?q=")
    check("error body shape {error:{code,message}}", s == 400 and set((j or {}).get("error", {})) == {"code", "message"}, str(j))
    hostile = ["%22", "NEAR(a%20b)", "a%20OR%20b%20AND%20NOT", "%27%20OR%201%3D1%20--", "%27)%3B%20DROP%20TABLE%20documents%3B--", "col%3Awadi", "%E6%97%A5%E6%9C%AC%E8%AA%9E", "wadi*", "((((("]
    codes = {q: c.json("GET", "/api/search?q=" + q)[0] for q in hostile}
    check("hostile / FTS-syntax / SQL-looking queries never produce a 5xx", all(v in (200, 400) for v in codes.values()), str(codes))
    s, *_ = c.req("GET", "/api/search?q=" + "a" * 70000)
    check("absurdly long URL is refused (4xx or connection closed), never 5xx/200", s is None or 400 <= s < 500, str(s))

    # ---------------- 404 JSON, headers, CSP, UI ----------------
    s, h, _, j = c.json("GET", "/definitely-not-here")
    check("unknown route -> 404 JSON {error:{code:404,...}}", s == 404 and (j or {}).get("error", {}).get("code") == 404, f"{s} {j}")
    s, *_ = c.req("GET", "/docs"); s2, *_ = c.req("GET", "/openapi.json")
    check("interactive docs / openapi schema are not exposed", s == 404 and s2 == 404, f"{s} {s2}")
    for path in ("/", "/api/search?q=wadi", "/api/health", "/nope", "/api/admin/stats", "/admin"):
        s, h, _, _ = c.req("GET", path)
        ok = h.get("content-security-policy") == CSP and h.get("x-content-type-options") == "nosniff" and h.get("x-frame-options") == "DENY" and h.get("referrer-policy") == "no-referrer"
        check(f"security headers + exact CSP on {path}", ok, str({k: h.get(k) for k in ("content-security-policy", "x-frame-options")}))
    s, h, _, body = c.req("GET", "/")
    check("GET / serves the Wadiya UI (html, search form present)", s == 200 and "text/html" in h.get("content-type", "") and b'id="searchForm"' in body and b"wadiya" in body.lower(), f"{s} {h.get('content-type')}")
    s, h, _, body = c.req("GET", "/static/app.js"); s2, h2, _, _ = c.req("GET", "/static/style.css")
    check("static assets served with correct content types", s == 200 and "javascript" in h.get("content-type", "") and b"/api/search" in body and s2 == 200 and "css" in h2.get("content-type", ""), f"{h.get('content-type')} {h2.get('content-type')}")
    leaks = {}
    for p in ("/static/../config/settings.py", "/static/%2e%2e/config/settings.py", "/static/..%2fconfig%2fsettings.py", "/static/%2e%2e%2f%2e%2e%2fREADME.md", "/static//etc/passwd", "/static/..\\config\\settings.py"):
        s, _, _, body = c.req("GET", p); leaks[p] = (s, b"class Settings" in body or b"root:" in body)
    check("path traversal under /static is refused and leaks no source/system files", all(not leak for _, leak in leaks.values()), str(leaks))
    s, _, _, body = c.req("GET", "/admin")
    check("GET /admin serves the admin shell (no data in it)", s == 200 and b"loginView" in body and b"documents" not in body.lower().replace(b"indexed documents", b""), str(s))

    # ---------------- admin protection / login ----------------
    s, *_ = c.req("GET", "/api/admin/stats"); check("admin stats without a session -> 401", s == 401, str(s))
    s, *_ = c.req("GET", "/api/admin/stats", headers={"Cookie": "wadiya_admin=forged.token.value"}); check("forged session cookie -> 401", s == 401, str(s))
    JH = {"Content-Type": "application/json"}
    s, *_ = c.req("POST", "/api/admin/login", headers=JH, body=json.dumps({"password": "wrong"})); check("wrong password -> 401", s == 401, str(s))
    s, *_ = c.req("POST", "/api/admin/login", headers={"Content-Type": "application/x-www-form-urlencoded"}, body="password=" + admin_pw); check("login via HTML form post (cross-site style) -> 415", s == 415, str(s))
    s, *_ = c.req("POST", "/api/admin/login", headers=JH, body="{not json"); check("malformed JSON -> 400", s == 400, str(s))
    big = json.dumps({"password": "x" * 200_000})
    s, _, _, j = c.json("POST", "/api/admin/login", headers=JH, body=big); check("oversized login body (200 KB, Content-Length) -> 413", s == 413, str(s))
    s, *_ = c.req("POST", "/api/admin/login", headers={**JH, "Transfer-Encoding": "chunked"}, body=iter([b'{"password":"' + b"x" * 50_000, b"y" * 50_000, b'"}']), chunked=True)
    check("oversized CHUNKED login body (no Content-Length) -> 413", s == 413, str(s), real_only=True)
    s, *_ = c.req("POST", "/api/admin/login", headers={**JH, "Content-Length": "abc"}, body=b"{}"); check("malformed Content-Length -> 400/413 (never 5xx)", s in (None, 400, 413), str(s))
    s, h, cookies, j = c.json("POST", "/api/admin/login", headers=JH, body=json.dumps({"password": admin_pw}))
    check("correct password -> 200 {ok: true}, password not echoed", s == 200 and j == {"ok": True} and admin_pw not in json.dumps(j), f"{s} {j}")
    ck = (cookies[0] if cookies else ""); low = ck.lower()
    check("session cookie: HttpOnly", "httponly" in low, ck)
    check("session cookie: SameSite=Strict", "samesite=strict" in low, ck)
    check("session cookie: Secure (default)", "secure" in low.replace("samesite", ""), ck, real_only=True)
    check("session cookie: Path=/ and Max-Age set", "path=/" in low and "max-age=" in low, ck, real_only=True)
    token = ck.split(";")[0] if ck else ""
    s, h, _, stats = c.json("GET", "/api/admin/stats", headers={"Cookie": token})
    check("admin stats with the session -> 200 with dashboard data", s == 200 and {"documents", "domains", "index", "crawler", "search", "recent_errors"} <= set(stats or {}), f"{s}")
    check("admin responses are Cache-Control: no-store", h.get("cache-control") == "no-store", str(h.get("cache-control")), real_only=True)
    check("admin stats expose no filesystem paths or secrets", not any(x in json.dumps(stats) for x in (tempfile.gettempdir(), "scrypt$", "secret")), "")
    s, _, lc, _ = c.json("POST", "/api/admin/logout", headers={"Cookie": token})
    check("logout clears the cookie", s == 200 and any("max-age=0" in x.lower() or "expires=" in x.lower() for x in lc), str(lc), real_only=True)
    s, *_ = c.req("GET", "/api/admin/stats", headers={"Cookie": token})
    print(f"INFO  replaying the pre-logout token is {'still ACCEPTED' if s == 200 else 'rejected'} (sessions are stateless signed cookies; see README limitations)")
    # rate limiting last (per client address; 5 failures / 5 min)
    codes = [c.req("POST", "/api/admin/login", headers=JH, body=json.dumps({"password": f"bad{i}"}))[0] for i in range(5)]
    s, *_ = c.req("POST", "/api/admin/login", headers=JH, body=json.dumps({"password": admin_pw}))
    check("login rate limit: after 5 failures even the correct password -> 429", codes == [401] * 5 and s == 429, f"{codes} then {s}")


def spawn(root, extra_env, port):
    env = {**os.environ, "PYTHONPATH": ROOT, **extra_env}
    p = subprocess.Popen([sys.executable, "-m", "wadiya", "serve", "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(100):
        if p.poll() is not None:
            print("SERVER FAILED TO START:\n" + p.stderr.read()); sys.exit(2)
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); return p
        except OSError: time.sleep(0.2)
    p.kill(); print("server did not open its port"); sys.exit(2)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def seed(tmp):
    from tests.helpers import make_doc
    from wadiya.indexer.fts5 import FTS5Indexer
    from wadiya.pipeline import index_pending
    from wadiya.storage.sqlite_store import SQLiteStorage
    st, ix = SQLiteStorage(f"{tmp}/w.db"), FTS5Indexer(f"{tmp}/i.db"); st.init(); ix.init()
    st.save_document(make_doc(url="https://example.org/wadi", title="Wadi guide", content="A wadi is a dry riverbed that fills with water after heavy rain."))
    for i in range(25):
        st.save_document(make_doc(url=f"https://paginate.example/{i}", title=f"Paginate item {i:02d}", domain="paginate.example", content=f"paginate sample document {i}", chash=f"p{i}"))
    index_pending(st, ix)


def main():
    global REAL
    ap = argparse.ArgumentParser(); ap.add_argument("--spawn", action="store_true"); ap.add_argument("--base-url"); ap.add_argument("--admin-password", default=ADMIN_PW)
    a = ap.parse_args(); procs = []
    try:
        if a.spawn:
            REAL = True; tmp = tempfile.mkdtemp(prefix="wadiya-live-"); seed(tmp)
            from wadiya.admin.auth import hash_password
            env = {"WADIYA_DB_PATH": f"{tmp}/w.db", "WADIYA_INDEX_PATH": f"{tmp}/i.db", "WADIYA_ADMIN_PASSWORD_HASH": hash_password(ADMIN_PW), "WADIYA_SECRET_KEY": "k" * 48}
            port = free_port(); procs.append(spawn(tmp, env, port)); base = f"http://127.0.0.1:{port}"
        else:
            base = a.base_url or sys.exit("give --spawn or --base-url")
        c = Client(base); run_checks(c, a.admin_password)
        if a.spawn:
            # 500 JSON: break the database underneath the running server, then restore it
            db = sqlite3.connect(f"{tmp}/w.db"); db.execute("ALTER TABLE documents RENAME TO documents_x"); db.commit()
            s, _, _, body = c.req("GET", "/api/search?q=wadi")
            db.execute("ALTER TABLE documents_x RENAME TO documents"); db.commit(); db.close()
            try: j = json.loads(body)
            except Exception: j = None
            check("internal failure -> 500 JSON {error:{code:500,message:'internal error'}}", s == 500 and (j or {}).get("error", {}).get("code") == 500, f"{s} {body[:120]}")
            check("500 body leaks no internals (SQL, table names, paths, tracebacks)", not any(x in body.decode("utf-8", "replace") for x in ("sqlite", "documents", "Traceback", "OperationalError", tmp, ".py")), body.decode("utf-8", "replace")[:160])
            s, *_ = c.req("GET", "/api/search?q=wadi"); check("server recovers after the failure", s == 200, str(s))
            # admin not configured -> disabled (no default credentials)
            port2 = free_port(); procs.append(spawn(tmp, {"WADIYA_DB_PATH": f"{tmp}/w.db", "WADIYA_INDEX_PATH": f"{tmp}/i.db", "WADIYA_ADMIN_PASSWORD_HASH": "", "WADIYA_SECRET_KEY": ""}, port2))
            c2 = Client(f"http://127.0.0.1:{port2}")
            s, *_ = c2.req("POST", "/api/admin/login", headers={"Content-Type": "application/json"}, body=json.dumps({"password": ADMIN_PW})); check("admin unconfigured: login -> 503 (no default credentials)", s == 503, str(s))
            s, *_ = c2.req("GET", "/api/admin/stats"); check("admin unconfigured: stats -> 401", s == 401, str(s))
    finally:
        for p in procs: p.terminate()
    n = lambda k: sum(1 for r in RESULTS if r[1] == k)
    print(f"\n{n('PASS')} passed, {n('FAIL')} failed, {n('SKIP')} skipped (of {len(RESULTS)})")
    sys.exit(1 if n("FAIL") else 0)


if __name__ == "__main__":
    main()

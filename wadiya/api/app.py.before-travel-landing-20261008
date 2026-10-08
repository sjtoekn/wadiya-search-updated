"""FastAPI wiring. Thin on purpose: validation/logic live in handlers/service so they are testable
without a web framework. Requires: pip install -r requirements.txt"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..admin.auth import AdminAuth
from ..config.settings import Settings
from ..indexer.fts5 import FTS5Indexer
from ..indexer.books import BooksIndexer
from ..search.books import DBBooksProvider
from ..search.finance import AlphaVantageFinanceProvider
from ..search.crypto import SQLiteCryptoProvider, seed_default_crypto_assets
from ..ranking.bm25 import BM25Ranker
from ..search.service import SearchService
from ..storage.sqlite_store import SQLiteStorage
from . import handlers
from .limits import MAX_LOGIN_BODY, BodyLimiter, BodyTooLarge, SubmitLimiter
from ..crawler.fetcher import Fetcher
from ..crawler.robots import RobotsChecker
from ..crawler.scheduler import ContinuousCrawler
from ..crawler.seeds import load_seeds
from .security import COOKIE_NAME as COOKIE, SECURITY_HEADERS, session_cookie_kwargs
from .user_auth import (
    UserSessionManager,
    build_google_authorization_url,
    create_google_state,
    google_exchange_code,
    google_userinfo,
    verify_google_state,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app(settings=None, storage=None, indexer=None, ranker=None, fetcher=None) -> FastAPI:
    settings = settings or Settings.from_env()
    storage = storage or SQLiteStorage(settings.db_path)
    storage.init()
    indexer = indexer or FTS5Indexer(settings.index_path)
    indexer.init()

    books_index_path = str(
        Path(settings.index_path).with_name("wadiya_books_index.db")
    )
    books_indexer = BooksIndexer(books_index_path)
    books_indexer.init()

    finance_provider = AlphaVantageFinanceProvider(
        settings.alpha_vantage_api_key,
        timeout=settings.request_timeout,
    )

    seed_default_crypto_assets(storage)
    crypto_provider = SQLiteCryptoProvider(storage)

    service = SearchService(
        settings,
        storage,
        indexer,
        ranker or BM25Ranker(),
        books_provider=DBBooksProvider(storage, books_indexer),
        finance_provider=finance_provider,
        crypto_provider=crypto_provider,
    )
    auth = AdminAuth(settings)
    user_sessions = UserSessionManager(settings.secret_key, settings.user_session_max_age) if len(settings.secret_key) >= 32 else None
    submit_limiter = SubmitLimiter()
    preview_limiter = SubmitLimiter(limit=5, window=600)
    user_auth_limiter = SubmitLimiter(limit=10, window=600)
    page_limiter = SubmitLimiter(limit=60, window=60)
    preview_fetcher = fetcher or Fetcher(settings)

    app = FastAPI(title="Wadiya", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.storage, app.state.indexer, app.state.auth = settings, storage, indexer, auth
    app.state.user_sessions = user_sessions

    # Background crawling is OPT-IN (WADIYA_BACKGROUND_CRAWLER=true). Prefer running
    # `python -m wadiya crawl --continuous` as a separate process.
    def _run_continuous_crawler():
        import time
        from ..crawler.lock import CrawlAlreadyRunning

        delay = 30.0
        while True:
            try:
                seeds = load_seeds(settings.seeds_path)
                robots = RobotsChecker(
                    preview_fetcher,
                    settings.robots_token,
                    settings.robots_cache_ttl,
                    settings.max_robots_bytes,
                )
                books_index_path = str(
                    Path(settings.index_path).with_name("wadiya_books_index.db")
                )
                books_indexer = BooksIndexer(books_index_path)

                scheduler = ContinuousCrawler(
                    settings,
                    storage,
                    indexer,
                    preview_fetcher,
                    robots,
                    books_indexer=books_indexer,
                )
                for cycle in scheduler.run(seeds, interval=60):
                    print("background crawl cycle:", cycle.number, flush=True)
                return
            except CrawlAlreadyRunning:
                print("background crawler: another crawler holds the lock; retrying", flush=True)
            except Exception as e:
                print("background crawler error:", type(e).__name__, e, flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 900.0)

    app.state.crawler_thread = None
    if settings.background_crawler:
        crawler_thread = threading.Thread(
            target=_run_continuous_crawler,
            name="wadiya-continuous-crawler",
            daemon=True,
        )
        crawler_thread.start()
        app.state.crawler_thread = crawler_thread

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            resp.headers[k] = v
        if request.url.path.startswith("/api/admin"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def security_response(response):
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        status, body = handlers.error(exc.status_code, str(exc.detail))
        return security_response(JSONResponse(body, status_code=status))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        status, body = handlers.error(500, "internal error")     # never leak internals
        return security_response(JSONResponse(body, status_code=status))

    # ------------------------------------------------------------------ public API
    @app.get("/api/search")
    def search(q: str = "", page: str = "1", type: str = "web"):
        status, body = handlers.handle_search(service, q, page, type)
        return JSONResponse(body, status_code=status)

    @app.get("/api/finance/history")
    def finance_history(
        symbol: str = "",
        range: str = "1M",
    ):
        symbol = symbol.strip()
        range_name = range.strip().upper()

        allowed_ranges = {
            "1D",
            "1W",
            "1M",
            "3M",
            "6M",
            "1Y",
            "5Y",
            "MAX",
        }

        if not symbol:
            return JSONResponse(
                {"error": "symbol is required"},
                status_code=400,
            )

        if range_name not in allowed_ranges:
            return JSONResponse(
                {"error": "invalid range"},
                status_code=400,
            )

        points = finance_provider.history(
            symbol,
            range_name,
        )

        return JSONResponse(
            {
                "symbol": symbol,
                "range": range_name,
                "result_count": len(points),
                "points": points,
            }
        )

    @app.get("/api/discovery")
    def discovery(domain: str = ""):
        status, body = handlers.handle_discovery(storage, domain)
        return JSONResponse(body, status_code=status)

    @app.post("/api/submit/preview")
    async def preview_website(request: Request):
        if not request.headers.get("content-type", "").lower().startswith("application/json"):
            raise HTTPException(status_code=415, detail="expected application/json")

        limiter = BodyLimiter(4096)

        try:
            limiter.declare(request.headers.get("content-length"))
            async for chunk in request.stream():
                limiter.feed(chunk)
        except BodyTooLarge:
            raise HTTPException(status_code=413, detail="request body too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content-length")

        try:
            data = json.loads(limiter.body() or b"null")
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")

        url = data.get("url") if isinstance(data, dict) else None

        client_key = request.client.host if request.client else "unknown"

        if not preview_limiter.allowed(client_key):
            retry_after = preview_limiter.retry_after(client_key)
            response = JSONResponse(
                handlers.error(
                    429,
                    "too many website previews; try again later",
                )[1],
                status_code=429,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

        preview_limiter.hit(client_key)

        status, body = await run_in_threadpool(
            handlers.handle_preview_website,
            settings,
            url,
            fetcher=preview_fetcher,
        )
        return JSONResponse(body, status_code=status)

    @app.post("/api/submit")
    async def submit_website(request: Request):
        if not request.headers.get("content-type", "").lower().startswith("application/json"):
            raise HTTPException(status_code=415, detail="expected application/json")

        limiter = BodyLimiter(4096)

        try:
            limiter.declare(request.headers.get("content-length"))
            async for chunk in request.stream():
                limiter.feed(chunk)
        except BodyTooLarge:
            raise HTTPException(status_code=413, detail="request body too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content-length")

        try:
            data = json.loads(limiter.body() or b"null")
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")

        url = data.get("url") if isinstance(data, dict) else None

        client_key = request.client.host if request.client else "unknown"

        if not submit_limiter.allowed(client_key):
            retry_after = submit_limiter.retry_after(client_key)
            response = JSONResponse(
                handlers.error(
                    429,
                    "too many website submissions; try again later",
                )[1],
                status_code=429,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

        submit_limiter.hit(client_key)

        status, body = await run_in_threadpool(handlers.handle_submit_website, storage, url)
        return JSONResponse(body, status_code=status)

    @app.get("/api/page")
    def page(request: Request, url: str = ""):
        client_key = request.client.host if request.client else "unknown"
        if not page_limiter.allowed(client_key):
            retry_after = page_limiter.retry_after(client_key)
            response = JSONResponse(
                {"error": "too many page requests; try again later"},
                status_code=429,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response
        page_limiter.hit(client_key)
        status, body = handlers.handle_page(storage, url)
        return JSONResponse(body, status_code=status)

    @app.get("/submit-website", include_in_schema=False)
    def submit_website_page():
        return FileResponse(WEB_DIR / "submit-website.html")

    @app.get("/discovery", include_in_schema=False)
    def discovery_page():
        return FileResponse(WEB_DIR / "discovery.html")

    @app.get("/search", include_in_schema=False)
    def search_page():
        return FileResponse(WEB_DIR / "search.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # ------------------------------------------------------------------ public user API
    async def read_user_auth_body(request: Request):
        if not request.headers.get("content-type", "").lower().startswith("application/json"):
            raise HTTPException(status_code=415, detail="expected application/json")
        limiter = BodyLimiter(MAX_LOGIN_BODY)
        try:
            limiter.declare(request.headers.get("content-length"))
            async for chunk in request.stream():
                limiter.feed(chunk)
        except BodyTooLarge:
            raise HTTPException(status_code=413, detail="request body too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content-length")
        try:
            data = json.loads(limiter.body() or b"null")
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="invalid json")
        return data

    def check_user_auth_limit(request: Request, action: str):
        client = request.client.host if request.client else "unknown"
        key = action + ":" + client
        if not user_auth_limiter.allowed(key):
            retry_after = user_auth_limiter.retry_after(key)
            response = JSONResponse(
                {"error": {"message": "too many authentication attempts; try again later"}},
                status_code=429,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response
        user_auth_limiter.hit(key)
        return None

    @app.post("/api/auth/register")
    async def user_register(request: Request):
        limited = check_user_auth_limit(request, "register")
        if limited:
            return limited
        data = await read_user_auth_body(request)
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="invalid json")
        if not user_sessions:
            raise HTTPException(status_code=503, detail="user authentication is not configured")
        status, body, token = await run_in_threadpool(
            handlers.handle_user_register,
            storage, user_sessions, data.get("email"), data.get("password"), data.get("display_name", ""),
        )
        resp = JSONResponse(body, status_code=status)
        if token:
            resp.set_cookie("wadiya_user", token, **session_cookie_kwargs(settings))
        return resp

    @app.post("/api/auth/login")
    async def user_login(request: Request):
        limited = check_user_auth_limit(request, "login")
        if limited:
            return limited
        data = await read_user_auth_body(request)
        if not user_sessions:
            raise HTTPException(status_code=503, detail="user authentication is not configured")
        status, body, token = await run_in_threadpool(
            handlers.handle_user_login,
            storage, user_sessions, data.get("email"), data.get("password"),
        )
        resp = JSONResponse(body, status_code=status)
        if token:
            resp.set_cookie("wadiya_user", token, **session_cookie_kwargs(settings))
        return resp


    @app.get("/api/auth/google/login")
    def google_login():
        if not user_sessions:
            raise HTTPException(status_code=503, detail="user authentication is not configured")
        if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
            raise HTTPException(status_code=503, detail="Google authentication is not configured")
        state = create_google_state(settings.secret_key)
        response = RedirectResponse(
            build_google_authorization_url(
                settings.google_client_id,
                settings.google_redirect_uri,
                state,
            ),
            status_code=302,
        )
        response.set_cookie(
            "wadiya_google_oauth_nonce",
            state,
            max_age=600,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            path="/api/auth/google",
        )
        return response

    @app.get("/api/auth/google/callback")
    def google_callback(
        request: Request,
        code: str = "",
        state: str = "",
        error: str = "",
    ):
        oauth_nonce = request.cookies.get("wadiya_google_oauth_nonce")
        if error:
            resp = RedirectResponse("/login?error=google_denied", status_code=302)
            resp.delete_cookie("wadiya_google_oauth_nonce", path="/api/auth/google")
            return resp
        if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
            raise HTTPException(status_code=503, detail="Google authentication is not configured")
        if (
            not code
            or not oauth_nonce
            or not verify_google_state(settings.secret_key, state)
            or state != oauth_nonce
        ):
            resp = RedirectResponse("/login?error=google_state", status_code=302)
            resp.delete_cookie("wadiya_google_oauth_nonce", path="/api/auth/google")
            return resp

        try:
            tokens = google_exchange_code(
                settings.google_client_id,
                settings.google_client_secret,
                settings.google_redirect_uri,
                code,
            )
            access_token = tokens.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("missing Google access token")

            info = google_userinfo(access_token)
            subject = info.get("sub")
            email = info.get("email")
            if info.get("email_verified") is not True:
                raise ValueError("Google email is not verified")

            status, body, token = handlers.handle_google_user(
                storage,
                user_sessions,
                subject,
                email,
                info.get("name", ""),
            )
            if not token:
                return RedirectResponse("/login?error=google_account", status_code=302)

            resp = RedirectResponse("/profile", status_code=302)
            resp.set_cookie("wadiya_user", token, **session_cookie_kwargs(settings))
            resp.delete_cookie("wadiya_google_oauth_nonce", path="/api/auth/google")
            return resp
        except Exception:
            return RedirectResponse("/login?error=google_failed", status_code=302)

    @app.post("/api/auth/logout")
    def user_logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("wadiya_user", path="/")
        return resp

    def require_user(request: Request):
        if not user_sessions:
            raise HTTPException(status_code=503, detail="user authentication is not configured")
        user_id = user_sessions.verify(request.cookies.get("wadiya_user"))
        if not user_id:
            raise HTTPException(status_code=401, detail="authentication required")
        return user_id

    @app.get("/api/auth/me")
    def user_me(request: Request):
        status, body = handlers.handle_user_profile(storage, require_user(request))
        return JSONResponse(body, status_code=status)

    @app.patch("/api/auth/profile")
    async def user_profile(request: Request):
        user_id = require_user(request)
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")
        status, body = await run_in_threadpool(
            handlers.handle_user_profile_update,
            storage, user_id, data.get("display_name") if isinstance(data, dict) else None,
        )
        return JSONResponse(body, status_code=status)

    # ------------------------------------------------------------------ admin API
    def require_admin(request: Request):
        if not auth.verify_token(request.cookies.get(COOKIE)):
            raise HTTPException(status_code=401, detail="authentication required")

    @app.post("/api/admin/login")
    async def admin_login(request: Request):
        if not request.headers.get("content-type", "").lower().startswith("application/json"):
            raise HTTPException(status_code=415, detail="expected application/json")   # also blocks cross-site form posts
        limiter = BodyLimiter(MAX_LOGIN_BODY)          # never buffer an unbounded body
        try:
            limiter.declare(request.headers.get("content-length"))
            async for chunk in request.stream():
                limiter.feed(chunk)
        except BodyTooLarge:
            raise HTTPException(status_code=413, detail="request body too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content-length")
        try:
            data = json.loads(limiter.body() or b"null")
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")
        password = data.get("password") if isinstance(data, dict) else None
        client = request.client.host if request.client else "unknown"
        status, body, token = await run_in_threadpool(handlers.handle_login, auth, password, client)
        resp = JSONResponse(body, status_code=status)
        if token:
            resp.set_cookie(COOKIE, token, **session_cookie_kwargs(settings))
        return resp

    @app.post("/api/admin/logout")
    def admin_logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
    def admin_stats():
        status, body = handlers.handle_stats(storage, indexer)
        return JSONResponse(body, status_code=status)

    @app.post("/api/admin/discovery/domain", dependencies=[Depends(require_admin)])
    def admin_discovery_domain(payload: dict):
        code, body = handlers.handle_admin_discovery_domain_action(
            storage,
            domain=str(payload.get("domain", "")),
            admission=str(payload.get("admission", "")),
        )
        return JSONResponse(body, status_code=code)

    @app.get("/api/admin/discovery", dependencies=[Depends(require_admin)])
    def admin_discovery(
        status: str = "",
        source: str = "",
        q: str = "",
        page: str = "1",
        limit: str = "50",
    ):
        code, body = handlers.handle_admin_discovery(
            storage,
            status=status or None,
            source=source or None,
            query=q or None,
            page=page,
            limit=limit,
        )
        return JSONResponse(body, status_code=code)

    # ------------------------------------------------------------------ pages
    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/robots.txt", include_in_schema=False)
    def robots_txt():
        return FileResponse(WEB_DIR / "robots.txt", media_type="text/plain")

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap_xml():
        return FileResponse(WEB_DIR / "sitemap.xml", media_type="application/xml")

    @app.get("/login", include_in_schema=False)
    def login_page():
        return FileResponse(WEB_DIR / "login.html")

    @app.get("/register", include_in_schema=False)
    def register_page():
        return FileResponse(WEB_DIR / "register.html")

    @app.get("/profile", include_in_schema=False)
    def profile_page():
        return FileResponse(WEB_DIR / "profile.html")

    @app.get("/admin", include_in_schema=False)
    def admin_page():          # static shell only; every data endpoint above is protected
        return FileResponse(WEB_DIR / "admin.html")

    @app.get("/admin/discovery", include_in_schema=False)
    def admin_discovery_page():
        return FileResponse(WEB_DIR / "admin-discovery.html")

    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
    return app

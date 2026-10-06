"""FastAPI wiring. Thin on purpose: validation/logic live in handlers/service so they are testable
without a web framework. Requires: pip install -r requirements.txt"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..admin.auth import AdminAuth
from ..config.settings import Settings
from ..indexer.fts5 import FTS5Indexer
from ..ranking.bm25 import BM25Ranker
from ..search.service import SearchService
from ..storage.sqlite_store import SQLiteStorage
from . import handlers
from .limits import MAX_LOGIN_BODY, BodyLimiter, BodyTooLarge, SubmitLimiter
from ..crawler.fetcher import Fetcher
from .security import COOKIE_NAME as COOKIE, SECURITY_HEADERS, session_cookie_kwargs

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app(settings=None, storage=None, indexer=None, ranker=None, fetcher=None) -> FastAPI:
    settings = settings or Settings.from_env()
    storage = storage or SQLiteStorage(settings.db_path)
    storage.init()
    indexer = indexer or FTS5Indexer(settings.index_path)
    indexer.init()
    service = SearchService(settings, storage, indexer, ranker or BM25Ranker())
    auth = AdminAuth(settings)
    submit_limiter = SubmitLimiter()
    preview_limiter = SubmitLimiter(limit=5, window=600)
    preview_fetcher = fetcher or Fetcher(settings)

    app = FastAPI(title="Wadiya", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.storage, app.state.indexer, app.state.auth = settings, storage, indexer, auth

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
    def search(q: str = "", page: str = "1"):
        status, body = handlers.handle_search(service, q, page)
        return JSONResponse(body, status_code=status)

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

        status, body = handlers.handle_preview_website(
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

        status, body = handlers.handle_submit_website(storage, url)
        return JSONResponse(body, status_code=status)

    @app.get("/api/page")
    def page(url: str = ""):
        status, body = handlers.handle_page(storage, url)
        return JSONResponse(body, status_code=status)

    @app.get("/discovery", include_in_schema=False)
    def discovery_page():
        return FileResponse(WEB_DIR / "discovery.html")

    @app.get("/search", include_in_schema=False)
    def search_page():
        return FileResponse(WEB_DIR / "search.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

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
        status, body, token = handlers.handle_login(auth, password, client)
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

    @app.get("/admin", include_in_schema=False)
    def admin_page():          # static shell only; every data endpoint above is protected
        return FileResponse(WEB_DIR / "admin.html")

    @app.get("/admin/discovery", include_in_schema=False)
    def admin_discovery_page():
        return FileResponse(WEB_DIR / "admin-discovery.html")

    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
    return app

"""Framework-independent HTTP security constants/helpers. api/app.py applies them; tests check them directly."""
from __future__ import annotations

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}

COOKIE_NAME = "wadiya_admin"


def session_cookie_kwargs(settings) -> dict:
    """Attributes for the admin session cookie (passed to Response.set_cookie)."""
    return {"max_age": settings.session_max_age, "httponly": True, "secure": settings.cookie_secure,
            "samesite": "strict", "path": "/"}

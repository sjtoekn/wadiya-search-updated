import re
import unittest
from pathlib import Path

from wadiya.api.security import COOKIE_NAME, CSP, SECURITY_HEADERS, session_cookie_kwargs
from wadiya.config.settings import Settings

WEB = Path(__file__).resolve().parent.parent / "wadiya" / "web"


class SecurityConstantTests(unittest.TestCase):
    def test_headers_present(self):
        self.assertEqual(set(SECURITY_HEADERS), {"Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"})
        self.assertEqual(SECURITY_HEADERS["X-Frame-Options"], "DENY")
        self.assertEqual(SECURITY_HEADERS["X-Content-Type-Options"], "nosniff")

    def test_csp_is_strict(self):
        for must in ("default-src 'self'", "script-src 'self'", "style-src 'self'", "frame-ancestors 'none'", "base-uri 'none'"):
            self.assertIn(must, CSP)
        self.assertNotIn("unsafe-inline", CSP); self.assertNotIn("unsafe-eval", CSP); self.assertNotIn("*", CSP)

    def test_web_pages_comply_with_csp(self):
        """CSP forbids inline script/style/handlers, so the shipped pages must not use any."""
        for name in ("index.html", "admin.html"):
            html = (WEB / name).read_text()
            self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), f"{name}: inline <script>")
            self.assertIsNone(re.search(r"<style", html, re.I), f"{name}: inline <style>")
            self.assertIsNone(re.search(r"\son[a-z]+\s*=", html, re.I), f"{name}: inline event handler")
            self.assertIsNone(re.search(r"\sstyle\s*=", html, re.I), f"{name}: inline style attribute")
            self.assertIsNone(re.search(r"https?://", re.sub(r'xmlns="[^"]*"', "", html)), f"{name}: external resource")

    def test_cookie_attributes(self):
        kw = session_cookie_kwargs(Settings())
        self.assertEqual((kw["httponly"], kw["secure"], kw["samesite"], kw["path"]), (True, True, "strict", "/"))   # Secure by default
        self.assertEqual(kw["max_age"], 8 * 3600)
        self.assertFalse(session_cookie_kwargs(Settings(cookie_secure=False))["secure"])
        self.assertEqual(COOKIE_NAME, "wadiya_admin")

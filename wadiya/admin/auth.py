"""Admin authentication: scrypt password hash from the environment + signed, expiring session cookie.
Framework-independent so it can be unit-tested without a web server."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

from itsdangerous import BadSignature, URLSafeTimedSerializer

_N, _R, _P = 2 ** 14, 8, 1
MAX_PASSWORD_LEN = 256
MIN_SECRET_LEN = 32


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password, stored: str) -> bool:
    try:
        if not isinstance(password, str) or len(password) > MAX_PASSWORD_LEN:
            return False
        algo, n, r, p, salt, expected = stored.split("$")
        n, r, p = int(n), int(r), int(p)
        if algo != "scrypt" or n > 2 ** 20 or n < 2 ** 10 or r > 16 or p > 4:
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=n, r=r, p=p,
                            dklen=len(base64.b64decode(expected)), maxmem=256 * 1024 * 1024)
        return hmac.compare_digest(dk, base64.b64decode(expected))
    except Exception:
        return False


class SessionManager:
    def __init__(self, secret: str, max_age: int):
        if len(secret) < MIN_SECRET_LEN:
            raise ValueError(f"secret key must be at least {MIN_SECRET_LEN} characters")
        self._s = URLSafeTimedSerializer(secret, salt="wadiya-admin-session")
        self.max_age = max_age

    def issue(self) -> str:
        return self._s.dumps({"role": "admin", "n": secrets.token_hex(8)})

    def verify(self, token) -> bool:
        if not token or not isinstance(token, str) or len(token) > 512:
            return False
        try:
            return self._s.loads(token, max_age=self.max_age).get("role") == "admin"
        except BadSignature:   # includes SignatureExpired
            return False


class LoginLimiter:
    """Max `limit` failed attempts per `window` seconds per client key (in memory, not persisted)."""
    def __init__(self, limit: int = 5, window: int = 300, clock=time.monotonic):
        self.limit, self.window, self._clock, self._fails = limit, window, clock, {}

    def _recent(self, key):
        now = self._clock()
        self._fails[key] = [t for t in self._fails.get(key, []) if now - t < self.window]
        return self._fails[key]

    def allowed(self, key) -> bool:
        return len(self._recent(key)) < self.limit

    def fail(self, key) -> None:
        self._recent(key).append(self._clock())

    def reset(self, key) -> None:
        self._fails.pop(key, None)


class AdminAuth:
    """Admin is DISABLED unless both a password hash and a strong secret are configured."""
    def __init__(self, settings, limiter: LoginLimiter = None):
        self.enabled = bool(settings.admin_password_hash) and len(settings.secret_key) >= MIN_SECRET_LEN
        self._hash = settings.admin_password_hash
        self.sessions = SessionManager(settings.secret_key, settings.session_max_age) if self.enabled else None
        self.limiter = limiter or LoginLimiter()

    def verify_token(self, token) -> bool:
        return self.enabled and self.sessions.verify(token)

    def login(self, password, client_key: str):
        """Returns (status_code, message, token_or_None)."""
        if not self.enabled:
            return 503, "admin is not configured", None
        if not self.limiter.allowed(client_key):
            return 429, "too many failed attempts; try again later", None
        if verify_password(password, self._hash):
            self.limiter.reset(client_key)
            return 200, "ok", self.sessions.issue()
        self.limiter.fail(client_key)
        return 401, "invalid credentials", None

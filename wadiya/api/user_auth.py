"""Public user authentication: scrypt passwords + signed expiring user sessions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import json
import urllib.parse
import urllib.request
from itsdangerous import BadSignature, URLSafeTimedSerializer

N, R, P = 2 ** 14, 8, 1
MAX_PASSWORD_LEN = 256
MIN_PASSWORD_LEN = 12
MIN_SECRET_LEN = 32


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password, stored: str) -> bool:
    try:
        if not isinstance(password, str) or len(password) > MAX_PASSWORD_LEN:
            return False
        algo, n, r, p, salt, expected = stored.split("$")
        n, r, p = int(n), int(r), int(p)
        if algo != "scrypt" or n > 2 ** 20 or n < 2 ** 10 or r > 16 or p > 4:
            return False
        expected_b = base64.b64decode(expected)
        dk = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt),
            n=n, r=r, p=p, dklen=len(expected_b),
            maxmem=256 * 1024 * 1024,
        )
        return hmac.compare_digest(dk, expected_b)
    except Exception:
        return False


class UserSessionManager:
    def __init__(self, secret: str, max_age: int):
        if len(secret) < MIN_SECRET_LEN:
            raise ValueError("secret key too short")
        self._s = URLSafeTimedSerializer(secret, salt="wadiya-user-session")
        self.max_age = max_age

    def issue(self, user_id: int) -> str:
        return self._s.dumps({"role": "user", "uid": int(user_id), "n": secrets.token_hex(8)})

    def verify(self, token):
        if not token or not isinstance(token, str) or len(token) > 512:
            return None
        try:
            data = self._s.loads(token, max_age=self.max_age)
            return int(data["uid"]) if data.get("role") == "user" else None
        except (BadSignature, KeyError, TypeError, ValueError):
            return None


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_STATE_MAX_AGE = 600


def google_state_serializer(secret: str) -> URLSafeTimedSerializer:
    if len(secret) < MIN_SECRET_LEN:
        raise ValueError("secret key too short")
    return URLSafeTimedSerializer(secret, salt="wadiya-google-oauth-state")


def create_google_state(secret: str) -> str:
    return google_state_serializer(secret).dumps({
        "nonce": secrets.token_urlsafe(32),
    })


def verify_google_state(secret: str, state: str) -> bool:
    if not isinstance(state, str) or len(state) > 1024:
        return False
    try:
        data = google_state_serializer(secret).loads(state, max_age=GOOGLE_STATE_MAX_AGE)
        return isinstance(data.get("nonce"), str) and len(data["nonce"]) >= 32
    except (BadSignature, TypeError, ValueError):
        return False


def build_google_authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    })
    return f"{GOOGLE_AUTH_URL}?{params}"


def google_exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }).encode()
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read(64 * 1024))


def google_userinfo(access_token: str) -> dict:
    req = urllib.request.Request(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read(64 * 1024))

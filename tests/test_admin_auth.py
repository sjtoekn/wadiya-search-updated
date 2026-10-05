import time
import unittest

from wadiya.admin.auth import AdminAuth, LoginLimiter, SessionManager, hash_password, verify_password
from wadiya.config.settings import Settings

SECRET = "s" * 48


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        h = hash_password("correct horse battery")
        self.assertTrue(h.startswith("scrypt$"))
        self.assertTrue(verify_password("correct horse battery", h))
        self.assertFalse(verify_password("wrong", h))
        self.assertNotEqual(h, hash_password("correct horse battery"))     # random salt
        self.assertNotIn("correct horse", h)

    def test_malformed_hashes_never_verify(self):
        for bad in ["", "plaintext", "scrypt$1$2$3", "md5$a$b$c$d$e", "scrypt$99999999$8$1$AAAA$AAAA", None]:
            self.assertFalse(verify_password("x", bad if bad is not None else ""), bad)
        h = hash_password("pw-pw-pw-pw-pw")
        self.assertFalse(verify_password("x" * 10_000, h))                  # over-long input rejected before hashing
        self.assertFalse(verify_password(None, h))


class SessionTests(unittest.TestCase):
    def test_roundtrip_tamper_expiry(self):
        sm = SessionManager(SECRET, 3600)
        tok = sm.issue()
        self.assertTrue(sm.verify(tok))
        self.assertFalse(sm.verify(tok[:-2] + ("AA" if not tok.endswith("AA") else "BB")))
        self.assertFalse(sm.verify(None)); self.assertFalse(sm.verify("")); self.assertFalse(sm.verify("x" * 1000))
        self.assertFalse(SessionManager("t" * 48, 3600).verify(tok))        # different key
        expiring = SessionManager(SECRET, 1)
        t = expiring.issue()
        self.assertTrue(expiring.verify(t))
        time.sleep(2.1)
        self.assertFalse(expiring.verify(t))                                # expired after max_age

    def test_weak_secret_refused(self):
        with self.assertRaises(ValueError):
            SessionManager("short", 10)


class AdminAuthTests(unittest.TestCase):
    def auth(self, **kw):
        return AdminAuth(Settings(admin_password_hash=hash_password("open sesame 123"), secret_key=SECRET, **kw))

    def test_login_flow(self):
        a = self.auth()
        s, _, tok = a.login("open sesame 123", "1.2.3.4")
        self.assertEqual(s, 200); self.assertTrue(a.verify_token(tok))
        self.assertEqual(a.login("nope", "1.2.3.4")[0], 401)

    def test_disabled_without_config(self):
        for st in (Settings(), Settings(admin_password_hash=hash_password("x" * 12)), Settings(secret_key=SECRET),
                   Settings(admin_password_hash=hash_password("x" * 12), secret_key="short")):
            a = AdminAuth(st)
            self.assertFalse(a.enabled)
            self.assertEqual(a.login("anything", "k")[0], 503)
            self.assertFalse(a.verify_token("anything"))

    def test_rate_limit(self):
        a = self.auth()
        for _ in range(5):
            self.assertEqual(a.login("bad", "ip")[0], 401)
        self.assertEqual(a.login("open sesame 123", "ip")[0], 429)          # even the right password is refused while locked
        self.assertEqual(a.login("open sesame 123", "other-ip")[0], 200)    # per-client

    def test_limiter_window(self):
        now = [0]
        lim = LoginLimiter(limit=2, window=10, clock=lambda: now[0])
        lim.fail("k"); lim.fail("k"); self.assertFalse(lim.allowed("k"))
        now[0] = 11; self.assertTrue(lim.allowed("k"))


if __name__ == "__main__":
    unittest.main()

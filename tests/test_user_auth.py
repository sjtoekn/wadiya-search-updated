import tempfile
import unittest
from pathlib import Path

from wadiya.api.user_auth import hash_password, verify_password, UserSessionManager
from wadiya.storage.sqlite_store import SQLiteStorage


class UserAuthTests(unittest.TestCase):
    def test_password_hash_and_verify(self):
        h = hash_password("correct horse battery staple")
        self.assertNotEqual(h, "correct horse battery staple")
        self.assertTrue(verify_password("correct horse battery staple", h))
        self.assertFalse(verify_password("wrong password", h))

    def test_session(self):
        s = UserSessionManager("k" * 48, 3600)
        token = s.issue(7)
        self.assertEqual(s.verify(token), 7)
        self.assertIsNone(s.verify("bad"))

    def test_user_storage(self):
        with tempfile.TemporaryDirectory() as d:
            st = SQLiteStorage(str(Path(d) / "w.db"))
            st.init()
            u = st.create_user("Test@Example.com", hash_password("password123456"), "Test User")
            self.assertEqual(u.email, "test@example.com")
            self.assertEqual(st.get_user_by_email("TEST@example.com").id, u.id)
            self.assertEqual(st.get_user(u.id).display_name, "Test User")
            self.assertEqual(st.update_user_profile(u.id, "Updated").display_name, "Updated")


if __name__ == "__main__":
    unittest.main()


class UserApiTests(unittest.TestCase):
    def test_public_user_auth_api(self):
        from fastapi.testclient import TestClient
        from dataclasses import replace
        from wadiya.config.settings import Settings
        from wadiya.api.app import create_app

        with tempfile.TemporaryDirectory() as d:
            st = Settings(
                db_path=str(Path(d) / "w.db"),
                index_path=str(Path(d) / "i.db"),
                secret_key="k" * 48,
                cookie_secure=False,
            )
            app = create_app(settings=st)
            c = TestClient(app)

            r = c.post("/api/auth/register", json={
                "email": "user@example.com",
                "password": "password123456",
                "display_name": "Test User",
            })
            self.assertEqual(r.status_code, 201)
            self.assertIn("wadiya_user", r.cookies)
            self.assertEqual(r.json()["user"]["email"], "user@example.com")

            r = c.get("/api/auth/me")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["user"]["display_name"], "Test User")

            r = c.patch("/api/auth/profile", json={"display_name": "Updated User"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["user"]["display_name"], "Updated User")

            r = c.post("/api/auth/logout")
            self.assertEqual(r.status_code, 200)

            r = c.get("/api/auth/me")
            self.assertEqual(r.status_code, 401)

            r = c.post("/api/auth/login", json={
                "email": "user@example.com",
                "password": "password123456",
            })
            self.assertEqual(r.status_code, 200)
            self.assertIn("wadiya_user", r.cookies)

            r = c.post("/api/auth/login", json={
                "email": "user@example.com",
                "password": "wrong-password",
            })
            self.assertEqual(r.status_code, 401)

            r = c.post("/api/auth/register", json={
                "email": "USER@example.com",
                "password": "password123456",
            })
            self.assertEqual(r.status_code, 409)

if __name__ == "__main__":
    unittest.main()

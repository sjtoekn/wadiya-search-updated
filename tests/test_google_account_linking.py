import unittest

from tests.helpers import TempDirCase
from wadiya.api import handlers
from wadiya.api.user_auth import UserSessionManager, hash_password, verify_password

SECRET = "x" * 40


class GoogleAccountLinkingTests(TempDirCase):
    def setUp(self):
        super().setUp()
        self.sessions = UserSessionManager(SECRET, 3600)

    def test_google_login_neutralises_password_set_by_unverified_registrant(self):
        # An attacker registers the victim's email with a password of their own.
        status, _, _ = handlers.handle_user_register(
            self.storage, self.sessions, "victim@example.com", "attacker-password-123", "x")
        self.assertEqual(status, 201)

        # The real owner signs in with Google (verified email).
        status, body, token = handlers.handle_google_user(
            self.storage, self.sessions, "google-sub-1", "victim@example.com", "Victim")
        self.assertEqual(status, 200)
        self.assertTrue(token)

        # The attacker's password must no longer work.
        status, _, token = handlers.handle_user_login(
            self.storage, self.sessions, "victim@example.com", "attacker-password-123")
        self.assertEqual(status, 401)
        self.assertIsNone(token)

        user = self.storage.get_user_by_email("victim@example.com")
        self.assertEqual(user.google_subject, "google-sub-1")
        self.assertFalse(verify_password("attacker-password-123", user.password_hash))

    def test_account_linked_to_other_google_identity_is_not_relinked(self):
        handlers.handle_google_user(self.storage, self.sessions, "sub-A", "a@example.com", "A")
        status, _, token = handlers.handle_google_user(
            self.storage, self.sessions, "sub-B", "a@example.com", "A")
        self.assertEqual(status, 403)
        self.assertIsNone(token)
        self.assertEqual(self.storage.get_user_by_email("a@example.com").google_subject, "sub-A")

    def test_new_google_user_is_created_and_repeat_login_reuses_it(self):
        s1, b1, t1 = handlers.handle_google_user(
            self.storage, self.sessions, "sub-N", "new@example.com", "New")
        s2, b2, t2 = handlers.handle_google_user(
            self.storage, self.sessions, "sub-N", "new@example.com", "New")
        self.assertEqual((s1, s2), (200, 200))
        self.assertEqual(b1["user"]["id"], b2["user"]["id"])

    def test_link_google_subject_without_reset_keeps_password(self):
        user = self.storage.create_user("k@example.com", hash_password("keep-this-password"), "K")
        linked = self.storage.link_google_subject(user.id, "sub-K")
        self.assertTrue(verify_password("keep-this-password", linked.password_hash))


if __name__ == "__main__":
    unittest.main()

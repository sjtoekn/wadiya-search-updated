import unittest

from wadiya.api import handlers


class FakeStorage:
    def get_user_by_email(self, email):
        return None


class LoginHandlerTests(unittest.TestCase):
    def test_invalid_input_returns_three_values(self):
        result = handlers.handle_user_login(FakeStorage(), None, 123, "x")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], 400)
        self.assertIsNone(result[2])

    def test_unknown_user_returns_401(self):
        result = handlers.handle_user_login(FakeStorage(), None, "a@b.c", "x")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], 401)
        self.assertIsNone(result[2])


if __name__ == "__main__":
    unittest.main()

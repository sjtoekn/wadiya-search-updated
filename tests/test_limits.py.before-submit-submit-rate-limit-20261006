import unittest

from wadiya.api.limits import MAX_LOGIN_BODY, BodyLimiter, BodyTooLarge, parse_declared_length


class BodyLimitTests(unittest.TestCase):
    def test_declared_length_parsing(self):
        self.assertIsNone(parse_declared_length(None))
        self.assertEqual(parse_declared_length(" 42 "), 42)
        for bad in ["", "abc", "-1", "1.5", "1e3", "１２", "9" * 20, "0x10"]:
            with self.assertRaises(ValueError, msg=bad):
                parse_declared_length(bad)

    def test_oversized_declared_length_rejected_before_reading(self):
        lim = BodyLimiter(MAX_LOGIN_BODY)
        lim.declare(str(MAX_LOGIN_BODY))                                 # exactly at the limit is fine
        with self.assertRaises(BodyTooLarge):
            BodyLimiter(MAX_LOGIN_BODY).declare(str(MAX_LOGIN_BODY + 1))
        with self.assertRaises(BodyTooLarge):
            BodyLimiter(MAX_LOGIN_BODY).declare("999999999999")

    def test_streamed_bytes_are_counted_even_if_header_lies_or_is_absent(self):
        lim = BodyLimiter(100)
        lim.declare("10")                                               # lies: claims 10
        lim.feed(b"x" * 60)
        with self.assertRaises(BodyTooLarge):
            lim.feed(b"x" * 41)                                          # 101 total
        chunked = BodyLimiter(100)                                      # no Content-Length at all (chunked upload)
        chunked.declare(None)
        with self.assertRaises(BodyTooLarge):
            for _ in range(1000):
                chunked.feed(b"y" * 10)
        self.assertLessEqual(chunked.total, 110)                         # stopped early, did not buffer the flood

    def test_normal_body_roundtrip(self):
        lim = BodyLimiter(MAX_LOGIN_BODY)
        for part in (b'{"pass', b'word": "x"}'):
            lim.feed(part)
        self.assertEqual(lim.body(), b'{"password": "x"}')

    def test_limit_is_small_but_fits_the_maximum_password(self):
        from wadiya.admin.auth import MAX_PASSWORD_LEN
        import json
        self.assertGreater(MAX_LOGIN_BODY, len(json.dumps({"password": "p" * MAX_PASSWORD_LEN}).encode()))
        self.assertLessEqual(MAX_LOGIN_BODY, 16 * 1024)


if __name__ == "__main__":
    unittest.main()

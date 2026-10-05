import unittest

from wadiya.crawler.robots import RobotsChecker, parse_robots
from wadiya.crawler.fetcher import FetchResult

TXT = """
User-agent: *
Disallow: /private/
Disallow: /*.json$
Disallow: /*?session=
Allow: /private/public/
Crawl-delay: 2

User-agent: WadiyaBot
Disallow: /secret
Allow: /secret/open
Crawl-delay: 5

User-agent: OtherBot
Disallow: /
"""


class ParseTests(unittest.TestCase):
    def test_specific_group_beats_wildcard(self):
        r = parse_robots(TXT, "WadiyaBot")
        self.assertFalse(r.allowed("/secret"))
        self.assertFalse(r.allowed("/secret/x"))
        self.assertTrue(r.allowed("/secret/open/page"))   # longest match wins
        self.assertTrue(r.allowed("/private/x"))           # '*' group ignored for a named group
        self.assertEqual(r.delay, 5)

    def test_wildcard_group_rules(self):
        r = parse_robots(TXT, "SomeoneElse")
        self.assertFalse(r.allowed("/private/a"))
        self.assertTrue(r.allowed("/private/public/a"))
        self.assertFalse(r.allowed("/data/x.json"))
        self.assertTrue(r.allowed("/data/x.json.html"))   # '$' anchor
        self.assertFalse(r.allowed("/p?session=1"))
        self.assertTrue(r.allowed("/index.html"))
        self.assertEqual(r.delay, 2)

    def test_disallow_all_and_empty(self):
        self.assertFalse(parse_robots("User-agent: *\nDisallow: /", "x").allowed("/anything"))
        self.assertTrue(parse_robots("User-agent: *\nDisallow:", "x").allowed("/anything"))
        self.assertTrue(parse_robots("", "x").allowed("/a"))
        self.assertTrue(parse_robots("garbage <html> no colons", "x").allowed("/a"))

    def test_allow_wins_ties_and_comments_case(self):
        r = parse_robots("USER-AGENT: *  # c\nDISALLOW: /a # trailing\nALLOW: /a\n", "x")
        self.assertTrue(r.allowed("/a"))

    def test_redos_guard(self):
        r = parse_robots("User-agent: *\nDisallow: " + "/*a" * 50, "x")
        self.assertTrue(r.allowed("/" + "a" * 5000))   # over-wildcarded rule is ignored, not catastrophic


class FakeFetcher:
    def __init__(self, status=200, body=b"", error=None):
        self.status, self.body, self.error, self.calls = status, body, error, 0

    def fetch(self, url, **kw):
        self.calls += 1
        return FetchResult(url, url, None if self.error else self.status, "text/plain", self.body, error=self.error)


class CheckerTests(unittest.TestCase):
    def checker(self, **kw):
        self.f = FakeFetcher(**kw)
        self.now = 0
        return RobotsChecker(self.f, "WadiyaBot", ttl=100, clock=lambda: self.now)

    def test_allow_deny_and_cache(self):
        c = self.checker(body=b"User-agent: *\nDisallow: /nope\nCrawl-delay: 3")
        self.assertFalse(c.is_allowed("https://e.org/nope/x"))
        self.assertTrue(c.is_allowed("https://e.org/ok?q=1"))
        self.assertEqual(c.crawl_delay("https://e.org/ok"), 3)
        self.assertEqual(self.f.calls, 1)
        self.now = 101
        c.is_allowed("https://e.org/ok")
        self.assertEqual(self.f.calls, 2)   # TTL expiry refetches

    def test_invalid_crawl_delay_values_are_ignored(self):
        for value in ("-1", "not-a-number", "nan"):
            rules = parse_robots(
                f"User-agent: *\nCrawl-delay: {value}\n",
                "WadiyaBot",
            )
            self.assertIsNone(rules.delay, value)

        rules = parse_robots(
            "User-agent: *\nCrawl-delay: 999999\n",
            "WadiyaBot",
        )
        self.assertEqual(rules.delay, 999999.0)

    def test_missing_robots_allows(self):
        self.assertTrue(self.checker(status=404).is_allowed("https://e.org/x"))

    def test_unreachable_robots_blocks_everything(self):
        for kw in ({"status": 500}, {"status": 403}, {"status": 429}, {"error": "timeout"}, {"error": "unsafe_url: x"}):
            self.assertFalse(self.checker(**kw).is_allowed("https://e.org/x"), kw)


if __name__ == "__main__":
    unittest.main()


class PercentEncodingRegressionTests(unittest.TestCase):
    """Regression: normalize_url decodes %7E -> '~'; robots matching must stay equivalent (RFC 9309 s2.2.2)."""

    def allowed(self, rules, url, token="WadiyaBot"):
        from urllib.parse import urlsplit
        from wadiya.crawler.urls import normalize_url
        n = normalize_url(url)
        parts = urlsplit(n)
        return parse_robots("User-agent: *\n" + rules, token).allowed(parts.path + (f"?{parts.query}" if parts.query else ""))

    def test_the_reported_bug_percent_7e_rule_vs_normalised_url(self):
        self.assertEqual(__import__("wadiya.crawler.urls", fromlist=["x"]).normalize_url("https://e.org/%7Euser/page"), "https://e.org/~user/page")
        self.assertFalse(self.allowed("Disallow: /%7Euser/", "https://e.org/%7Euser/page"))
        self.assertFalse(self.allowed("Disallow: /%7Euser/", "https://e.org/~user/page"))

    def test_literal_rule_vs_encoded_url_and_lowercase_hex(self):
        self.assertFalse(self.allowed("Disallow: /~user/", "https://e.org/%7Euser/page"))
        self.assertFalse(self.allowed("Disallow: /%7euser/", "https://e.org/~user/page"))     # lower-case hex in the rule
        self.assertFalse(self.allowed("Disallow: /a%62c/", "https://e.org/abc/x"))            # %62 = 'b' (unreserved)

    def test_reserved_encodings_stay_distinct(self):
        self.assertTrue(self.allowed("Disallow: /a/b", "https://e.org/a%2Fb"))               # %2F is NOT '/'
        self.assertFalse(self.allowed("Disallow: /a%2Fb", "https://e.org/a%2Fb"))
        self.assertFalse(self.allowed("Disallow: /a%2fb", "https://e.org/a%2Fb"))            # only hex case differs
        self.assertTrue(self.allowed("Disallow: /a%2Fb", "https://e.org/a/b"))

    def test_non_ascii_rule_and_url(self):
        self.assertFalse(self.allowed("Disallow: /caf\u00e9/", "https://e.org/caf%C3%A9/menu"))
        self.assertFalse(self.allowed("Disallow: /caf%C3%A9/", "https://e.org/caf\u00e9/menu"))

    def test_wildcards_and_anchors_with_encoding(self):
        self.assertFalse(self.allowed("Disallow: /*%7Efoo$", "https://e.org/x/~foo"))
        self.assertTrue(self.allowed("Disallow: /*%7Efoo$", "https://e.org/x/~foo/more"))
        self.assertFalse(self.allowed("Disallow: /*?s=%7E", "https://e.org/p?s=~"))

    def test_longest_match_uses_canonical_length(self):
        rules = "Disallow: /~user/\nAllow: /%7Euser/public/"
        self.assertTrue(self.allowed(rules, "https://e.org/~user/public/x"))
        self.assertFalse(self.allowed(rules, "https://e.org/~user/private/x"))

    def test_checker_level(self):
        f = FakeFetcher(body=b"User-agent: *\nDisallow: /%7Euser/\n")
        c = RobotsChecker(f, "WadiyaBot")
        self.assertFalse(c.is_allowed("https://e.org/%7Euser/x"))
        self.assertFalse(c.is_allowed("https://e.org/~user/x"))
        self.assertTrue(c.is_allowed("https://e.org/other"))


class XRobotsTagParserTests(unittest.TestCase):
    def test_parser(self):
        from wadiya.crawler.robots import parse_x_robots_tag as p
        T = "WadiyaBot"
        cases = [
            (["noindex"], (True, False)), (["NOINDEX, NOFOLLOW"], (True, True)), (["none"], (True, True)),
            (["nofollow"], (False, True)), (["noarchive, nosnippet"], (False, False)), ([], (False, False)), ([""], (False, False)),
            (["wadiyabot: noindex"], (True, False)), (["WadiyaBot: noindex, nofollow"], (True, True)),
            (["otherbot: noindex"], (False, False)), (["googlebot: none"], (False, False)),
            (["unavailable_after: 25 Jun 2030 15:00:00 PST"], (False, False)),
            (["otherbot: noindex", "wadiyabot: nofollow"], (False, True)),              # separate header instances, scoped separately
            (["noindex", "otherbot: nofollow"], (True, False)),
            (["max-snippet: 20, noindex"], (True, False)),
        ]
        for values, expected in cases:
            self.assertEqual(p(values, T), expected, values)

    def test_block_reason_distinguishes_rules_from_unavailable(self):
        c = RobotsChecker(FakeFetcher(body=b"User-agent: *\nDisallow: /no\n"), "WadiyaBot")
        self.assertEqual((c.block_reason("https://e.org/no/x"), c.block_reason("https://e.org/ok")), ("rules", None))
        self.assertEqual(RobotsChecker(FakeFetcher(status=503), "WadiyaBot").block_reason("https://e.org/ok"), "unavailable")
        self.assertEqual(RobotsChecker(FakeFetcher(error="timeout"), "WadiyaBot").block_reason("https://e.org/ok"), "unavailable")


class SitemapDirectiveTests(unittest.TestCase):
    def test_sitemap_directive_is_collected(self):
        text = """
        Sitemap: https://example.org/sitemap.xml

        User-agent: *
        Disallow: /private/
        """
        rules = parse_robots(text, "WadiyaBot")

        self.assertEqual(
            rules.sitemaps,
            ("https://example.org/sitemap.xml",),
        )
        self.assertFalse(rules.allowed("/private/page"))
        self.assertTrue(rules.allowed("/public/page"))

    def test_multiple_sitemap_directives_are_preserved_and_deduplicated(self):
        text = """
        Sitemap: https://example.org/sitemap-a.xml
        Sitemap: https://example.org/sitemap-b.xml
        Sitemap: https://example.org/sitemap-a.xml

        User-agent: *
        Crawl-delay: 2
        """
        rules = parse_robots(text, "WadiyaBot")

        self.assertEqual(
            rules.sitemaps,
            (
                "https://example.org/sitemap-a.xml",
                "https://example.org/sitemap-b.xml",
            ),
        )
        self.assertEqual(rules.delay, 2.0)

    def test_sitemap_directive_is_not_tied_to_user_agent_group(self):
        text = """
        User-agent: OtherBot
        Disallow: /other/

        Sitemap: https://example.org/sitemap.xml

        User-agent: WadiyaBot
        Disallow: /private/
        """
        rules = parse_robots(text, "WadiyaBot")

        self.assertEqual(
            rules.sitemaps,
            ("https://example.org/sitemap.xml",),
        )
        self.assertFalse(rules.allowed("/private/page"))
        self.assertTrue(rules.allowed("/other/page"))


class SitemapCheckerTests(unittest.TestCase):
    def test_checker_exposes_sitemap_urls_from_robots(self):
        fetcher = FakeFetcher(
            body=b"""
            User-agent: *
            Disallow: /private/

            Sitemap: https://example.org/sitemap.xml
            Sitemap: https://example.org/news.xml
            """
        )
        checker = RobotsChecker(fetcher, "WadiyaBot")

        self.assertEqual(
            checker.sitemap_urls("https://example.org/page"),
            (
                "https://example.org/sitemap.xml",
                "https://example.org/news.xml",
            ),
        )

        # The existing robots behavior must still work.
        self.assertFalse(checker.is_allowed("https://example.org/private/page"))
        self.assertTrue(checker.is_allowed("https://example.org/public/page"))

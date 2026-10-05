import unittest

from wadiya.crawler.feed import (
    MAX_FEED_LOCS,
    MAX_FEED_XML_BYTES,
    parse_feed,
)


class FeedParserTests(unittest.TestCase):
    def test_rss_links(self):
        xml = b"""
        <rss version="2.0">
          <channel>
            <title>Example Feed</title>
            <item>
              <title>One</title>
              <link>https://example.org/one</link>
            </item>
            <item>
              <title>Two</title>
              <link>https://example.org/two#section</link>
            </item>
          </channel>
        </rss>
        """
        result = parse_feed(xml, "https://example.org/feed.xml")
        self.assertEqual(result.kind, "rss")
        self.assertEqual(
            result.urls,
            (
                "https://example.org/one",
                "https://example.org/two",
            ),
        )

    def test_atom_links(self):
        xml = b"""
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Example Feed</title>
          <entry>
            <title>One</title>
            <link href="https://example.org/one" />
          </entry>
          <entry>
            <title>Two</title>
            <link href="/two" />
          </entry>
        </feed>
        """
        result = parse_feed(xml, "https://example.org/feed.xml")
        self.assertEqual(result.kind, "atom")
        self.assertEqual(
            result.urls,
            (
                "https://example.org/one",
                "https://example.org/two",
            ),
        )

    def test_atom_prefers_alternate_link(self):
        xml = b"""
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <link rel="self" href="https://example.org/feed.xml" />
            <link rel="alternate" href="https://example.org/page" />
          </entry>
        </feed>
        """
        result = parse_feed(xml, "https://example.org/feed.xml")
        self.assertEqual(result.urls, ("https://example.org/page",))

    def test_xml_namespace(self):
        xml = b"""
        <rss xmlns:content="http://purl.org/rss/1.0/modules/content/">
          <channel>
            <item>
              <link>https://example.org/page</link>
            </item>
          </channel>
        </rss>
        """
        result = parse_feed(xml, "https://example.org/feed.xml")
        self.assertEqual(result.kind, "rss")
        self.assertEqual(result.urls, ("https://example.org/page",))

    def test_duplicate_urls_are_removed(self):
        xml = b"""
        <rss>
          <channel>
            <item><link>https://example.org/page</link></item>
            <item><link>https://example.org/page#top</link></item>
            <item><link>https://example.org/page</link></item>
          </channel>
        </rss>
        """
        result = parse_feed(xml, "https://example.org/feed.xml")
        self.assertEqual(result.urls, ("https://example.org/page",))

    def test_unsafe_urls_are_ignored(self):
        xml = b"""
        <rss>
          <channel>
            <item><link>javascript:alert(1)</link></item>
            <item><link>mailto:test@example.org</link></item>
            <item><link>https://example.org/safe</link></item>
          </channel>
        </rss>
        """
        result = parse_feed(xml, "https://example.org/feed.xml")
        self.assertEqual(result.urls, ("https://example.org/safe",))

    def test_malformed_xml_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "malformed_feed"):
            parse_feed(
                b"<rss><channel><item><link>https://example.org/page</link>",
                "https://example.org/feed.xml",
            )

    def test_doctype_is_rejected(self):
        xml = b"""<?xml version="1.0"?>
        <!DOCTYPE rss [
          <!ENTITY xxe "SHOULD_NOT_EXPAND">
        ]>
        <rss>
          <channel>
            <item><link>https://example.org/&xxe;</link></item>
          </channel>
        </rss>
        """
        with self.assertRaisesRegex(ValueError, "malformed_feed"):
            parse_feed(xml, "https://example.org/feed.xml")

    def test_unsupported_root_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported_feed_root"):
            parse_feed(
                b"<urlset><url><loc>https://example.org/page</loc></url></urlset>",
                "https://example.org/feed.xml",
            )

    def test_url_limit_is_bounded(self):
        items = "".join(
            f"<item><link>https://example.org/{i}</link></item>"
            for i in range(MAX_FEED_LOCS + 25)
        )
        xml = f"<rss><channel>{items}</channel></rss>".encode()

        result = parse_feed(xml, "https://example.org/feed.xml")
        self.assertEqual(len(result.urls), MAX_FEED_LOCS)

    def test_xml_size_limit_is_bounded(self):
        oversized = b"<rss><channel>" + b"x" * MAX_FEED_XML_BYTES + b"</channel></rss>"
        with self.assertRaisesRegex(ValueError, "feed_too_large"):
            parse_feed(oversized, "https://example.org/feed.xml")


if __name__ == "__main__":
    unittest.main()

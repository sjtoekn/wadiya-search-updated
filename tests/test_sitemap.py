
import unittest

from wadiya.crawler.sitemap import (
    MAX_SITEMAP_LOCS,
    MAX_SITEMAP_XML_BYTES,
    parse_sitemap,
)


class SitemapParserTests(unittest.TestCase):
    def test_simple_urlset(self):
        xml = b"""
        <urlset>
          <url><loc>https://example.org/one</loc></url>
          <url><loc>https://example.org/two#section</loc></url>
        </urlset>
        """
        result = parse_sitemap(xml, "https://example.org/sitemap.xml")
        self.assertEqual(result.kind, "urlset")
        self.assertEqual(
            result.urls,
            (
                "https://example.org/one",
                "https://example.org/two",
            ),
        )

    def test_xml_namespace(self):
        xml = b"""
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.org/page</loc></url>
        </urlset>
        """
        result = parse_sitemap(xml, "https://example.org/sitemap.xml")
        self.assertEqual(result.kind, "urlset")
        self.assertEqual(result.urls, ("https://example.org/page",))

    def test_sitemap_index(self):
        xml = b"""
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://example.org/sitemap-1.xml</loc></sitemap>
          <sitemap><loc>https://example.org/sitemap-2.xml</loc></sitemap>
        </sitemapindex>
        """
        result = parse_sitemap(xml, "https://example.org/sitemap.xml")
        self.assertEqual(result.kind, "sitemapindex")
        self.assertEqual(
            result.urls,
            (
                "https://example.org/sitemap-1.xml",
                "https://example.org/sitemap-2.xml",
            ),
        )

    def test_relative_loc_is_normalized(self):
        xml = b"""
        <urlset>
          <url><loc>/docs/page</loc></url>
        </urlset>
        """
        result = parse_sitemap(xml, "https://example.org/sitemap.xml")
        self.assertEqual(result.urls, ("https://example.org/docs/page",))

    def test_duplicate_locs_are_removed(self):
        xml = b"""
        <urlset>
          <url><loc>https://example.org/page</loc></url>
          <url><loc>https://example.org/page#top</loc></url>
          <url><loc>https://example.org/page</loc></url>
        </urlset>
        """
        result = parse_sitemap(xml, "https://example.org/sitemap.xml")
        self.assertEqual(result.urls, ("https://example.org/page",))

    def test_malformed_xml_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "malformed_sitemap"):
            parse_sitemap(
                b"<urlset><url><loc>https://example.org/page</loc></url>",
                "https://example.org/sitemap.xml",
            )

    def test_doctype_is_rejected(self):
        xml = b"""<?xml version="1.0"?>
        <!DOCTYPE urlset [
          <!ENTITY xxe "SHOULD_NOT_EXPAND">
        ]>
        <urlset>
          <url><loc>https://example.org/&xxe;</loc></url>
        </urlset>
        """
        with self.assertRaisesRegex(ValueError, "malformed_sitemap"):
            parse_sitemap(xml, "https://example.org/sitemap.xml")

    def test_external_entity_is_rejected(self):
        xml = b"""<?xml version="1.0"?>
        <!DOCTYPE urlset [
          <!ENTITY xxe SYSTEM "file:///etc/passwd">
        ]>
        <urlset>
          <url><loc>https://example.org/&xxe;</loc></url>
        </urlset>
        """
        with self.assertRaisesRegex(ValueError, "malformed_sitemap"):
            parse_sitemap(xml, "https://example.org/sitemap.xml")

    def test_unsupported_root_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported_sitemap_root"):
            parse_sitemap(
                b"<rss><channel /></rss>",
                "https://example.org/sitemap.xml",
            )

    def test_unsafe_or_invalid_loc_is_ignored(self):
        xml = b"""
        <urlset>
          <url><loc>javascript:alert(1)</loc></url>
          <url><loc>mailto:test@example.org</loc></url>
          <url><loc>https://example.org/safe</loc></url>
        </urlset>
        """
        result = parse_sitemap(xml, "https://example.org/sitemap.xml")
        self.assertEqual(result.urls, ("https://example.org/safe",))

    def test_loc_limit_is_bounded(self):
        items = "".join(
            f"<url><loc>https://example.org/{i}</loc></url>"
            for i in range(MAX_SITEMAP_LOCS + 25)
        )
        xml = f"<urlset>{items}</urlset>".encode()
        result = parse_sitemap(xml, "https://example.org/sitemap.xml")
        self.assertEqual(len(result.urls), MAX_SITEMAP_LOCS)

    def test_xml_size_limit_is_bounded(self):
        oversized = b"<urlset>" + b"x" * MAX_SITEMAP_XML_BYTES + b"</urlset>"
        with self.assertRaisesRegex(ValueError, "sitemap_too_large"):
            parse_sitemap(oversized, "https://example.org/sitemap.xml")


if __name__ == "__main__":
    unittest.main()

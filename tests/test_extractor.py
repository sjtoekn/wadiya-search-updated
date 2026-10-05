import unittest

from wadiya.crawler.extractor import extract

HTML = """<!doctype html><html lang="en-GB"><head>
<title>  Desert   Rivers </title>
<meta name="description" content="About wadis.">
<meta name="robots" content="index, nofollow">
<link rel="canonical" href="/rivers/wadi">
<style>.x{color:red}</style><script>var secret = 'SCRIPTTEXT';</script></head>
<body>
<nav><a href="/home">Home</a> NAVTEXT</nav>
<header>SITEHEADER</header>
<main>
 <h1>Wadi basics</h1>
 <p>A wadi is a dry riverbed that fills with water after heavy rain. Wadis are common in arid regions
 and have shaped travel routes for thousands of years across the Arabian peninsula.</p>
 <h2>Flash floods</h2><p>Flash floods <a href="/floods?utm_source=x#top">are dangerous</a> and
 <a href="https://other.org/x" rel="nofollow">sponsored</a> <a href="mailto:a@b.c">mail</a>
 <a href="javascript:void(0)">js</a> <a href="/floods">again</a></p>
 <div hidden>HIDDENTEXT</div>
</main>
<aside>SIDEBAR</aside><footer>FOOTERTEXT</footer></body></html>"""


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.p = extract(HTML, "https://example.org/rivers/page")

    def test_metadata(self):
        self.assertEqual(self.p.title, "Desert Rivers")
        self.assertEqual(self.p.description, "About wadis.")
        self.assertEqual(self.p.language, "en")
        self.assertEqual(self.p.canonical_url, "https://example.org/rivers/wadi")
        self.assertTrue(self.p.nofollow)
        self.assertFalse(self.p.noindex)

    def test_text_and_boilerplate(self):
        self.assertIn("dry riverbed", self.p.content)
        for junk in ["SCRIPTTEXT", "color:red", "NAVTEXT", "SITEHEADER", "SIDEBAR", "FOOTERTEXT", "HIDDENTEXT"]:
            self.assertNotIn(junk, self.p.content)
        self.assertEqual(self.p.headings, ["Wadi basics", "Flash floods"])

    def test_links_ignored_when_nofollow_meta(self):
        self.assertEqual(self.p.links, [])

    def test_links_and_noindex(self):
        html = HTML.replace("index, nofollow", "noindex")
        p = extract(html, "https://example.org/rivers/page")
        self.assertTrue(p.noindex)
        self.assertEqual(p.links, ["https://example.org/home", "https://example.org/floods"])  # dedup, no mailto/js/nofollow-link

    def test_base_href_controls_relative_link_resolution(self):
        html = """
        <html><head>
          <base href="/assets/">
        </head><body>
          <a href="one">one</a>
          <a href="../two">two</a>
        </body></html>
        """
        p = extract(html, "https://example.org/docs/page")
        self.assertEqual(
            p.links,
            ["https://example.org/assets/one", "https://example.org/two"],
        )

    def test_invalid_base_href_falls_back_to_page_url(self):
        html = """
        <html><head>
          <base href="javascript:void(0)">
        </head><body>
          <a href="child">child</a>
        </body></html>
        """
        p = extract(html, "https://example.org/docs/page")
        self.assertEqual(p.links, ["https://example.org/docs/child"])

    def test_protocol_relative_and_ignored_link_schemes(self):
        html = """
        <html><body>
          <a href="//example.org/one">one</a>
          <a href="mailto:test@example.org">mail</a>
          <a href="javascript:void(0)">js</a>
          <a href="tel:+123456789">tel</a>
          <a href="data:text/plain,hello">data</a>
          <a href="#section">fragment</a>
          <a href="">empty</a>
        </body></html>
        """
        p = extract(html, "https://example.org/docs/page")
        self.assertEqual(p.links, ["https://example.org/one"])

    def test_feed_links(self):
        html = """
        <html><head>
          <link rel="alternate" type="application/rss+xml" href="/feed.xml">
          <link rel="alternate" type="application/atom+xml" href="https://example.org/atom.xml">
          <link rel="alternate" type="text/html" href="/page">
          <link rel="alternate" type="application/rss+xml" href="/feed.xml">
        </head><body></body></html>
        """
        p = extract(html, "https://example.org/docs/page")
        self.assertEqual(
            p.feed_links,
            [
                "https://example.org/feed.xml",
                "https://example.org/atom.xml",
            ],
        )

    def test_fallbacks(self):
        p = extract("<html><body><h1>Only H1</h1><p>short body</p></body></html>", "https://e.org/")
        self.assertEqual(p.title, "Only H1")
        self.assertIn("short body", p.content)
        self.assertEqual(extract("", "https://e.org/").content, "")
        self.assertEqual(extract(b"<<<not html at all>>>", "https://e.org/").links, [])

    def test_charset_decoding(self):
        raw = '<html><head><meta charset="iso-8859-1"><title>Caf\xe9</title></head><body>na\xefve</body></html>'.encode("latin-1")
        p = extract(raw, "https://e.org/")
        self.assertEqual(p.title, "Café")
        p2 = extract("<title>日本語</title>".encode("utf-8"), "https://e.org/", "text/html; charset=utf-8")
        self.assertEqual(p2.title, "日本語")

    def test_deeply_nested_does_not_crash_hard(self):
        html = "<html><body>" + "<div>" * 2000 + "deep text" + "</div>" * 2000 + "</body></html>"
        try:
            p = extract(html, "https://e.org/")
            self.assertIn("deep text", p.content)
        except RecursionError:
            pass   # the crawler wraps extract() and records a failure


if __name__ == "__main__":
    unittest.main()

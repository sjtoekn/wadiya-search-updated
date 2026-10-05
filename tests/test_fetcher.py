import socket
import unittest

from tests.mock_site import MockSite
from wadiya.config.settings import Settings
from wadiya.crawler.fetcher import Fetcher
from wadiya.crawler.urls import UrlPolicy

HTML = "<html><title>x</title><body>hi</body></html>"
LOCAL = UrlPolicy(allowed_ports=None, allow_private_networks=True)


def mk(**kw):
    s = Settings(max_retries=kw.pop("max_retries", 1), retry_backoff=0, request_timeout=2, total_fetch_timeout=5, **kw)
    return Fetcher(s, policy=LOCAL, sleep=lambda x: None)


class FetcherTests(unittest.TestCase):
    def test_ok_and_user_agent(self):
        with MockSite({"/": (200, "text/html; charset=utf-8", HTML, {})}) as site:
            r = mk().fetch(site.base + "/")
            self.assertTrue(r.ok)
            self.assertEqual(r.body.decode(), HTML)
            self.assertEqual(r.content_type, "text/html")

    def test_content_type_rejected(self):
        with MockSite({"/img": (200, "image/png", b"\x89PNG", {}), "/nt": (200, None, "x", {})}) as site:
            self.assertEqual(mk().fetch(site.base + "/img").error, "unsupported_content_type")
            self.assertEqual(mk().fetch(site.base + "/nt").error, "unsupported_content_type")

    def test_size_limit(self):
        with MockSite({"/big": (200, "text/html", "a" * 5000, {})}) as site:
            self.assertEqual(mk(max_response_bytes=1000).fetch(site.base + "/big").error, "too_large")

    def test_status_handling_and_retry(self):
        with MockSite({"/e": (503, "text/html", "x", {}), "/gone": (404, "text/html", "x", {})}) as site:
            r = mk(max_retries=2).fetch(site.base + "/e")
            self.assertEqual(r.status, 503)
            self.assertEqual(site.hits.count("/e"), 3)            # 1 + 2 retries
            self.assertEqual(mk().fetch(site.base + "/gone").status, 404)
            self.assertEqual(site.hits.count("/gone"), 1)         # 404 not retried

    def test_redirects(self):
        routes = {"/a": (301, None, "", {"Location": "/b"}), "/b": (200, "text/html", HTML, {}),
                  "/loop": (302, None, "", {"Location": "/loop"})}
        with MockSite(routes) as site:
            r = mk().fetch(site.base + "/a")
            self.assertTrue(r.ok); self.assertEqual(r.final_url, site.base + "/b"); self.assertEqual(r.redirects, 1)
            self.assertEqual(mk().fetch(site.base + "/loop").error, "too_many_redirects")
            self.assertEqual(mk().fetch(site.base + "/a", redirect_filter=lambda u: False).error, "redirect_blocked")

    def test_content_encoding_rejected(self):
        with MockSite({"/z": (200, "text/html", b"\x1f\x8b", {"Content-Encoding": "gzip"})}) as site:
            self.assertEqual(mk().fetch(site.base + "/z").error, "unsupported_encoding")

    def test_ssrf_default_policy_blocks_local_server(self):
        with MockSite({"/": (200, "text/html", HTML, {})}) as site:
            f = Fetcher(Settings(max_retries=0))           # default, secure policy
            r = f.fetch(site.base + "/")
            self.assertTrue(r.error.startswith("unsafe_url"))
            self.assertEqual(site.hits, [])                 # nothing was ever requested

    def test_redirect_to_internal_address_blocked(self):
        """A public host that redirects to the cloud-metadata IP must be refused ON THE REDIRECT HOP."""
        resolver = lambda h, p, type=None: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34" if h == "public.example" else h, p))]
        f = Fetcher(Settings(max_retries=0), resolver=resolver)
        calls = []

        def fake_request(url, ips, accept_types, limit, deadline):
            calls.append((url, ips))
            return 302, {"location": "http://169.254.169.254/latest/meta-data/"}, b"", None, None
        f._request = fake_request
        r = f.fetch("https://public.example/")
        self.assertTrue(r.error.startswith("unsafe_url"), r.error)
        self.assertEqual(len(calls), 1)                      # the metadata URL was never requested
        self.assertEqual(calls[0][1], ["93.184.216.34"])     # and the first hop used the vetted, pinned IP

    def test_connection_is_pinned_to_the_vetted_ip_and_keeps_the_original_host_header(self):
        """DNS-rebinding defence: 'pinned.example' exists ONLY in our resolver (real DNS cannot resolve it).
        The fetch can succeed only if the socket goes to the IP we vetted instead of looking the name up again."""
        lookups = []

        def resolver(host, port, type=None):
            lookups.append(host)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
        with MockSite({"/": (200, "text/html", HTML, {})}) as site:
            port = site.base.rsplit(":", 1)[1]
            f = Fetcher(Settings(max_retries=0, request_timeout=3), policy=LOCAL, resolver=resolver)
            r = f.fetch(f"http://pinned.example:{port}/")
            self.assertTrue(r.ok, r.error)
            self.assertEqual(lookups, ["pinned.example"])                       # resolved exactly once, then pinned
            self.assertEqual(site.hosts, [f"pinned.example:{port}"])            # virtual-host header = original name, not the IP

    def test_connection_refused(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        r = mk(max_retries=0).fetch(f"http://127.0.0.1:{port}/")
        self.assertEqual(r.error, "connection_error")


if __name__ == "__main__":
    unittest.main()

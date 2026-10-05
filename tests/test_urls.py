import socket
import unittest

from wadiya.crawler.urls import (UnsafeURLError, UrlPolicy, check_url, ip_is_public, looks_crawlable,
                                 normalize_url, site_key)


def fake_resolver(mapping):
    def r(host, port, type=None):
        ips = mapping.get(host)
        if ips is None:
            raise socket.gaierror("nx")
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]
    return r


class NormalizeTests(unittest.TestCase):
    def test_basics(self):
        n = normalize_url
        self.assertEqual(n("HTTP://Example.COM:80/a/../b#frag"), "http://example.com/b")
        self.assertEqual(n("https://example.com"), "https://example.com/")
        self.assertEqual(n("https://example.com:443/x"), "https://example.com/x")
        self.assertEqual(n("https://example.com:8443/x"), "https://example.com:8443/x")
        self.assertEqual(n("/p?b=2&a=1&utm_source=x", base="https://e.org/d/"), "https://e.org/p?a=1&b=2")
        self.assertEqual(n("../up", base="https://e.org/a/b/c"), "https://e.org/a/up")
        self.assertEqual(n("https://e.org/%7euser/%2f"), "https://e.org/~user/%2F")

    def test_rejects(self):
        for bad in ["javascript:alert(1)", "mailto:a@b.c", "ftp://e.org/", "file:///etc/passwd",
                    "https://user:pw@e.org/", "", "   ", None, 5, "https://", "http://e.org:99999/",
                    "https://e.org/" + "a" * 3000]:
            self.assertIsNone(normalize_url(bad), bad)

    def test_protocol_relative_and_fragment_normalization(self):
        self.assertEqual(
            normalize_url("//Example.COM/path#section", base="https://example.org/"),
            "https://example.com/path",
        )
        self.assertEqual(
            normalize_url("#section", base="https://example.org/docs/page"),
            "https://example.org/docs/page",
        )

    def test_query_normalization_keeps_non_tracking_parameters(self):
        self.assertEqual(
            normalize_url(
                "https://example.org/search?utm_source=x&page=2&q=wadi#results"
            ),
            "https://example.org/search?page=2&q=wadi",
        )

    def test_idna_and_misc(self):
        self.assertEqual(normalize_url("https://BÜCHER.example/"), "https://xn--bcher-kva.example/")
        self.assertEqual(site_key("WWW.Example.org."), "example.org")
        self.assertFalse(looks_crawlable("https://e.org/a.PDF"))
        self.assertTrue(looks_crawlable("https://e.org/a/page"))


class SSRFTests(unittest.TestCase):
    def check(self, url, mapping=None, policy=UrlPolicy()):
        return check_url(url, policy, fake_resolver(mapping or {}))

    def test_public_ok(self):
        self.assertEqual(self.check("https://example.org/", {"example.org": ["93.184.216.34"]}), ["93.184.216.34"])

    def test_blocked_ranges(self):
        for ip in ["127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "100.100.100.200",
                   "0.0.0.0", "224.0.0.1", "::1", "fe80::1", "fd00:ec2::254", "::ffff:127.0.0.1",
                   "::ffff:169.254.169.254", "64:ff9b::7f00:1", "2002:7f00:1::1", "fc00::1"]:
            self.assertFalse(ip_is_public(ip), ip)
            with self.assertRaises(UnsafeURLError, msg=ip):
                self.check("https://evil.example/", {"evil.example": [ip]})
        self.assertTrue(ip_is_public("8.8.8.8"))
        self.assertTrue(ip_is_public("2606:4700:4700::1111"))

    def test_literal_and_trick_hosts(self):
        for url in ["http://localhost/", "http://LOCALHOST./", "http://foo.localhost/", "http://metadata.google.internal/",
                    "http://printer.local/", "http://127.0.0.1/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/",
                    "http://2130706433/", "http://0x7f.0.0.1/", "http://017700000001/"]:
            with self.assertRaises(UnsafeURLError, msg=url):
                check_url(url)   # real resolver: numeric forms resolve to loopback and get rejected

    def test_dns_rebinding_mixed_records(self):
        with self.assertRaises(UnsafeURLError):
            self.check("https://rebind.example/", {"rebind.example": ["93.184.216.34", "10.0.0.1"]})

    def test_schemes_ports_credentials(self):
        m = {"example.org": ["93.184.216.34"]}
        for url in ["ftp://example.org/", "file:///etc/passwd", "gopher://example.org/", "https://u:p@example.org/",
                    "https://example.org:22/", "https://example.org:8080/"]:
            with self.assertRaises(UnsafeURLError, msg=url):
                self.check(url, m)
        self.check("https://example.org:8080/", m, UrlPolicy(allowed_ports=None))   # opt-in only

    def test_unresolvable(self):
        with self.assertRaises(UnsafeURLError):
            self.check("https://nope.invalid/")

    def test_private_allowed_only_by_explicit_policy(self):
        pol = UrlPolicy(allowed_ports=None, allow_private_networks=True)
        self.assertEqual(self.check("http://127.0.0.1:8000/", policy=pol, mapping={"127.0.0.1": ["127.0.0.1"]}), ["127.0.0.1"])


if __name__ == "__main__":
    unittest.main()

"""Real HTTPS through the IP-pinned connection (self-signed cert generated at test time; needs `openssl`)."""
import os
import shutil
import socket
import ssl
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.helpers import TempDirCase
from wadiya.config.settings import Settings
from wadiya.crawler.fetcher import Fetcher
from wadiya.crawler.urls import UrlPolicy


@unittest.skipUnless(shutil.which("openssl"), "openssl not available")
class TlsTests(TempDirCase):
    def setUp(self):
        super().setUp()
        d = self.tmp
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{d}/k.pem", "-out", f"{d}/c.pem",
                        "-days", "2", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                       check=True, capture_output=True)

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                b = b"<html><title>tls ok</title><body>secure</body></html>"
                self.send_response(200); self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(f"{d}/c.pem", f"{d}/k.pem")
        self.srv.socket = ctx.wrap_socket(self.srv.socket, server_side=True)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def fetcher(self, trust=True, resolver=socket.getaddrinfo):
        f = Fetcher(Settings(max_retries=0, request_timeout=3), policy=UrlPolicy(allowed_ports=None, allow_private_networks=True), resolver=resolver)
        if trust:
            f._ctx = ssl.create_default_context(cafile=f"{self.tmp}/c.pem")
        return f

    def test_trusted_cert_verified_against_hostname(self):
        r = self.fetcher().fetch(f"https://localhost:{self.port}/")
        self.assertTrue(r.ok); self.assertIn(b"tls ok", r.body)

    def test_untrusted_certificate_rejected(self):
        self.assertFalse(self.fetcher(trust=False).fetch(f"https://localhost:{self.port}/").ok)

    def test_hostname_mismatch_rejected_even_when_pinned_ip_is_reachable(self):
        res = lambda h, p, type=None: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))]
        r = self.fetcher(resolver=res).fetch(f"https://wrong.example:{self.port}/")
        self.assertFalse(r.ok); self.assertEqual(r.error, "connection_error")
